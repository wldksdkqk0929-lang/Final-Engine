import os
import json
import hashlib
import time
import fcntl
import logging
import shutil
from datetime import datetime, timedelta

class SniperCacheLayer:
    def __init__(self, base_dir=None, ttl_minutes=60):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        self.cache_root = os.path.join(base_dir, "data", "cache")
        self.ttl_seconds = ttl_minutes * 60
        self.logger = logging.getLogger("CacheLayer")
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('[CACHE] %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _generate_key(self, provider: str, model: str, symbol: str, prompt: str) -> str:
        normalized_prompt = " ".join(prompt.strip().lower().split())
        payload = f"{provider}|{model}|{symbol}|{normalized_prompt}"
        hash_key = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        return hash_key

    def _get_cache_path(self, symbol: str, hash_key: str) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        daily_dir = os.path.join(self.cache_root, today)
        os.makedirs(daily_dir, exist_ok=True)
        filename = f"{symbol}_{hash_key}.json"
        return os.path.join(daily_dir, filename)

    def _read_cache(self, path: str) -> dict:
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                data = json.load(f)
                fcntl.flock(f, fcntl.LOCK_UN)
                return data
        except Exception as e:
            self.logger.warning(f"Cache Read Failed: {e}")
            return None

    def _write_cache(self, path: str, content: dict):
        try:
            temp_path = path + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                json.dump(content, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
                fcntl.flock(f, fcntl.LOCK_UN)
            os.replace(temp_path, path)
        except Exception as e:
            self.logger.error(f"Cache Write Failed: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def resolve_request(self, provider, model, symbol, prompt, gatekeeper_status, llm_call_func) -> dict:
        hash_key = self._generate_key(provider, model, symbol, prompt)
        cache_path = self._get_cache_path(symbol, hash_key)
        
        cached_data = self._read_cache(cache_path)
        
        if cached_data:
            timestamp = cached_data.get("meta", {}).get("cached_at_ts", 0)
            if time.time() - timestamp < self.ttl_seconds:
                self.logger.info(f"🟢 [HIT] Cache used for {symbol} (Ghost Mode Active)")
                return cached_data["payload"]
            else:
                self.logger.info(f"🟡 [EXPIRED] Cache found but expired for {symbol}")
                try: os.remove(cache_path)
                except: pass

        self.logger.info(f"⚪ [MISS] No valid cache for {symbol}")

        if not gatekeeper_status["allowed"]:
            self.logger.error(f"🔴 [BLOCK] Gatekeeper denied access: {gatekeeper_status['reason']}")
            raise PermissionError(f"Gatekeeper Blocked: {gatekeeper_status['reason']}")

        try:
            llm_result = llm_call_func()
        except Exception as e:
            self.logger.error(f"LLM Call Failed: {e}")
            raise e

        cache_packet = {
            "meta": {
                "key": hash_key,
                "cached_at": datetime.now().isoformat(),
                "cached_at_ts": time.time(),
                "provider": provider,
                "model": model,
                "ttl_config": self.ttl_seconds
            },
            "payload": llm_result
        }
        self._write_cache(cache_path, cache_packet)
        self.logger.info(f"🔵 [SAVED] New cache created for {symbol}")
        return llm_result

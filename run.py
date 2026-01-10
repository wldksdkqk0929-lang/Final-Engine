import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_config() -> dict:
    config_path = os.getenv("FINAL_ENGINE_CONFIG", "config/base.yaml")
    p = Path(config_path)

    default_cfg = {
        "engine": {
            "name": "Final Engine",
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "prompt_ko": "턴어라운드 스나이퍼 전략에서 뉴스→펀더멘털→차트 필터 순서를 한국어로 3줄 요약해줘.",
        },
        "paths": {
            "logs_root": "data/logs/runs",
            "intel_out": "data/processed/intel_30/intel_30.json",
        },
        "run": {
            "test_ticker": "TEST",
        },
        "_meta": {
            "config_path": config_path,
            "config_loaded": False,
        },
    }

    if not p.exists():
        return default_cfg

    try:
        loaded = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        cfg = default_cfg

        # shallow merge (필요한 키만 덮어쓰기)
        for top_key in ("engine", "paths", "run"):
            if isinstance(loaded.get(top_key), dict):
                cfg[top_key].update(loaded[top_key])

        cfg["_meta"]["config_loaded"] = True
        return cfg

    except Exception:
        # 설정 파싱이 깨져도 시스템은 멈추지 않음
        return default_cfg


def main() -> None:
    cfg = load_config()

    engine_name = cfg["engine"]["name"]
    model = cfg["engine"]["model"]
    prompt_ko = cfg["engine"]["prompt_ko"]

    logs_root = Path(cfg["paths"]["logs_root"])
    intel_out = Path(cfg["paths"]["intel_out"])
    test_ticker = cfg["run"]["test_ticker"]

    # run_id (재현/추적용)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{ts}_{uuid.uuid4().hex[:8]}"

    run_dir = logs_root / run_id
    ensure_dir(run_dir)

    run_json = {
        "engine_name": engine_name,
        "run_id": run_id,
        "created_at_utc": now_utc_iso(),
        "status": "STARTED",
        "engine": cfg["engine"]["provider"],
        "model": model,
        "config_path": cfg["_meta"]["config_path"],
        "config_loaded": cfg["_meta"]["config_loaded"],
        "artifacts": {},
        "errors": [],
    }

    # Gemini 호출 (실패해도 멈추지 않음)
    gemini_key = os.getenv("GEMINI_API_KEY", "")

    if not gemini_key:
        intel = [{
            "ticker": test_ticker,
            "status": "SKIPPED",
            "reason": "GEMINI_API_KEY not set",
            "text_ko": "Gemini API 키가 설정되지 않아 인텔 모듈을 건너뜀."
        }]
        write_json(intel_out, intel)

        run_json["status"] = "SUCCESS_WITHOUT_INTEL"
        run_json["artifacts"]["intel_30"] = str(intel_out)
        write_json(run_dir / "run.json", run_json)

        print(f"[OK] run_id={run_id} (intel skipped)")
        return

    try:
        from google import genai  # google-genai SDK

        client = genai.Client()  # GEMINI_API_KEY 환경변수에서 자동 인식

        resp = client.models.generate_content(
            model=model,
            contents=prompt_ko,
        )

        text = (resp.text or "").strip()
        if not text:
            raise RuntimeError("Empty response text")

        intel = [{
            "ticker": test_ticker,
            "status": "SUCCESS",
            "reason": None,
            "text_ko": text,
        }]
        write_json(intel_out, intel)

        run_json["status"] = "SUCCESS"
        run_json["artifacts"]["intel_30"] = str(intel_out)

    except Exception as e:
        intel = [{
            "ticker": test_ticker,
            "status": "FAILED",
            "reason": repr(e),
            "text_ko": "Gemini 호출 실패. 기술 모드로 대체 필요."
        }]
        write_json(intel_out, intel)

        run_json["status"] = "SUCCESS_WITH_INTEL_FAILED"
        run_json["artifacts"]["intel_30"] = str(intel_out)
        run_json["errors"].append(repr(e))

    write_json(run_dir / "run.json", run_json)
    print(f"[OK] run_id={run_id} status={run_json['status']}")


if __name__ == "__main__":
    main()

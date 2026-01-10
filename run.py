import os
import re
import csv
import json
import time
import math
import html
import random
import hashlib
import datetime
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml

# =========================
# Utils
# =========================

def utc_now_iso() -> str:
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()

def utc_run_id() -> str:
    # 20260110T153658Z_xxxxxxxx
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    h = hashlib.sha1(f"{ts}_{random.random()}".encode("utf-8")).hexdigest()[:8]
    return f"{ts}_{h}"

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path: str, obj: Any) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_text(path: str, s: str) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)

def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def clamp(x: float, a: float, b: float) -> float:
    return max(a, min(b, x))

# =========================
# HTTP with rate limit
# =========================

class RateLimiter:
    def __init__(self, min_delay_sec: float):
        self.min_delay_sec = max(0.0, float(min_delay_sec))
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self):
        if self.min_delay_sec <= 0:
            return
        with self._lock:
            now = time.time()
            gap = now - self._last
            if gap < self.min_delay_sec:
                time.sleep(self.min_delay_sec - gap)
            self._last = time.time()

def http_get(url: str, timeout: int, retries: int, backoff_base: float, rl: RateLimiter) -> requests.Response:
    last_err = None
    for i in range(max(1, retries)):
        try:
            rl.wait()
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": "FinalEngine/1.0"})
            if resp.status_code == 200:
                return resp
            last_err = RuntimeError(f"HTTP {resp.status_code}")
        except Exception as e:
            last_err = e
        sleep_s = backoff_base * (2 ** i) + random.random() * 0.2
        time.sleep(sleep_s)
    raise RuntimeError(f"GET failed: {url} err={last_err}")

# =========================
# Universe (nasdaqtrader)
# =========================

def parse_nasdaqtrader_txt(txt: str) -> Tuple[List[Dict[str, str]], Optional[str]]:
    lines = txt.splitlines()
    data: List[Dict[str, str]] = []
    header: List[str] = []
    file_date = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("File Creation Time:"):
            # "File Creation Time: 01102026..."
            file_date = line.split(":", 1)[1].strip()
            continue
        if line.startswith("Symbol|") or line.startswith("ACT Symbol|"):
            header = [h.strip() for h in line.split("|")]
            continue
        if line.startswith("EOF"):
            break
        if "|" in line and header:
            parts = line.split("|")
            if len(parts) != len(header):
                continue
            row = {header[i]: parts[i].strip() for i in range(len(header))}
            data.append(row)

    return data, file_date

def build_universe(cfg: Dict[str, Any], rl: RateLimiter) -> Tuple[List[str], Dict[str, Any]]:
    uni_cfg = cfg.get("universe", {})
    sources = uni_cfg.get("sources") or [
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt",
        "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    ]
    exclude_etf = bool(uni_cfg.get("exclude_etf", True))
    max_symbols = int(uni_cfg.get("max_symbols", 6500))

    nasdaq_count = 0
    other_count = 0

    merged: List[str] = []
    dropped = {"test_issue": 0, "etf": 0, "non_equity_like": 0}

    # nasdaqtraded
    resp1 = http_get(sources[0], timeout=30, retries=5, backoff_base=0.8, rl=rl)
    rows1, _ = parse_nasdaqtrader_txt(resp1.text)
    nasdaq_count = len(rows1)

    # otherlisted
    resp2 = http_get(sources[1], timeout=30, retries=5, backoff_base=0.8, rl=rl)
    rows2, _ = parse_nasdaqtrader_txt(resp2.text)
    other_count = len(rows2)

    # Extract symbols
    seen = set()

    def is_equity_like(sym: str) -> bool:
        # Keep mostly common equities: A-Z 0-9 plus '.' and '-' only (single delimiter)
        if not sym:
            return False
        if len(sym) > 12:
            return False
        if re.match(r"^[A-Z0-9]+([.\-][A-Z0-9]+)?$", sym) is None:
            return False
        return True

    def maybe_etf_row(row: Dict[str, str]) -> bool:
        # Best-effort: nasdaqtraded has "ETF" field sometimes
        # otherlisted has "ETF" too sometimes
        for k in ["ETF", "Etf", "IsETF", "Is Etf"]:
            if k in row and row[k].strip().upper() == "Y":
                return True
        return False

    # Some files have test symbols / issues - already minimal filtered
    for row in rows1:
        sym = (row.get("Symbol") or "").strip().upper()
        if not sym:
            dropped["test_issue"] += 1
            continue
        if exclude_etf and maybe_etf_row(row):
            dropped["etf"] += 1
            continue
        if not is_equity_like(sym):
            dropped["non_equity_like"] += 1
            continue
        if sym not in seen:
            seen.add(sym)
            merged.append(sym)

    for row in rows2:
        sym = (row.get("ACT Symbol") or row.get("Symbol") or "").strip().upper()
        if not sym:
            dropped["test_issue"] += 1
            continue
        if exclude_etf and maybe_etf_row(row):
            dropped["etf"] += 1
            continue
        if not is_equity_like(sym):
            dropped["non_equity_like"] += 1
            continue
        if sym not in seen:
            seen.add(sym)
            merged.append(sym)

    merged = merged[:max_symbols]

    meta = {
        "provider": uni_cfg.get("provider", "nasdaqtrader"),
        "exclude_etf": exclude_etf,
        "max_symbols": max_symbols,
        "sources": sources,
        "counts": {
            "nasdaqtraded": nasdaq_count,
            "otherlisted": other_count,
            "merged": len(merged),
        },
        "dropped": dropped,
    }
    return merged, meta

# =========================
# Stooq scanner with cache + normalization
# =========================

@dataclass
class ScanResult:
    ticker: str
    status: str  # REAL / NODATA / FALLBACK
    note: str
    dd_52w_pct: Optional[float]
    adv_usd_m: Optional[float]
    price: Optional[float]
    score: float

def stooq_symbol_variants(ticker: str) -> List[str]:
    t = ticker.strip().upper()
    # Class shares: BRK.B -> BRK-B (stooq style)
    t_norm = t.replace(".", "-")
    # Prefer US suffix
    variants = [
        f"{t_norm}.US",
        t_norm,
        f"{t}.US",
        t,
    ]
    # Dedup preserving order
    out = []
    seen = set()
    for v in variants:
        v2 = v.strip().upper()
        if v2 and v2 not in seen:
            seen.add(v2)
            out.append(v2)
    return out

def stooq_url(symbol: str) -> str:
    # Stooq expects lowercase in URL: aapl.us
    s = symbol.strip().lower()
    return f"https://stooq.com/q/d/l/?s={s}&i=d"

def cache_paths(cache_dir: str, key: str) -> Tuple[str, str]:
    safe = re.sub(r"[^a-zA-Z0-9_.\-]+", "_", key)
    return (os.path.join(cache_dir, f"{safe}.csv"), os.path.join(cache_dir, f"{safe}.meta.json"))

def is_cache_valid(meta_path: str, ttl_hours: int) -> bool:
    if not os.path.exists(meta_path):
        return False
    try:
        meta = read_json(meta_path)
        ts = meta.get("saved_at_utc")
        if not ts:
            return False
        saved = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        age = datetime.datetime.now(datetime.timezone.utc) - saved
        return age.total_seconds() <= ttl_hours * 3600
    except Exception:
        return False

def parse_stooq_csv(csv_text: str) -> List[Dict[str, Any]]:
    # Expected header: Date,Open,High,Low,Close,Volume
    rows: List[Dict[str, Any]] = []
    rdr = csv.DictReader(csv_text.splitlines())
    for r in rdr:
        try:
            date = r.get("Date")
            close = float(r.get("Close") or 0)
            high = float(r.get("High") or 0)
            vol = float(r.get("Volume") or 0)
            if not date or close <= 0 or high <= 0:
                continue
            rows.append({"date": date, "close": close, "high": high, "volume": vol})
        except Exception:
            continue
    return rows

def compute_metrics(rows: List[Dict[str, Any]], adv_window: int) -> Tuple[float, float, float]:
    # Use last row as current
    rows_sorted = sorted(rows, key=lambda x: x["date"])
    cur = rows_sorted[-1]["close"]

    # 52w high: max(high) over last ~252 trading days if possible
    last_252 = rows_sorted[-252:] if len(rows_sorted) >= 252 else rows_sorted
    high_52w = max(r["high"] for r in last_252)

    dd_pct = (cur / high_52w - 1.0) * 100.0

    # ADV($M): average(close * volume) over last adv_window rows
    tail = rows_sorted[-adv_window:] if len(rows_sorted) >= adv_window else rows_sorted
    dv = [(r["close"] * r["volume"]) for r in tail]
    adv_usd_m = (sum(dv) / max(1, len(dv))) / 1_000_000.0

    return cur, dd_pct, adv_usd_m

def scan_one_ticker(
    ticker: str,
    cfg: Dict[str, Any],
    rl: RateLimiter,
    cache_dir: str,
) -> ScanResult:
    scfg = cfg.get("scanner", {})
    ttl = int(scfg.get("cache_ttl_hours", 168))
    timeout = int(scfg.get("timeout_sec", 20))
    retries = int(scfg.get("retries", 5))
    adv_window = int(scfg.get("adv_window", 20))
    fallback_to_fake = bool(scfg.get("fallback_to_fake", True))

    # Try variants
    cache_hit = False
    for sym in stooq_symbol_variants(ticker):
        csv_path, meta_path = cache_paths(cache_dir, sym)

        if os.path.exists(csv_path) and is_cache_valid(meta_path, ttl):
            try:
                csv_text = read_text(csv_path)
                rows = parse_stooq_csv(csv_text)
                if len(rows) >= 30:
                    price, dd_pct, adv_usd_m = compute_metrics(rows, adv_window)
                    score = (-dd_pct) * 10.0 + math.log10(max(1e-6, adv_usd_m + 1.0)) * 10.0
                    return ScanResult(
                        ticker=ticker,
                        status="REAL",
                        note="REAL_STOOQ_CACHE",
                        dd_52w_pct=dd_pct,
                        adv_usd_m=adv_usd_m,
                        price=price,
                        score=score,
                    )
                # bad cache, continue to fetch
            except Exception:
                pass
            cache_hit = True

        # Fetch
        try:
            url = stooq_url(sym)
            resp = http_get(url, timeout=timeout, retries=retries, backoff_base=0.7, rl=rl)
            csv_text = resp.text.strip()
            rows = parse_stooq_csv(csv_text)
            if len(rows) < 30:
                continue

            # Save cache
            write_text(csv_path, csv_text)
            write_json(meta_path, {"saved_at_utc": utc_now_iso()})

            price, dd_pct, adv_usd_m = compute_metrics(rows, adv_window)
            score = (-dd_pct) * 10.0 + math.log10(max(1e-6, adv_usd_m + 1.0)) * 10.0

            return ScanResult(
                ticker=ticker,
                status="REAL",
                note="REAL_STOOQ",
                dd_52w_pct=dd_pct,
                adv_usd_m=adv_usd_m,
                price=price,
                score=score,
            )
        except Exception:
            continue

    # NODATA
    if not fallback_to_fake:
        return ScanResult(
            ticker=ticker,
            status="NODATA",
            note="NODATA",
            dd_52w_pct=None,
            adv_usd_m=None,
            price=None,
            score=-1e9,
        )

    # FALLBACK (kept out by funnel nodata drop)
    fake_dd = -random.uniform(20.0, 80.0)
    fake_adv = random.uniform(1.0, 200.0)
    fake_price = random.uniform(5.0, 300.0)
    score = (-fake_dd) * 10.0 + math.log10(fake_adv + 1.0) * 10.0

    return ScanResult(
        ticker=ticker,
        status="FALLBACK",
        note="FAKE_FALLBACK" if cache_hit else "FAKE_FALLBACK",
        dd_52w_pct=fake_dd,
        adv_usd_m=fake_adv,
        price=fake_price,
        score=score,
    )

def scan_universe(tickers: List[str], cfg: Dict[str, Any], rl: RateLimiter) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    scfg = cfg.get("scanner", {})
    max_workers = int(scfg.get("max_workers", 2))

    cache_dir = os.path.join("data", "cache", "stooq")
    ensure_dir(cache_dir)

    scan_limit = int(cfg.get("run", {}).get("scan_limit", 400))
    target = tickers[:scan_limit]

    results: List[ScanResult] = []
    lock = threading.Lock()

    # Very simple worker pool (threading)
    def worker(chunk: List[str]):
        nonlocal results
        local = []
        for t in chunk:
            r = scan_one_ticker(t, cfg, rl, cache_dir)
            local.append(r)
        with lock:
            results.extend(local)

    if max_workers < 1:
        max_workers = 1

    # split into chunks
    chunks: List[List[str]] = [[] for _ in range(max_workers)]
    for i, t in enumerate(target):
        chunks[i % max_workers].append(t)

    threads = []
    for ch in chunks:
        th = threading.Thread(target=worker, args=(ch,), daemon=True)
        threads.append(th)
        th.start()
    for th in threads:
        th.join()

    # Stats
    real = sum(1 for r in results if r.status == "REAL")
    fallback = sum(1 for r in results if r.status == "FALLBACK")
    nodata = sum(1 for r in results if r.status != "REAL")  # treat fallback as nodata-equivalent at source level

    cache_hit = 0
    # we mark cache hit inside note
    for r in results:
        if r.note == "REAL_STOOQ_CACHE":
            cache_hit += 1

    # Normalize for output
    out = []
    for r in results:
        out.append({
            "ticker": r.ticker,
            "dd_52w_pct": r.dd_52w_pct,
            "adv_usd_m": r.adv_usd_m,
            "price": r.price,
            "score": r.score,
            "note": r.note,
            "status": "SUCCESS" if r.status == "REAL" else ("NODATA" if r.status == "NODATA" else "FALLBACK"),
        })

    stats = {
        "real": real,
        "fallback": fallback,
        "nodata": (fallback if fallback_to_nodata(cfg) else nodata),
        "cache_hit": cache_hit,
        "provider": scfg.get("provider", "stooq"),
    }
    return out, stats

def fallback_to_nodata(cfg: Dict[str, Any]) -> bool:
    # Our pipeline treats FALLBACK as nodata for funnel dropping anyway.
    return True

# =========================
# Funnel
# =========================

def funnel_select(candidates: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    fcfg = cfg.get("funnel", {})
    target_n = int(fcfg.get("survivors_n", 30))

    min_price = float(fcfg.get("min_price_usd", 5.0))
    min_adv = float(fcfg.get("min_adv_usd_m", 20.0))
    min_dd = float(fcfg.get("min_dd_52w_pct", -95.0))
    max_dd = float(fcfg.get("max_dd_52w_pct", -15.0))

    dropped = {"price": 0, "adv": 0, "dd": 0, "nodata": 0}
    kept: List[Dict[str, Any]] = []

    for c in candidates:
        # Drop nodata/fallback at source-level: note contains REAL only
        if str(c.get("note", "")).startswith("REAL_") is False:
            dropped["nodata"] += 1
            continue

        price = c.get("price")
        adv = c.get("adv_usd_m")
        dd = c.get("dd_52w_pct")

        if price is None or price < min_price:
            dropped["price"] += 1
            continue
        if adv is None or adv < min_adv:
            dropped["adv"] += 1
            continue
        if dd is None or dd < min_dd or dd > max_dd:
            dropped["dd"] += 1
            continue

        kept.append(c)

    # If too many, take top by score
    kept_sorted = sorted(kept, key=lambda x: float(x.get("score", -1e9)), reverse=True)
    final = kept_sorted[:target_n]

    stats = {
        "filter": {
            "min_price_usd": min_price,
            "min_adv_usd_m": min_adv,
            "min_dd_52w_pct": min_dd,
            "max_dd_52w_pct": max_dd,
            "dropped": dropped,
            "kept": len(kept),
        },
        "pick": {
            "target_n": target_n,
            "after_filter": len(kept),
            "final": len(final),
        }
    }
    return final, stats

# =========================
# Gemini Intel
# =========================

def render_prompt(template: str, ticker: str) -> str:
    return template.replace("{{ticker}}", ticker)

def gemini_generate(api_key: str, model: str, prompt: str, timeout: int = 60) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 600,
        },
    }
    r = requests.post(url, json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    # best-effort extract
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return json.dumps(data, ensure_ascii=False)

def build_intel(survivors: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = cfg.get("engine", {}).get("model", "gemini-2.5-flash")
    template = cfg.get("engine", {}).get("prompt_ko_template", "티커: {{ticker}}\n한국어로 요약해줘.")
    if not api_key:
        # no key -> skipped
        out = []
        for s in survivors:
            out.append({"ticker": s["ticker"], "status": "SKIPPED", "reason": "NO_API_KEY", "text_ko": ""})
        return out, "SKIPPED"

    out = []
    ok = 0
    for s in survivors:
        t = s["ticker"]
        prompt = render_prompt(template, t)
        try:
            text = gemini_generate(api_key, model, prompt, timeout=80)
            out.append({"ticker": t, "status": "SUCCESS", "reason": None, "text_ko": text})
            ok += 1
        except Exception as e:
            out.append({"ticker": t, "status": "FAILED", "reason": str(e), "text_ko": ""})

    return out, ("SUCCESS" if ok > 0 else "FAILED")

# =========================
# Dashboard
# =========================

def html_escape(s: str) -> str:
    return html.escape(s or "", quote=True)

def nl2br(s: str) -> str:
    return "<br>".join(html_escape(s).splitlines())

def render_dashboard(run_obj: Dict[str, Any], candidates: List[Dict[str, Any]], intel: List[Dict[str, Any]]) -> str:
    top_scan = sorted([c for c in candidates if str(c.get("note","")).startswith("REAL_")],
                      key=lambda x: float(x.get("score", -1e9)), reverse=True)[:20]
    intel_ok = [x for x in intel if x.get("status") == "SUCCESS"][:10]

    rows_scan = ""
    for i, c in enumerate(top_scan, start=1):
        rows_scan += (
            "<tr>"
            f"<td>{i}</td>"
            f"<td><b>{html_escape(c.get('ticker',''))}</b></td>"
            f"<td>{c.get('dd_52w_pct', ''):.2f}</td>"
            f"<td>{c.get('adv_usd_m', ''):.2f}</td>"
            f"<td>{c.get('score', ''):.0f}</td>"
            f"<td>{html_escape(c.get('note',''))}</td>"
            "</tr>"
        )

    rows_intel = ""
    for i, it in enumerate(intel_ok, start=1):
        rows_intel += (
            "<tr>"
            f"<td>{i}</td>"
            f"<td><b>{html_escape(it.get('ticker',''))}</b></td>"
            f"<td>{html_escape(it.get('status',''))}</td>"
            f"<td style='white-space:pre-wrap'>{nl2br(it.get('text_ko',''))}</td>"
            "</tr>"
        )

    counts = run_obj.get("counts", {})
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Final Engine 상황판</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Arial, sans-serif; background: #ffffff; color:#111; margin: 24px; }}
    h1 {{ margin: 0 0 12px 0; }}
    .meta {{ margin: 10px 0 20px 0; line-height: 1.6; }}
    .badge {{ display:inline-block; padding: 2px 10px; border-radius: 999px; border: 1px solid #ddd; }}
    table {{ width: 100%; border-collapse: collapse; margin: 10px 0 24px 0; }}
    th, td {{ border-bottom: 1px solid #eee; padding: 10px 8px; vertical-align: top; }}
    th {{ text-align: left; background: #fafafa; }}
    .small {{ color:#666; font-size: 13px; }}
  </style>
</head>
<body>
  <h1>Final Engine 상황판</h1>
  <div class="meta">
    <div>run_id: <b>{html_escape(run_obj.get("run_id",""))}</b></div>
    <div>created_at_utc: <b>{html_escape(run_obj.get("created_at_utc",""))}</b></div>
    <div>status: <span class="badge">{html_escape(run_obj.get("status",""))}</span></div>
    <div>model: <b>{html_escape(run_obj.get("model",""))}</b></div>
    <div class="small">
      universe_scanned: {counts.get("universe_scanned",0)}
      / candidates_raw: {counts.get("candidates_raw",0)}
      / survivors: {counts.get("survivors",0)}
      / intel: {counts.get("intel",0)}
    </div>
  </div>

  <h2>Scanner TOP 20</h2>
  <div class="small">stooq 실데이터(REAL) 기준 상위 20개 표시</div>
  <table>
    <thead>
      <tr>
        <th>#</th><th>Ticker</th><th>DD(52w)%</th><th>ADV($M)</th><th>Score</th><th>Note</th>
      </tr>
    </thead>
    <tbody>
      {rows_scan if rows_scan else "<tr><td colspan='6'>표시할 데이터가 없습니다.</td></tr>"}
    </tbody>
  </table>

  <h2>Intel TOP 10</h2>
  <div class="small">Gemini 분석 결과 중 SUCCESS 상위 10개만 표시</div>
  <table>
    <thead>
      <tr>
        <th>#</th><th>Ticker</th><th>Status</th><th>요약</th>
      </tr>
    </thead>
    <tbody>
      {rows_intel if rows_intel else "<tr><td colspan='4'>표시할 인텔 결과가 없습니다.</td></tr>"}
    </tbody>
  </table>
</body>
</html>"""

# =========================
# Main
# =========================

def main():
    run_id = utc_run_id()
    created_at = utc_now_iso()

    config_path = os.environ.get("FINAL_ENGINE_CONFIG", "config/base.yaml")
    cfg = load_yaml(config_path)

    # rate limit
    min_delay = float(cfg.get("scanner", {}).get("min_delay_sec", 0.35))
    rl = RateLimiter(min_delay_sec=min_delay)

    # paths
    paths = cfg.get("paths", {})
    out_universe = paths.get("universe_out", "data/processed/universe/universe.json")
    out_candidates = paths.get("candidates_out", "data/processed/candidates_raw/candidates_raw.json")
    out_survivors = paths.get("survivors_out", "data/processed/survivors/survivors.json")
    out_intel = paths.get("intel_out", "data/processed/intel_30/intel_30.json")
    out_dashboard = paths.get("dashboard_out", "data/artifacts/dashboard/index.html")
    out_run = os.path.join("data", "logs", "runs", run_id, "run.json")

    engine_name = cfg.get("engine", {}).get("name", "Final Engine")
    model = cfg.get("engine", {}).get("model", "gemini-2.5-flash")

    run_obj: Dict[str, Any] = {
        "engine_name": engine_name,
        "run_id": run_id,
        "created_at_utc": created_at,
        "status": "SUCCESS",
        "engine": "gemini",
        "model": model,
        "config_path": config_path,
        "config_loaded": True,
        "artifacts": {},
        "errors": [],
        "counts": {},
    }

    # Phase A: Universe
    try:
        universe, uni_meta = build_universe(cfg, rl)
        write_json(out_universe, universe)
        run_obj["artifacts"]["universe"] = out_universe
        run_obj["universe_meta"] = uni_meta
        run_obj["counts"]["universe_total"] = len(universe)
    except Exception as e:
        run_obj["status"] = "FAILED"
        run_obj["errors"].append({"phase": "universe", "error": str(e)})
        write_json(out_run, run_obj)
        return

    # Phase B: Scanner
    try:
        candidates, scanner_stats = scan_universe(universe, cfg, rl)
        # Keep only the scan_limit in candidates_raw output
        scan_limit = int(cfg.get("run", {}).get("scan_limit", 400))
        candidates = candidates[:scan_limit]
        write_json(out_candidates, candidates)
        run_obj["artifacts"]["candidates_raw"] = out_candidates

        run_obj["scanner_stats"] = scanner_stats
        run_obj["counts"]["universe_scanned"] = len(candidates)
        run_obj["counts"]["candidates_raw"] = len(candidates)
    except Exception as e:
        run_obj["status"] = "FAILED"
        run_obj["errors"].append({"phase": "scanner", "error": str(e)})
        write_json(out_run, run_obj)
        return

    # Phase E: Funnel
    try:
        survivors, funnel_stats = funnel_select(candidates, cfg)
        write_json(out_survivors, survivors)
        run_obj["artifacts"]["survivors"] = out_survivors
        run_obj["funnel_stats"] = funnel_stats
        run_obj["counts"]["survivors"] = len(survivors)
    except Exception as e:
        run_obj["status"] = "FAILED"
        run_obj["errors"].append({"phase": "funnel", "error": str(e)})
        write_json(out_run, run_obj)
        return

    # Phase C: Intel
    try:
        intel, intel_status = build_intel(survivors, cfg)
        write_json(out_intel, intel)
        run_obj["artifacts"]["intel_30"] = out_intel
        run_obj["intel_status"] = intel_status
        run_obj["counts"]["intel"] = len([x for x in intel if x.get("status") == "SUCCESS"])
    except Exception as e:
        run_obj["intel_status"] = "FAILED"
        run_obj["errors"].append({"phase": "intel", "error": str(e)})

    # Phase D: Dashboard (always)
    try:
        dash = render_dashboard(run_obj, candidates, read_json(out_intel) if os.path.exists(out_intel) else [])
        write_text(out_dashboard, dash)
        run_obj["artifacts"]["dashboard"] = out_dashboard
    except Exception as e:
        run_obj["errors"].append({"phase": "dashboard", "error": str(e)})

    # Write run.json
    write_json(out_run, run_obj)

if __name__ == "__main__":
    main()

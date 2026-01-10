import os
import json
import uuid
import csv
import time
import random
from io import StringIO
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml
import requests

NASDQ_NASDAQTRADED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"
NASDQ_OTHERLISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_json_any(paths: list[Path], default=None):
    for p in paths:
        obj = read_json(p, default=None)
        if obj is not None:
            return obj, str(p)
    return default, None


def write_json_all(paths: list[Path], obj) -> None:
    for p in paths:
        try:
            write_json(p, obj)
        except Exception:
            pass


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def load_config() -> dict:
    config_path = os.getenv("FINAL_ENGINE_CONFIG", "config/base.yaml")
    p = Path(config_path)

    default_cfg = {
        "engine": {
            "name": "Final Engine",
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "prompt_ko_template": (
                "너는 미국 주식 턴어라운드 스나이퍼 전략 분석가다.\n"
                "티커: {{ticker}}\n"
                "아래 형식으로 한국어로만 답해라.\n"
                "- 핵심 악재(1줄)\n"
                "- 회복 신호(1줄)\n"
                "- 확인할 지표(3개)\n"
                "- 결론(관찰/예비/확정 중 1개)\n"
            ),
        },
        "paths": {
            "logs_root": "data/logs/runs",
            "universe_out": "data/processed/universe/universe.json",
            "candidates_out": "data/processed/candidates_raw/candidates_raw.json",
            "survivors_out": "data/processed/survivors/survivors.json",
            "intel_out": "data/processed/intel_30/intel_30.json",
            "dashboard_out": "data/artifacts/dashboard/index.html",
            "dashboard_template": "templates/dashboard.html",
        },
        "universe": {
            "provider": "nasdaqtrader",
            "exclude_etf": True,
            "max_symbols": 6500,
        },
        "run": {
            "mode": "daily",
            "coverage_min": 600,
            "coverage_cap": 6000,
            "scan_limit": 800,
            "expand_scan_limit": 500,
            "intel_n": 30,
        },
        "scanner": {
            "provider": "stooq",
            "lookback_days": 365,
            "adv_window": 20,
            "timeout_sec": 20,
            "retries": 4,
            "max_workers": 4,
            "cache_ttl_hours": 168,
            "fallback_to_fake": True,
        },
        "funnel": {
            "survivors_n": 30,
            "min_price_usd": 5.0,
            "min_adv_usd_m": 20.0,
            "min_dd_52w_pct": -95.0,
            "max_dd_52w_pct": -15.0,
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
        for top_key in ("engine", "paths", "universe", "run", "scanner", "funnel"):
            if isinstance(loaded.get(top_key), dict):
                cfg[top_key].update(loaded[top_key])
        cfg["_meta"]["config_loaded"] = True
        return cfg
    except Exception:
        return default_cfg


def safe_html_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_dashboard_html(template_path: Path, out_path: Path, context: dict) -> None:
    tpl = read_text(template_path)
    html = tpl
    raw_keys = {"scan_table_html", "survivors_table_html", "intel_table_html"}

    for key, val in context.items():
        token = f"{{{{{key}}}}}"
        rendered = "" if val is None else str(val)
        if key in raw_keys:
            html = html.replace(token, rendered)
        else:
            html = html.replace(token, safe_html_escape(rendered))

    write_text(out_path, html)


def _download_text(url: str, timeout_sec: int) -> str:
    r = requests.get(url, timeout=timeout_sec)
    r.raise_for_status()
    return r.text


def _is_equity_like(symbol: str, name: str) -> bool:
    n = (name or "").lower()
    bad_keywords = [
        "warrant", "warrants", "rights", "units",
        "preferred", "depositary",
        "note", "notes", "bond", "bonds",
        "trust", "etn",
    ]
    if any(k in n for k in bad_keywords):
        return False
    for ch in ["^", " ", "/"]:
        if ch in symbol:
            return False
    return True


def fetch_universe_nasdaqtrader(exclude_etf: bool, max_symbols: int, timeout_sec: int = 25) -> dict:
    meta = {
        "provider": "nasdaqtrader",
        "exclude_etf": exclude_etf,
        "max_symbols": max_symbols,
        "sources": [NASDQ_NASDAQTRADED_URL, NASDQ_OTHERLISTED_URL],
        "counts": {"nasdaqtraded": 0, "otherlisted": 0, "merged": 0},
        "dropped": {"test_issue": 0, "etf": 0, "non_equity_like": 0},
    }

    tickers = set()

    txt1 = _download_text(NASDQ_NASDAQTRADED_URL, timeout_sec=timeout_sec)
    lines1 = [ln for ln in txt1.splitlines() if ln and "|" in ln]
    if not lines1:
        raise RuntimeError("nasdaqtraded.txt empty or blocked")

    header1 = lines1[0].split("|")
    for ln in lines1[1:]:
        if ln.startswith("File Creation Time") or ln.startswith("Number of Symbols"):
            continue
        parts = ln.split("|")
        if len(parts) != len(header1):
            continue
        row = dict(zip(header1, parts))
        sym = (row.get("Symbol") or "").strip().upper()
        name = (row.get("Security Name") or "").strip()
        test_issue = (row.get("Test Issue") or "").strip().upper()
        etf = (row.get("ETF") or "").strip().upper()

        if not sym:
            continue
        meta["counts"]["nasdaqtraded"] += 1

        if test_issue == "Y":
            meta["dropped"]["test_issue"] += 1
            continue
        if exclude_etf and etf == "Y":
            meta["dropped"]["etf"] += 1
            continue
        if not _is_equity_like(sym, name):
            meta["dropped"]["non_equity_like"] += 1
            continue

        tickers.add(sym)

    txt2 = _download_text(NASDQ_OTHERLISTED_URL, timeout_sec=timeout_sec)
    lines2 = [ln for ln in txt2.splitlines() if ln and "|" in ln]
    if not lines2:
        raise RuntimeError("otherlisted.txt empty or blocked")

    header2 = lines2[0].split("|")
    for ln in lines2[1:]:
        if ln.startswith("File Creation Time") or ln.startswith("Number of Symbols"):
            continue
        parts = ln.split("|")
        if len(parts) != len(header2):
            continue
        row = dict(zip(header2, parts))
        sym = (row.get("ACT Symbol") or "").strip().upper()
        name = (row.get("Security Name") or "").strip()
        test_issue = (row.get("Test Issue") or "").strip().upper()
        etf = (row.get("ETF") or "").strip().upper()

        if not sym:
            continue
        meta["counts"]["otherlisted"] += 1

        if test_issue == "Y":
            meta["dropped"]["test_issue"] += 1
            continue
        if exclude_etf and etf == "Y":
            meta["dropped"]["etf"] += 1
            continue
        if not _is_equity_like(sym, name):
            meta["dropped"]["non_equity_like"] += 1
            continue

        tickers.add(sym)

    merged = sorted(tickers)
    if max_symbols and len(merged) > int(max_symbols):
        merged = merged[: int(max_symbols)]

    meta["counts"]["merged"] = len(merged)
    return {"meta": meta, "tickers": merged}


def fake_metrics_for_ticker(ticker: str) -> dict:
    score = sum(ord(c) for c in ticker) % 100
    dd_52w = round(-1.0 * (20 + (score * 0.6)), 2)
    adv_usd_m = round(0.5 + (score * 0.08), 2)
    return {
        "dd_52w_pct": dd_52w,
        "adv_usd_m": adv_usd_m,
        "scan_score": score,
        "note": "FAKE_FALLBACK",
        "price_source": "fake",
        "last_close": None,
    }


def _is_cache_fresh(path: Path, ttl_hours: int) -> bool:
    if not path.exists():
        return False
    age_sec = time.time() - path.stat().st_mtime
    return age_sec <= ttl_hours * 3600


def _http_get_text_with_retries(url: str, timeout_sec: int, retries: int) -> str | None:
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, timeout=timeout_sec)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            return r.text
        except Exception:
            if attempt >= retries:
                return None
            time.sleep(0.4 + random.random() * 0.8)
    return None


def fetch_stooq_csv_text(ticker: str, timeout_sec: int, retries: int) -> str | None:
    variants = []
    t = ticker.lower()
    variants.append(f"{t}.us")
    if "." in t:
        variants.append(f"{t.replace('.', '-')}.us")

    for sym in variants:
        url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
        text = _http_get_text_with_retries(url, timeout_sec=timeout_sec, retries=retries)
        if not text:
            continue
        text = text.strip()
        if "Date,Open,High,Low,Close,Volume" in text:
            return text
    return None


def parse_stooq_rows(csv_text: str) -> list[dict] | None:
    try:
        f = StringIO(csv_text)
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            try:
                rows.append({
                    "date": row["Date"],
                    "high": float(row["High"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"]),
                })
            except Exception:
                continue
        return rows if rows else None
    except Exception:
        return None


def compute_real_metrics_from_rows(rows: list[dict], adv_window: int) -> dict | None:
    usable = [r for r in rows if r.get("volume", 0) > 0]
    if len(usable) < max(adv_window, 60):
        return None

    tail = usable[-min(len(usable), 320):]
    latest = tail[-1]
    last_close = latest["close"]

    high_52w = max(r["high"] for r in tail)
    if high_52w <= 0:
        return None

    dd_52w_pct = round((last_close / high_52w - 1.0) * 100.0, 2)

    adv_slice = tail[-min(len(tail), adv_window):]
    adv_usd = sum(r["close"] * r["volume"] for r in adv_slice) / len(adv_slice)
    adv_usd_m = round(adv_usd / 1_000_000.0, 2)

    scan_score = int(min(999, max(0, round(-dd_52w_pct * 10))))
    return {
        "dd_52w_pct": dd_52w_pct,
        "adv_usd_m": adv_usd_m,
        "scan_score": scan_score,
        "note": "REAL_STOOQ",
        "price_source": "stooq",
        "last_close": round(last_close, 2),
    }


def get_stooq_metrics_with_cache(
    ticker: str,
    adv_window: int,
    timeout_sec: int,
    retries: int,
    cache_ttl_hours: int,
    stooq_cache_dir: Path,
) -> tuple[dict | None, bool]:
    ensure_dir(stooq_cache_dir)
    cache_path = stooq_cache_dir / f"{ticker.upper()}.csv"

    cached = False
    csv_text = None

    if _is_cache_fresh(cache_path, cache_ttl_hours):
        try:
            csv_text = cache_path.read_text(encoding="utf-8")
            cached = True
        except Exception:
            csv_text = None
            cached = False

    if not csv_text:
        csv_text = fetch_stooq_csv_text(ticker, timeout_sec=timeout_sec, retries=retries)
        if csv_text:
            try:
                cache_path.write_text(csv_text, encoding="utf-8")
            except Exception:
                pass

    if not csv_text:
        return None, cached

    rows = parse_stooq_rows(csv_text)
    if not rows:
        return None, cached

    m = compute_real_metrics_from_rows(rows, adv_window=adv_window)
    return m, cached


def _metrics_for_one_ticker(ticker: str, scanner_cfg: dict, stooq_cache_dir: Path) -> tuple[str, dict, dict, bool]:
    provider = str(scanner_cfg.get("provider", "stooq")).lower()
    timeout_sec = int(scanner_cfg.get("timeout_sec", 20))
    adv_window = int(scanner_cfg.get("adv_window", 20))
    retries = int(scanner_cfg.get("retries", 4))
    cache_ttl_hours = int(scanner_cfg.get("cache_ttl_hours", 168))
    fallback = bool(scanner_cfg.get("fallback_to_fake", True))

    local_stats = {"real": 0, "fallback": 0, "nodata": 0, "cache_hit": 0}
    is_real = False

    if provider == "fake":
        m = fake_metrics_for_ticker(ticker)
        local_stats["fallback"] += 1
        return ticker, m, local_stats, False

    m, cached = get_stooq_metrics_with_cache(
        ticker=ticker,
        adv_window=adv_window,
        timeout_sec=timeout_sec,
        retries=retries,
        cache_ttl_hours=cache_ttl_hours,
        stooq_cache_dir=stooq_cache_dir,
    )
    if cached and m is not None:
        local_stats["cache_hit"] += 1

    if m is None:
        local_stats["nodata"] += 1
        if fallback:
            m = fake_metrics_for_ticker(ticker)
            local_stats["fallback"] += 1
        else:
            m = {"dd_52w_pct": 0.0, "adv_usd_m": 0.0, "scan_score": 0, "note": "NO_DATA", "price_source": "none", "last_close": None}
            local_stats["fallback"] += 1
    else:
        local_stats["real"] += 1
        is_real = True
        if cached:
            m = dict(m)
            m["note"] = "REAL_STOOQ_CACHE"

    return ticker, m, local_stats, is_real


def build_candidates(tickers: list[str], scanner_cfg: dict, stooq_cache_dir: Path) -> tuple[list[dict], dict, list[str]]:
    provider = str(scanner_cfg.get("provider", "stooq")).lower()
    max_workers = int(scanner_cfg.get("max_workers", 4))

    rows = []
    real_tickers = []
    stats = {"real": 0, "fallback": 0, "nodata": 0, "cache_hit": 0, "provider": provider}

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_metrics_for_one_ticker, t, scanner_cfg, stooq_cache_dir): t for t in tickers}
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                _, m, st, is_real = fut.result()
            except Exception:
                m = fake_metrics_for_ticker(t)
                st = {"real": 0, "fallback": 1, "nodata": 1, "cache_hit": 0}
                is_real = False

            stats["real"] += st["real"]
            stats["fallback"] += st["fallback"]
            stats["nodata"] += st["nodata"]
            stats["cache_hit"] += st["cache_hit"]

            rows.append({"ticker": t, **m})
            if is_real:
                real_tickers.append(t)

    rows.sort(key=lambda r: (r.get("dd_52w_pct", 0.0), -r.get("adv_usd_m", 0.0)))
    real_tickers = sorted(set(real_tickers))
    return rows, stats, real_tickers


def apply_funnel_filters(candidates: list[dict], funnel_cfg: dict) -> tuple[list[dict], dict]:
    min_price = float(funnel_cfg.get("min_price_usd", 5.0))
    min_adv = float(funnel_cfg.get("min_adv_usd_m", 20.0))
    min_dd = float(funnel_cfg.get("min_dd_52w_pct", -95.0))
    max_dd = float(funnel_cfg.get("max_dd_52w_pct", -15.0))

    kept = []
    drop_reasons = {"price": 0, "adv": 0, "dd": 0, "nodata": 0}

    for r in candidates:
        last_close = r.get("last_close", None)
        adv = float(r.get("adv_usd_m", 0.0) or 0.0)
        dd = float(r.get("dd_52w_pct", 0.0) or 0.0)

        if last_close is None:
            drop_reasons["nodata"] += 1
            continue
        if float(last_close) < min_price:
            drop_reasons["price"] += 1
            continue
        if adv < min_adv:
            drop_reasons["adv"] += 1
            continue
        if not (min_dd <= dd <= max_dd):
            drop_reasons["dd"] += 1
            continue

        kept.append(r)

    kept.sort(key=lambda r: (r.get("dd_52w_pct", 0.0), -r.get("adv_usd_m", 0.0)))
    stats = {
        "min_price_usd": min_price,
        "min_adv_usd_m": min_adv,
        "min_dd_52w_pct": min_dd,
        "max_dd_52w_pct": max_dd,
        "dropped": drop_reasons,
        "kept": len(kept),
    }
    return kept, stats


def pick_survivors(candidates: list[dict], funnel_cfg: dict) -> tuple[list[dict], dict]:
    target_n = int(funnel_cfg.get("survivors_n", 30))
    filtered, filter_stats = apply_funnel_filters(candidates, funnel_cfg)

    survivors = filtered[:target_n]
    if len(survivors) < target_n:
        already = {r["ticker"] for r in survivors}
        with_data = [r for r in candidates if r.get("last_close") is not None and r["ticker"] not in already]
        for r in with_data:
            survivors.append(r)
            already.add(r["ticker"])
            if len(survivors) >= target_n:
                break

    survivors = survivors[:target_n]
    pick_stats = {"target_n": target_n, "after_filter": len(filtered), "final": len(survivors)}
    return survivors, {"filter": filter_stats, "pick": pick_stats}


def build_scan_table_html(top_rows: list[dict]) -> str:
    if not top_rows:
        return "<div class='muted'>스캔 결과 없음</div>"
    head = (
        "<table><thead><tr>"
        "<th>#</th><th>Ticker</th><th>DD(52w)%</th><th>ADV($M)</th><th>Score</th><th>Note</th>"
        "</tr></thead><tbody>"
    )
    body = ""
    for i, r in enumerate(top_rows, start=1):
        body += (
            "<tr>"
            f"<td>{i}</td>"
            f"<td><b>{safe_html_escape(r['ticker'])}</b></td>"
            f"<td>{r.get('dd_52w_pct','')}</td>"
            f"<td>{r.get('adv_usd_m','')}</td>"
            f"<td>{r.get('scan_score','')}</td>"
            f"<td>{safe_html_escape(r.get('note',''))}</td>"
            "</tr>"
        )
    return head + body + "</tbody></table>"


def build_survivors_table_html(rows: list[dict]) -> str:
    if not rows:
        return "<div class='muted'>서바이버 없음</div>"
    head = (
        "<table><thead><tr>"
        "<th>#</th><th>Ticker</th><th>Price</th><th>DD(52w)%</th><th>ADV($M)</th><th>Score</th><th>Source</th>"
        "</tr></thead><tbody>"
    )
    body = ""
    for i, r in enumerate(rows, start=1):
        body += (
            "<tr>"
            f"<td>{i}</td>"
            f"<td><b>{safe_html_escape(r['ticker'])}</b></td>"
            f"<td>{r.get('last_close','')}</td>"
            f"<td>{r.get('dd_52w_pct','')}</td>"
            f"<td>{r.get('adv_usd_m','')}</td>"
            f"<td>{r.get('scan_score','')}</td>"
            f"<td>{safe_html_escape(r.get('price_source',''))}</td>"
            "</tr>"
        )
    return head + body + "</tbody></table>"


def render_prompt(template: str, ticker: str) -> str:
    return template.replace("{{ticker}}", ticker)


def gemini_generate_rest(api_key: str, model: str, prompt: str, timeout: int = 80) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 600},
    }
    r = requests.post(url, json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    try:
        return (data["candidates"][0]["content"]["parts"][0]["text"] or "").strip()
    except Exception:
        return json.dumps(data, ensure_ascii=False)


def build_intel(survivors: list[dict], cfg: dict) -> tuple[list[dict], str, int]:
    api_key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    model = cfg.get("engine", {}).get("model", "gemini-2.5-flash")
    template = cfg.get("engine", {}).get("prompt_ko_template", "티커: {{ticker}}\n한국어로 요약해줘.")

    if not api_key:
        out = [{"ticker": s["ticker"], "status": "SKIPPED", "reason": "NO_API_KEY", "text_ko": ""} for s in survivors]
        return out, "SKIPPED", 0

    # 1) google-genai 있으면 우선 사용, 없으면 REST
    use_sdk = False
    client = None
    try:
        from google import genai  # type: ignore
        client = genai.Client(api_key=api_key)
        use_sdk = True
    except Exception:
        use_sdk = False
        client = None

    out = []
    ok = 0
    for s in survivors:
        t = s["ticker"]
        prompt = render_prompt(template, t)
        try:
            if use_sdk and client is not None:
                resp = client.models.generate_content(model=model, contents=prompt)
                text = (resp.text or "").strip()
            else:
                text = gemini_generate_rest(api_key, model, prompt)

            if text:
                out.append({"ticker": t, "status": "SUCCESS", "reason": None, "text_ko": text})
                ok += 1
            else:
                out.append({"ticker": t, "status": "FAILED", "reason": "EMPTY_TEXT", "text_ko": ""})
        except Exception as e:
            out.append({"ticker": t, "status": "FAILED", "reason": str(e), "text_ko": ""})

    return out, ("SUCCESS" if ok > 0 else "FAILED"), ok


def build_intel_table_html(rows: list[dict], top_n: int = 10) -> str:
    ok = [r for r in rows if r.get("status") == "SUCCESS"]
    show = ok[:top_n]
    if not show:
        return "<div class='muted'>Intel SUCCESS 없음</div>"

    head = (
        "<table><thead><tr>"
        "<th>#</th><th>Ticker</th><th>Status</th><th>요약</th>"
        "</tr></thead><tbody>"
    )
    body = ""
    for i, r in enumerate(show, start=1):
        text = r.get("text_ko", "")
        body += (
            "<tr>"
            f"<td>{i}</td>"
            f"<td><b>{safe_html_escape(r['ticker'])}</b></td>"
            f"<td>{safe_html_escape(r.get('status',''))}</td>"
            f"<td class='small'>{safe_html_escape(text)}</td>"
            "</tr>"
        )
    return head + body + "</tbody></table>"


def slice_with_wrap(items: list[str], offset: int, n: int) -> tuple[list[str], int]:
    if not items:
        return [], 0
    offset = max(0, offset) % len(items)
    if n >= len(items):
        return items[:], (offset + n) % len(items)
    end = offset + n
    if end <= len(items):
        return items[offset:end], end % len(items)
    part1 = items[offset:]
    part2 = items[: end - len(items)]
    return part1 + part2, (end - len(items)) % len(items)


def main() -> None:
    cfg = load_config()

    engine_name = cfg["engine"]["name"]
    model = cfg["engine"]["model"]

    paths = cfg["paths"]
    logs_root = Path(paths["logs_root"])
    universe_out = Path(paths["universe_out"])
    candidates_out = Path(paths["candidates_out"])
    survivors_out = Path(paths["survivors_out"])
    intel_out = Path(paths["intel_out"])
    dashboard_out = Path(paths["dashboard_out"])
    dashboard_template = Path(paths["dashboard_template"])

    universe_cfg = cfg.get("universe", {})
    run_cfg = cfg.get("run", {})
    scanner_cfg = cfg.get("scanner", {})
    funnel_cfg = cfg.get("funnel", {})

    mode = str(run_cfg.get("mode", "daily")).lower()
    coverage_min = int(run_cfg.get("coverage_min", 600))
    coverage_cap = int(run_cfg.get("coverage_cap", 6000))
    scan_limit = int(run_cfg.get("scan_limit", 800))
    expand_scan_limit = int(run_cfg.get("expand_scan_limit", 500))
    intel_n = int(run_cfg.get("intel_n", 30))

    # stooq csv cache dir (이미 네가 cache_hit로 확인한 “살아있는” 영역)
    stooq_cache_dir = Path("data/cache/stooq")
    ensure_dir(stooq_cache_dir)

    # ✅ coverage/state를 “양쪽 경로”에서 읽고, 양쪽에 동시에 저장 (캐시 설정이 뭐든 살아남게)
    legacy_state = Path("data/cache/state.json")
    legacy_cov = Path("data/cache/coverage_universe.json")
    stooq_state = stooq_cache_dir / "state.json"
    stooq_cov = stooq_cache_dir / "coverage_universe.json"

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{ts}_{uuid.uuid4().hex[:8]}"
    run_dir = Path(paths["logs_root"]) / run_id
    ensure_dir(run_dir)

    state_obj, state_loaded_from = read_json_any([stooq_state, legacy_state], default={"universe_offset": 0, "coverage_offset": 0})
    universe_offset = int((state_obj or {}).get("universe_offset", 0))
    coverage_offset = int((state_obj or {}).get("coverage_offset", 0))

    cov_obj, cov_loaded_from = read_json_any([stooq_cov, legacy_cov], default={"tickers": []})
    cov_list = (cov_obj or {}).get("tickers", [])
    coverage_tickers = sorted({t.strip().upper() for t in cov_list if isinstance(t, str) and t.strip()})

    run_json = {
        "engine_name": engine_name,
        "run_id": run_id,
        "created_at_utc": now_utc_iso(),
        "status": "SUCCESS",
        "engine": cfg["engine"]["provider"],
        "model": model,
        "config_path": cfg["_meta"]["config_path"],
        "config_loaded": cfg["_meta"]["config_loaded"],
        "artifacts": {},
        "errors": [],
        "counts": {},
        "scanner_stats": {},
        "funnel_stats": {},
        "universe_meta": {},
        "run_mode": mode,
        "coverage": {"before": len(coverage_tickers), "after": None},
        "scan_source": None,
        "state_loaded_from": state_loaded_from,
        "coverage_loaded_from": cov_loaded_from,
        "coverage_paths": {"stooq": str(stooq_cov), "legacy": str(legacy_cov)},
        "state_paths": {"stooq": str(stooq_state), "legacy": str(legacy_state)},
    }

    # A) Universe
    exclude_etf = bool(universe_cfg.get("exclude_etf", True))
    max_symbols = int(universe_cfg.get("max_symbols", 6500))
    uni = fetch_universe_nasdaqtrader(exclude_etf=exclude_etf, max_symbols=max_symbols)
    tickers_all = uni["tickers"]
    run_json["universe_meta"] = uni["meta"]

    write_json(universe_out, {
        "source": "nasdaqtrader",
        "created_at_utc": now_utc_iso(),
        "count": len(tickers_all),
        "meta": run_json["universe_meta"],
        "tickers": tickers_all
    })
    run_json["artifacts"]["universe"] = str(universe_out)
    run_json["counts"]["universe_total"] = len(tickers_all)

    # Decide scan list
    if mode == "expand":
        scan_list, universe_offset = slice_with_wrap(tickers_all, universe_offset, max(1, expand_scan_limit))
        run_json["scan_source"] = "expand_from_universe"
    else:
        use_cov = len(coverage_tickers) >= coverage_min
        if use_cov:
            scan_list, coverage_offset = slice_with_wrap(coverage_tickers, coverage_offset, scan_limit)
            run_json["scan_source"] = "daily_from_coverage"
        else:
            scan_list, universe_offset = slice_with_wrap(tickers_all, universe_offset, scan_limit)
            run_json["scan_source"] = "daily_from_universe"

    run_json["counts"]["universe_scanned"] = len(scan_list)

    # B) Scanner
    candidates, scan_stats, real_tickers = build_candidates(scan_list, scanner_cfg, stooq_cache_dir)
    write_json(candidates_out, {
        "source": f"scanner_{scan_stats.get('provider','')}",
        "created_at_utc": now_utc_iso(),
        "count": len(candidates),
        "scanner_stats": scan_stats,
        "rows": candidates
    })
    run_json["artifacts"]["candidates_raw"] = str(candidates_out)
    run_json["counts"]["candidates_raw"] = len(candidates)
    run_json["scanner_stats"] = scan_stats

    # Update coverage
    cov_set = set(coverage_tickers)
    for t in real_tickers:
        cov_set.add(t)
    new_cov = sorted(cov_set)[:coverage_cap]
    run_json["coverage"]["after"] = len(new_cov)

    # ✅ 양쪽에 같이 저장
    write_json_all([stooq_cov, legacy_cov], {"created_at_utc": now_utc_iso(), "tickers": new_cov})
    write_json_all([stooq_state, legacy_state], {
        "updated_at_utc": now_utc_iso(),
        "universe_offset": universe_offset,
        "coverage_offset": coverage_offset,
    })

    # E) Funnel
    survivors, funnel_stats = pick_survivors(candidates, funnel_cfg)
    run_json["funnel_stats"] = funnel_stats
    write_json(survivors_out, {
        "source": "funnel_v2_numeric",
        "created_at_utc": now_utc_iso(),
        "count": len(survivors),
        "stats": funnel_stats,
        "rows": survivors
    })
    run_json["artifacts"]["survivors"] = str(survivors_out)
    run_json["counts"]["survivors"] = len(survivors)

    # C) Intel
    intel_targets = survivors[: max(0, min(intel_n, len(survivors)))]
    intel_rows, intel_status, intel_ok = build_intel(intel_targets, cfg)
    write_json(intel_out, intel_rows)
    run_json["artifacts"]["intel_30"] = str(intel_out)
    run_json["intel_status"] = intel_status

    run_json["counts"]["intel"] = len(intel_targets)          # “요청 개수”
    run_json["counts"]["intel_success"] = int(intel_ok)       # “성공 개수”

    # D) Dashboard
    try:
        scan_table_html = build_scan_table_html(candidates[:20])
        survivors_table_html = build_survivors_table_html(survivors)
        intel_table_html = build_intel_table_html(intel_rows, top_n=10)

        ctx = {
            "engine_name": run_json["engine_name"],
            "run_id": run_json["run_id"],
            "created_at_utc": run_json["created_at_utc"],
            "status": run_json["status"],
            "model": run_json["model"],
            "universe_count": run_json["counts"]["universe_scanned"],
            "candidates_count": run_json["counts"]["candidates_raw"],
            "survivors_count": run_json["counts"]["survivors"],
            "intel_count": run_json["counts"]["intel_success"],
            "scan_table_html": scan_table_html,
            "survivors_table_html": survivors_table_html,
            "intel_table_html": intel_table_html,
        }
        if dashboard_template.exists():
            build_dashboard_html(dashboard_template, dashboard_out, ctx)
            run_json["artifacts"]["dashboard"] = str(dashboard_out)
        else:
            run_json["errors"].append("dashboard_template_missing")
    except Exception as e:
        run_json["errors"].append(f"dashboard_error:{repr(e)}")

    write_json(run_dir / "run.json", run_json)
    print(
        "[OK] "
        f"run_id={run_id} mode={mode} scan_source={run_json.get('scan_source')} "
        f"coverage_before={run_json['coverage']['before']} coverage_after={run_json['coverage']['after']} "
        f"intel_status={run_json.get('intel_status')}"
    )


if __name__ == "__main__":
    main()

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
            "scan_limit": 800,
            "intel_n": 30,
        },
        "scanner": {
            "provider": "stooq",
            "lookback_days": 365,
            "adv_window": 20,
            "timeout_sec": 12,
            "retries": 2,
            "max_workers": 12,
            "cache_ttl_hours": 48,
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
        s.replace("&", "&amp;")
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


def load_universe_seed() -> list[str]:
    seed_path = Path("data/raw/universe/universe_seed.json")
    if not seed_path.exists():
        return []
    try:
        obj = json.loads(seed_path.read_text(encoding="utf-8"))
        tickers = obj.get("tickers", [])
        return sorted({t.strip().upper() for t in tickers if isinstance(t, str) and t.strip()})
    except Exception:
        return []


def _download_text(url: str, timeout_sec: int) -> str:
    r = requests.get(url, timeout=timeout_sec)
    r.raise_for_status()
    return r.text


def _is_equity_like(symbol: str, name: str) -> bool:
    n = (name or "").lower()
    bad_keywords = [
        "warrant", "warrants",
        "rights",
        "units",
        "preferred",
        "depositary",
        "note", "notes",
        "bond", "bonds",
        "trust",
        "etn",
    ]
    if any(k in n for k in bad_keywords):
        return False
    for ch in ["^", " ", "/"]:
        if ch in symbol:
            return False
    return True


def fetch_universe_nasdaqtrader(exclude_etf: bool, max_symbols: int, timeout_sec: int = 20) -> dict:
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
        raise RuntimeError("nasdaqtraded.txt empty")

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
        raise RuntimeError("otherlisted.txt empty")

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
            time.sleep(0.3 + random.random() * 0.7)
    return None


def fetch_stooq_csv_text(ticker: str, timeout_sec: int, retries: int) -> str | None:
    symbol = f"{ticker.lower()}.us"
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    text = _http_get_text_with_retries(url, timeout_sec=timeout_sec, retries=retries)
    if not text:
        return None
    text = text.strip()
    if "Date,Open,High,Low,Close,Volume" not in text:
        return None
    return text


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
) -> tuple[dict | None, bool]:
    cache_dir = Path("data/cache/stooq")
    ensure_dir(cache_dir)
    cache_path = cache_dir / f"{ticker.upper()}.csv"

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


def _metrics_for_one_ticker(ticker: str, scanner_cfg: dict) -> tuple[str, dict, dict]:
    provider = str(scanner_cfg.get("provider", "stooq")).lower()
    timeout_sec = int(scanner_cfg.get("timeout_sec", 12))
    adv_window = int(scanner_cfg.get("adv_window", 20))
    retries = int(scanner_cfg.get("retries", 2))
    cache_ttl_hours = int(scanner_cfg.get("cache_ttl_hours", 48))
    fallback = bool(scanner_cfg.get("fallback_to_fake", True))

    local_stats = {"real": 0, "fallback": 0, "nodata": 0, "cache_hit": 0}

    if provider == "fake":
        m = fake_metrics_for_ticker(ticker)
        local_stats["fallback"] += 1
        return ticker, m, local_stats

    m, cached = get_stooq_metrics_with_cache(
        ticker=ticker,
        adv_window=adv_window,
        timeout_sec=timeout_sec,
        retries=retries,
        cache_ttl_hours=cache_ttl_hours,
    )
    if cached:
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

    return ticker, m, local_stats


def build_candidates(tickers: list[str], scanner_cfg: dict) -> tuple[list[dict], dict]:
    provider = str(scanner_cfg.get("provider", "stooq")).lower()
    max_workers = int(scanner_cfg.get("max_workers", 12))

    rows = []
    stats = {"real": 0, "fallback": 0, "nodata": 0, "cache_hit": 0, "provider": provider}

    if provider == "fake" or max_workers <= 1:
        for t in tickers:
            _, m, st = _metrics_for_one_ticker(t, scanner_cfg)
            stats["real"] += st["real"]
            stats["fallback"] += st["fallback"]
            stats["nodata"] += st["nodata"]
            stats["cache_hit"] += st["cache_hit"]
            rows.append({"ticker": t, **m})
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(_metrics_for_one_ticker, t, scanner_cfg): t for t in tickers}
            for fut in as_completed(futs):
                t = futs[fut]
                try:
                    _, m, st = fut.result()
                except Exception:
                    m = fake_metrics_for_ticker(t)
                    st = {"real": 0, "fallback": 1, "nodata": 1, "cache_hit": 0}

                stats["real"] += st["real"]
                stats["fallback"] += st["fallback"]
                stats["nodata"] += st["nodata"]
                stats["cache_hit"] += st["cache_hit"]
                rows.append({"ticker": t, **m})

    rows.sort(key=lambda r: (r.get("dd_52w_pct", 0.0), -r.get("adv_usd_m", 0.0)))
    return rows, stats


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

    # 부족하면 "데이터 있는 종목" 우선으로 보충
    if len(survivors) < target_n:
        already = {r["ticker"] for r in survivors}
        with_data = [r for r in candidates if r.get("last_close") is not None and r["ticker"] not in already]
        for r in with_data:
            survivors.append(r)
            already.add(r["ticker"])
            if len(survivors) >= target_n:
                break

    # 그래도 부족하면 마지막으로 nodata까지 허용(무조건 송출)
    if len(survivors) < target_n:
        already = {r["ticker"] for r in survivors}
        for r in candidates:
            if r["ticker"] in already:
                continue
            survivors.append(r)
            if len(survivors) >= target_n:
                break

    survivors = survivors[:target_n]
    pick_stats = {"target_n": target_n, "after_filter": len(filtered), "final": len(survivors)}
    return survivors, {"filter": filter_stats, "pick": pick_stats}


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


def run_intel_for_ticker(client, model: str, prompt_template: str, ticker: str) -> dict:
    prompt = render_prompt(prompt_template, ticker)
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        text = (resp.text or "").strip()
        if not text:
            raise RuntimeError("Empty response text")
        return {"ticker": ticker, "status": "SUCCESS", "reason": None, "text_ko": text}
    except Exception as e:
        return {"ticker": ticker, "status": "FAILED", "reason": repr(e), "text_ko": "분석 실패"}


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


def main() -> None:
    cfg = load_config()

    engine_name = cfg["engine"]["name"]
    model = cfg["engine"]["model"]
    prompt_template = cfg["engine"]["prompt_ko_template"]

    logs_root = Path(cfg["paths"]["logs_root"])
    universe_out = Path(cfg["paths"]["universe_out"])
    candidates_out = Path(cfg["paths"]["candidates_out"])
    survivors_out = Path(cfg["paths"]["survivors_out"])
    intel_out = Path(cfg["paths"]["intel_out"])
    dashboard_out = Path(cfg["paths"]["dashboard_out"])
    dashboard_template = Path(cfg["paths"]["dashboard_template"])

    universe_cfg = cfg.get("universe", {})
    run_cfg = cfg.get("run", {})
    scanner_cfg = cfg.get("scanner", {})
    funnel_cfg = cfg.get("funnel", {})

    scan_limit = int(run_cfg.get("scan_limit", 800))
    intel_n = int(run_cfg.get("intel_n", 30))

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
        "counts": {},
        "scanner_stats": {},
        "funnel_stats": {},
        "universe_meta": {},
    }

    # A) Universe
    provider = str(universe_cfg.get("provider", "nasdaqtrader")).lower()
    exclude_etf = bool(universe_cfg.get("exclude_etf", True))
    max_symbols = int(universe_cfg.get("max_symbols", 6500))

    if provider == "seed":
        tickers_all = load_universe_seed()
        run_json["universe_meta"] = {"provider": "seed", "count": len(tickers_all)}
    else:
        uni = fetch_universe_nasdaqtrader(exclude_etf=exclude_etf, max_symbols=max_symbols)
        tickers_all = uni["tickers"]
        run_json["universe_meta"] = uni["meta"]

    write_json(universe_out, {
        "source": provider,
        "created_at_utc": now_utc_iso(),
        "count": len(tickers_all),
        "meta": run_json["universe_meta"],
        "tickers": tickers_all
    })
    run_json["artifacts"]["universe"] = str(universe_out)
    run_json["counts"]["universe_total"] = len(tickers_all)

    tickers_scan = tickers_all[: max(0, scan_limit)]
    run_json["counts"]["universe_scanned"] = len(tickers_scan)

    # B) Candidates
    candidates, scan_stats = build_candidates(tickers_scan, scanner_cfg)
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

    # E) Survivors
    survivors, funnel_stats = pick_survivors(candidates, funnel_cfg)
    run_json["funnel_stats"] = funnel_stats

    write_json(survivors_out, {
        "source": "funnel_v2_numeric",
        "created_at_utc": now_utc_iso(),
        "count": len(survivors),
        "rules": {
            "survivors_n": int(funnel_cfg.get("survivors_n", 30)),
            "min_price_usd": float(funnel_cfg.get("min_price_usd", 5.0)),
            "min_adv_usd_m": float(funnel_cfg.get("min_adv_usd_m", 20.0)),
            "min_dd_52w_pct": float(funnel_cfg.get("min_dd_52w_pct", -95.0)),
            "max_dd_52w_pct": float(funnel_cfg.get("max_dd_52w_pct", -15.0)),
        },
        "stats": funnel_stats,
        "rows": survivors
    })
    run_json["artifacts"]["survivors"] = str(survivors_out)
    run_json["counts"]["survivors"] = len(survivors)

    # C) Intel
    intel_rows = []
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        for r in survivors[:intel_n]:
            intel_rows.append({"ticker": r["ticker"], "status": "SKIPPED", "reason": "GEMINI_API_KEY not set", "text_ko": "API 키 없음"})
        run_json["status"] = "SUCCESS_WITHOUT_INTEL"
    else:
        try:
            from google import genai
            client = genai.Client()

            for r in survivors[:intel_n]:
                intel_rows.append(run_intel_for_ticker(client, model, prompt_template, r["ticker"]))

            run_json["status"] = "SUCCESS"
        except Exception as e:
            run_json["status"] = "SUCCESS_WITH_INTEL_FAILED"
            run_json["errors"].append(repr(e))
            for r in survivors[:intel_n]:
                intel_rows.append({"ticker": r["ticker"], "status": "FAILED", "reason": "client_init_failed", "text_ko": "클라이언트 초기화 실패"})

    write_json(intel_out, intel_rows)
    run_json["artifacts"]["intel_30"] = str(intel_out)
    run_json["counts"]["intel"] = len(intel_rows)

    # D) Dashboard
    try:
        if not dashboard_template.exists():
            raise FileNotFoundError(f"Missing template: {dashboard_template}")

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
            "intel_count": run_json["counts"]["intel"],
            "scan_table_html": scan_table_html,
            "survivors_table_html": survivors_table_html,
            "intel_table_html": intel_table_html,
        }
        build_dashboard_html(dashboard_template, dashboard_out, ctx)
        run_json["artifacts"]["dashboard"] = str(dashboard_out)
    except Exception as e:
        run_json["errors"].append(f"dashboard_error:{repr(e)}")

    write_json(run_dir / "run.json", run_json)
    print(
        "[OK] "
        f"run_id={run_id} status={run_json['status']} "
        f"universe_total={run_json['counts'].get('universe_total')} "
        f"scanned={run_json['counts'].get('universe_scanned')} "
        f"scanner={run_json.get('scanner_stats',{})} "
        f"funnel={run_json.get('funnel_stats',{})}"
    )


if __name__ == "__main__":
    main()

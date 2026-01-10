import os
import json
import uuid
import csv
from io import StringIO
from datetime import datetime, timezone
from pathlib import Path

import yaml
import requests


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
        "run": {
            "intel_n": 30,
        },
        "scanner": {
            "provider": "stooq",
            "lookback_days": 365,
            "adv_window": 20,
            "timeout_sec": 12,
            "fallback_to_fake": True,
        },
        "funnel": {
            "survivors_n": 30,
            "sort_key": "dd_52w_pct",
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
        for top_key in ("engine", "paths", "run", "scanner", "funnel"):
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
    }


def fetch_stooq_daily(ticker: str, timeout_sec: int) -> list[dict] | None:
    symbol = f"{ticker.lower()}.us"
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    try:
        r = requests.get(url, timeout=timeout_sec)
        if r.status_code != 200:
            return None
        text = r.text.strip()
        if "Date,Open,High,Low,Close,Volume" not in text:
            return None

        f = StringIO(text)
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            try:
                rows.append({
                    "date": row["Date"],
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"]),
                })
            except Exception:
                continue

        if not rows:
            return None
        return rows
    except Exception:
        return None


def compute_real_metrics_from_rows(rows: list[dict], lookback_days: int, adv_window: int) -> dict | None:
    # stooq는 오래된 데이터부터 정렬되어 오는 경우가 많음 → 최신이 마지막
    usable = [r for r in rows if r.get("volume", 0) > 0]
    if len(usable) < max(adv_window, 60):
        return None

    # lookback_days는 캘린더 기준 근사. 데이터는 trading day라서 마지막 N개를 사용.
    # 365일 근사로 260개 정도면 충분하지만 여유로 320개까지 사용
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

    # scan_score: 낙폭이 클수록 높게(간단)
    scan_score = int(min(999, max(0, round(-dd_52w_pct * 10))))

    return {
        "dd_52w_pct": dd_52w_pct,
        "adv_usd_m": adv_usd_m,
        "scan_score": scan_score,
        "note": "REAL_STOOQ",
        "price_source": "stooq",
    }


def build_candidates(tickers: list[str], scanner_cfg: dict) -> tuple[list[dict], dict]:
    provider = str(scanner_cfg.get("provider", "stooq")).lower()
    timeout_sec = int(scanner_cfg.get("timeout_sec", 12))
    lookback_days = int(scanner_cfg.get("lookback_days", 365))
    adv_window = int(scanner_cfg.get("adv_window", 20))
    fallback = bool(scanner_cfg.get("fallback_to_fake", True))

    rows = []
    stats = {"real": 0, "fallback": 0, "provider": provider}

    for t in tickers:
        if provider == "fake":
            m = fake_metrics_for_ticker(t)
            stats["fallback"] += 1
            rows.append({"ticker": t, **m})
            continue

        real_rows = fetch_stooq_daily(t, timeout_sec=timeout_sec)
        m = None
        if real_rows is not None:
            m = compute_real_metrics_from_rows(real_rows, lookback_days=lookback_days, adv_window=adv_window)

        if m is None:
            if fallback:
                m = fake_metrics_for_ticker(t)
                stats["fallback"] += 1
            else:
                # 폴백 금지면 최소값으로 넣어서 파이프라인 유지
                m = {"dd_52w_pct": 0.0, "adv_usd_m": 0.0, "scan_score": 0, "note": "NO_DATA", "price_source": "none"}
                stats["fallback"] += 1
        else:
            stats["real"] += 1

        rows.append({"ticker": t, **m})

    # 정렬: 낙폭 큰 순(더 음수) → 거래대금 큰 순
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


def funnel_survivors(candidates: list[dict], n: int, sort_key: str) -> list[dict]:
    if sort_key == "dd_52w_pct":
        sorted_rows = sorted(candidates, key=lambda r: (r.get("dd_52w_pct", 0.0), -r.get("adv_usd_m", 0.0)))
    else:
        sorted_rows = candidates[:]
    return sorted_rows[: max(0, int(n))]


def build_survivors_table_html(rows: list[dict]) -> str:
    if not rows:
        return "<div class='muted'>서바이버 없음</div>"
    head = (
        "<table><thead><tr>"
        "<th>#</th><th>Ticker</th><th>DD(52w)%</th><th>ADV($M)</th><th>Score</th><th>Source</th>"
        "</tr></thead><tbody>"
    )
    body = ""
    for i, r in enumerate(rows, start=1):
        body += (
            "<tr>"
            f"<td>{i}</td>"
            f"<td><b>{safe_html_escape(r['ticker'])}</b></td>"
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

    intel_n = int(cfg["run"]["intel_n"])
    scanner_cfg = cfg.get("scanner", {})
    survivors_n = int(cfg["funnel"]["survivors_n"])
    sort_key = str(cfg["funnel"]["sort_key"])

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
    }

    # A) Universe
    tickers = load_universe_seed()
    write_json(universe_out, {"source": "seed", "created_at_utc": now_utc_iso(), "count": len(tickers), "tickers": tickers})
    run_json["artifacts"]["universe"] = str(universe_out)
    run_json["counts"]["universe"] = len(tickers)

    # B) Candidates (REAL with fallback)
    candidates, scan_stats = build_candidates(tickers, scanner_cfg)
    write_json(candidates_out, {"source": f"scanner_{scan_stats.get('provider','')}", "created_at_utc": now_utc_iso(), "count": len(candidates), "rows": candidates})
    run_json["artifacts"]["candidates_raw"] = str(candidates_out)
    run_json["counts"]["candidates_raw"] = len(candidates)
    run_json["scanner_stats"] = scan_stats

    # E) Survivors
    survivors = funnel_survivors(candidates, survivors_n, sort_key)
    write_json(survivors_out, {
        "source": "funnel_v1",
        "created_at_utc": now_utc_iso(),
        "count": len(survivors),
        "rules": {"survivors_n": survivors_n, "sort_key": sort_key},
        "rows": survivors
    })
    run_json["artifacts"]["survivors"] = str(survivors_out)
    run_json["counts"]["survivors"] = len(survivors)

    # C) Intel (멀티)
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
            "universe_count": run_json["counts"]["universe"],
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
    print(f"[OK] run_id={run_id} status={run_json['status']} scanner={run_json.get('scanner_stats',{})}")


if __name__ == "__main__":
    main()

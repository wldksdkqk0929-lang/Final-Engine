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
            "prompt_ko": "턴어라운드 스나이퍼 전략에서 뉴스→펀더멘털→차트 필터 순서를 한국어로 3줄 요약해줘.",
        },
        "paths": {
            "logs_root": "data/logs/runs",
            "universe_out": "data/processed/universe/universe.json",
            "candidates_out": "data/processed/candidates_raw/candidates_raw.json",
            "intel_out": "data/processed/intel_30/intel_30.json",
            "dashboard_out": "data/artifacts/dashboard/index.html",
            "dashboard_template": "templates/dashboard.html",
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
        for top_key in ("engine", "paths", "run"):
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
    for key, val in context.items():
        html = html.replace(f"{{{{{key}}}}}", safe_html_escape(str(val if val is not None else "")))
    write_text(out_path, html)


def load_universe_seed() -> list[str]:
    seed_path = Path("data/raw/universe/universe_seed.json")
    if not seed_path.exists():
        return []
    try:
        obj = json.loads(seed_path.read_text(encoding="utf-8"))
        tickers = obj.get("tickers", [])
        tickers = sorted({t.strip().upper() for t in tickers if isinstance(t, str) and t.strip()})
        return tickers
    except Exception:
        return []


def fake_scan_candidates(tickers: list[str]) -> list[dict]:
    """
    외부 가격 데이터 연결 전 단계.
    스키마/정렬/대시보드 표시를 고정하기 위해
    티커 문자열을 기반으로 결정론적(재현 가능한) 점수를 만든다.
    """
    rows = []
    for t in tickers:
        # 결정론적 점수: 문자 코드 합으로 0~99 생성
        score = sum(ord(c) for c in t) % 100
        dd_52w = round(-1.0 * (20 + (score * 0.6)), 2)  # -20% ~ -79.4% 범위
        adv_usd_m = round(0.5 + (score * 0.08), 2)      # 0.5 ~ 8.42 (백만달러 가정)
        rows.append({
            "ticker": t,
            "dd_52w_pct": dd_52w,
            "adv_usd_m": adv_usd_m,
            "scan_score": score,
            "note": "FAKE_SCAN",
        })

    # 정렬: 낙폭 큰 순(더 음수), 그 다음 거래대금 큰 순
    rows.sort(key=lambda r: (r["dd_52w_pct"], -r["adv_usd_m"]))
    return rows


def build_scan_table_html(top_rows: list[dict]) -> str:
    if not top_rows:
        return "<div class='muted'>스캔 결과 없음</div>"

    head = (
        "<table>"
        "<thead><tr>

import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_OUT = os.path.join(BASE_DIR, "data", "out")
DATA_METRICS = os.path.join(BASE_DIR, "data", "metrics")


def _safe_listdir(path):
    try:
        return os.listdir(path)
    except Exception:
        return []


def load_latest_date_dir(base_path):
    if not os.path.exists(base_path):
        return None

    dirs = sorted(
        [d for d in _safe_listdir(base_path) if os.path.isdir(os.path.join(base_path, d))],
        reverse=True
    )
    return os.path.join(base_path, dirs[0]) if dirs else None


def load_latest_metrics_file(metrics_date_dir):
    if not metrics_date_dir or not os.path.exists(metrics_date_dir):
        return None

    files = [f for f in _safe_listdir(metrics_date_dir) if f.endswith(".json")]
    if not files:
        return None

    # ✅ 파일명 정렬이 아니라 "수정시간(mtime)"으로 최신 선택
    files_full = [os.path.join(metrics_date_dir, f) for f in files]
    latest = max(files_full, key=lambda p: os.path.getmtime(p))
    return latest


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def scan_out_files(out_date_dir):
    if not out_date_dir or not os.path.exists(out_date_dir):
        return []
    return sorted([f for f in _safe_listdir(out_date_dir) if f.endswith(".json")])


def scan_run_history(metrics_date_dir, limit=5):
    if not metrics_date_dir or not os.path.exists(metrics_date_dir):
        return []

    files = [f for f in _safe_listdir(metrics_date_dir) if f.endswith(".json")]
    files_full = [os.path.join(metrics_date_dir, f) for f in files]
    files_full_sorted = sorted(files_full, key=lambda p: os.path.getmtime(p), reverse=True)

    history = []
    for fpath in files_full_sorted[:limit]:
        fname = os.path.basename(fpath)
        payload = load_json(fpath) or {}
        history.append((fname, payload))
    return history


def pipeline_status(metrics_payload, out_files):
    logger_ok = True
    metrics_ok = bool(metrics_payload)
    out_connected = len(out_files) > 0

    provider_mode = "UNKNOWN (check logs)"
    if isinstance(metrics_payload, dict) and metrics_payload.get("api_call_count", 0) > 0:
        provider_mode = "LIKELY REAL (api_call_count > 0)"
    else:
        provider_mode = "LIKELY MOCK (api_call_count == 0)"

    return {
        "Logger": "OK" if logger_ok else "CHECK",
        "Metrics": "OK" if metrics_ok else "CHECK",
        "Data Out": "CONNECTED" if out_connected else "NOT CONNECTED",
        "LLM Provider": provider_mode,
    }


def health_label(metrics_payload, out_files):
    if not metrics_payload:
        return "CHECK REQUIRED"

    err = int(metrics_payload.get("error_count", 0) or 0)
    symbols = int(metrics_payload.get("symbol_processed_count", 0) or 0)
    out_connected = len(out_files) > 0

    if err > 0:
        return "CHECK REQUIRED"
    if symbols == 0 and not out_connected:
        return "CHECK REQUIRED"
    return "HEALTHY"


def next_actions(metrics_payload, out_files):
    actions = []
    out_connected = len(out_files) > 0
    err = int((metrics_payload or {}).get("error_count", 0) or 0)
    symbols = int((metrics_payload or {}).get("symbol_processed_count", 0) or 0)

    if not out_connected:
        actions.append("A) Connect BatchRunner -> persist per-symbol JSON into data/out/<date>/")
    if err > 0:
        actions.append("B) Investigate why error_count is non-zero. Consider baseline reset.")
    if symbols == 0:
        actions.append("C) Wire orchestration to real processor loop so symbol_processed_count increments.")
    if not actions:
        actions.append("OK) System looks healthy. Next: expand targets list and schedule cadence.")
    return actions


def print_kv(key, value, width=22):
    print(f"{key:<{width}}: {value}")


def main():
    print("\n" + "=" * 70)
    print("SNIPER DASHBOARD v2 (Phase-4C)".center(70))
    print("=" * 70)

    latest_out_dir = load_latest_date_dir(DATA_OUT)
    latest_metrics_dir = load_latest_date_dir(DATA_METRICS)

    out_date = os.path.basename(latest_out_dir) if latest_out_dir else "N/A"
    metrics_date = os.path.basename(latest_metrics_dir) if latest_metrics_dir else "N/A"

    out_files = scan_out_files(latest_out_dir)
    latest_metrics_file = load_latest_metrics_file(latest_metrics_dir)
    metrics_payload = load_json(latest_metrics_file) if latest_metrics_file else None

    print("\n[Summary]")
    print_kv("Out Date", out_date)
    print_kv("Metrics Date", metrics_date)
    print_kv("Out Files", len(out_files))
    print_kv("Latest Metrics File", os.path.basename(latest_metrics_file) if latest_metrics_file else "N/A")

    print("\n[Latest Metrics]")
    if metrics_payload:
        print_kv("run_id", metrics_payload.get("run_id", "N/A"))
        print_kv("symbol_processed_count", metrics_payload.get("symbol_processed_count", "N/A"))
        print_kv("api_call_count", metrics_payload.get("api_call_count", "N/A"))
        print_kv("cache_hit_count", metrics_payload.get("cache_hit_count", "N/A"))
        print_kv("cache_miss_count", metrics_payload.get("cache_miss_count", "N/A"))
        print_kv("kill_switch_block_count", metrics_payload.get("kill_switch_block_count", "N/A"))
        print_kv("error_count", metrics_payload.get("error_count", "N/A"))
        print_kv("avg_latency_ms", metrics_payload.get("avg_latency_ms", "N/A"))
    else:
        print("No metrics payload found.")

    print("\n[Run History] (latest 5)")
    history = scan_run_history(latest_metrics_dir, limit=5)
    if not history:
        print("No run history found.")
    else:
        for fname, payload in history:
            rid = payload.get("run_id", "N/A") if isinstance(payload, dict) else "N/A"
            err = payload.get("error_count", "N/A") if isinstance(payload, dict) else "N/A"
            sym = payload.get("symbol_processed_count", "N/A") if isinstance(payload, dict) else "N/A"
            api = payload.get("api_call_count", "N/A") if isinstance(payload, dict) else "N/A"
            print(f"- {fname:<18} | run_id={rid} | symbols={sym} | errors={err} | api={api}")

    print("\n[Out Samples] (up to 5)")
    if out_files:
        for f in out_files[:5]:
            print(f"- {f}")
    else:
        print("No per-symbol JSON outputs found in data/out. (pipeline not connected yet)")

    print("\n[Pipeline Status]")
    ps = pipeline_status(metrics_payload, out_files)
    for k, v in ps.items():
        print_kv(k, v)

    print("\n[System Health]")
    print_kv("Status", health_label(metrics_payload, out_files))

    print("\n[Next Suggested Actions]")
    for a in next_actions(metrics_payload, out_files):
        print(f"- {a}")

    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()

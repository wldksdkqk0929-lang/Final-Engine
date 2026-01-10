import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    # run_id (재현/추적용)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{ts}_{uuid.uuid4().hex[:8]}"

    # 표준 경로
    base = Path(".")
    run_dir = base / "data" / "logs" / "runs" / run_id
    out_dir = base / "data" / "processed" / "intel_30"

    ensure_dir(run_dir)
    ensure_dir(out_dir)

    run_json = {
        "engine_name": "Final Engine",
        "run_id": run_id,
        "created_at_utc": now_utc_iso(),
        "status": "STARTED",
        "engine": "gemini",
        "artifacts": {},
        "errors": [],
    }

    # Gemini 호출 (실패해도 멈추지 않음)
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    intel_path = out_dir / "intel_30.json"

    if not gemini_key:
        # 키 없으면 SKIPPED로 종료(파이프라인은 계속 살아있어야 함)
        intel = [{
            "ticker": "TEST",
            "status": "SKIPPED",
            "reason": "GEMINI_API_KEY not set",
            "text_ko": "Gemini API 키가 설정되지 않아 인텔 모듈을 건너뜀."
        }]
        write_json(intel_path, intel)
        run_json["status"] = "SUCCESS_WITHOUT_INTEL"
        run_json["artifacts"]["intel_30"] = str(intel_path)
        write_json(run_dir / "run.json", run_json)
        print(f"[OK] run_id={run_id} (intel skipped)")
        return

    try:
        from google import genai  # google-genai SDK

        client = genai.Client()  # GEMINI_API_KEY 환경변수에서 자동 인식
        prompt = "턴어라운드 스나이퍼 전략에서 '뉴스→펀더멘털→차트' 필터 순서를 한국어로 3줄 요약해줘."

        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        text = (resp.text or "").strip()
        if not text:
            raise RuntimeError("Empty response text")

        intel = [{
            "ticker": "TEST",
            "status": "SUCCESS",
            "reason": None,
            "text_ko": text,
        }]
        write_json(intel_path, intel)

        run_json["status"] = "SUCCESS"
        run_json["artifacts"]["intel_30"] = str(intel_path)

    except Exception as e:
        # 실패해도 결과 파일을 남기고 종료
        intel = [{
            "ticker": "TEST",
            "status": "FAILED",
            "reason": repr(e),
            "text_ko": "Gemini 호출 실패. 기술 모드로 대체 필요."
        }]
        write_json(intel_path, intel)

        run_json["status"] = "SUCCESS_WITH_INTEL_FAILED"
        run_json["artifacts"]["intel_30"] = str(intel_path)
        run_json["errors"].append(repr(e))

    write_json(run_dir / "run.json", run_json)
    print(f"[OK] run_id={run_id} status={run_json['status']}")


if __name__ == "__main__":
    main()

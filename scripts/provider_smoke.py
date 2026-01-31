from engine.providers.factory import get_provider


def main():
    p = get_provider()
    ok = p.health_check()
    print(f"[Smoke] health_check={ok}")

    payload = p.analyze_symbol("AAPL", {"raw_text": "hello"})
    print(
        f"[Smoke] result.status={payload.get('status')}, "
        f"api_called={payload.get('api_called')}, "
        f"blocked={payload.get('blocked')}"
    )

    stats = p.get_usage_stats()
    print(f"[Smoke] usage={stats}")


if __name__ == "__main__":
    main()

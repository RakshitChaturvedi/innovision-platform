import asyncio
import os
import time
import asyncpg
import redis.asyncio as aioredis
import httpx

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
DATABASE_URL = DATABASE_URL.replace("@postgres:", "@localhost:")

REDIS_URL = os.environ.get("REDIS_LOCAL_URL", "redis://localhost:6379")
ALERT_MGMT_URL = os.environ.get("ALERT_MGMT_URL", "http://localhost:8010")

EXPECTED_UCS = {"uc1", "uc2", "uc3", "uc4"}


async def check_health() -> bool:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{ALERT_MGMT_URL}/health", timeout=5)
            assert resp.status_code == 200
            print("✓ Alert management service healthy")
            return True
        except Exception as e:
            print(f"✗ Alert management health check failed: {e}")
            return False


async def wait_for_alerts(
    timeout_s: int = 60,
    min_per_uc: int = 1,
) -> dict[str, int]:
    """Wait until each UC has at least min_per_uc alerts in DB."""
    conn = await asyncpg.connect(DATABASE_URL)
    start = time.monotonic()

    while time.monotonic() - start < timeout_s:
        rows = await conn.fetch("""
            SELECT source_uc, COUNT(*) as count
            FROM alerts
            GROUP BY source_uc
        """)
        counts = {row["source_uc"]: row["count"] for row in rows}
        print(f"[{int(time.monotonic()-start)}s] Alert counts: {counts}")

        missing = EXPECTED_UCS - set(counts.keys())
        insufficient = {
            uc for uc, count in counts.items()
            if count < min_per_uc
        }

        if not missing and not insufficient:
            await conn.close()
            return counts

        await asyncio.sleep(3)

    await conn.close()
    raise TimeoutError(
        f"Expected alerts from all UCs within {timeout_s}s. "
        f"Got: {counts}"
    )


async def check_dead_letter() -> int:
    r = await aioredis.from_url(REDIS_URL)
    count = await r.xlen("alerts:dead_letter")
    await r.aclose()
    return count


async def check_stream_lag() -> dict:
    r = await aioredis.from_url(REDIS_URL)
    try:
        groups = await r.xinfo_groups("alerts:live")
        lag_info = {}
        for group in groups:
            name = group["name"]
            if isinstance(name, bytes):
                name = name.decode()
            lag_info[name] = group.get("lag", 0)
        await r.aclose()
        return lag_info
    except Exception as e:
        await r.aclose()
        return {"error": str(e)}


async def main():
    print("=" * 60)
    print("Phase 1 Smoke Test")
    print("=" * 60)

    # Check 1: Alert management health
    print("\n[1] Alert Management Service Health")
    healthy = await check_health()
    if not healthy:
        print("FAIL: Alert management not running")
        return

    # Check 2: Alerts accumulating from all UCs
    print("\n[2] Waiting for alerts from all 4 UC stubs...")
    try:
        counts = await wait_for_alerts(timeout_s=120, min_per_uc=2)
        for uc, count in sorted(counts.items()):
            print(f"  ✓ {uc}: {count} alerts persisted")
    except TimeoutError as e:
        print(f"  ✗ {e}")
        return

    # Check 3: Dead letter stream empty
    print("\n[3] Dead Letter Stream")
    dead_count = await check_dead_letter()
    if dead_count == 0:
        print("  ✓ No malformed alerts in dead letter")
    else:
        print(f"  ⚠ {dead_count} alerts in dead letter — check logs")

    # Check 4: Stream lag
    print("\n[4] Stream Lag")
    lag = await check_stream_lag()
    for group, lag_count in lag.items():
        status = "✓" if lag_count == 0 else "⚠"
        print(f"  {status} {group}: lag={lag_count}")

    print("\n" + "=" * 60)
    print("Phase 1 Smoke Test PASSED")
    print("=" * 60)
    print("\nNext: Phase 2 — Ingestion Layer")


if __name__ == "__main__":
    asyncio.run(main())
import redis
import sys

PLATFORM_STREAMS = {
    "alerts:live": ["alert_management_group"],
    "alerts:dead_letter": ["dead_letter_review_group"],
    "incidents:live": ["incident_management_group"],
    "notifications:live": ["notification_group"]
}

def create_platform_streams(redis_url: str = "redis://localhost:6379") -> None:
    r = redis.Redis.from_url(redis_url, decode_responses=True)

    for stream, groups in PLATFORM_STREAMS.items():
        for group in groups:
            try:
                r.xgroup_create(stream, group, id="0", mkstream=True)
                print(f"Created: {stream}/{group}")
            except redis.exceptions.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    print(f"Exists: {stream}/{group}")
                else:
                    print(f"Error: {stream}/{group}: {e}", file=sys.stderr)
                    raise
    print("\nPlatform streams ready.")

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    redis_url = os.environ.get("REDIS_LOCAL_URL", "redis://localhost:6378")
    create_platform_streams(redis_url)
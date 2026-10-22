"""
Centralized pytest configuration and test database safety guard for Innovision.
Enforces that database-writing tests NEVER run against the development/operational database
(innovision_platform), production databases, or unverified remote targets.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
import sqlalchemy.ext.asyncio as sa_async

# Ensure tests directory is in sys.path so tests can import helpers
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

REPO_ROOT = TESTS_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


UNSAFE_DATABASE_NAMES = {
    "innovision_platform",
    "innovision",
    "postgres",
    "template1",
    "production",
    "prod",
}

SAFE_LOCAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "postgres",
    "test-postgres",
    "test-db",
}


def validate_test_database_target(db_url: str | None) -> str:
    """
    Validates that a database URL points to an explicitly configured, dedicated test database.
    Rejects:
    1. Empty or missing URLs (no silent fallback to development DB).
    2. Known platform/development database names (e.g. 'innovision_platform').
    3. Database names that do not follow test naming conventions (*_test or test_*).
    4. Unapproved remote hostnames and IP addresses by default.
    """
    if not db_url or not str(db_url).strip():
        raise RuntimeError(
            "SAFETY ERROR: No test database URL provided. "
            "Tests must explicitly configure DATABASE_URL_LOCAL or TEST_DATABASE_URL targeting a dedicated test database. "
            "Silent fallback to 'innovision_platform' or development database is strictly prohibited."
        )

    url_str = str(db_url).strip()
    # Normalize for urlsplit if scheme uses +asyncpg
    normalized_for_parse = url_str
    if "://" in url_str:
        scheme, remainder = url_str.split("://", 1)
        normalized_for_parse = f"http://{remainder}"

    parsed = urlsplit(normalized_for_parse)
    db_name = (parsed.path or "").lstrip("/")

    if not db_name:
        raise RuntimeError(
            f"SAFETY ERROR: Unable to parse database name from URL: '{url_str}'. "
            "A dedicated test database must be specified."
        )

    # 1. Reject known operational / platform database names
    if db_name.lower() in UNSAFE_DATABASE_NAMES:
        raise RuntimeError(
            f"SAFETY VIOLATION: Database test connection attempted against operational database '{db_name}'. "
            "Tests must NEVER run against 'innovision_platform' or operational data. "
            "Configure a dedicated test database such as 'innovision_platform_test'."
        )

    # 2. Require test database suffix or prefix
    if not (db_name.lower().endswith("_test") or db_name.lower().startswith("test_")):
        raise RuntimeError(
            f"SAFETY VIOLATION: Database name '{db_name}' is not recognized as a dedicated test database. "
            "Test database names must end with '_test' (e.g., 'innovision_platform_test') or start with 'test_'."
        )

    # 3. Host validation: restrict database hosts safely (DEF-03)
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise RuntimeError(f"SAFETY ERROR: Unable to parse hostname from database URL: '{url_str}'.")

    if hostname not in SAFE_LOCAL_HOSTS:
        allow_remote = os.getenv("INNOVISION_ALLOW_REMOTE_TEST_HOST", "0").lower() in ("1", "true", "yes")
        if not allow_remote:
            raise RuntimeError(
                f"SAFETY VIOLATION: Unapproved remote or non-local database host '{hostname}'. "
                "Database tests strictly permit approved local/test-container hosts by default. "
                "Set INNOVISION_ALLOW_REMOTE_TEST_HOST=1 only for verified dedicated remote test databases."
            )
        # Even with explicit remote opt-in, reject dangerous operational keywords:
        for forbidden in ("prod", "production", "aws", "rds", "azure", "gcp", "cluster"):
            if forbidden in hostname:
                raise RuntimeError(
                    f"SAFETY VIOLATION: Refusing connection to potential production host '{hostname}' even with remote opt-in."
                )

    return url_str


def get_safe_test_db_url() -> str:
    """
    Retrieves and validates the test database URL from environment.
    Handles both DATABASE_URL_LOCAL and TEST_DATABASE_URL consistently.
    If both variables are set to different targets, validates both and fails
    if either points to an unsafe database.
    Raises RuntimeError if neither is set or if either is invalid.
    """
    url_local = os.getenv("DATABASE_URL_LOCAL")
    url_test = os.getenv("TEST_DATABASE_URL")

    if not url_local and not url_test:
        raise RuntimeError(
            "SAFETY ERROR: No test database URL provided. "
            "Neither DATABASE_URL_LOCAL nor TEST_DATABASE_URL is set. "
            "Tests must explicitly configure a dedicated test database (e.g. 'innovision_platform_test'). "
            "Silent fallback to 'innovision_platform' or development database is strictly prohibited."
        )

    # Validate both if both are present; fail closed if either is unsafe
    validated_local = validate_test_database_target(url_local) if url_local else None
    validated_test = validate_test_database_target(url_test) if url_test else None

    # Prefer TEST_DATABASE_URL if both are set and valid, otherwise return whichever is set
    return validated_test or validated_local


def pytest_sessionstart(session):
    """
    Early session hook: If DATABASE_URL_LOCAL or TEST_DATABASE_URL is present in the environment,
    immediately validate both to prevent latent execution against development DBs.
    """
    url_local = os.getenv("DATABASE_URL_LOCAL")
    url_test = os.getenv("TEST_DATABASE_URL")

    # If either variable is set, validate it immediately at session start
    if url_local:
        validate_test_database_target(url_local)
    if url_test:
        validate_test_database_target(url_test)


# Intercept create_async_engine at the module level in tests for defense-in-depth
_orig_create_async_engine = sa_async.create_async_engine


def _guarded_create_async_engine(url, *args, **kwargs):
    # Enforce database target validation before opening any async engine in tests
    validate_test_database_target(str(url))
    return _orig_create_async_engine(url, *args, **kwargs)


sa_async.create_async_engine = _guarded_create_async_engine

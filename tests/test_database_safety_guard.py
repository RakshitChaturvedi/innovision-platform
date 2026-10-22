"""
Unit tests for the centralized test database safety guard (Stage 1 Corrections).
Validates that:
1. Unsafe databases, platform databases, and missing configurations are strictly rejected.
2. Unapproved remote hostnames and IP addresses are rejected by default (DEF-03).
3. Both DATABASE_URL_LOCAL and TEST_DATABASE_URL are validated consistently (DEF-02).
4. Conflicting unsafe environment variables fail closed (DEF-02).
5. All ten test suites cannot fall back to innovision_platform (DEF-01).
6. Engine creation is guarded against operational database targets.
"""
import sys
from pathlib import Path
import pytest
import sqlalchemy.ext.asyncio as sa_async

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

REPO_ROOT = TESTS_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from conftest import validate_test_database_target, get_safe_test_db_url


def test_rejects_empty_or_none_db_url():
    """Confirms no silent fallback: empty or None URL must raise RuntimeError."""
    with pytest.raises(RuntimeError, match="No test database URL provided.*Silent fallback.*is strictly prohibited"):
        validate_test_database_target(None)

    with pytest.raises(RuntimeError, match="No test database URL provided.*Silent fallback.*is strictly prohibited"):
        validate_test_database_target("")

    with pytest.raises(RuntimeError, match="No test database URL provided.*Silent fallback.*is strictly prohibited"):
        validate_test_database_target("   ")


def test_rejects_operational_platform_database_5432():
    """Confirms that innovision_platform on port 5432 is strictly blocked."""
    unsafe_url = "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform"
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION.*operational database 'innovision_platform'"):
        validate_test_database_target(unsafe_url)


def test_rejects_operational_platform_database_5433():
    """Confirms that innovision_platform on port 5433 is strictly blocked."""
    unsafe_url = "postgresql+asyncpg://innovision:changeme@localhost:5433/innovision_platform"
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION.*operational database 'innovision_platform'"):
        validate_test_database_target(unsafe_url)


def test_rejects_postgres_default_database():
    """Confirms that default maintenance DB 'postgres' is strictly blocked."""
    unsafe_url = "postgresql+asyncpg://innovision:changeme@localhost:5432/postgres"
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION.*operational database 'postgres'"):
        validate_test_database_target(unsafe_url)


def test_rejects_non_test_database_name():
    """Confirms that arbitrary database names without _test or test_ are blocked."""
    unsafe_url = "postgresql+asyncpg://innovision:changeme@localhost:5432/custom_database"
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION.*must end with '_test'.*or start with 'test_'"):
        validate_test_database_target(unsafe_url)


def test_rejects_unapproved_remote_ip_and_hostname_by_default(monkeypatch):
    """Confirms DEF-03: all unapproved remote hosts and IP addresses are rejected by default."""
    monkeypatch.delenv("INNOVISION_ALLOW_REMOTE_TEST_HOST", raising=False)

    ip_url = "postgresql+asyncpg://innovision:changeme@192.168.1.100:5432/my_test"
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION.*Unapproved remote or non-local database host '192.168.1.100'"):
        validate_test_database_target(ip_url)

    host_url = "postgresql+asyncpg://innovision:changeme@db.internal.net:5432/my_test"
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION.*Unapproved remote or non-local database host 'db.internal.net'"):
        validate_test_database_target(host_url)


def test_remote_opt_in_allows_safe_remote_host(monkeypatch):
    """Confirms DEF-03: INNOVISION_ALLOW_REMOTE_TEST_HOST=1 allows unapproved hosts if DB name is valid."""
    monkeypatch.setenv("INNOVISION_ALLOW_REMOTE_TEST_HOST", "1")
    remote_url = "postgresql+asyncpg://innovision:changeme@10.0.0.5:5432/innovision_platform_test"
    result = validate_test_database_target(remote_url)
    assert result == remote_url


def test_remote_opt_in_still_rejects_operational_database(monkeypatch):
    """Confirms operational databases are strictly blocked even with remote host opt-in."""
    monkeypatch.setenv("INNOVISION_ALLOW_REMOTE_TEST_HOST", "1")
    unsafe_remote = "postgresql+asyncpg://innovision:changeme@10.0.0.5:5432/innovision_platform"
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION.*operational database 'innovision_platform'"):
        validate_test_database_target(unsafe_remote)


def test_remote_opt_in_still_rejects_production_keywords(monkeypatch):
    """Confirms production keyword hosts are blocked even with remote opt-in."""
    monkeypatch.setenv("INNOVISION_ALLOW_REMOTE_TEST_HOST", "1")
    aws_url = "postgresql+asyncpg://innovision:changeme@prod-db.aws.com:5432/my_test"
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION.*Refusing connection to potential production host"):
        validate_test_database_target(aws_url)


def test_accepts_valid_dedicated_test_database_localhost():
    """Confirms valid dedicated test database on localhost is accepted."""
    valid_url = "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform_test"
    result = validate_test_database_target(valid_url)
    assert result == valid_url


def test_accepts_valid_dedicated_test_database_docker_host():
    """Confirms valid dedicated test database on docker network host 'postgres' is accepted."""
    valid_url = "postgresql+asyncpg://innovision:changeme@postgres:5432/innovision_platform_test"
    result = validate_test_database_target(valid_url)
    assert result == valid_url


def test_get_safe_test_db_url_with_test_database_url_only(monkeypatch):
    """Confirms DEF-02: TEST_DATABASE_URL is supported consistently when DATABASE_URL_LOCAL is unset."""
    monkeypatch.delenv("DATABASE_URL_LOCAL", raising=False)
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform_test")
    assert get_safe_test_db_url() == "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform_test"


def test_get_safe_test_db_url_conflicting_unsafe_fails_closed(monkeypatch):
    """Confirms DEF-02: If both variables are set and either is unsafe, validation fails closed."""
    # Case 1: DATABASE_URL_LOCAL is unsafe, TEST_DATABASE_URL is safe
    monkeypatch.setenv("DATABASE_URL_LOCAL", "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform_test")
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION.*operational database 'innovision_platform'"):
        get_safe_test_db_url()

    # Case 2: DATABASE_URL_LOCAL is safe, TEST_DATABASE_URL is unsafe
    monkeypatch.setenv("DATABASE_URL_LOCAL", "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform_test")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform")
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION.*operational database 'innovision_platform'"):
        get_safe_test_db_url()


def test_guarded_create_async_engine_intercepts_operational_target():
    """Confirms create_async_engine is guarded and immediately rejects operational targets."""
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION.*operational database 'innovision_platform'"):
        sa_async.create_async_engine("postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform")


def test_no_test_file_contains_hardcoded_innovision_platform_fallback():
    """Confirms DEF-01: static verification that zero test files contain fallback to innovision_platform."""
    test_files = list(TESTS_DIR.glob("**/*.py"))
    offenders = []
    for tf in test_files:
        if tf.name in ("conftest.py", "test_database_safety_guard.py"):
            continue
        content = tf.read_text(encoding="utf-8")
        if "innovision_platform" in content:
            offenders.append(str(tf.relative_to(REPO_ROOT)))

    assert offenders == [], f"Found test files with unpatched innovision_platform: {offenders}"

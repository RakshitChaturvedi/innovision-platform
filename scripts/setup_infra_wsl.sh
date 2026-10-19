#!/usr/bin/env bash
# setup_infra.sh — Install, configure, and start PostgreSQL + Redis in WSL.
# Creates innovision_platform database with user innovision/changeme,
# then runs Alembic migrations. Designed to be idempotent.

set -e

echo "===== [1] Installing PostgreSQL & Redis ====="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq postgresql redis-server curl lsof

echo "===== [2] Configuring PostgreSQL ====="
# Start PostgreSQL (pg 16 in Ubuntu 24.04)
service postgresql start

# Allow sufficient startup time
sleep 3

# Create user and database (idempotent)
su -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='innovision'\" | grep -q 1 || createuser -s innovision" postgres 2>/dev/null || true
su -c "psql -c \"ALTER USER innovision WITH PASSWORD 'changeme'\"" postgres
su -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname='innovision_platform'\" | grep -q 1 || createdb -O innovision innovision_platform" postgres 2>/dev/null || true

echo "===== [3] Configuring PostgreSQL port (5433) ====="
# Tests and docker-compose.yml map postgres to port 5433
PGCONF="/etc/postgresql/16/main/postgresql.conf"
if [ -f "$PGCONF" ]; then
    sed -i "s/^#\?port = .*/port = 5433/" "$PGCONF"
    service postgresql restart
    sleep 3
fi

echo "===== [4] Starting Redis on default port 6379 ====="
service redis-server start || redis-server --daemonize yes --port 6379
sleep 2

echo "===== [5] Health Verification ====="
# Verify PostgreSQL
su -c "psql -p 5433 -U innovision -d innovision_platform -c 'SELECT 1'" postgres && echo "PostgreSQL OK at port 5433" || echo "ERROR: PostgreSQL not responding"

# Verify Redis
redis-cli -p 6379 ping && echo "Redis OK at port 6379" || echo "ERROR: Redis not responding"

echo "===== [6] Running Alembic Migrations ====="
# Convert Windows path to WSL path
cd /mnt/c/Users/Sai\ Charan/Desktop/innovision-platform
export DATABASE_URL="postgresql+asyncpg://innovision:changeme@localhost:5433/innovision_platform"
export DATABASE_URL_LOCAL="postgresql+asyncpg://innovision:changeme@localhost:5433/innovision_platform"

# Use system python3 or find the local python
PYTHON=$(which python3)
echo "Using Python: $PYTHON ($($PYTHON --version))"

$PYTHON -m pip install --quiet alembic asyncpg python-dotenv sqlalchemy 2>/dev/null || true
DATABASE_URL_LOCAL="postgresql+asyncpg://innovision:changeme@localhost:5433/innovision_platform" $PYTHON -m alembic -c migrations/alembic.ini upgrade head

echo ""
echo "===== [7] Infrastructure READY ====="
echo "PostgreSQL: localhost:5433 (user: innovision, db: innovision_platform)"
echo "Redis:      localhost:6379"
echo "All Alembic migrations applied."

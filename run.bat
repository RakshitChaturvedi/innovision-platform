@echo off
REM ========================================================
REM   Innovision Platform + UC2 + UC3/PART One-Click Runner
REM ========================================================

echo [1/3] Checking environment configuration...
if not exist .env (
    echo [INFO] .env not found. Copying .env.example to .env...
    copy .env.example .env
)

echo [2/3] Verifying Docker installation...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not installed or not in PATH! Please install Docker Desktop and start it.
    pause
    exit /b 1
)

echo [3/3] Starting complete Innovision Platform in Docker...
docker compose up -d --build

echo.
echo ========================================================
echo   Innovision Platform Successfully Started!
echo ========================================================
echo   Dashboard UI:       http://localhost:3000
echo   Detection Module:   http://localhost:3000/detection
echo   UC1 Worker Count:   http://localhost:8021
echo   UC2 Fire/Smoke/Sparks: http://localhost:8030/health
echo   UC3/PART PPE Safety:   http://localhost:8031/health
echo   Camera Ingestion:   http://localhost:8020
echo   Alert Management:   http://localhost:8010/docs
echo   Camera Registry:    http://localhost:8011/docs
echo   Auth Service:       http://localhost:8000/docs
echo   MinIO Console:      http://localhost:9001 (User: minioadmin / Pass: changeme)
echo   Grafana Dashboard:  http://localhost:3001 (Pass: changeme)
echo   Prometheus:         http://localhost:9090
echo ========================================================
echo   Default Admin: admin@innovision.com
echo ========================================================
pause

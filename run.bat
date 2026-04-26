@echo off
setlocal

:: Resolve paths
set SCRIPT_DIR=%~dp0
if exist "%SCRIPT_DIR%backend\app\main.py" (
    set APP_BASE=%SCRIPT_DIR%backend
) else (
    set APP_BASE=%SCRIPT_DIR%
)

:: Activate virtualenv
if exist "%SCRIPT_DIR%venv\Scripts\activate.bat" (
    call "%SCRIPT_DIR%venv\Scripts\activate.bat"
    echo Activated virtualenv from %SCRIPT_DIR%venv
) else if exist "%SCRIPT_DIR%..\venv\Scripts\activate.bat" (
    call "%SCRIPT_DIR%..\venv\Scripts\activate.bat"
    echo Activated virtualenv from parent
)

:: Move to root for migrations
cd /d "%SCRIPT_DIR%"

:: Run migrations
echo Running database migrations...
alembic upgrade head
if %ERRORLEVEL% neq 0 (
    echo Migrations failed. Note: Ensure PostgreSQL is running.
    exit /b %ERRORLEVEL%
)

:: Move to backend for uvicorn
if exist "%SCRIPT_DIR%backend" (
    cd /d "%SCRIPT_DIR%backend"
)

:: Start server
if "%1"=="--dev" (
    echo Starting in DEVELOPMENT mode...
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug
) else (
    echo Starting in PRODUCTION mode...
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --log-level info
)

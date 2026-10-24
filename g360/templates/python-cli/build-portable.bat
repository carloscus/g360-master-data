@echo off
chcp 65001 >nul
title G360 - Portable CLI Launcher

echo.
echo ==============================================
echo   G360 CLI - Portable Version
echo   (Requires Python + uv installed)
echo ==============================================
echo.

where uv >nul 2>&1
if errorlevel 1 (
    echo [SETUP] uv no encontrado
    echo.
    echo Por favor instala uv desde:
    echo https://github.com/astral-sh/uv
    echo.
    pause
    exit /b 1
)

echo [CHECK] uv: OK

if not exist ".venv" (
    echo [SETUP] Creando entorno virtual...
    uv venv
)

echo [SETUP] Sincronizando dependencias...
uv sync

if not exist "src\main.py" (
    echo ERROR: src\main.py no encontrado
    pause
    exit /b 1
)

echo.
echo [RUN] Ejecutando G360 CLI...
uv run python src\main.py %*

pause
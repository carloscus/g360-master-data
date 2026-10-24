@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ========================================
echo    G360 Flet Migration App
echo    powered by G360
echo ========================================
echo.

REM uv run detecta/instala Python y dependencias automaticamente
uv run python src/main.py

if errorlevel 1 (
    echo.
    echo ERROR: La aplicacion fallo.
    echo Verifique que uv este instalado: https://docs.astral.sh/uv/
    pause
)

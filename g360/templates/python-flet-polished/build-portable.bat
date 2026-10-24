@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo === G360 - Build Portable ===
echo.

REM Verificar uv
where uv >nul 2>&1
if errorlevel 1 (
    echo Instalando uv...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
)

REM Build standalone con PyInstaller
echo [BUILD] Generando ejecutable standalone...
uv run pyinstaller ^
    --onefile ^
    --windowed ^
    --name "G360-App" ^
    --icon assets\images\cipsa.ico ^
    --add-data "assets;assets" ^
    --add-data "src;src" ^
    --add-data "g360_flet;g360_flet" ^
    --collect-all flet ^
    main.py

if errorlevel 1 (
    echo.
    echo ERROR: Fallo el build.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   BUILD EXITOSO
echo   Ejecutable en: dist\G360-App.exe
echo ========================================
echo.
pause

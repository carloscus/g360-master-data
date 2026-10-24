@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ========================================
echo    G360 - Build Windows App
echo    Genera ejecutable standalone
echo ========================================
echo.

REM Verificar uv
where uv >nul 2>&1
if errorlevel 1 (
    echo Instalando uv...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
)

REM Build con flet (maneja dependencias automaticamente)
echo [BUILD] Generando ejecutable...
uv run flet build windows --name "G360-App" --icon assets/images/app.ico

if errorlevel 1 (
    echo.
    echo ERROR: Fallo la generacion del ejecutable.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   BUILD EXITOSO
echo   Ejecutable en: build/windows/
echo ========================================
echo.
pause

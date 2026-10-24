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

REM Verificar dependencias
uv sync --extra build

REM Build con PyInstaller
echo [BUILD] Generando ejecutable...
uv run pyinstaller --onefile --windowed ^
    --name "G360-App" ^
    --add-data "src/core;core" ^
    --icon "assets/images/app.ico" ^
    --distpath "dist" ^
    --workpath "build" ^
    --specpath "build" ^
    --noconfirm ^
    src/main.py

if errorlevel 1 (
    echo.
    echo ERROR: Fallo la generacion del ejecutable.
    pause
    exit /b 1
)

REM Limpiar temporales
if exist "build" rmdir /s /q build

echo.
echo ========================================
echo   BUILD EXITOSO
echo   Ejecutable: dist/G360-App.exe
echo ========================================
echo.
pause

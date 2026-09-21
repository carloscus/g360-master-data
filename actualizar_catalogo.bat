@echo off
setlocal enabledelayedexpansion
REM G360 Master Data - Workflow de generacion
REM Autor: CCUSI | v3.1.0
REM
REM Uso:
REM   actualizar_catalogo.bat              Modo interactivo (menu)
REM   actualizar_catalogo.bat --auto       Genera + sube sin preguntar
REM   actualizar_catalogo.bat --auto-local Genera + copia local, sin subir
REM
REM Variables de entorno opcionales:
REM   API_KEY   Clave administrativa del API (requerida para upload)
REM   API_URL   URL del API (default: https://g360-stock-api.onrender.com)

set "AUTO_MODE=0"
set "UPLOAD_MODE=0"

if "%~1"=="--auto" (
    set "AUTO_MODE=1"
    set "UPLOAD_MODE=1"
    goto bat1
)
if "%~1"=="--auto-local" (
    set "AUTO_MODE=1"
    set "UPLOAD_MODE=0"
    goto bat1
)

echo.
echo ==========================================
echo G360 MASTER DATA - WORKFLOW v3.1.0
echo ==========================================
echo.
echo  1) Generar catalogo base (PRODUCTOS.xls + SKU_BX)
echo  2) Ver estado del catalogo
echo  0) Salir
echo.
echo  Modo automatico: actualizar_catalogo.bat --auto
echo.

set /p choice="Seleccione opcion: "

if "%choice%"=="1" goto bat1
if "%choice%"=="2" goto bat3
if "%choice%"=="0" exit /b 0
goto :eof

:bat1
echo.
echo ==========================================
echo GENERAR CATALOGO BASE
echo ==========================================
echo.

if not exist .venv\Scripts\python.exe (
    echo ERROR: Entorno virtual no encontrado
    echo Ejecute: uv venv
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

call :ensure_deps

if not exist data\PRODUCTOS.xls (
    echo ERROR: data/PRODUCTOS.xls no encontrado
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

if not exist data\SKU_BX.xlsx (
    echo ERROR: data/SKU_BX.xlsx no encontrado
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo Generando catalogo...
.venv\Scripts\python.exe scripts/generar_catalogo_base.py

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Fallo al generar catalogo
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo.
echo Copiando a proyectos G360...
if exist ..\g360-stock-api\data (
    copy /Y output\catalogo_productos.json ..\g360-stock-api\data\catalog_cache.json >nul
    if !ERRORLEVEL! EQU 0 (
        echo   OK: g360-stock-api catalog_cache.json
    ) else (
        echo   WARN: No se pudo copiar a g360-stock-api
    )
) else (
    echo   SKIP: g360-stock-api no encontrado
)

REM Upload: automatico (--auto) o interactivo
if "%AUTO_MODE%"=="1" (
    if "%UPLOAD_MODE%"=="1" (
        goto do_upload
    ) else (
        echo.
        echo Modo auto-local: sin upload al API
        goto done
    )
)

echo.
echo ==========================================
echo SUBIR AL API
echo ==========================================
echo.
set /p upload="Subir catalogo al API? (s/n): "
if /i "%upload%"=="s" goto do_upload
goto done

:do_upload
if not defined API_KEY (
    echo ERROR: Variable API_KEY no definida
    if "%AUTO_MODE%"=="0" (
        echo Defina: set API_KEY=su_clave_aqui
        pause
    )
    exit /b 1
)
if not defined API_URL set API_URL=https://g360-stock-api.onrender.com
echo.
echo Subiendo a %API_URL%/api/v1/catalog/upload ...
call :upload_with_retry
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Upload fallo despues de %MAX_RETRIES% intentos
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)
echo Upload OK

:done
echo.
echo ==========================================
echo COMPLETADO
echo ==========================================
if "%AUTO_MODE%"=="0" pause
exit /b 0

:bat3
echo.
echo ==========================================
echo ESTADO DEL CATALOGO
echo ==========================================
echo.
if exist output\catalogo_productos.json (
    .venv\Scripts\python.exe scripts\ver_estado.py
) else (
    echo No hay catalogo generado
)
echo.
if "%AUTO_MODE%"=="0" pause
exit /b 0

:: ----------------------------------------------------------------------------
:: Upload con reintentos (cold start de Render free-tier)
:upload_with_retry
set "MAX_RETRIES=3"
set "RETRY_DELAY=15"
for /l %%i in (1,1,%MAX_RETRIES%) do (
    echo   Intento %%i/%MAX_RETRIES%...
    curl -s --max-time 60 -X POST "%API_URL%/api/v1/catalog/upload" -H "X-API-Key: %API_KEY%" -F "archivo=@output/catalogo_productos.json"
    echo.
    if !ERRORLEVEL! EQU 0 (
        echo   Upload exitoso en intento %%i
        exit /b 0
    )
    if %%i LSS %MAX_RETRIES% (
        echo   Fallo, reintentando en %RETRY_DELAY%s...
        timeout /t %RETRY_DELAY% /nobreak >nul
    )
)
exit /b 1

:: ----------------------------------------------------------------------------
:: Auto-instala dependencias minimas si faltan en .venv
:ensure_deps
.venv\Scripts\python.exe -c "import openpyxl, xlrd" >nul 2>&1
if not errorlevel 1 exit /b 0
echo Instalando dependencias (openpyxl + xlrd) en .venv ...
uv pip install --python .venv openpyxl xlrd >nul 2>&1
if errorlevel 1 (
    echo ERROR: pip install openpyxl xlrd
    echo Instale manualmente: uv pip install --python .venv openpyxl xlrd
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)
exit /b 0

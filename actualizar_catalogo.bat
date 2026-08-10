@echo off
REM G360 Master Data - Workflow de generación
REM Autor: CCUSI | v3.0.0
REM
REM BAT 1: generar_catalogo_base
REM   Lee PRODUCTOS.xls + SKU_BX.xlsx
REM   Genera output/catalogo_productos.json
REM   Copia a proyectos G360
REM
REM BAT 2: generar_catalogo_enrich (ejecutar cuando haya descuentos/precios_fijos nuevos)
REM   Lee output/catalogo_productos.json + CSVs opcionales
REM   Genera output/catalogo_completo.json
REM   Sube al API de Render

echo.
echo ==========================================
echo G360 MASTER DATA - WORKFLOW
echo ==========================================
echo.
echo  1) Generar catalogo base (PRODUCTOS.xls + SKU_BX)
echo  2) Generar catalogo enriquecido (descuentos/precios)
echo  3) Ver estado del catalogo
echo  0) Salir
echo.

set /p choice="Seleccione opcion: "

if "%choice%"=="1" goto bat1
if "%choice%"=="2" goto bat2
if "%choice%"=="3" goto bat3
if "%choice%"=="0" exit /b 0
goto :eof

:bat1
echo.
echo ==========================================
echo BAT 1: GENERAR CATALOGO BASE
echo ==========================================
echo.

if not exist .venv\Scripts\python.exe (
    echo ERROR: Entorno virtual no encontrado
    echo Ejecute: uv venv
    pause
    exit /b 1
)

call :ensure_deps

if not exist data\PRODUCTOS.xls (
    echo ERROR: data/PRODUCTOS.xls no encontrado
    pause
    exit /b 1
)

echo Generando catalogo...
.venv\Scripts\python.exe scripts/generar_catalogo_base.py

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Fallo al generar catalogo
    pause
    exit /b 1
)

echo.
echo Copiando a proyectos G360...
if exist ..\g360-stock-api\data (
    copy /Y output\catalogo_productos.json ..\g360-stock-api\data\catalog_cache.json >nul
    echo   OK: g360-stock-api (catalog_cache.json)
)

echo.
echo ==========================================
echo SUBIR AL API (Render)
echo ==========================================
echo.
set /p upload="Subir catalogo al API? (s/n): "
if "%upload%"=="s" (
    if not defined API_URL set API_URL=https://g360-stock-api.onrender.com
    echo Uploading to %API_URL%/api/v1/catalog/upload ...
    curl -s -X POST "%API_URL%/api/v1/catalog/upload" -F "archivo=@output/catalogo_productos.json"
    echo.
)

echo.
pause
goto :eof

:bat2
echo.
echo ==========================================
echo BAT 2: GENERAR CATALOGO ENRIQUECIDO
echo ==========================================
echo.
echo (En desarrollo - proxima version)
pause
goto :eof

:bat3
echo.
echo ==========================================
echo ESTADO DEL CATALOGO
echo ==========================================
echo.
if exist output\catalogo_productos.json (
    for %%f in (output\catalogo_productos.json) do (
        echo Archivo: output\catalogo_productos.json
        echo Tamano: %%~zf bytes
    )
    .venv\Scripts\python.exe -c "import json; d=json.load(open('output/catalogo_productos.json',encoding='utf-8')); m=d['metadata']; print(f'Productos: {m[\"total_productos\"]}'); print(f'Generado: {m[\"generated_at\"]}'); e=m['estadisticas']; print(f'Con ean14: {e[\"con_ean14\"]}'); print(f'Con un_bx: {e[\"con_unbx\"]}')"
) else (
    echo No hay catalogo generado
)
echo.
pause
goto :eof

:: ----------------------------------------------------------------------------
:: Auto-instala dependencias minimas si faltan en .venv (evita "ERROR: pip install xlrd")
:ensure_deps
.venv\Scripts\python.exe -c "import openpyxl, xlrd" >nul 2>&1
if not errorlevel 1 exit /b 0
echo Instalando dependencias (openpyxl + xlrd) en .venv ...
uv pip install --python .venv openpyxl xlrd >nul 2>&1
if errorlevel 1 (
    echo ERROR: pip install openpyxl xlrd
    echo Instale manualmente: uv pip install --python .venv openpyxl xlrd
    pause
    exit /b 1
)
exit /b 0

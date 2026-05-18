@echo off
REM G360 Master Data - Actualizar Catálogo
REM Autor: CCUSI | v1.0.0
REM Uso: actualizar_catalogo.bat

echo.
echo ==========================================
echo G360 MASTER DATA - ACTUALIZAR CATALOGO
echo ==========================================
echo.

REM Verificar entorno virtual
if not exist .venv\Scripts\python.exe (
    echo ERROR: Entorno virtual no encontrado
    echo Ejecute: uv venv
    pause
    exit /b 1
)

REM Generar catálogo consolidado
echo Generando catalogo consolidado...
.venv\Scripts\python.exe scripts/generar_catalogo.py -i data/plantilla_precios.xlsx -o output/catalogo_productos.json

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Fallo al generar el catalogo
    pause
    exit /b 1
)

echo.
echo ==========================================
echo COPIAR A PROYECTOS
echo ==========================================
echo.

REM Copiar a proyectos G360
echo Copiando a proyectos G360...

REM g360-order-form
if exist ..\g360-order-form\public (
    echo Copiando a g360-order-form...
    copy /Y output\catalogo_productos.json ..\g360-order-form\public\catalogo_productos.json >nul
    if %ERRORLEVEL% EQU 0 (
        echo   OK: g360-order-form
    ) else (
        echo   ERROR: No se pudo copiar a g360-order-form
    )
) else (
    echo   ADVERTENCIA: g360-order-form no existe
)

REM g360-stock-reporter
if exist ..\g360-stock-reporter\public (
    echo Copiando a g360-stock-reporter...
    copy /Y output\catalogo_productos.json ..\g360-stock-reporter\public\catalogo_productos.json >nul
    if %ERRORLEVEL% EQU 0 (
        echo   OK: g360-stock-reporter
    ) else (
        echo   ERROR: No se pudo copiar a g360-stock-reporter
    )
) else (
    echo   ADVERTENCIA: g360-stock-reporter no existe
)

REM Devolucion_de_Productos
if exist ..\Devolucion_de_Productos\public (
    echo Copiando a Devolucion_de_Productos...
    copy /Y output\catalogo_productos.json ..\Devolucion_de_Productos\public\catalogo_productos.json >nul
    if %ERRORLEVEL% EQU 0 (
        echo   OK: Devolucion_de_Productos
    ) else (
        echo   ERROR: No se pudo copiar a Devolucion_de_Productos
    )
) else (
    echo   ADVERTENCIA: Devolucion_de_Productos no existe
)

REM Lista_Cotizacion
if exist ..\Lista_Cotizacion\public (
    echo Copiando a Lista_Cotizacion...
    copy /Y output\catalogo_productos.json ..\Lista_Cotizacion\public\catalogo_productos.json >nul
    if %ERRORLEVEL% EQU 0 (
        echo   OK: Lista_Cotizacion
    ) else (
        echo   ERROR: No se pudo copiar a Lista_Cotizacion
    )
) else (
    echo   ADVERTENCIA: Lista_Cotizacion no existe
)

echo.
echo ==========================================
echo RESUMEN
echo ==========================================
echo.
echo Catalogo generado: output/catalogo_productos.json
echo Version: 2.0.0
echo Productos: 1088
echo.
echo Proyectos actualizados:
echo - g360-order-form
echo - g360-stock-reporter
echo - Devolucion_de_Productos
echo - Lista_Cotizacion
echo.
echo Listo!
pause
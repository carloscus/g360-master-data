@echo off
setlocal enabledelayedexpansion
REM G360 Master Data - Workflow de generacion
REM Autor: CCUSI | v3.7.0
REM
REM Uso:
REM   actualizar_catalogo.bat              Modo interactivo (menu)
REM   actualizar_catalogo.bat --auto       Genera + sube sin preguntar
REM   actualizar_catalogo.bat --auto-local Genera + copia local, sin subir
REM   actualizar_catalogo.bat --upload     Sube el JSON existente sin regenerar
REM
REM Variables de entorno opcionales:
REM   API_KEY   Clave administrativa del API (requerida para upload y para el
REM             universo de stock: el API acepta la misma clave para leer)
REM   API_URL   URL del API (default: https://g360-stock-api.onrender.com)
REM   G360_S1_CACHE  JSON local del reporte S1 (modo offline: no consulta el
REM             API ni necesita clave para generar; el upload sigue necesitandola)
REM
REM El universo de stock (SKUs con stock o compromiso) se consulta en el mismo
REM API, endpoint compacto /api/v1/stock/skus: sin el, el catalogo sale
REM incompleto y no se nota. Por eso la clave se pide ANTES de generar.
REM
REM v3.6.0: el catalogo publica los flags de negocio (categoria_venta, en_guia,
REM compromiso, cotizable, por_activar, vigente, derivado_de) y la regla de
REM inclusion es: guia OR stock OR compromiso OR (vigente AND precio > 0).
REM
REM v3.7.0: paso 0 de contrato de encabezados (scripts/validar_encabezados.py):
REM las fuentes se leen por NOMBRE de columna y una fuente rota frena todo.
REM El catalogo agrega las dimensiones de caja y el m3 (plantillas/).

set "AUTO_MODE=0"
set "UPLOAD_MODE=0"
set "PYTHONIOENCODING=utf-8"

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
if "%~1"=="--upload" (
    set "AUTO_MODE=1"
    goto upload_only
)

:menu
echo.
echo ==========================================
echo G360 MASTER DATA - WORKFLOW v3.7.0
echo ==========================================
echo.
echo  1) Generar catalogo base (PRODUCTOS.xls + SKU_BX + universo de stock)
echo  2) Ver estado del catalogo
echo  0) Salir
echo.
echo  Modo automatico: actualizar_catalogo.bat --auto
echo.

set /p choice="Seleccione opcion: "
set "choice=%choice: =%"

if "%choice%"=="1" goto bat1
if "%choice%"=="2" goto estado
if "%choice%"=="0" exit /b 0
echo.
echo Opcion invalida: "%choice%"
pause
goto menu

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

REM La clave hace falta para el universo de stock (generacion) y para el
REM upload. En modo interactivo se pide aqui, antes de generar. Con
REM G360_S1_CACHE no hace falta para generar: el universo sale del JSON local.
if "%AUTO_MODE%"=="1" if not defined API_KEY if not defined G360_S1_CACHE (
    echo ERROR: API_KEY no esta definida.
    echo El universo de stock y la subida al API la necesitan: sin clave el
    echo catalogo sale incompleto y no lo vas a notar.
    echo Defina: set API_KEY=su_clave_aqui
    echo O genere offline: set G360_S1_CACHE=..\g360-stock-api\data\stock_cache.json
    exit /b 1
)
if "%AUTO_MODE%"=="0" (
    if not defined API_KEY if not defined G360_S1_CACHE call :pedir_clave
)
call :preparar_entorno

REM Paso 0: contrato de encabezados. Si una fuente cambio de formato (columna
REM nueva, renombrada o corrida), se corta ACA. Generar con columnas corridas
REM produce un catalogo corrupto sin un solo error.
echo.
echo Validando encabezados de las fuentes...
.venv\Scripts\python.exe scripts\validar_encabezados.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: una fuente no cumple el contrato de encabezados.
    echo Corregi el archivo o el contrato en scripts/contratos.py y reintenta.
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo Generando catalogo...
set "GEN_CMD=.venv\Scripts\python.exe scripts/generar_catalogo_base.py"
if defined G360_S1_CACHE set "GEN_CMD=%GEN_CMD% --s1-cache "%G360_S1_CACHE%""
%GEN_CMD%

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Fallo al generar catalogo
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

REM Gate: un catalogo incoherente no se sube. Las lineas nuevas de marca
REM (p.ej. una sub-marca Crayola) y la divergencia con el API de stock
REM se detectan aqui, antes de publicar.
echo.
echo Validando taxonomia...
.venv\Scripts\python.exe scripts\validar_taxonomia.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: El catalogo tiene incoherencias de taxonomia. NO se sube al API.
    echo Corregi y vuelve a generar.
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo.
echo Validando regresion (tests: el gate que detecta linea vacia y D mal
echo enlazados antes de publicar)...
.venv\Scripts\python.exe -m pytest scripts\tests -q
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: un test fallo. El catalogo recien generado rompe una regla.
    echo Revisa el fallo antes de subir: NO se copia ni se sube nada.
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
set "upload=%upload: =%"
if /i "%upload%"=="s" goto do_upload
goto done

:do_upload
call :sanitizar
if defined API_KEY goto clave_ok
if "%AUTO_MODE%"=="0" call :pedir_clave
if not defined API_KEY (
    echo ERROR: Variable API_KEY no definida o vacia
    echo Defina: set API_KEY=su_clave_aqui
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)
:clave_ok
if %KEYLEN% GEQ 1 if %KEYLEN% LSS 4 (
    echo ERROR: La clave tiene %KEYLEN% caracteres, valor incompleto o corrupto.
    echo Escribala a mano con: set API_KEY=su_clave_aqui
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)
if exist .venv\Scripts\python.exe .venv\Scripts\python.exe -c "import os;v=os.environ.get('API_KEY','');print('  Clave:',len(v),'caracteres, extremos:',repr(v[:1]+v[-1:]))"
call :preparar_entorno
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

:estado
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

:upload_only
echo.
echo ==========================================
echo SUBIR JSON EXISTENTE (sin regenerar)
echo ==========================================
echo.
if not exist output\catalogo_productos.json (
    echo ERROR: output/catalogo_productos.json no existe, genere primero con opcion 1
    exit /b 1
)
goto do_upload

:: ----------------------------------------------------------------------------
:: Prepara el entorno de generacion: el universo de stock se consulta en el
:: MISMO API que recibe el catalogo, endpoint compacto /api/v1/stock/skus.
:: Sin G360_STOCK_API_KEY el catalogo sale incompleto (se pierden los SKUs con
:: stock/compromiso que no estan en SKU_BX). La clave de lectura cae a API_KEY:
:: el API acepta la admin para leer. Con G360_S1_CACHE no se usa la red.
:preparar_entorno
if not defined API_URL set "API_URL=https://g360-stock-api.onrender.com"
if not defined G360_STOCK_URL set "G360_STOCK_URL=%API_URL%"
if not defined G360_STOCK_API_KEY if defined API_KEY set "G360_STOCK_API_KEY=%API_KEY%"
exit /b 0

:: ----------------------------------------------------------------------------
:: Upload con reintentos (cold start de Render free-tier)
:upload_with_retry
set "MAX_RETRIES=3"
set "RETRY_DELAY=15"
set /a "WAIT_N=RETRY_DELAY+1" >nul
for /l %%i in (1,1,%MAX_RETRIES%) do (
    echo   Intento %%i/%MAX_RETRIES%...
    curl -sS -f --max-time 60 -X POST "%API_URL%/api/v1/catalog/upload" -H "X-API-Key: %API_KEY%" -F "archivo=@output/catalogo_productos.json"
    echo.
    if !ERRORLEVEL! EQU 0 (
        echo   Upload exitoso en intento %%i
        exit /b 0
    )
    if %%i LSS %MAX_RETRIES% (
        echo   Fallo, reintentando en %RETRY_DELAY%s...
        ping -n %WAIT_N% 127.0.0.1 >nul
    )
)
exit /b 1

:: ----------------------------------------------------------------------------
:: Sanitiza API_KEY (quita todo whitespace incl. invisibles) y expone KEYLEN.
:: OJO: no usar for/f dentro de bloques if (...) — rompe el parser de batch.
:sanitizar
set "KEYLEN=0"
if not exist .venv\Scripts\python.exe goto sanitizar_fb
for /f "tokens=1* delims= " %%a in ('.venv\Scripts\python.exe scripts\sanitize_key.py') do (set "KEYLEN=%%a" & set "API_KEY=%%b")
exit /b 0
:sanitizar_fb
set "API_KEY=%API_KEY: =%"
set "API_KEY=%API_KEY:"=%"
exit /b 0

:: Pide la clave interactivamente y la sanitiza
:pedir_clave
echo.
echo Variable API_KEY no definida.
set /p "API_KEY=Pegue la clave del API: "
call :sanitizar
exit /b 0

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

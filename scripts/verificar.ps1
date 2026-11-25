# Un solo comando de verificacion: bootstrap (.venv + requirements.txt) +
# tests (pytest) + lint (ruff). Es el comando que declara AGENTS.md.
#
#   .\scripts\verificar.ps1
#
# Primera vez: crea .venv e instala requirements.txt (necesita red una vez).
# Cualquier otra vez: 100% offline, sin activar el venv a mano.
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$py = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Primera vez: creando .venv e instalando requirements.txt (necesita red)..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $py -m pip install --quiet -r requirements.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "== pytest (scripts/tests) =="
& $py -m pytest scripts/tests -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# == Bloque BD: generar data/catalogo.db desde output/ y verificar --check ==
# No toca output/ (ni mtime). El .db se escribe en %TEMP% y se limpia al final.
Write-Host "== BD: generar_catalogo_db.py --check =="
$dbVerify = Join-Path $env:TEMP "g360_catalogo_verify.db"
$dbTmp = Join-Path $env:TEMP "g360_catalogo_verify.db.tmp"
# Borrar artefactos residuales de una corrida anterior (kill violento pudo dejarlos)
if (Test-Path $dbVerify) { Remove-Item $dbVerify -Force -ErrorAction SilentlyContinue }
if (Test-Path $dbTmp) { Remove-Item $dbTmp -Force -ErrorAction SilentlyContinue }
& $py scripts\generar_catalogo_db.py --json output\catalogo_productos.json --db "$dbVerify" --quiet
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $py scripts\generar_catalogo_db.py --json output\catalogo_productos.json --db "$dbVerify" --check --quiet
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# Limpiar artefacto al terminar (autosuficiente: %TEMP% sin residuos)
if (Test-Path "$dbVerify") { Remove-Item "$dbVerify" -Force -ErrorAction SilentlyContinue }
if (Test-Path "$dbTmp") { Remove-Item "$dbTmp" -Force -ErrorAction SilentlyContinue }

Write-Host "== ruff (scripts) =="
& $py -m ruff check scripts
exit $LASTEXITCODE

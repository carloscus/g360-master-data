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

Write-Host "== ruff (scripts) =="
& $py -m ruff check scripts
exit $LASTEXITCODE

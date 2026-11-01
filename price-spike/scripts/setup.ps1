# Price Spike — Windows setup (adaptado de devspeed-live).
# Uso: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "==> Creando .venv en $Root"
python -m venv "$Root\.venv"
& "$Root\.venv\Scripts\python.exe" -m pip install --upgrade pip

Write-Host "==> Instalando dependencias"
& "$Root\.venv\Scripts\python.exe" -m pip install -r "$Root\requirements.txt"

$envExample = Join-Path $Root "agents\price_extractor\.env.example"
$envFile = Join-Path $Root "agents\price_extractor\.env"
if (-not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
    Write-Host "==> Copiado .env.example -> .env (pega tu GOOGLE_API_KEY)"
} else {
    Write-Host "==> .env ya existe; no se toca"
}

Write-Host "==> Opcional (P3, navegador): .\.venv\Scripts\python.exe -m playwright install chromium"
Write-Host "==> Listo. Activa con: .\.venv\Scripts\Activate.ps1"

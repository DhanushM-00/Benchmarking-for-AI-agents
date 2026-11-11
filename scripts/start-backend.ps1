# Start the Bifrost FastAPI backend on port 8000.
# Usage (from repo root):
#   .\scripts\start-backend.ps1
#   .\scripts\start-backend.ps1 -Reload

param(
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Port = 8000

Write-Host "== Bifrost backend ==" -ForegroundColor Cyan
Write-Host "Root:    $Root"
Write-Host "Backend: $Backend"
Write-Host "Port:    $Port (http://127.0.0.1:$Port)"

if (-not (Test-Path (Join-Path $Backend "app\main.py"))) {
    throw "Cannot find backend\app\main.py under $Root"
}

# Prefer project venv on Windows (.venv or .myenv)
$Python = $null
foreach ($venv in @(".venv", ".myenv", "venv")) {
    $candidate = Join-Path $Backend "$venv\Scripts\python.exe"
    if (Test-Path $candidate) { $Python = $candidate; break }
}
if (-not $Python) {
    $Python = (Get-Command python -ErrorAction SilentlyContinue)?.Source
}
if (-not $Python) {
    throw "No Python found. Create a venv: cd backend; python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt"
}
Write-Host "Python:  $Python"

# Port conflict check
$inUse = $false
try {
    $inUse = $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
} catch {
    $inUse = $null -ne (netstat -ano 2>$null | Select-String ":$Port\s")
}
if ($inUse) {
    Write-Host "WARNING: Port $Port already has a listener. If it is an older Bifrost backend, reuse it or stop it first." -ForegroundColor Yellow
}

Push-Location $Backend
try {
    $env:BIFROST_GATEWAY_URL = if ($env:BIFROST_GATEWAY_URL) { $env:BIFROST_GATEWAY_URL } else { "http://127.0.0.1:8081" }
    $args = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")
    if ($Reload) { $args += "--reload" }
    Write-Host "Starting: $Python $($args -join ' ')"
    & $Python @args
} finally {
    Pop-Location
}

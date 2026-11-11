# Start the Vite React frontend on port 5173.
# Usage (from repo root):
#   .\scripts\start-frontend.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
$Port = 5173

Write-Host "== Bifrost frontend ==" -ForegroundColor Cyan
Write-Host "Frontend: $Frontend"
Write-Host "Port:     $Port (http://127.0.0.1:$Port)"

if (-not (Test-Path (Join-Path $Frontend "package.json"))) {
    throw "Cannot find frontend\package.json under $Root"
}

$env:VITE_API_BASE_URL = if ($env:VITE_API_BASE_URL) { $env:VITE_API_BASE_URL } else { "http://127.0.0.1:8000/api/v1" }
$env:VITE_PROXY_TARGET = if ($env:VITE_PROXY_TARGET) { $env:VITE_PROXY_TARGET } else { "http://127.0.0.1:8000" }
$env:VITE_USE_MOCK = if ($env:VITE_USE_MOCK) { $env:VITE_USE_MOCK } else { "false" }

Push-Location $Frontend
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "Installing npm dependencies..."
        npm install
    }
    Write-Host "VITE_API_BASE_URL=$env:VITE_API_BASE_URL"
    npx vite --port $Port --host 127.0.0.1
} finally {
    Pop-Location
}

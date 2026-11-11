# Start the Maxim AI Bifrost gateway on port 8081 (not 8080 — often taken).
# Usage (from repo root):
#   .\scripts\start-bifrost.ps1
#
# Requires Node.js / npx. Provider keys are configured inside Bifrost, not in this script.

$ErrorActionPreference = "Stop"
$Port = 8081

Write-Host "== Maxim AI Bifrost gateway ==" -ForegroundColor Cyan
Write-Host "Port: $Port (http://127.0.0.1:$Port)"
Write-Host "Note: Port 8080 is intentionally avoided (commonly occupied)."

$inUse = $false
try {
    $inUse = $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
} catch {
    $inUse = $null -ne (netstat -ano 2>$null | Select-String ":$Port\s")
}
if ($inUse) {
    Write-Host "Port $Port already listening — assuming Bifrost is running." -ForegroundColor Yellow
    Write-Host "Health check: Invoke-WebRequest http://127.0.0.1:$Port/health"
    exit 0
}

Write-Host "Launching: npx -y @maximhq/bifrost -port $Port"
npx -y @maximhq/bifrost -port $Port

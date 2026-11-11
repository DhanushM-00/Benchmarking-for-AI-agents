# One-command Windows launcher for Bifrost Benchmark Platform.
# Starts Bifrost (8081), FastAPI backend (8000) and Vite frontend (5173)
# in separate PowerShell windows. Checks ports, waits for health, reports failures.
#
# Usage (from repo root, elevated PowerShell if needed):
#   .\scripts\start-all.ps1
#   .\scripts\start-all.ps1 -SkipBifrost   # backend + frontend only
#   .\scripts\start-all.ps1 -NoNewWindows  # run backend/frontend in this session (blocking)

param(
    [switch]$SkipBifrost,
    [switch]$NoNewWindows,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "ports.ps1")

$PidFile = Join-Path $Root ".bifrost-launcher.pids"
$LogDir = Join-Path $Root "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  !!  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  ERR $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "Bifrost Benchmark Platform — start-all" -ForegroundColor Cyan
Write-Host "Root: $Root"
Write-Host ""

# --- Already running? ---
$already = @()
if (Test-PortInUse -Port $BifrostPort) { $already += "Bifrost:$BifrostPort" }
if (Test-PortInUse -Port $BackendPort) { $already += "Backend:$BackendPort" }
if (Test-PortInUse -Port $FrontendPort) { $already += "Frontend:$FrontendPort" }
if ($already.Count -gt 0) {
    Write-Warn "Already listening: $($already -join ', ')"
    Write-Warn "Will not start duplicates for those ports. Use .\scripts\stop-all.ps1 first if needed."
}

$started = @()

# --- 1. Bifrost gateway ---
if (-not $SkipBifrost) {
    if (Test-PortInUse -Port $BifrostPort) {
        Write-Ok "Bifrost already on port $BifrostPort"
    } else {
        Write-Step "Starting Bifrost gateway on $BifrostPort"
        $bifrostCmd = "npx -y @maximhq/bifrost -port $BifrostPort"
        if ($NoNewWindows) {
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $bifrostCmd -WorkingDirectory $Root -WindowStyle Minimized
        } else {
            Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root'; Write-Host 'Bifrost gateway'; $bifrostCmd" -WindowStyle Normal
        }
        $started += "bifrost"
        Write-Host "  Waiting for Bifrost health..."
        # Bifrost may not expose a standard /health; just wait for TCP listen
        $deadline = (Get-Date).AddSeconds(45)
        $up = $false
        while ((Get-Date) -lt $deadline) {
            if (Test-PortInUse -Port $BifrostPort) { $up = $true; break }
            Start-Sleep -Milliseconds 500
        }
        if ($up) { Write-Ok "Bifrost listening on $BifrostUrl" }
        else {
            Write-Err "Bifrost did not open port $BifrostPort within 45s"
            Write-Err "Start manually: npx -y @maximhq/bifrost -port 8081"
            throw "Bifrost startup failed"
        }
    }
} else {
    Write-Warn "Skipping Bifrost (-SkipBifrost)"
}

# --- 2. Backend ---
if (Test-PortInUse -Port $BackendPort) {
    Write-Ok "Backend already on port $BackendPort"
} else {
    Write-Step "Starting FastAPI backend on $BackendPort"
    $backendScript = Join-Path $PSScriptRoot "start-backend.ps1"
    $reloadArg = if ($Reload) { "-Reload" } else { "" }
    if ($NoNewWindows) {
        Start-Process powershell -ArgumentList "-NoProfile", "-Command", "& '$backendScript' $reloadArg" -WindowStyle Minimized
    } else {
        Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-Command", "Set-Location '$Root'; & '$backendScript' $reloadArg" -WindowStyle Normal
    }
    $started += "backend"
    Write-Host "  Waiting for backend /health ..."
    $healthUrl = "$BackendUrl/health"
    if (-not (Wait-HttpOk -Url $healthUrl -TimeoutSec 40)) {
        Write-Err "Backend health check failed at $healthUrl"
        throw "Backend startup failed"
    }
    Write-Ok "Backend healthy at $BackendUrl"
}

# --- 3. Frontend ---
if (Test-PortInUse -Port $FrontendPort) {
    Write-Ok "Frontend already on port $FrontendPort"
} else {
    Write-Step "Starting Vite frontend on $FrontendPort"
    $frontendScript = Join-Path $PSScriptRoot "start-frontend.ps1"
    if ($NoNewWindows) {
        Start-Process powershell -ArgumentList "-NoProfile", "-Command", "& '$frontendScript'" -WindowStyle Minimized
    } else {
        Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-Command", "Set-Location '$Root'; & '$frontendScript'" -WindowStyle Normal
    }
    $started += "frontend"
    Write-Host "  Waiting for frontend ..."
    $deadline = (Get-Date).AddSeconds(45)
    $up = $false
    while ((Get-Date) -lt $deadline) {
        if (Test-PortInUse -Port $FrontendPort) { $up = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if ($up) { Write-Ok "Frontend listening at $FrontendUrl" }
    else {
        Write-Err "Frontend did not open port $FrontendPort"
        throw "Frontend startup failed"
    }
}

# Record what we started (for stop-all)
if ($started.Count -gt 0) {
    $started -join "," | Set-Content -Path $PidFile -Encoding ascii
}

Write-Host ""
Write-Host "All services up." -ForegroundColor Green
Write-Host "  Frontend : $FrontendUrl"
Write-Host "  Backend  : $BackendUrl  (API $ApiBase)"
Write-Host "  Bifrost  : $BifrostUrl  (internal; virtual keys never sent to browser)"
Write-Host ""
Write-Host "Status:  .\scripts\status.ps1"
Write-Host "Stop:    .\scripts\stop-all.ps1"
Write-Host ""

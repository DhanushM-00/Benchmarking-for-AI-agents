# Shared port configuration — single source of truth for Windows scripts.
# Bifrost gateway : 8081
# FastAPI backend : 8000
# Vite frontend   : 5173

$ErrorActionPreference = "Stop"

$script:BifrostPort = 8081
$script:BackendPort = 8000
$script:FrontendPort = 5173

$script:BifrostUrl = "http://127.0.0.1:$BifrostPort"
$script:BackendUrl = "http://127.0.0.1:$BackendPort"
$script:FrontendUrl = "http://127.0.0.1:$FrontendPort"
$script:ApiBase = "$BackendUrl/api/v1"

function Test-PortInUse {
    param([int]$Port)
    try {
        $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return $null -ne $c
    } catch {
        # Fallback when Get-NetTCPConnection is unavailable
        $lines = netstat -ano 2>$null | Select-String ":$Port\s"
        return $null -ne $lines
    }
}

function Assert-PortFree {
    param([int]$Port, [string]$Name)
    if (Test-PortInUse -Port $Port) {
        Write-Host "ERROR: Port $Port ($Name) is already in use." -ForegroundColor Red
        Write-Host "  Find the process:  Get-NetTCPConnection -LocalPort $Port | Select OwningProcess"
        Write-Host "  Or: netstat -ano | findstr :$Port"
        throw "Port $Port occupied"
    }
}

function Wait-HttpOk {
    param([string]$Url, [int]$TimeoutSec = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { return $true }
        } catch {
            Start-Sleep -Milliseconds 400
        }
    }
    return $false
}

Export-ModuleMember -Variable BifrostPort, BackendPort, FrontendPort, BifrostUrl, BackendUrl, FrontendUrl, ApiBase -Function Test-PortInUse, Assert-PortFree, Wait-HttpOk

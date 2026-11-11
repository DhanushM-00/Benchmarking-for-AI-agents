# Independent status check for Bifrost, backend and frontend.
# Does not start or stop anything.

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "ports.ps1")

function Port-State([int]$Port) {
    if (Test-PortInUse -Port $Port) { return "LISTEN" }
    return "closed"
}

function Http-Probe([string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return "HTTP $($r.StatusCode)"
    } catch {
        $msg = $_.Exception.Message
        if ($msg -match "actively refused|connection refused") { return "refused" }
        if ($msg -match "timed out|timeout") { return "timeout" }
        return "error"
    }
}

Write-Host ""
Write-Host "Bifrost Benchmark Platform — status" -ForegroundColor Cyan
Write-Host ("{0,-12} {1,-8} {2}" -f "Service", "Port", "Status")
Write-Host ("{0,-12} {1,-8} {2}" -f "-------", "----", "------")

$bfPort = Port-State $BifrostPort
$bfHttp = if ($bfPort -eq "LISTEN") { Http-Probe "$BifrostUrl/health" } else { "n/a" }
# Bifrost may not have /health; TCP listen is the primary signal
Write-Host ("{0,-12} {1,-8} {2} (probe: $bfHttp)" -f "Bifrost", $BifrostPort, $bfPort)

$bePort = Port-State $BackendPort
$beHttp = if ($bePort -eq "LISTEN") { Http-Probe "$BackendUrl/health" } else { "n/a" }
Write-Host ("{0,-12} {1,-8} {2} (health: $beHttp)" -f "Backend", $BackendPort, $bePort)

$fePort = Port-State $FrontendPort
$feHttp = if ($fePort -eq "LISTEN") { Http-Probe $FrontendUrl } else { "n/a" }
Write-Host ("{0,-12} {1,-8} {2} (http: $feHttp)" -f "Frontend", $FrontendPort, $fePort)

Write-Host ""
if ($bePort -eq "LISTEN" -and $beHttp -match "200") {
    try {
        $h = Invoke-RestMethod -Uri "$BackendUrl/health" -TimeoutSec 3
        Write-Host "Backend detail:"
        Write-Host "  mode     : $($h.mode)"
        Write-Host "  status   : $($h.status)"
        if ($h.bifrost) {
            Write-Host "  gateway  : $($h.bifrost.status) @ $($h.bifrost.gateway_url)"
            Write-Host "  reachable: $($h.bifrost.reachable)"
        }
    } catch {}
}
Write-Host ""

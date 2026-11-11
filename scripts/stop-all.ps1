# Stop services started by start-all.ps1 (or any listeners on the three ports).
# Only kills processes listening on Bifrost/Backend/Frontend ports — does not
# kill unrelated Python/Node processes.

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "ports.ps1")

function Stop-PortListeners {
    param([int]$Port, [string]$Name)
    $killed = 0
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            $pid = $c.OwningProcess
            if ($pid -and $pid -ne 0) {
                try {
                    $p = Get-Process -Id $pid -ErrorAction SilentlyContinue
                    if ($p) {
                        Write-Host "  Stopping $Name PID $pid ($($p.ProcessName))"
                        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                        $killed++
                    }
                } catch {}
            }
        }
    } catch {
        # Fallback: netstat
        $lines = netstat -ano 2>$null | Select-String ":$Port\s+.*LISTENING"
        foreach ($line in $lines) {
            $parts = ($line -split '\s+') | Where-Object { $_ }
            $pid = $parts[-1]
            if ($pid -match '^\d+$' -and [int]$pid -gt 0) {
                Write-Host "  Stopping $Name PID $pid"
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                $killed++
            }
        }
    }
    if ($killed -eq 0) {
        Write-Host "  $Name (port $Port): nothing listening"
    } else {
        Write-Host "  $Name (port $Port): stopped $killed process(es)" -ForegroundColor Green
    }
}

Write-Host "Stopping Bifrost Benchmark Platform services..." -ForegroundColor Cyan
Stop-PortListeners -Port $FrontendPort -Name "Frontend"
Stop-PortListeners -Port $BackendPort -Name "Backend"
Stop-PortListeners -Port $BifrostPort -Name "Bifrost"

$PidFile = Join-Path $Root ".bifrost-launcher.pids"
if (Test-Path $PidFile) { Remove-Item $PidFile -Force -ErrorAction SilentlyContinue }

Write-Host "Done." -ForegroundColor Green

<#
.SYNOPSIS
    Launches Darwin Trader Web Dashboard with automatic API Gateway lifecycle management.
.DESCRIPTION
    1. Checks if Darwinex MetaTrader 5 (terminal64.exe) is running.
    2. Checks if the FastAPI backend (api_gateway) is listening on port 8000; if not, starts it.
    3. Auto-connects to Account 4000073238 on Darwinex-Live.
    4. Launches the Vite Web server in the foreground.
    5. Cleanly terminates the background gateway process on Web exit if started by this script.
#>

param(
    [switch]$Mock = $false,
    [int]$Port = 8000,
    [int]$WebPort = 5173,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Set-Location $ProjectRoot

# 1. Verify MT5 Terminal process
$mt5Process = Get-Process terminal64 -ErrorAction SilentlyContinue
if (-not $mt5Process -and -not $Mock) {
    Write-Host "[WARNING] MetaTrader 5 (terminal64.exe) is not running!" -ForegroundColor Yellow
    Write-Host "Please launch Darwinex MetaTrader 5 to view live telemetry and positions." -ForegroundColor Yellow
    Write-Host "Continuing in 2 seconds...`n" -ForegroundColor Gray
    Start-Sleep -Seconds 2
}

# 2. Check if Gateway is already running
$gatewayUrl = "http://${HostAddress}:${Port}"
$gatewayStartedByScript = $false
$gatewayProcess = $null

$isPortOpen = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect($HostAddress, $Port)
    $isPortOpen = $true
    $tcp.Close()
} catch {
    $isPortOpen = $false
}

if (-not $isPortOpen) {
    Write-Host "[INFO] Starting Darwin Trader API Gateway on ${gatewayUrl}..." -ForegroundColor Cyan
    $gatewayProcess = Start-Process python -ArgumentList "-m uvicorn api_gateway.main:app --host $HostAddress --port $Port" -PassThru -WindowStyle Hidden
    $gatewayStartedByScript = $true

    # Wait up to 10 seconds for Gateway to become healthy
    $healthy = $false
    $timeout = 10
    $elapsed = 0
    while (-not $healthy -and $elapsed -lt $timeout) {
        Start-Sleep -Milliseconds 500
        $elapsed += 0.5
        try {
            $resp = Invoke-RestMethod -Uri "${gatewayUrl}/" -TimeoutSec 1 -ErrorAction SilentlyContinue
            if ($resp.status -eq "ONLINE") {
                $healthy = $true
            }
        } catch {}
    }

    if (-not $healthy) {
        Write-Host "[ERROR] API Gateway failed to start within $timeout seconds." -ForegroundColor Red
        if ($gatewayProcess) { Stop-Process -Id $gatewayProcess.Id -Force -ErrorAction SilentlyContinue }
        exit 1
    }
    Write-Host "[OK] API Gateway is ONLINE." -ForegroundColor Green
} else {
    Write-Host "[INFO] API Gateway is already running on ${gatewayUrl}." -ForegroundColor Green
}

# 3. Auto-connect to Darwinex-Live if not mock
if (-not $Mock) {
    try {
        $connectBody = @{
            login = 4000073238
            server = "Darwinex-Live"
            path = "C:\Program Files\Darwinex MetaTrader 5\terminal64.exe"
            mock_mode = $false
        } | ConvertTo-Json

        $connectResp = Invoke-RestMethod -Uri "${gatewayUrl}/api/v1/account/connect" -Method Post -Body $connectBody -ContentType "application/json" -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($connectResp.status -eq "CONNECTED") {
            Write-Host "[OK] Connected to Darwinex-Live (Login: 4000073238, Balance: `$$($connectResp.balance))." -ForegroundColor Green
        }
    } catch {
        Write-Host "[NOTICE] Gateway ready; auto-connect skipped (will use current state)." -ForegroundColor Gray
    }
} else {
    $env:VITE_MOCK_MODE = "true"
}

# 4. Launch Web Server in foreground
Write-Host "[INFO] Launching Darwin Trader Web Dashboard on http://localhost:${WebPort}..." -ForegroundColor Cyan
try {
    npm --prefix "$ProjectRoot\web" run web -- --port $WebPort
} finally {
    # 5. Clean teardown if gateway was spawned by this script
    if ($gatewayStartedByScript -and $gatewayProcess) {
        Write-Host "`n[INFO] Stopping background API Gateway..." -ForegroundColor Gray
        Stop-Process -Id $gatewayProcess.Id -Force -ErrorAction SilentlyContinue
    }
}

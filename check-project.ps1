$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    $Python = "python"
}

$BackendUrl = "http://127.0.0.1:8000"
$FrontendUrl = "http://127.0.0.1:5173"

$backendProcess = $null
$frontendProcess = $null
$keepServersRunning = $false

function Assert-Endpoint {
    param(
        [string]$Name,
        [string]$Url,
        [switch]$Json
    )

    Write-Host "Checking $Name ..." -ForegroundColor Cyan

    $response = Invoke-WebRequest `
        -Uri $Url `
        -UseBasicParsing `
        -TimeoutSec 10

    if ($response.StatusCode -ne 200) {
        throw "$Name returned HTTP $($response.StatusCode)"
    }

    Write-Host "  OK: HTTP $($response.StatusCode)" -ForegroundColor Green
    if ($Json) {
        return ($response.Content | ConvertFrom-Json)
    }

    return $response.Content
}

try {
    Write-Host "Repository: $Root" -ForegroundColor Yellow
    Write-Host "Python: $Python" -ForegroundColor Yellow

    Write-Host "`nRunning backend tests..." -ForegroundColor Cyan
    & $Python -m pytest backend/tests -q

    if ($LASTEXITCODE -ne 0) {
        throw "Backend tests failed."
    }

    Write-Host "`nBuilding frontend..." -ForegroundColor Cyan
    Push-Location (Join-Path $Root "frontend")
    npm run build

    if ($LASTEXITCODE -ne 0) {
        throw "Frontend build failed."
    }

    Pop-Location

    Write-Host "`nStarting FastAPI backend..." -ForegroundColor Cyan
    $backendProcess = Start-Process `
        -FilePath $Python `
        -ArgumentList "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000" `
        -WorkingDirectory $Root `
        -PassThru `
        -WindowStyle Minimized

    Write-Host "Starting Vite frontend..." -ForegroundColor Cyan
    $frontendProcess = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile", "-WindowStyle", "Hidden", "-Command", "npm run dev -- --host 127.0.0.1" `
        -WorkingDirectory (Join-Path $Root "frontend") `
        -PassThru `
        -WindowStyle Hidden

    Start-Sleep -Seconds 5

    $health = Assert-Endpoint `
        -Name "Backend health" `
        -Url "$BackendUrl/health" `
        -Json

    if ($health.status -ne "ok") {
        throw "Backend health status was not 'ok'."
    }

    $reference = Assert-Endpoint `
        -Name "Reference data" `
        -Url "$BackendUrl/reference-data" `
        -Json

    if (-not $reference.data.jsl_benchmarks) {
        throw "JSL benchmarks are missing from the reference-data bundle."
    }

    if (-not $reference.data.jsl_climate_targets) {
        throw "JSL climate targets are missing from the reference-data bundle."
    }

    $benchmarks = Assert-Endpoint `
        -Name "JSL benchmarks" `
        -Url "$BackendUrl/reference-data/jsl-benchmarks" `
        -Json

    $intensity = @(
        $benchmarks.records |
        Where-Object { $_.parameter -eq "Scope 1+2 GHG intensity" }
    )

    $fy2026 = $intensity |
        Where-Object { $_.financial_year -eq "FY2026" } |
        Select-Object -First 1

    if ($null -eq $fy2026 -or [double]$fy2026.value -ne 1.76) {
        throw "FY2026 benchmark is not 1.76 tCO2e/tcs."
    }

    $targets = Assert-Endpoint `
        -Name "JSL climate targets" `
        -Url "$BackendUrl/reference-data/jsl-climate-targets" `
        -Json

    $target = $targets.records | Select-Object -First 1

    if ([double]$target.baseline_intensity -ne 1.98) {
        throw "Target baseline is not 1.98."
    }

    if ([double]$target.target_reduction_percent -ne 50) {
        throw "Target reduction is not 50%."
    }

    if ([double]$target.derived_target_intensity -ne 0.99) {
        throw "Derived target is not 0.99."
    }

    $gap = [double]$fy2026.value - [double]$target.derived_target_intensity
    $remainingReduction = ($gap / [double]$fy2026.value) * 100

    if ([math]::Round($gap, 2) -ne 0.77) {
        throw "Absolute gap is not 0.77."
    }

    if ([math]::Round($remainingReduction, 2) -ne 43.75) {
        throw "Remaining reduction is not 43.75%."
    }

    Assert-Endpoint `
        -Name "Frontend" `
        -Url $FrontendUrl | Out-Null

    Write-Host "`nALL CHECKS PASSED" -ForegroundColor Green
    Write-Host "FY2026 actual:       1.76 tCO2e/tcs"
    Write-Host "FY2035 target:       0.99 tCO2e/tcs"
    Write-Host "Absolute gap:        0.77 tCO2e/tcs"
    Write-Host "Remaining reduction: 43.75%"
    Write-Host "`nOpen the application at: $FrontendUrl"
    Write-Host "Backend remains available at: $BackendUrl"
    Write-Host "The development servers are still running."
    Write-Host "Stop them later with:"
    Write-Host "  Stop-Process -Id $($backendProcess.Id) -Force"
    Write-Host "  Stop-Process -Id $($frontendProcess.Id) -Force"
    $keepServersRunning = $true
}
catch {
    Write-Host "`nCHECK FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    if (-not $keepServersRunning -and $backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }

    if (-not $keepServersRunning -and $frontendProcess -and -not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }

    Pop-Location -ErrorAction SilentlyContinue
}

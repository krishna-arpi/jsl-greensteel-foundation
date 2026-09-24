$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    $Python = "python"
}

$backendProcess = $null
$ownsBackend = $false

try {
    try {
        $health = Invoke-WebRequest `
            -Uri "http://127.0.0.1:8000/health" `
            -UseBasicParsing `
            -TimeoutSec 2
        if ($health.StatusCode -eq 200) {
            Write-Host "Using the existing FastAPI backend on http://127.0.0.1:8000." -ForegroundColor Green
        }
    }
    catch {
        Write-Host "Starting FastAPI backend on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
        $backendProcess = Start-Process `
            -FilePath $Python `
            -ArgumentList "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000" `
            -WorkingDirectory $Root `
            -PassThru `
            -WindowStyle Hidden
        $ownsBackend = $true

        Start-Sleep -Seconds 2

        if ($backendProcess.HasExited) {
            throw "FastAPI backend stopped unexpectedly. Check the backend configuration and dependencies."
        }
    }

    $frontendAlreadyRunning = $false
    try {
        $frontend = Invoke-WebRequest `
            -Uri "http://127.0.0.1:5173" `
            -UseBasicParsing `
            -TimeoutSec 2
        if ($frontend.StatusCode -eq 200) {
            $frontendAlreadyRunning = $true
            Write-Host "Using the existing Vite frontend on http://127.0.0.1:5173." -ForegroundColor Green
        }
    }
    catch {
        $frontendAlreadyRunning = $false
    }

    if (-not $frontendAlreadyRunning) {
        Write-Host "Starting Vite frontend on http://127.0.0.1:5173 ..." -ForegroundColor Cyan
        Push-Location (Join-Path $Root "frontend")
        npm run dev -- --host 127.0.0.1
    }
}
finally {
    Pop-Location -ErrorAction SilentlyContinue

    if ($ownsBackend -and $backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
        Write-Host "FastAPI backend stopped." -ForegroundColor DarkGray
    }
}

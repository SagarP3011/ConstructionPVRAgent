# Dev: backend on :8000 and frontend on :5173 together. Ctrl+C stops both.
# PowerShell equivalent of `make dev`.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) { throw 'backend\.venv not found. Run scripts\setup.ps1 first.' }

Write-Host 'Starting backend on http://127.0.0.1:8000 ...'
$backend = Start-Process -FilePath $venvPython -NoNewWindow -PassThru `
    -WorkingDirectory (Join-Path $root 'backend') `
    -ArgumentList '-m', 'uvicorn', 'pvr.api.main:app', '--host', '127.0.0.1', '--port', '8000', '--reload', '--reload-dir', 'pvr'

try {
    Write-Host 'Starting frontend on http://localhost:5173 ...'
    Push-Location (Join-Path $root 'frontend')
    npm run dev
} finally {
    Pop-Location
    if ($backend -and -not $backend.HasExited) {
        Write-Host 'Stopping backend...'
        # /T also stops the uvicorn reloader's worker process.
        & taskkill /PID $backend.Id /T /F | Out-Null
    }
}

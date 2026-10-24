# Test: pytest (excluding live tests) + vitest. PowerShell equivalent of `make test`.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\test.ps1 [-Live]
#   -Live  run only the live tests (needs OPENAI_API_KEY), like `make test-live`.
param([switch]$Live)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) { throw 'backend\.venv not found. Run scripts\setup.ps1 first.' }

Push-Location (Join-Path $root 'backend')
try {
    if ($Live) {
        & $venvPython -m pytest -m live
        exit $LASTEXITCODE
    }
    Write-Host '== Backend tests (pytest, not live) ==' -ForegroundColor Cyan
    & $venvPython -m pytest -m 'not live'
    $backendCode = $LASTEXITCODE
} finally { Pop-Location }

Push-Location (Join-Path $root 'frontend')
try {
    Write-Host '== Frontend typecheck (tsc) ==' -ForegroundColor Cyan
    npm run --silent typecheck
    $typeCode = $LASTEXITCODE
    Write-Host '== Frontend tests (vitest) ==' -ForegroundColor Cyan
    npm run --silent test
    $frontendCode = $LASTEXITCODE
} finally { Pop-Location }

if ($backendCode -ne 0 -or $typeCode -ne 0 -or $frontendCode -ne 0) {
    Write-Host "FAILED (pytest=$backendCode, tsc=$typeCode, vitest=$frontendCode)" -ForegroundColor Red
    exit 1
}
Write-Host 'All tests passed.' -ForegroundColor Green

# Setup: backend virtual environment + dependencies, frontend npm install.
# PowerShell equivalent of `make setup`.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root 'backend\.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'

function Find-Python {
    # Prefer a mature version through the py launcher; very new releases may lack wheels.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in '3.12', '3.13', '3.11', '3.14') {
            & py "-$v" -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) { return @('py', "-$v") }
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
        if ($LASTEXITCODE -eq 0) { return @('python') }
    }
    throw 'Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/'
}

if (-not (Test-Path $venvPython)) {
    $py = Find-Python
    Write-Host "Creating backend\.venv with: $($py -join ' ')"
    $pyArgs = @($py | Select-Object -Skip 1) + @('-m', 'venv', $venv)
    & $py[0] @pyArgs
    if ($LASTEXITCODE -ne 0) { throw 'Creating the virtual environment failed.' }
}

Write-Host 'Installing backend dependencies...'
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -e "$root\backend[dev]"
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency install failed.' }

Write-Host 'Installing frontend dependencies...'
Push-Location (Join-Path $root 'frontend')
try {
    if (Test-Path 'package-lock.json') { npm ci } else { npm install }
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency install failed.' }
} finally { Pop-Location }

if (-not (Test-Path (Join-Path $root '.env'))) {
    Write-Host 'No .env found. Copy .env.example to .env and fill in your values.' -ForegroundColor Yellow
}
Write-Host 'Setup complete.' -ForegroundColor Green

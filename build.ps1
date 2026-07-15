param(
    [string]$VenvPath = "C:\Users\Hanlun Fintech\Projects\venv_313"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " PyCyBase NT Build Script" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

# Activate venv
$ActivateScript = Join-Path $VenvPath "Scripts\Activate.ps1"
if (-not (Test-Path $ActivateScript)) {
    Write-Host "[ERROR] Venv not found: $VenvPath" -ForegroundColor Red
    exit 1
}

Write-Host "[venv] Activating: $VenvPath" -ForegroundColor Green
. $ActivateScript

# Verify python
$py = & python --version 2>&1
Write-Host "[python] $py" -ForegroundColor Green

# Clean build artifacts
Write-Host "[clean] Removing build artifacts..." -ForegroundColor Yellow
Push-Location $ScriptDir
try {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, "PyCyBase.egg-info", "cbase\includes"
    Write-Host "[clean] Done" -ForegroundColor Green
}
finally {
    Pop-Location
}

# Build
Write-Host "[build] Compiling Cython extensions..." -ForegroundColor Yellow
Push-Location $ScriptDir
try {
    python setup.py build_ext --inplace --verbose --force
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[build] FAILED with exit code $LASTEXITCODE" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "[build] Complete — cbase compiled in-place" -ForegroundColor Green
}
finally {
    Pop-Location
}

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " Build successful." -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

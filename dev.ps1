<#
.SYNOPSIS
    FairLend Watch developer helper. Run from the project folder.

.EXAMPLE
    .\dev.ps1                 # start the dashboard (http://localhost:8501)
    .\dev.ps1 -Present        # start the dashboard in presentation mode (demo data only)
    .\dev.ps1 -Install        # create .venv if needed and install requirements-dev.txt (app + tests + Gemini check)
    .\dev.ps1 -Rebuild        # rebuild the demo dataset, labels, scores and lender comparison
    .\dev.ps1 -Test           # run the automatic checks
    .\dev.ps1 -Preflight      # check everything is ready for a demo (PASS/FAIL per check)
    .\dev.ps1 -Install -Rebuild -Preflight -Present   # switches can be combined; they run in this order

.NOTES
    Never opens or prints .env. Nothing here uses the network except -Install (pip).
#>
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Rebuild,
    [switch]$Test,
    [switch]$Preflight,
    [switch]$Present
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Invoke-Step([string]$Title, [scriptblock]$Action) {
    Write-Host "== $Title" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        Write-Host "== $Title FAILED (exit code $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

if ($Install) {
    Invoke-Step "Install" {
        if (-not (Test-Path $python)) { py -m venv .venv }
        & $python -m pip install -r requirements-dev.txt
    }
}

if (-not (Test-Path $python)) {
    Write-Host "No virtual environment found. Run: .\dev.ps1 -Install" -ForegroundColor Yellow
    exit 1
}

if ($Rebuild)   { Invoke-Step "Rebuild the demo" { & $python -m src.build_all } }
if ($Test)      { Invoke-Step "Tests" { & $python -m pytest -q } }
if ($Preflight) { Invoke-Step "Preflight" { & $python -m src.preflight } }

$onlyChecks = ($Install -or $Rebuild -or $Test -or $Preflight) -and -not $Present
if (-not $onlyChecks) {
    $previous = $env:FAIRLEND_PRESENT
    try {
        if ($Present) {
            $env:FAIRLEND_PRESENT = "1"   # this run only
            Write-Host "== Presentation mode: demo data only; Data and Review pages are off." -ForegroundColor Yellow
        }
        Invoke-Step "Dashboard (Ctrl+C to stop)" { & $python -m streamlit run app.py }
    }
    finally {
        $env:FAIRLEND_PRESENT = $previous
    }
}

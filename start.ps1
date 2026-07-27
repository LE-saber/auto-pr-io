# auto-pr-io one-click launcher
# Usage: right-click and run with PowerShell, or execute .\start.ps1
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  auto-pr-io  |  VLM Screen Analyzer" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

function Find-CompatiblePython {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe")
    )
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $candidates += $pythonCommand.Source
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path $candidate)) { continue }
        & $candidate -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)" > $null 2>&1
        if ($LASTEXITCODE -eq 0) { return $candidate }
    }
    return $null
}

# ---------- 1. Validate or repair the virtual environment ----------
$venvPython = Join-Path $root ".venv312\Scripts\python.exe"
$venvOk = $false
if (Test-Path $venvPython) {
    & $venvPython -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)" > $null 2>&1
    $venvOk = $LASTEXITCODE -eq 0
}

if (-not $venvOk) {
    $bootstrapPython = Find-CompatiblePython
    if (-not $bootstrapPython) {
        Write-Host "[ERROR] Python 3.10-3.12 was not found. Install Python 3.12 and retry." -ForegroundColor Red
        Read-Host "Press Enter to exit"; exit 1
    }
    if (Test-Path ".venv312") {
        Write-Host "[INFO] The virtual environment is broken; repairing .venv312 ..." -ForegroundColor Yellow
        & $bootstrapPython -m venv --upgrade .venv312
    } else {
        Write-Host "[INFO] Creating .venv312 ..." -ForegroundColor Yellow
        & $bootstrapPython -m venv .venv312
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Could not create or repair the virtual environment." -ForegroundColor Red
        Read-Host "Press Enter to exit"; exit 1
    }
    Write-Host "[INFO] Installing dependencies ..." -ForegroundColor Yellow
    & $venvPython -m pip install --upgrade pip -q
    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Dependency installation failed." -ForegroundColor Red
        Read-Host "Press Enter to exit"; exit 1
    }
    Write-Host "[INFO] Dependencies are ready." -ForegroundColor Green
}

# ---------- 2. Check the Tcl/Tk runtime ----------
if (-not (Test-Path ".runtime\tcl\tcl8.6\init.tcl")) {
    Write-Host "[WARN] Bundled Tcl/Tk is missing; copying it from Python ..." -ForegroundColor Yellow
    $pybase = & $venvPython -c "import sys; print(sys.base_prefix)"
    $tclSrc = Join-Path $pybase "tcl\tcl8.6"
    $tkSrc  = Join-Path $pybase "tcl\tk8.6"
    if (Test-Path "$tclSrc\init.tcl") {
        New-Item -ItemType Directory -Force -Path ".runtime\tcl" | Out-Null
        Copy-Item -Recurse -Force $tclSrc ".runtime\tcl\tcl8.6"
        Copy-Item -Recurse -Force $tkSrc  ".runtime\tcl\tk8.6"
        Write-Host "[INFO] Tcl/Tk was copied to .runtime\tcl." -ForegroundColor Green
    } else {
        Write-Host "[WARN] Tcl/Tk was not found; the GUI may not start." -ForegroundColor Yellow
    }
}

# ---------- 3. Check optional ADB support ----------
$adbOk = $null -ne (Get-Command adb -ErrorAction SilentlyContinue)
if ($adbOk) {
    Write-Host "[INFO] ADB is available." -ForegroundColor Green
} else {
    Write-Host "[WARN] ADB was not found. Configure its path in Settings to use Android features." -ForegroundColor Yellow
}

# ---------- 4. Start the application ----------
Write-Host ""
Write-Host "[INFO] Starting auto-pr-io ..." -ForegroundColor Cyan
try {
    & $venvPython main.py
} catch {
    Write-Host "[ERROR] Startup failed: $_" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

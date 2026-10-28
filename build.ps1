# build.ps1 — Build PiKit into an installable .exe
# Run from the PiKit directory.

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "=============================" -ForegroundColor Cyan
Write-Host "  PiKit Build Script" -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan
Write-Host ""

# ── Check Python ──────────────────────────────────────────────────────────────
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "[ERROR] Python not found in PATH" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Python: $(python --version)" -ForegroundColor Green

# ── Install / upgrade dependencies ────────────────────────────────────────────
Write-Host ""
Write-Host "[DEPS] Installing requirements..." -ForegroundColor Cyan
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt
python -m pip install -q pyinstaller

# ── Download pishrink.sh if missing ───────────────────────────────────────────
$pishrink = "assets\pishrink.sh"
if (-not (Test-Path $pishrink)) {
    Write-Host ""
    Write-Host "[ASSET] Downloading pishrink.sh..." -ForegroundColor Cyan
    $url = "https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh"
    try {
        Invoke-WebRequest -Uri $url -OutFile $pishrink -UseBasicParsing
        Write-Host "[OK] pishrink.sh downloaded" -ForegroundColor Green
    } catch {
        Write-Host "[WARN] Could not download pishrink.sh: $_" -ForegroundColor Yellow
        Write-Host "       Shrink step will not work until assets\pishrink.sh is present." -ForegroundColor Yellow
    }
} else {
    Write-Host "[OK] pishrink.sh already present" -ForegroundColor Green
}

# ── Clean previous build ──────────────────────────────────────────────────────
Write-Host ""
Write-Host "[BUILD] Cleaning previous build..." -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

# ── PyInstaller ───────────────────────────────────────────────────────────────
Write-Host "[BUILD] Running PyInstaller..." -ForegroundColor Cyan
python -m PyInstaller pikit.spec

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] PyInstaller failed" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Build complete → dist\PiKit\" -ForegroundColor Green

# ── Inno Setup (optional) ─────────────────────────────────────────────────────
Write-Host ""
$inno = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "C:\Program Files (x86)\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($inno) {
    Write-Host "[INSTALLER] Building installer with Inno Setup..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force installer_out | Out-Null
    & $inno installer.iss
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Installer → installer_out\PiKit_Setup_<version>.exe" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Inno Setup failed (exit $LASTEXITCODE)" -ForegroundColor Yellow
    }
} else {
    Write-Host "[SKIP] Inno Setup not found — skipping installer build." -ForegroundColor DarkGray
    Write-Host "       Install from: https://jrsoftware.org/isdl.php" -ForegroundColor DarkGray
    Write-Host "       Then re-run this script to produce a .exe installer." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "=============================" -ForegroundColor Cyan
Write-Host "  Done!" -ForegroundColor Green
Write-Host "=============================" -ForegroundColor Cyan
Write-Host ""

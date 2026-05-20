# SysCtl - Push to GitHub
# Run this script (right-click -> Run with PowerShell)

$repo = "https://github.com/ganeshparajuli11/desktop-optimizer-windows-app.git"
$folder = "$PSScriptRoot"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SysCtl - GitHub Push Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check git is installed
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: git is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Download it from: https://git-scm.com/download/win" -ForegroundColor Yellow
    pause
    exit 1
}

Set-Location $folder

# Remove any broken .git if present
if (Test-Path ".git") {
    Write-Host "Removing existing .git folder..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force ".git"
}

Write-Host "Initializing git repository..." -ForegroundColor Green
git init
git config user.name "ganeshparajuli11"
git config user.email "jackram177@gmail.com"

Write-Host ""
Write-Host "Staging all files..." -ForegroundColor Green
git add .

Write-Host ""
Write-Host "Creating commit..." -ForegroundColor Green
git commit -m "Initial release - SysCtl v3 Windows System Control Center

Features:
- Live process manager (no-flicker, 60 rows)
- Real-time network monitor with history graphs
- Disk I/O monitor per drive and per process
- RTX GPU monitor via pynvml (load, VRAM, temp, power)
- Docker container monitor via CLI (start/stop/restart/logs)
- StandBy fullscreen clock for second monitor with live stats + timer
- Gaming/Dev/Battery/Normal profiles via PowerShell
- Smart Windows toast alerts (RAM, CPU, GPU thresholds)
- Startup app manager (registry + startup folder)
- Quick Actions: free RAM, clean temp, flush DNS, kill hogs
- PyInstaller .exe auto-build via GitHub Actions
- UAC admin elevation for full system access"

Write-Host ""
Write-Host "Setting branch to main..." -ForegroundColor Green
git branch -M main

Write-Host ""
Write-Host "Adding remote origin..." -ForegroundColor Green
git remote add origin $repo

Write-Host ""
Write-Host "Pushing to GitHub (force push - your local code wins)..." -ForegroundColor Green
Write-Host "(A browser window or credential prompt may appear)" -ForegroundColor Yellow
Write-Host ""

# Force push because the remote already has a commit (e.g. auto-created README)
# --force-with-lease is safer than --force: it only overrides if no one else pushed
git push -u origin main --force

Write-Host ""
if ($LASTEXITCODE -eq 0) {
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  SUCCESS! Project is live on GitHub." -ForegroundColor Green
    Write-Host "  $repo" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Next: tag a release so GitHub builds the .exe:" -ForegroundColor Yellow
    Write-Host "    git tag v1.0.0" -ForegroundColor White
    Write-Host "    git push --tags" -ForegroundColor White
    Write-Host "========================================" -ForegroundColor Green
} else {
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "  Push failed. Try these fixes:" -ForegroundColor Red
    Write-Host ""
    Write-Host "  1. Wrong password? Use a Personal Access Token:" -ForegroundColor Yellow
    Write-Host "     GitHub -> Settings -> Developer Settings ->" -ForegroundColor Yellow
    Write-Host "     Personal Access Tokens -> Tokens (classic)" -ForegroundColor Yellow
    Write-Host "     Generate token with 'repo' scope checked" -ForegroundColor Yellow
    Write-Host "     Paste the token when asked for password" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  2. To clear saved wrong credentials:" -ForegroundColor Yellow
    Write-Host "     Windows -> Credential Manager -> Windows Credentials" -ForegroundColor Yellow
    Write-Host "     Remove any entry for github.com, then retry" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Red
}

Write-Host ""
pause

$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$vbsPath    = Join-Path $scriptDir "SysCtl.vbs"
$desktop    = [System.Environment]::GetFolderPath("Desktop")
$shortcut   = Join-Path $desktop "SysCtl.lnk"

$shell = New-Object -ComObject WScript.Shell
$lnk   = $shell.CreateShortcut($shortcut)
$lnk.TargetPath       = "wscript.exe"
$lnk.Arguments        = "`"$vbsPath`""
$lnk.WorkingDirectory = $scriptDir
$lnk.Description      = "SysCtl - System Control Center"
$lnk.IconLocation     = "C:\Windows\System32\SystemPropertiesPerformance.exe,0"
$lnk.Save()

Write-Host "  [OK] Desktop shortcut created: SysCtl.lnk" -ForegroundColor Green
Write-Host "  You can now double-click SysCtl on your desktop to launch it." -ForegroundColor Cyan
Write-Host "  Right-click the shortcut and choose 'Pin to taskbar' to add it to your taskbar." -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter to close"

@echo off
title SysCtl - Build EXE
color 0A
echo.
echo  ==========================================
echo   SysCtl - Building Standalone EXE
echo  ==========================================
echo.

pip show pyinstaller >nul 2>&1 || pip install pyinstaller
pip install customtkinter psutil pynvml

echo.
echo  Building SysCtl.exe (this takes ~60 seconds)...
echo.
pyinstaller sysctl.spec --clean

echo.
if exist dist\SysCtl.exe (
    echo  ==========================================
    echo   SUCCESS! EXE is ready:
    echo   dist\SysCtl.exe
    echo.
    echo   Double-click it to run.
    echo   Windows will ask for admin permission - click Yes.
    echo  ==========================================
    explorer dist
) else (
    echo  BUILD FAILED - check errors above
)

pause

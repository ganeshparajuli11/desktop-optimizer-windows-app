@echo off
title SysCtl v3
color 0B
echo.
echo  SysCtl v3 - Installing dependencies...
echo.
where python >nul 2>&1
if errorlevel 1 ( echo [ERROR] Python not found - install from python.org & pause & exit /b 1 )
pip install customtkinter psutil pynvml --quiet
echo  Launching SysCtl v3...
python "%~dp0sysctl.py"
if errorlevel 1 ( echo. & echo [ERROR] Crashed - ensure Python 3.8+ & pause )

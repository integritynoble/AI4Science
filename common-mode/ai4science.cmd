@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0ai4science.ps1" %*
exit /b %ERRORLEVEL%

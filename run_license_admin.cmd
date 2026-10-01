@echo off
setlocal
cd /d "%~dp0"
where pythonw.exe >nul 2>nul
if errorlevel 1 (
    python -m license_admin
) else (
    start "License Admin" pythonw.exe -m license_admin
)
endlocal

@echo off
REM Script để commit và push
REM Cách dùng: git-commit-push.bat "Commit message"
if "%1"=="" (
    powershell.exe -ExecutionPolicy Bypass -File "%~dp0git-commit-push.ps1"
) else (
    powershell.exe -ExecutionPolicy Bypass -File "%~dp0git-commit-push.ps1" -message "%*"
)

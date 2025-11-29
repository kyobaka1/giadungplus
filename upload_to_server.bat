@echo off
REM Script upload code từ Windows lên server Ubuntu
REM Sử dụng: upload_to_server.bat

set SERVER_IP=103.110.85.223
set SERVER_USER=root
set REMOTE_PATH=/var/www/giadungplus
set PROJECT_DIR=D:\giadungplus\giadungplus-1

echo ====================================
echo  Uploading code to server...
echo ====================================
echo Server: %SERVER_USER%@%SERVER_IP%
echo Remote: %REMOTE_PATH%
echo Local: %PROJECT_DIR%
echo.

REM Upload tất cả file
echo [1/2] Uploading code files...
echo Note: SCP will upload all files. Exclude patterns not supported in Windows SCP.
echo.
scp -r "%PROJECT_DIR%\*" %SERVER_USER%@%SERVER_IP%:%REMOTE_PATH%/

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Upload failed!
    pause
    exit /b 1
)

echo.
echo [2/2] Setting permissions...
ssh %SERVER_USER%@%SERVER_IP% "cd %REMOTE_PATH% && sudo chown -R giadungplus:giadungplus . && sudo chmod +x deploy.sh"

echo.
echo ====================================
echo  Upload completed successfully!
echo ====================================
echo.
echo Next steps on server:
echo   1. cd /var/www/giadungplus
echo   2. bash deploy.sh
echo.
pause


@echo off
REM Script để tải về chỉ thư mục backup từ git (Windows)
REM Chỉ tải thư mục data_backup, không tải toàn bộ repository

echo ========================================
echo Script tai thu muc backup tu Git
echo ========================================
echo.

REM Kiểm tra git có được cài đặt không
where git >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Loi: Git chua duoc cai dat hoac khong co trong PATH
    echo Vui long cai dat Git: https://git-scm.com/download/win
    pause
    exit /b 1
)

REM Lấy đường dẫn thư mục hiện tại
cd /d "%~dp0"

REM Kiểm tra xem đã có git repository chưa
if exist ".git" (
    echo Phat hien git repository da ton tai.
    echo.
    echo Lua chon:
    echo 1. Pull chi thu muc backup (khuyen nghi)
    echo 2. Pull toan bo repository
    echo 3. Huy
    set /p "CHOICE=Nhap lua chon (1/2/3): "
    
    if "%CHOICE%"=="1" goto PULL_BACKUP_ONLY
    if "%CHOICE%"=="2" goto PULL_ALL
    if "%CHOICE%"=="3" goto END
    goto PULL_BACKUP_ONLY
) else (
    echo Chua co git repository.
    echo.
    set /p "GIT_URL=Nhap URL git repository (hoac Enter de huy): "
    if "%GIT_URL%"=="" goto END
    
    echo.
    echo Dang clone chi thu muc backup...
    goto CLONE_BACKUP_ONLY
)

:PULL_BACKUP_ONLY
echo.
echo Dang pull chi thu muc backup...
git fetch origin
git checkout origin/main -- data_backup/ 2>nul
if %ERRORLEVEL% NEQ 0 (
    git checkout origin/master -- data_backup/ 2>nul
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo Thu pull tu branch hien tai...
        git checkout HEAD -- data_backup/
    )
)

if exist "data_backup" (
    echo.
    echo ========================================
    echo Tai backup thanh cong!
    echo ========================================
    echo Thu muc: %CD%\data_backup
    dir /b data_backup\*.json 2>nul | find /c /v "" >nul
    if %ERRORLEVEL% EQU 0 (
        echo So file backup: 
        for /f %%i in ('dir /b data_backup\*.json 2^>nul ^| find /c /v ""') do echo %%i
    )
) else (
    echo.
    echo Canh bao: Khong tim thay thu muc data_backup trong repository
    echo Co the thu muc backup chua duoc commit len git
)
goto END

:PULL_ALL
echo.
echo Dang pull toan bo repository...
git pull origin main
if %ERRORLEVEL% NEQ 0 (
    git pull origin master
)
goto END

:CLONE_BACKUP_ONLY
REM Tạo thư mục tạm để clone
set "TEMP_CLONE=temp_git_clone_%RANDOM%"
mkdir "%TEMP_CLONE%" 2>nul

REM Clone repository vào thư mục tạm
echo Dang clone repository...
git clone --no-checkout "%GIT_URL%" "%TEMP_CLONE%"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Loi: Khong the clone repository
    rmdir /s /q "%TEMP_CLONE%" 2>nul
    pause
    exit /b 1
)

REM Sparse checkout chỉ thư mục backup
cd "%TEMP_CLONE%"
git sparse-checkout init --cone
git sparse-checkout set data_backup
git checkout

REM Copy thư mục backup về thư mục gốc
if exist "data_backup" (
    xcopy /E /I /Y "data_backup" "..\data_backup\"
    cd ..
    echo.
    echo ========================================
    echo Tai backup thanh cong!
    echo ========================================
    echo Thu muc: %CD%\data_backup
) else (
    echo.
    echo Canh bao: Khong tim thay thu muc data_backup trong repository
)

REM Xóa thư mục tạm
cd ..
rmdir /s /q "%TEMP_CLONE%"

:END
echo.
pause


@echo off
REM Script import dữ liệu vào SQLite (Test - Windows)
REM Chạy script này trên Windows để import dữ liệu từ file JSON

echo ========================================
echo Script import dữ liệu vào SQLite (Test)
echo ========================================
echo.

REM Lấy đường dẫn thư mục hiện tại
cd /d "%~dp0"

REM Kiểm tra xem manage.py có tồn tại không
if not exist "manage.py" (
    echo Loi: Khong tim thay manage.py. Vui long chay script trong thu muc goc cua project.
    pause
    exit /b 1
)

REM Tìm file backup mới nhất trong thư mục data_backup
set "BACKUP_DIR=data_backup"
set "LATEST_FILE="

if exist "%BACKUP_DIR%\*.json" (
    for /f "delims=" %%F in ('dir /b /o-d "%BACKUP_DIR%\*.json" 2^>nul') do (
        set "LATEST_FILE=%BACKUP_DIR%\%%F"
        goto :found
    )
)

:found
if "%LATEST_FILE%"=="" (
    echo.
    echo Khong tim thay file backup trong thu muc %BACKUP_DIR%
    echo Vui long:
    echo 1. Copy file backup tu server Ubuntu vao thu muc %BACKUP_DIR%
    echo 2. Hoac dat file backup vao thu muc goc cua project
    echo.
    set /p "LATEST_FILE=Nhap duong dan den file backup (hoac keo tha file vao day): "
    set "LATEST_FILE=%LATEST_FILE:"=%"
)

REM Kiểm tra file có tồn tại không
if not exist "%LATEST_FILE%" (
    echo.
    echo Loi: File khong ton tai: %LATEST_FILE%
    pause
    exit /b 1
)

echo.
echo File backup: %LATEST_FILE%
echo.

REM Hỏi xác nhận trước khi import
echo CANH BAO: Thao tac nay se ghi de toan bo du lieu hien tai trong database!
set /p "CONFIRM=Ban co chac chan muon tiep tuc? (y/n): "
if /i not "%CONFIRM%"=="y" (
    echo Da huy thao tac.
    pause
    exit /b 0
)

echo.
echo Dang backup database hien tai...
set "BACKUP_DB=db.sqlite3.backup_%date:~-4,4%%date:~-7,2%%date:~-10,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
set "BACKUP_DB=%BACKUP_DB: =0%"
if exist "db.sqlite3" (
    copy "db.sqlite3" "%BACKUP_DB%" >nul
    echo Da backup database hien tai thanh: %BACKUP_DB%
)

echo.
echo Dang xoa database cu...
if exist "db.sqlite3" del "db.sqlite3"

echo.
echo Dang tao database moi...
python manage.py migrate --run-syncdb

echo.
echo Dang import du lieu...
python manage.py loaddata "%LATEST_FILE%"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo Import du lieu thanh cong!
    echo ========================================
    echo.
    echo Database backup cu: %BACKUP_DB%
    echo File da import: %LATEST_FILE%
) else (
    echo.
    echo ========================================
    echo Loi khi import du lieu!
    echo ========================================
    echo.
    echo Neu can, ban co the restore database cu tu file: %BACKUP_DB%
)

echo.
pause


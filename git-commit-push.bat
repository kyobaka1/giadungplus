@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   Git Commit and Push Script
echo ========================================
echo.

:: Kiểm tra xem có phải git repository không
git rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Không phải git repository!
    echo Vui lòng chạy script này trong thư mục git repository.
    pause
    exit /b 1
)

:: Kiểm tra branch hiện tại
for /f "tokens=*" %%i in ('git branch --show-current') do set CURRENT_BRANCH=%%i
echo [INFO] Branch hiện tại: %CURRENT_BRANCH%
echo.

:: Kiểm tra có thay đổi nào không
git status --porcelain >nul 2>&1
if errorlevel 1 (
    echo [INFO] Không có thay đổi nào để commit.
    pause
    exit /b 0
)

:: Hiển thị status
echo [INFO] Các file đã thay đổi:
git status --short
echo.

:: Nhập tên phiên bản / commit message
set /p VERSION="Nhập tên phiên bản / commit message: "

if "!VERSION!"=="" (
    echo [ERROR] Tên phiên bản không được để trống!
    pause
    exit /b 1
)

echo.
echo [INFO] Commit message: !VERSION!
echo.

:: Xác nhận
set /p CONFIRM="Bạn có chắc chắn muốn commit và push? (y/n): "
if /i not "!CONFIRM!"=="y" (
    echo [INFO] Đã hủy.
    pause
    exit /b 0
)

echo.
echo [INFO] Đang thêm các file vào staging area...
git add .

if errorlevel 1 (
    echo [ERROR] Lỗi khi thêm file vào staging area!
    pause
    exit /b 1
)

echo [INFO] Đang commit...
git commit -m "!VERSION!"

if errorlevel 1 (
    echo [ERROR] Lỗi khi commit!
    pause
    exit /b 1
)

echo [INFO] Đang push lên GitHub...
git push origin %CURRENT_BRANCH%

if errorlevel 1 (
    echo [ERROR] Lỗi khi push!
    echo [INFO] Có thể cần pull trước hoặc kiểm tra remote.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   [SUCCESS] Đã push thành công!
echo ========================================
echo [INFO] Branch: %CURRENT_BRANCH%
echo [INFO] Commit: !VERSION!
echo.

pause

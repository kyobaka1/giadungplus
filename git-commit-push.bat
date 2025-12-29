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

:: Fetch để kiểm tra xem có thay đổi trên remote không
echo [INFO] Đang kiểm tra remote...
git fetch origin %CURRENT_BRANCH%

:: Kiểm tra xem branch local có behind remote không
git rev-list --left-right --count origin/%CURRENT_BRANCH%...HEAD >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Không thể so sánh với remote. Thử push trực tiếp...
    goto :push_direct
)

for /f "tokens=1,2" %%a in ('git rev-list --left-right --count origin/%CURRENT_BRANCH%...HEAD 2^>nul') do (
    set BEHIND=%%a
    set AHEAD=%%b
)

if !BEHIND! GTR 0 (
    echo [WARNING] Branch local đang behind remote !BEHIND! commit(s)
    echo [INFO] Cần pull trước để đồng bộ với remote.
    echo.
    set /p PULL_CHOICE="Bạn có muốn pull và merge trước? (y/n): "
    
    if /i "!PULL_CHOICE!"=="y" (
        echo [INFO] Đang pull từ remote...
        git pull origin %CURRENT_BRANCH% --no-rebase
        
        if errorlevel 1 (
            echo [ERROR] Lỗi khi pull! Có thể có conflict.
            echo [INFO] Vui lòng giải quyết conflict thủ công và chạy lại script.
            pause
            exit /b 1
        )
        
        echo [INFO] Pull thành công! Đang push...
        goto :push_direct
    ) else (
        echo [INFO] Bỏ qua pull. Thử push trực tiếp...
        echo [WARNING] Push có thể bị reject nếu có conflict.
    )
)

:push_direct
echo [INFO] Đang push lên GitHub...
git push origin %CURRENT_BRANCH%

if errorlevel 1 (
    echo [ERROR] Lỗi khi push!
    echo.
    echo [INFO] Các lựa chọn:
    echo   1. Pull trước: git pull origin %CURRENT_BRANCH%
    echo   2. Force push (NGUY HIỂM): git push origin %CURRENT_BRANCH% --force
    echo   3. Xem log: git log --oneline --graph --all
    echo.
    set /p FORCE_CHOICE="Bạn có muốn thử force push? (y/n - NGUY HIỂM): "
    
    if /i "!FORCE_CHOICE!"=="y" (
        echo [WARNING] Đang force push - NGUY HIỂM!
        git push origin %CURRENT_BRANCH% --force
        
        if errorlevel 1 (
            echo [ERROR] Force push cũng thất bại!
            pause
            exit /b 1
        ) else (
            echo [SUCCESS] Force push thành công!
            goto :success
        )
    ) else (
        echo [INFO] Đã hủy. Vui lòng pull và merge thủ công trước khi push.
        pause
        exit /b 1
    )
)

:success

goto :end_success

:end_success
echo.
echo ========================================
echo   [SUCCESS] Đã push thành công!
echo ========================================
echo [INFO] Branch: %CURRENT_BRANCH%
echo [INFO] Commit: !VERSION!
echo.

pause
exit /b 0

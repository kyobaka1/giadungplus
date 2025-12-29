# Script PowerShell để tải về chỉ thư mục backup từ git (Windows)
# Chỉ tải thư mục data_backup, không tải toàn bộ repository

Write-Host "========================================" -ForegroundColor Green
Write-Host "Script tải thư mục backup từ Git" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Kiểm tra git có được cài đặt không
$gitPath = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitPath) {
    Write-Host "Lỗi: Git chưa được cài đặt hoặc không có trong PATH" -ForegroundColor Red
    Write-Host "Vui lòng cài đặt Git: https://git-scm.com/download/win" -ForegroundColor Yellow
    Read-Host "Nhấn Enter để thoát"
    exit 1
}

# Lấy đường dẫn thư mục hiện tại
$currentDir = Get-Location

# Kiểm tra xem đã có git repository chưa
if (Test-Path ".git") {
    Write-Host "Phát hiện git repository đã tồn tại." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Lựa chọn:"
    Write-Host "1. Pull chỉ thư mục backup (khuyến nghị)"
    Write-Host "2. Pull toàn bộ repository"
    Write-Host "3. Hủy"
    $choice = Read-Host "Nhập lựa chọn (1/2/3)"
    
    if ($choice -eq "1") {
        # Pull chỉ thư mục backup
        Write-Host ""
        Write-Host "Đang pull chỉ thư mục backup..." -ForegroundColor Blue
        
        git fetch origin
        
        # Thử pull từ main branch
        $branch = "main"
        $result = git checkout "origin/$branch" -- data_backup/ 2>&1
        
        if ($LASTEXITCODE -ne 0) {
            # Thử master branch
            $branch = "master"
            $result = git checkout "origin/$branch" -- data_backup/ 2>&1
        }
        
        if ($LASTEXITCODE -ne 0) {
            # Thử từ branch hiện tại
            $result = git checkout HEAD -- data_backup/ 2>&1
        }
        
        if (Test-Path "data_backup") {
            $backupFiles = Get-ChildItem "data_backup\*.json" -ErrorAction SilentlyContinue
            Write-Host ""
            Write-Host "========================================" -ForegroundColor Green
            Write-Host "Tải backup thành công!" -ForegroundColor Green
            Write-Host "========================================" -ForegroundColor Green
            Write-Host "Thư mục: $currentDir\data_backup" -ForegroundColor Cyan
            if ($backupFiles) {
                Write-Host "Số file backup: $($backupFiles.Count)" -ForegroundColor Cyan
            }
        } else {
            Write-Host ""
            Write-Host "Cảnh báo: Không tìm thấy thư mục data_backup trong repository" -ForegroundColor Yellow
            Write-Host "Có thể thư mục backup chưa được commit lên git" -ForegroundColor Yellow
        }
    } elseif ($choice -eq "2") {
        # Pull toàn bộ
        Write-Host ""
        Write-Host "Đang pull toàn bộ repository..." -ForegroundColor Blue
        git pull origin main
        if ($LASTEXITCODE -ne 0) {
            git pull origin master
        }
    }
} else {
    # Chưa có git repository, cần clone
    Write-Host "Chưa có git repository." -ForegroundColor Yellow
    Write-Host ""
    $gitUrl = Read-Host "Nhập URL git repository (hoặc Enter để hủy)"
    
    if ([string]::IsNullOrWhiteSpace($gitUrl)) {
        exit 0
    }
    
    Write-Host ""
    Write-Host "Đang clone chỉ thư mục backup..." -ForegroundColor Blue
    
    # Tạo thư mục tạm để clone
    $tempClone = "temp_git_clone_$((Get-Random))"
    New-Item -ItemType Directory -Path $tempClone -Force | Out-Null
    
    try {
        # Clone repository vào thư mục tạm
        Write-Host "Đang clone repository..." -ForegroundColor Blue
        git clone --no-checkout $gitUrl $tempClone
        
        if ($LASTEXITCODE -ne 0) {
            throw "Không thể clone repository"
        }
        
        # Sparse checkout chỉ thư mục backup
        Set-Location $tempClone
        git sparse-checkout init --cone
        git sparse-checkout set data_backup
        git checkout
        
        # Copy thư mục backup về thư mục gốc
        if (Test-Path "data_backup") {
            Copy-Item -Path "data_backup" -Destination "..\data_backup" -Recurse -Force
            Set-Location ..
            Write-Host ""
            Write-Host "========================================" -ForegroundColor Green
            Write-Host "Tải backup thành công!" -ForegroundColor Green
            Write-Host "========================================" -ForegroundColor Green
            Write-Host "Thư mục: $currentDir\data_backup" -ForegroundColor Cyan
            
            $backupFiles = Get-ChildItem "data_backup\*.json" -ErrorAction SilentlyContinue
            if ($backupFiles) {
                Write-Host "Số file backup: $($backupFiles.Count)" -ForegroundColor Cyan
            }
        } else {
            Write-Host ""
            Write-Host "Cảnh báo: Không tìm thấy thư mục data_backup trong repository" -ForegroundColor Yellow
        }
    } catch {
        Write-Host ""
        Write-Host "Lỗi: $_" -ForegroundColor Red
    } finally {
        # Xóa thư mục tạm
        Set-Location $currentDir
        if (Test-Path $tempClone) {
            Remove-Item -Path $tempClone -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host ""
Read-Host "Nhấn Enter để thoát"


# Script upload code từ Windows PowerShell lên server Ubuntu
# Sử dụng: .\upload_to_server.ps1

$SERVER_IP = "103.110.85.223"
$SERVER_USER = "root"
$REMOTE_PATH = "/var/www/giadungplus"
$PROJECT_DIR = "D:\giadungplus\giadungplus-1"

Write-Host "====================================" -ForegroundColor Cyan
Write-Host " Uploading code to server..." -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host "Server: ${SERVER_USER}@${SERVER_IP}" -ForegroundColor Yellow
Write-Host "Remote: ${REMOTE_PATH}" -ForegroundColor Yellow
Write-Host "Local: ${PROJECT_DIR}" -ForegroundColor Yellow
Write-Host ""

# 1) Lấy danh sách các file vừa sửa (so với origin/main) và lưu vào log
$ChangedFilesLog = Join-Path $PROJECT_DIR "changed_files_for_upload.log"
try {
    git -C $PROJECT_DIR diff --name-only origin/main..HEAD | Out-File -FilePath $ChangedFilesLog -Encoding UTF8
} catch {
    Write-Host "⚠️  Không thể chạy 'git diff', sẽ upload toàn bộ code." -ForegroundColor Yellow
    $ChangedFilesLog = $null
}

$ChangedFiles = @()
if ($ChangedFilesLog -and (Test-Path $ChangedFilesLog)) {
    $ChangedFiles = Get-Content $ChangedFilesLog | Where-Object { $_ -and -not $_.StartsWith(" ") }
}

if ($ChangedFiles.Count -gt 0) {
    Write-Host "📄 Sẽ upload CHỈ các file vừa sửa (đã lưu trong changed_files_for_upload.log):" -ForegroundColor Yellow
    $ChangedFiles | ForEach-Object { Write-Host "   - $_" -ForegroundColor DarkGray }
} else {
    Write-Host "📄 Không tìm thấy file thay đổi (hoặc trống). Sẽ upload TOÀN BỘ code." -ForegroundColor Yellow
}

Write-Host "[1/2] Uploading code files..." -ForegroundColor Green

# SCP upload (Windows PowerShell có thể dùng pscp từ PuTTY hoặc OpenSSH)
# Kiểm tra xem có OpenSSH client không
$opensshPath = Get-Command ssh -ErrorAction SilentlyContinue

if ($opensshPath) {
    Write-Host "Using OpenSSH..." -ForegroundColor Gray

    if ($ChangedFiles.Count -gt 0) {
        # Upload CHỈ các file/thư mục vừa sửa
        foreach ($relPath in $ChangedFiles) {
            $localPath = Join-Path $PROJECT_DIR $relPath
            if (-not (Test-Path $localPath)) {
                Write-Host "  ⚠️  Bỏ qua (không tồn tại): $relPath" -ForegroundColor DarkYellow
                continue
            }

            $remoteDir = Split-Path $relPath -Parent
            if ($remoteDir -and $remoteDir -ne ".") {
                Write-Host "  → Uploading changed: $relPath" -ForegroundColor DarkGray
                ssh "${SERVER_USER}@${SERVER_IP}" "mkdir -p ${REMOTE_PATH}/$remoteDir"
                scp -r "$localPath" "${SERVER_USER}@${SERVER_IP}:${REMOTE_PATH}/$remoteDir/"
            } else {
                Write-Host "  → Uploading changed: $relPath" -ForegroundColor DarkGray
                scp -r "$localPath" "${SERVER_USER}@${SERVER_IP}:${REMOTE_PATH}/"
            }
        }
    } else {
        # Upload TOÀN BỘ code nếu không có danh sách file thay đổi
        Write-Host "  ⚡ Uploading ALL files (this may take a while)..." -ForegroundColor Gray
        $items = Get-ChildItem -Path $PROJECT_DIR -Force | Where-Object {
            $name = $_.Name
            $name -ne "venv" -and 
            $name -ne ".git" -and 
            $name -ne "__pycache__" -and 
            $name -ne "db.sqlite3" -and
            $name -ne ".env" -and
            $name -ne "node_modules"
        }
        
        foreach ($item in $items) {
            $itemPath = Join-Path $PROJECT_DIR $item.Name
            Write-Host "  → Uploading: $($item.Name)..." -ForegroundColor DarkGray
            scp -r "$itemPath" "${SERVER_USER}@${SERVER_IP}:${REMOTE_PATH}/"
        }
    }
    
} else {
    Write-Host "OpenSSH not found. Please install OpenSSH Client or use Git Bash." -ForegroundColor Red
    Write-Host ""
    Write-Host "Alternative: Use Git Bash and run:" -ForegroundColor Yellow
    Write-Host "  scp -r D:/giadungplus/giadungplus-1/* root@${SERVER_IP}:${REMOTE_PATH}/" -ForegroundColor Cyan
    exit 1
}

Write-Host ""
Write-Host "[2/2] Setting permissions..." -ForegroundColor Green
ssh "${SERVER_USER}@${SERVER_IP}" "cd ${REMOTE_PATH} && sudo chown -R giadungplus:giadungplus . && sudo chmod +x deploy.sh 2>/dev/null || true"

Write-Host ""
Write-Host "====================================" -ForegroundColor Green
Write-Host " Upload completed successfully!" -ForegroundColor Green
Write-Host "====================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps on server:" -ForegroundColor Yellow
Write-Host "  1. ssh root@${SERVER_IP}" -ForegroundColor Cyan
Write-Host "  2. cd ${REMOTE_PATH}" -ForegroundColor Cyan
Write-Host "  3. bash deploy.sh" -ForegroundColor Cyan
Write-Host ""


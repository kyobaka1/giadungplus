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

# Danh sách files/folders cần upload (trừ các thư mục không cần thiết)
$EXCLUDE_PATTERNS = @(
    "__pycache__",
    "*.pyc",
    ".git",
    "db.sqlite3",
    "venv",
    ".env",
    "*.log",
    ".DS_Store"
)

Write-Host "[1/2] Uploading code files..." -ForegroundColor Green

# Tạo rsync command cho SCP (hoặc dùng rsync nếu có)
# Vì SCP không hỗ trợ exclude tốt, dùng cách khác
# Tạo temporary exclude file
$EXCLUDE_FILE = "$env:TEMP\scp_exclude.txt"
$EXCLUDE_PATTERNS | Out-File -FilePath $EXCLUDE_FILE -Encoding ASCII

# SCP upload (Windows PowerShell có thể dùng pscp từ PuTTY hoặc OpenSSH)
# Kiểm tra xem có OpenSSH client không
$opensshPath = Get-Command ssh -ErrorAction SilentlyContinue

if ($opensshPath) {
    Write-Host "Using OpenSSH..." -ForegroundColor Gray
    Write-Host "  ⚡ Uploading all files (this may take a while)..." -ForegroundColor Gray
    
    # Upload tất cả, sẽ bỏ qua venv và các file lớn tự động
    # SCP sẽ upload theo thứ tự, bỏ qua các file không cần thiết
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


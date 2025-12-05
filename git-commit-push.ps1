# Script để commit và push
# Chạy: powershell.exe -ExecutionPolicy Bypass -File .\git-commit-push.ps1 "Commit message"

param(
    [Parameter(Mandatory=$false)]
    [string]$message = "Feature: Thêm tính năng auto xpress push - tự động tìm lại shipper và chuẩn bị hàng cho đơn hoả tốc"
)

$logFile = "d:\giadungplus\giadungplus-1\output-command.log"
$workspace = "d:\giadungplus\giadungplus-1"

Set-Location $workspace

# Clear log file
"" | Out-File -FilePath $logFile -Encoding utf8

"========================================" | Out-File -FilePath $logFile -Append -Encoding utf8
"Git Commit and Push" | Out-File -FilePath $logFile -Append -Encoding utf8
"Time: $(Get-Date)" | Out-File -FilePath $logFile -Append -Encoding utf8
"========================================" | Out-File -FilePath $logFile -Append -Encoding utf8
"" | Out-File -FilePath $logFile -Append -Encoding utf8

# Step 1: Git status
Write-Host "[1] Checking git status..." -ForegroundColor Yellow
"--- Git Status ---" | Out-File -FilePath $logFile -Append -Encoding utf8
git status | Out-File -FilePath $logFile -Append -Encoding utf8
"" | Out-File -FilePath $logFile -Append -Encoding utf8

# Step 2: Add changes (modified, deleted, and new files)
Write-Host "[2] Adding changes..." -ForegroundColor Yellow
"--- Git Add ---" | Out-File -FilePath $logFile -Append -Encoding utf8
git add -A | Out-File -FilePath $logFile -Append -Encoding utf8
"" | Out-File -FilePath $logFile -Append -Encoding utf8

# Step 3: Commit
Write-Host "[3] Committing..." -ForegroundColor Yellow
"--- Git Commit ---" | Out-File -FilePath $logFile -Append -Encoding utf8
git commit -m "$message" | Out-File -FilePath $logFile -Append -Encoding utf8
"" | Out-File -FilePath $logFile -Append -Encoding utf8

# Step 4: Push
Write-Host "[4] Pushing..." -ForegroundColor Yellow
"--- Git Push ---" | Out-File -FilePath $logFile -Append -Encoding utf8
git push | Out-File -FilePath $logFile -Append -Encoding utf8
"" | Out-File -FilePath $logFile -Append -Encoding utf8

"========================================" | Out-File -FilePath $logFile -Append -Encoding utf8
"Completed at: $(Get-Date)" | Out-File -FilePath $logFile -Append -Encoding utf8
"========================================" | Out-File -FilePath $logFile -Append -Encoding utf8

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Completed! Check output-command.log for details" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

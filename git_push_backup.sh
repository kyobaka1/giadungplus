#!/bin/bash
# Script để commit và push thư mục data_backup lên git
# CẢNH BÁO: File backup có thể rất lớn và chứa dữ liệu nhạy cảm

set -e  # Dừng nếu có lỗi

# Màu sắc cho output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Script push thư mục backup lên Git ===${NC}"

# Lấy đường dẫn thư mục hiện tại
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Kiểm tra xem có phải git repository không
if [ ! -d ".git" ]; then
    echo -e "${RED}Lỗi: Đây không phải là git repository.${NC}"
    exit 1
fi

# Kiểm tra thư mục backup có tồn tại không
BACKUP_DIR="data_backup"
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}Lỗi: Không tìm thấy thư mục $BACKUP_DIR${NC}"
    exit 1
fi

# Kiểm tra có file backup nào không
BACKUP_COUNT=$(find "$BACKUP_DIR" -name "*.json" -type f | wc -l)
if [ "$BACKUP_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}Cảnh báo: Không tìm thấy file backup nào trong $BACKUP_DIR${NC}"
    exit 1
fi

# Hiển thị thông tin
echo -e "${BLUE}Số file backup: $BACKUP_COUNT${NC}"
echo -e "${BLUE}Kích thước thư mục backup: $(du -sh "$BACKUP_DIR" | cut -f1)${NC}"
echo ""

# Cảnh báo
echo -e "${YELLOW}⚠ CẢNH BÁO:${NC}"
echo -e "${YELLOW}- File backup có thể rất lớn (hàng trăm MB hoặc GB)${NC}"
echo -e "${YELLOW}- File backup chứa dữ liệu nhạy cảm từ production${NC}"
echo -e "${YELLOW}- Việc push lên git sẽ làm tăng kích thước repository${NC}"
echo ""
read -p "Bạn có chắc chắn muốn tiếp tục? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Đã hủy thao tác."
    exit 0
fi

# Kiểm tra git status
echo ""
echo -e "${BLUE}Đang kiểm tra git status...${NC}"
git status

# Add thư mục backup (force add nếu đã có trong .gitignore)
echo ""
echo -e "${BLUE}Đang add thư mục backup...${NC}"
git add -f "$BACKUP_DIR"

# Kiểm tra có thay đổi để commit không
if git diff --cached --quiet; then
    echo -e "${YELLOW}Không có thay đổi nào để commit.${NC}"
    exit 0
fi

# Commit
echo ""
echo -e "${BLUE}Đang commit...${NC}"
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
git commit -m "Backup database: $TIMESTAMP"

# Kiểm tra remote
REMOTE=$(git remote | head -n 1)
if [ -z "$REMOTE" ]; then
    echo -e "${YELLOW}Cảnh báo: Không tìm thấy remote repository.${NC}"
    echo -e "${YELLOW}Bạn có thể push thủ công bằng lệnh: git push${NC}"
    exit 0
fi

# Push
echo ""
echo -e "${BLUE}Đang push lên git...${NC}"
BRANCH=$(git branch --show-current)
echo -e "${GREEN}Remote: $REMOTE${NC}"
echo -e "${GREEN}Branch: $BRANCH${NC}"
echo ""

read -p "Bạn có muốn push ngay bây giờ? (yes/no): " PUSH_CONFIRM

if [ "$PUSH_CONFIRM" = "yes" ]; then
    git push "$REMOTE" "$BRANCH"
    echo ""
    echo -e "${GREEN}✓ Đã push thành công!${NC}"
else
    echo ""
    echo -e "${YELLOW}Bạn có thể push sau bằng lệnh:${NC}"
    echo -e "${BLUE}git push $REMOTE $BRANCH${NC}"
fi


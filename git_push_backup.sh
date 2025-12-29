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
    # Fetch để kiểm tra xem có thay đổi trên remote không
    echo -e "${BLUE}Đang kiểm tra remote...${NC}"
    git fetch "$REMOTE" "$BRANCH"
    
    # Kiểm tra xem branch local có behind remote không
    LOCAL=$(git rev-parse @)
    REMOTE_REF=$(git rev-parse "$REMOTE/$BRANCH" 2>/dev/null)
    
    if [ -n "$REMOTE_REF" ]; then
        BEHIND=$(git rev-list --left-right --count "$REMOTE/$BRANCH"...HEAD 2>/dev/null | cut -f1)
        
        if [ "$BEHIND" -gt 0 ]; then
            echo -e "${YELLOW}⚠ Branch local đang behind remote $BEHIND commit(s)${NC}"
            echo -e "${YELLOW}Cần pull trước để đồng bộ với remote.${NC}"
            echo ""
            read -p "Bạn có muốn pull và merge trước? (yes/no): " PULL_CHOICE
            
            if [ "$PULL_CHOICE" = "yes" ]; then
                echo -e "${BLUE}Đang pull từ remote...${NC}"
                git pull "$REMOTE" "$BRANCH" --no-rebase
                
                if [ $? -ne 0 ]; then
                    echo -e "${RED}✗ Lỗi khi pull! Có thể có conflict.${NC}"
                    echo -e "${YELLOW}Vui lòng giải quyết conflict thủ công và chạy lại script.${NC}"
                    exit 1
                fi
                
                echo -e "${GREEN}✓ Pull thành công!${NC}"
            else
                echo -e "${YELLOW}Bỏ qua pull. Thử push trực tiếp...${NC}"
                echo -e "${YELLOW}Push có thể bị reject nếu có conflict.${NC}"
            fi
        fi
    fi
    
    # Thử push
    git push "$REMOTE" "$BRANCH"
    
    if [ $? -ne 0 ]; then
        echo ""
        echo -e "${RED}✗ Lỗi khi push!${NC}"
        echo ""
        echo -e "${YELLOW}Các lựa chọn:${NC}"
        echo -e "  1. Pull trước: ${BLUE}git pull $REMOTE $BRANCH${NC}"
        echo -e "  2. Force push (NGUY HIỂM): ${BLUE}git push $REMOTE $BRANCH --force${NC}"
        echo -e "  3. Xem log: ${BLUE}git log --oneline --graph --all${NC}"
        echo ""
        read -p "Bạn có muốn thử force push? (yes/no - NGUY HIỂM): " FORCE_CHOICE
        
        if [ "$FORCE_CHOICE" = "yes" ]; then
            echo -e "${YELLOW}⚠ Đang force push - NGUY HIỂM!${NC}"
            git push "$REMOTE" "$BRANCH" --force
            
            if [ $? -eq 0 ]; then
                echo ""
                echo -e "${GREEN}✓ Force push thành công!${NC}"
            else
                echo ""
                echo -e "${RED}✗ Force push cũng thất bại!${NC}"
                exit 1
            fi
        else
            echo -e "${YELLOW}Đã hủy. Vui lòng pull và merge thủ công trước khi push.${NC}"
            exit 1
        fi
    else
        echo ""
        echo -e "${GREEN}✓ Đã push thành công!${NC}"
    fi
else
    echo ""
    echo -e "${YELLOW}Bạn có thể push sau bằng lệnh:${NC}"
    echo -e "${BLUE}git push $REMOTE $BRANCH${NC}"
fi


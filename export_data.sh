#!/bin/bash
# Script xuất dữ liệu từ PostgreSQL (Production - Ubuntu)
# Chạy script này trên server Ubuntu để export toàn bộ dữ liệu

set -e  # Dừng nếu có lỗi

# Màu sắc cho output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Script xuất dữ liệu từ PostgreSQL (Production) ===${NC}"

# Lấy đường dẫn thư mục hiện tại (nơi chứa manage.py)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Kiểm tra xem manage.py có tồn tại không
if [ ! -f "manage.py" ]; then
    echo -e "${RED}Lỗi: Không tìm thấy manage.py. Vui lòng chạy script trong thư mục gốc của project.${NC}"
    exit 1
fi

# Tạo thư mục data_backup nếu chưa có
BACKUP_DIR="data_backup"
mkdir -p "$BACKUP_DIR"

# Tạo tên file với timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_FILE="$BACKUP_DIR/db_backup_$TIMESTAMP.json"

echo -e "${YELLOW}Đang xuất dữ liệu...${NC}"
echo -e "File output: ${GREEN}$OUTPUT_FILE${NC}"

# Export tất cả dữ liệu từ các apps
# Sử dụng settings_production.py để kết nối PostgreSQL
# --natural-foreign và --natural-primary giúp dữ liệu portable giữa các database
python3 manage.py dumpdata \
    --settings=GIADUNGPLUS.settings_production \
    --natural-foreign \
    --natural-primary \
    --exclude auth.permission \
    --indent 2 \
    --output "$OUTPUT_FILE"

# Kiểm tra kết quả
if [ $? -eq 0 ]; then
    FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
    echo -e "${GREEN}✓ Xuất dữ liệu thành công!${NC}"
    echo -e "Kích thước file: ${GREEN}$FILE_SIZE${NC}"
    echo -e "File location: ${GREEN}$(pwd)/$OUTPUT_FILE${NC}"
    echo ""
    echo -e "${YELLOW}Bước tiếp theo:${NC}"
    echo -e "1. Copy file ${GREEN}$OUTPUT_FILE${NC} về máy Windows"
    echo -e "2. Đặt file vào thư mục gốc của project trên Windows"
    echo -e "3. Chạy script import_data.bat hoặc import_data.py trên Windows"
else
    echo -e "${RED}✗ Lỗi khi xuất dữ liệu!${NC}"
    exit 1
fi

# Tạo file README với hướng dẫn
README_FILE="$BACKUP_DIR/README.txt"
cat > "$README_FILE" << EOF
HƯỚNG DẪN SỬ DỤNG BACKUP DATA
==============================

File backup: $OUTPUT_FILE
Ngày tạo: $(date)

CÁCH SỬ DỤNG:
1. Copy file $OUTPUT_FILE về máy Windows
2. Đặt file vào thư mục gốc của project (cùng cấp với manage.py)
3. Chạy script import_data.bat hoặc import_data.py trên Windows

LƯU Ý:
- File này chứa toàn bộ dữ liệu từ database production
- Khi import vào Windows, dữ liệu cũ sẽ bị ghi đè
- Nên backup database Windows trước khi import
EOF

echo -e "${GREEN}Đã tạo file hướng dẫn: $README_FILE${NC}"


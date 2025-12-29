#!/bin/bash
# Script xuất dữ liệu từ PostgreSQL (Production - Ubuntu)
# Chạy script này trên server Ubuntu để export toàn bộ dữ liệu
# Giải pháp: Export từng app một để tránh lỗi cursor PostgreSQL

# Không dùng set -e để có thể xử lý lỗi từng phần
# set -e  # Dừng nếu có lỗi

# Màu sắc cho output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
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
TEMP_DIR="$BACKUP_DIR/temp_$TIMESTAMP"
mkdir -p "$TEMP_DIR"

echo -e "${YELLOW}Đang xuất dữ liệu...${NC}"
echo -e "File output: ${GREEN}$OUTPUT_FILE${NC}"
echo ""

# Thử export tất cả một lần trước
echo -e "${BLUE}Thử export tất cả dữ liệu một lần...${NC}"
EXPORT_SUCCESS=false

if python3 manage.py dumpdata \
    --settings=GIADUNGPLUS.settings_production \
    --natural-foreign \
    --natural-primary \
    --exclude auth.permission \
    --indent 2 \
    --output "$OUTPUT_FILE" 2>&1 | tee /tmp/dumpdata_error.log; then
    
    # Kiểm tra file có dữ liệu hợp lệ không
    if [ -s "$OUTPUT_FILE" ] && [ "$(head -1 "$OUTPUT_FILE")" = "[" ] && [ "$(tail -1 "$OUTPUT_FILE")" = "]" ]; then
        EXPORT_SUCCESS=true
        echo -e "${GREEN}✓ Export tất cả thành công!${NC}"
    fi
fi

# Nếu export tất cả thất bại, chia nhỏ theo từng app
if [ "$EXPORT_SUCCESS" = false ]; then
    echo -e "${YELLOW}Export tất cả thất bại, đang thử export từng app...${NC}"
    echo ""
    
    # Xóa file output cũ nếu có
    rm -f "$OUTPUT_FILE"
    
    # Danh sách các apps cần export (theo thứ tự dependency)
    APPS=(
        "contenttypes"
        "auth"
        "sessions"
        "admin"
        "core"
        "kho"
        "cskh"
        "marketing"
        "service"
        "orders"
        "products"
        "customers"
        "settings"
        "chamcong"
    )
    
    # Export từng app một
    SUCCESS_COUNT=0
    FAILED_APPS=()
    
    for APP in "${APPS[@]}"; do
        APP_FILE="$TEMP_DIR/${APP}.json"
        echo -e "${BLUE}Đang export app: ${APP}...${NC}"
        
        # Export app với error handling
        if python3 manage.py dumpdata \
            --settings=GIADUNGPLUS.settings_production \
            --natural-foreign \
            --natural-primary \
            --exclude auth.permission \
            --indent 2 \
            "$APP" \
            --output "$APP_FILE" 2>/dev/null; then
            
            # Kiểm tra file có dữ liệu không (không phải chỉ có [])
            if [ -s "$APP_FILE" ] && [ "$(cat "$APP_FILE" | wc -l)" -gt 1 ]; then
                echo -e "${GREEN}✓ ${APP} - OK${NC}"
                SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
            else
                echo -e "${YELLOW}⚠ ${APP} - Không có dữ liệu${NC}"
                rm -f "$APP_FILE"
            fi
        else
            echo -e "${RED}✗ ${APP} - Lỗi${NC}"
            FAILED_APPS+=("$APP")
            rm -f "$APP_FILE"
        fi
        echo ""
    done
    
    # Merge tất cả các file lại bằng Python để đảm bảo JSON hợp lệ
    echo -e "${YELLOW}Đang merge các file (sử dụng Python để đảm bảo JSON hợp lệ)...${NC}"
    
    # Sử dụng Python để merge JSON đúng cách
    python3 << PYTHON_SCRIPT
import json
import glob
import os

temp_dir = "$TEMP_DIR"
output_file = "$OUTPUT_FILE"

# Tìm tất cả file JSON trong thư mục temp
json_files = sorted(glob.glob(os.path.join(temp_dir, "*.json")))

all_data = []

for json_file in json_files:
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                all_data.extend(data)
            else:
                all_data.append(data)
    except Exception as e:
        print(f"Warning: Error reading {json_file}: {e}")
        continue

# Ghi ra file output
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(all_data, f, ensure_ascii=False, indent=2)

print(f"Merged {len(all_data)} objects from {len(json_files)} files")
PYTHON_SCRIPT
    
    # Xóa thư mục temp
    rm -rf "$TEMP_DIR"
    
    # Hiển thị thống kê
    if [ ${#FAILED_APPS[@]} -gt 0 ]; then
        echo -e "${YELLOW}Cảnh báo: Các apps sau không export được: ${FAILED_APPS[*]}${NC}"
    fi
    echo -e "Số apps export thành công: ${GREEN}$SUCCESS_COUNT/${#APPS[@]}${NC}"
fi

# Kiểm tra kết quả
if [ -s "$OUTPUT_FILE" ] && [ "$(cat "$OUTPUT_FILE" | wc -l)" -gt 1 ]; then
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
    echo -e "${RED}✗ Lỗi khi xuất dữ liệu! File output rỗng hoặc không hợp lệ.${NC}"
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


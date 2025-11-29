#!/bin/bash
# Script để fix quyền cho thư mục settings/logs

# Màu sắc cho output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔧 Fixing permissions for settings/logs directory...${NC}"

# Đường dẫn đến thư mục project (thay đổi nếu cần)
PROJECT_DIR="/var/www/giadungplus"
SETTINGS_LOGS_DIR="$PROJECT_DIR/settings/logs"
COOKIE_DIR="$SETTINGS_LOGS_DIR/raw_cookie"

# Kiểm tra xem có quyền sudo không
if [ "$EUID" -ne 0 ]; then 
    echo -e "${YELLOW}⚠️  Cần quyền sudo. Chạy: sudo bash fix_permissions.sh${NC}"
    exit 1
fi

# Tạo thư mục nếu chưa tồn tại
echo -e "${GREEN}📁 Creating directories if not exist...${NC}"
mkdir -p "$SETTINGS_LOGS_DIR"
mkdir -p "$COOKIE_DIR"

# Xác định user chạy Django
# Cách 1: Kiểm tra từ supervisor config (nếu có)
if [ -f "/etc/supervisor/conf.d/giadungplus.conf" ]; then
    DJANGO_USER=$(grep -E "^user=" /etc/supervisor/conf.d/giadungplus.conf | cut -d'=' -f2 | tr -d ' ')
    if [ -n "$DJANGO_USER" ] && id "$DJANGO_USER" &>/dev/null; then
        echo -e "${GREEN}✓ Tìm thấy user từ supervisor config: $DJANGO_USER${NC}"
    else
        DJANGO_USER=""
    fi
fi

# Cách 2: Kiểm tra từ process gunicorn (nếu chưa tìm thấy)
if [ -z "$DJANGO_USER" ]; then
    GUNICORN_USER=$(ps aux | grep -E '[g]unicorn.*giadungplus' | head -1 | awk '{print $1}')
    # Loại bỏ các ký tự đặc biệt không hợp lệ (chỉ giữ chữ cái, số, gạch dưới, gạch ngang)
    GUNICORN_USER=$(echo "$GUNICORN_USER" | sed 's/[^a-zA-Z0-9_-]//g')
    
    if [ -n "$GUNICORN_USER" ] && id "$GUNICORN_USER" &>/dev/null; then
        DJANGO_USER="$GUNICORN_USER"
        echo -e "${GREEN}✓ Tìm thấy user từ gunicorn process: $DJANGO_USER${NC}"
    fi
fi

# Cách 3: Fallback - thử các user phổ biến
if [ -z "$DJANGO_USER" ]; then
    for user in "www-data" "nginx" "giadungplus" "ubuntu"; do
        if id "$user" &>/dev/null; then
            DJANGO_USER="$user"
            echo -e "${YELLOW}⚠️  Sử dụng user mặc định: $DJANGO_USER${NC}"
            break
        fi
    done
fi

# Cách 4: Cuối cùng dùng user hiện tại (trừ root)
if [ -z "$DJANGO_USER" ] || [ "$DJANGO_USER" = "root" ]; then
    CURRENT_USER=$(whoami)
    if [ "$CURRENT_USER" != "root" ] && id "$CURRENT_USER" &>/dev/null; then
        DJANGO_USER="$CURRENT_USER"
        echo -e "${YELLOW}⚠️  Sử dụng user hiện tại: $DJANGO_USER${NC}"
    else
        echo -e "${RED}❌ Không thể xác định user Django. Vui lòng chỉ định thủ công.${NC}"
        exit 1
    fi
fi

# Validate user cuối cùng
if ! id "$DJANGO_USER" &>/dev/null; then
    echo -e "${RED}❌ User '$DJANGO_USER' không tồn tại!${NC}"
    exit 1
fi

# Cấp quyền cho thư mục settings/logs
echo -e "${GREEN}🔐 Setting permissions...${NC}"
chown -R $DJANGO_USER:$DJANGO_USER "$SETTINGS_LOGS_DIR"
chmod -R 775 "$SETTINGS_LOGS_DIR"

# Đảm bảo thư mục raw_cookie có quyền ghi
chown -R $DJANGO_USER:$DJANGO_USER "$COOKIE_DIR"
chmod -R 775 "$COOKIE_DIR"

# Cấp quyền cho các file hiện có trong thư mục
if [ -d "$COOKIE_DIR" ]; then
    find "$COOKIE_DIR" -type f -exec chmod 664 {} \;
    find "$COOKIE_DIR" -type d -exec chmod 775 {} \;
fi

echo -e "${GREEN}✅ Done! Permissions fixed.${NC}"
echo -e "${GREEN}📋 Summary:${NC}"
echo -e "   Directory: $SETTINGS_LOGS_DIR"
echo -e "   Owner: $DJANGO_USER:$DJANGO_USER"
echo -e "   Permissions: 775 (directories), 664 (files)"


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

# Xác định user chạy Django (thường là www-data hoặc user hiện tại)
# Kiểm tra xem có process gunicorn đang chạy không
DJANGO_USER=$(ps aux | grep -E '[g]unicorn|python.*manage.py' | head -1 | awk '{print $1}')

if [ -z "$DJANGO_USER" ]; then
    # Nếu không tìm thấy, dùng www-data (mặc định cho web server)
    DJANGO_USER="www-data"
    echo -e "${YELLOW}⚠️  Không tìm thấy user Django, sử dụng: $DJANGO_USER${NC}"
else
    echo -e "${GREEN}✓ Tìm thấy user Django: $DJANGO_USER${NC}"
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


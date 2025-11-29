#!/bin/bash
# Script backup database và files cho GIADUNGPLUS
# Chạy với quyền root hoặc user có quyền: sudo bash backup.sh

set -e

# Cấu hình
BACKUP_DIR="/var/backups/giadungplus"
DATE=$(date +%Y%m%d_%H%M%S)
PROJECT_DIR="/var/www/giadungplus"
DB_NAME="giadungplus_db"
DB_USER="giadungplus"
DB_PASSWORD="123122aC@"

# Màu sắc
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}💾 Bắt đầu backup...${NC}"

# Tạo thư mục backup
mkdir -p $BACKUP_DIR

# Backup database
echo -e "${YELLOW}🗄️  Backup database...${NC}"
export PGPASSWORD="${DB_PASSWORD}"
if pg_dump -U ${DB_USER} -h localhost -d ${DB_NAME} > $BACKUP_DIR/db_$DATE.sql 2>/dev/null; then
    echo -e "${GREEN}✅ Database backup thành công: db_$DATE.sql${NC}"
    # Nén file
    gzip $BACKUP_DIR/db_$DATE.sql
    echo -e "${GREEN}✅ Đã nén: db_$DATE.sql.gz${NC}"
else
    echo -e "${RED}❌ Lỗi khi backup database${NC}"
    # Thử với sudo -u postgres nếu pg_dump trực tiếp không được
    if sudo -u postgres pg_dump ${DB_NAME} > $BACKUP_DIR/db_$DATE.sql 2>/dev/null; then
        echo -e "${GREEN}✅ Database backup thành công (dùng postgres user): db_$DATE.sql${NC}"
        gzip $BACKUP_DIR/db_$DATE.sql
    else
        echo -e "${RED}❌ Lỗi khi backup database${NC}"
        exit 1
    fi
fi
unset PGPASSWORD

# Backup media files (nếu có)
if [ -d "$PROJECT_DIR/media" ]; then
    echo -e "${YELLOW}📁 Backup media files...${NC}"
    tar -czf $BACKUP_DIR/media_$DATE.tar.gz -C $PROJECT_DIR media
    echo -e "${GREEN}✅ Media backup thành công: media_$DATE.tar.gz${NC}"
fi

# Backup static files (nếu cần)
if [ -d "$PROJECT_DIR/staticfiles" ]; then
    echo -e "${YELLOW}📁 Backup static files...${NC}"
    tar -czf $BACKUP_DIR/static_$DATE.tar.gz -C $PROJECT_DIR staticfiles
    echo -e "${GREEN}✅ Static files backup thành công: static_$DATE.tar.gz${NC}"
fi

# Backup code (tùy chọn - có thể bỏ qua nếu dùng git)
if [ -d "$PROJECT_DIR/.git" ]; then
    echo -e "${YELLOW}📁 Backup code (git archive)...${NC}"
    cd $PROJECT_DIR
    git archive --format=tar.gz --output=$BACKUP_DIR/code_$DATE.tar.gz HEAD 2>/dev/null || echo -e "${YELLOW}⚠️  Không thể backup code qua git${NC}"
fi

# Backup cấu hình (Supervisor, Traefik)
echo -e "${YELLOW}📁 Backup cấu hình hệ thống...${NC}"
mkdir -p $BACKUP_DIR/config_$DATE
if [ -f "/etc/supervisor/conf.d/giadungplus.conf" ]; then
    cp /etc/supervisor/conf.d/giadungplus.conf $BACKUP_DIR/config_$DATE/
fi
if [ -f "/etc/traefik/traefik.yml" ]; then
    cp /etc/traefik/traefik.yml $BACKUP_DIR/config_$DATE/
fi
if [ -f "/etc/traefik/dynamic/dynamic.yml" ]; then
    cp /etc/traefik/dynamic/dynamic.yml $BACKUP_DIR/config_$DATE/
fi
if [ -f "$PROJECT_DIR/GIADUNGPLUS/settings_production.py" ]; then
    cp $PROJECT_DIR/GIADUNGPLUS/settings_production.py $BACKUP_DIR/config_$DATE/
fi
tar -czf $BACKUP_DIR/config_$DATE.tar.gz -C $BACKUP_DIR config_$DATE
rm -rf $BACKUP_DIR/config_$DATE
echo -e "${GREEN}✅ Backup cấu hình thành công: config_$DATE.tar.gz${NC}"

# Xóa backup cũ hơn 7 ngày
echo -e "${YELLOW}🧹 Xóa backup cũ hơn 7 ngày...${NC}"
find $BACKUP_DIR -type f -mtime +7 -delete
echo -e "${GREEN}✅ Đã xóa backup cũ${NC}"

# Hiển thị thông tin backup
echo -e "${GREEN}✨ Backup hoàn tất!${NC}"
echo -e "${GREEN}📊 Thông tin backup:${NC}"
ls -lh $BACKUP_DIR/*$DATE* 2>/dev/null || echo "Không có file backup mới"

# Tính tổng dung lượng backup
TOTAL_SIZE=$(du -sh $BACKUP_DIR | cut -f1)
echo -e "${GREEN}💾 Tổng dung lượng backup: $TOTAL_SIZE${NC}"

# Hiển thị hướng dẫn restore
echo -e "${YELLOW}📖 Để restore database:${NC}"
echo -e "   gunzip -c $BACKUP_DIR/db_$DATE.sql.gz | psql -U ${DB_USER} -h localhost -d ${DB_NAME}"
echo -e "   hoặc: gunzip -c $BACKUP_DIR/db_$DATE.sql.gz | sudo -u postgres psql ${DB_NAME}"

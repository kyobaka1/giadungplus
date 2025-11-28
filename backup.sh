#!/bin/bash
# Script backup database và files cho GIADUNGPLUS
# Chạy với quyền root hoặc user có quyền: sudo bash backup.sh

set -e

# Cấu hình
BACKUP_DIR="/var/backups/giadungplus"
DATE=$(date +%Y%m%d_%H%M%S)
PROJECT_DIR="/var/www/giadungplus"
DB_NAME="giadungplus_db"
DB_USER="giadungplus_user"

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
if sudo -u postgres pg_dump $DB_NAME > $BACKUP_DIR/db_$DATE.sql 2>/dev/null; then
    echo -e "${GREEN}✅ Database backup thành công: db_$DATE.sql${NC}"
    # Nén file
    gzip $BACKUP_DIR/db_$DATE.sql
else
    echo -e "${RED}❌ Lỗi khi backup database${NC}"
    exit 1
fi

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


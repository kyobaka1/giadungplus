#!/bin/bash
# Script để migrate database từ SQLite (Windows/Dev) sang PostgreSQL (Production)
# Sử dụng: ./migrate_db_to_postgresql.sh

set -e

# Màu sắc
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🗄️  Migrate Database từ SQLite sang PostgreSQL${NC}"
echo ""

# Cấu hình
SQLITE_DB="${1:-db.sqlite3}"
BACKUP_DIR="./db_backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/sqlite_backup_${TIMESTAMP}.db"

# Tạo thư mục backup
mkdir -p "$BACKUP_DIR"

# Kiểm tra file SQLite có tồn tại không
if [ ! -f "$SQLITE_DB" ]; then
    echo -e "${RED}❌ Không tìm thấy file SQLite: $SQLITE_DB${NC}"
    exit 1
fi

echo -e "${YELLOW}📋 Các bước migrate:${NC}"
echo "  1. Backup SQLite database"
echo "  2. Export data từ SQLite"
echo "  3. Tạo schema trên PostgreSQL (migrations)"
echo "  4. Import data vào PostgreSQL"
echo ""

read -p "Bạn có muốn tiếp tục? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Đã hủy.${NC}"
    exit 0
fi

# Bước 1: Backup SQLite
echo -e "${YELLOW}📦 Bước 1: Backup SQLite database...${NC}"
cp "$SQLITE_DB" "$BACKUP_FILE"
echo -e "${GREEN}✅ Đã backup SQLite vào: $BACKUP_FILE${NC}"

# Bước 2: Export data từ SQLite
echo -e "${YELLOW}📤 Bước 2: Export data từ SQLite...${NC}"

# Tạo script Python để export data
cat > /tmp/export_sqlite.py <<'PYEOF'
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GIADUNGPLUS.settings')
django.setup()

from django.core import serializers
from django.apps import apps

# Lấy tất cả models
all_models = []
for app_config in apps.get_app_configs():
    for model in app_config.get_models():
        all_models.append(model)

# Export data
output_file = '/tmp/sqlite_data.json'
with open(output_file, 'w', encoding='utf-8') as f:
    for model in all_models:
        try:
            objects = model.objects.all()
            if objects.exists():
                data = serializers.serialize('json', objects, ensure_ascii=False, indent=2)
                f.write(f"# Model: {model.__name__}\n")
                f.write(data)
                f.write("\n\n")
                print(f"✅ Exported {model.__name__}: {objects.count()} objects")
        except Exception as e:
            print(f"⚠️  Warning: Could not export {model.__name__}: {e}")

print(f"\n✅ Export completed: {output_file}")
PYEOF

# Chạy export (với settings SQLite)
python /tmp/export_sqlite.py
EXPORT_FILE="/tmp/sqlite_data.json"

if [ ! -f "$EXPORT_FILE" ]; then
    echo -e "${RED}❌ Export failed!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Đã export data vào: $EXPORT_FILE${NC}"

# Bước 3: Tạo schema trên PostgreSQL
echo -e "${YELLOW}🗄️  Bước 3: Tạo schema trên PostgreSQL (chạy migrations)...${NC}"
echo -e "${BLUE}   Lưu ý: Bạn cần chạy trên server với settings_production.py${NC}"
echo ""
echo -e "${YELLOW}Trên server Ubuntu, chạy:${NC}"
echo -e "${BLUE}   cd /var/www/giadungplus${NC}"
echo -e "${BLUE}   source venv/bin/activate${NC}"
echo -e "${BLUE}   python manage.py migrate --settings=GIADUNGPLUS.settings_production${NC}"
echo ""

read -p "Đã chạy migrations trên server chưa? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}⚠️  Vui lòng chạy migrations trước khi tiếp tục.${NC}"
    exit 0
fi

# Bước 4: Import data vào PostgreSQL
echo -e "${YELLOW}📥 Bước 4: Import data vào PostgreSQL...${NC}"
echo -e "${BLUE}   Copy file $EXPORT_FILE lên server và chạy script import${NC}"
echo ""

# Tạo script import cho server
cat > /tmp/import_to_postgresql.py <<'PYEOF'
import os
import sys
import django
import json

# Setup Django với settings production
sys.path.insert(0, '/var/www/giadungplus')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GIADUNGPLUS.settings_production')
django.setup()

from django.core import serializers
from django.apps import apps
from django.db import transaction

EXPORT_FILE = '/tmp/sqlite_data.json'

if not os.path.exists(EXPORT_FILE):
    print(f"❌ File không tồn tại: {EXPORT_FILE}")
    sys.exit(1)

print(f"📥 Đang import từ: {EXPORT_FILE}")

# Đọc file export
with open(EXPORT_FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# Parse JSON data
# File có format: # Model: ModelName\n{json}\n\n
models_data = {}
current_model = None
current_json = []

for line in content.split('\n'):
    if line.startswith('# Model:'):
        if current_model and current_json:
            models_data[current_model] = '\n'.join(current_json)
        current_model = line.replace('# Model:', '').strip()
        current_json = []
    elif line.strip() and not line.startswith('#'):
        current_json.append(line)

if current_model and current_json:
    models_data[current_model] = '\n'.join(current_json)

# Import từng model
total_imported = 0
with transaction.atomic():
    for model_name, json_data in models_data.items():
        try:
            # Tìm model
            model = None
            for app_config in apps.get_app_configs():
                try:
                    model = app_config.get_model(model_name)
                    break
                except:
                    continue
            
            if not model:
                print(f"⚠️  Không tìm thấy model: {model_name}")
                continue
            
            # Deserialize và save
            objects = serializers.deserialize('json', json_data)
            count = 0
            for obj in objects:
                try:
                    obj.save()
                    count += 1
                except Exception as e:
                    print(f"⚠️  Lỗi khi save {model_name} object: {e}")
            
            print(f"✅ Imported {model_name}: {count} objects")
            total_imported += count
            
        except Exception as e:
            print(f"❌ Lỗi khi import {model_name}: {e}")

print(f"\n✅ Import hoàn tất! Tổng cộng: {total_imported} objects")
PYEOF

echo -e "${GREEN}✅ Đã tạo script import: /tmp/import_to_postgresql.py${NC}"
echo ""
echo -e "${YELLOW}📋 Hướng dẫn tiếp theo:${NC}"
echo -e "${BLUE}1. Copy file $EXPORT_FILE lên server:${NC}"
echo -e "   scp $EXPORT_FILE user@server:/tmp/"
echo ""
echo -e "${BLUE}2. Copy script import lên server:${NC}"
echo -e "   scp /tmp/import_to_postgresql.py user@server:/tmp/"
echo ""
echo -e "${BLUE}3. Trên server, chạy import:${NC}"
echo -e "   cd /var/www/giadungplus"
echo -e "   source venv/bin/activate"
echo -e "   python /tmp/import_to_postgresql.py"
echo ""

echo -e "${GREEN}✨ Hoàn tất!${NC}"


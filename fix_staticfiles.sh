#!/bin/bash
# Script để fix lỗi STATIC_ROOT trên server
# Chạy trên server Ubuntu: bash fix_staticfiles.sh

set -e

PROJECT_DIR="/var/www/giadungplus"

echo "🔧 Fixing STATIC_ROOT configuration..."

# Tạo thư mục staticfiles
echo "📁 Creating staticfiles directory..."
mkdir -p ${PROJECT_DIR}/staticfiles
chmod 755 ${PROJECT_DIR}/staticfiles

# Tạo thư mục assets nếu chưa có
echo "📁 Creating assets directory..."
mkdir -p ${PROJECT_DIR}/assets
chmod 755 ${PROJECT_DIR}/assets

# Set ownership nếu có quyền
if [ "$EUID" -eq 0 ]; then
    chown -R giadungplus:giadungplus ${PROJECT_DIR}/staticfiles 2>/dev/null || true
    chown -R giadungplus:giadungplus ${PROJECT_DIR}/assets 2>/dev/null || true
fi

echo "✅ Directories created successfully!"

# Chạy collectstatic
if [ -d "${PROJECT_DIR}/venv" ]; then
    echo "📦 Collecting static files..."
    cd ${PROJECT_DIR}
    source venv/bin/activate
    python manage.py collectstatic --noinput --settings=GIADUNGPLUS.settings_production
    echo "✅ Static files collected!"
else
    echo "⚠️  Virtual environment not found. Please run collectstatic manually:"
    echo "   cd ${PROJECT_DIR}"
    echo "   source venv/bin/activate"
    echo "   python manage.py collectstatic --noinput --settings=GIADUNGPLUS.settings_production"
fi


#!/bin/bash
# Script để fix lỗi blinker trên server
# Chạy trên server Ubuntu: bash fix_blinker.sh

set -e

echo "🔧 Fixing blinker version conflict..."

PROJECT_DIR="/var/www/giadungplus"
VENV_DIR="${PROJECT_DIR}/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "❌ Virtual environment not found at $VENV_DIR"
    exit 1
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Uninstall blinker và selenium-wire
echo "📦 Uninstalling conflicting packages..."
pip uninstall -y blinker selenium-wire || true

# Cài đặt lại với version tương thích
echo "📦 Installing compatible versions..."
pip install blinker==1.6.3
pip install selenium-wire

echo "✅ Fixed! Blinker version:"
pip show blinker | grep Version

echo ""
echo "🔄 Restarting service..."
sudo supervisorctl restart giadungplus || echo "⚠️  Please restart service manually: sudo supervisorctl restart giadungplus"


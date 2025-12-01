#!/bin/bash
# fix-permission.sh
# Script để fix quyền execute cho chromedriver-linux trên Linux server

set -e  # Exit on error

echo "🔧 [Fix Permission] Bắt đầu fix quyền cho ChromeDriver..."

# Xác định đường dẫn project (giả sử script nằm ở root của project)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Các đường dẫn có thể có chromedriver
POSSIBLE_PATHS=(
    "$PROJECT_ROOT/chromedriver-linux"
    "$PROJECT_ROOT/chromedriver"
    "/usr/bin/chromedriver"
    "/usr/local/bin/chromedriver"
)

CHROMEDRIVER_PATH=""

# Tìm chromedriver
echo "🔍 [Fix Permission] Đang tìm ChromeDriver..."
for path in "${POSSIBLE_PATHS[@]}"; do
    if [ -f "$path" ]; then
        CHROMEDRIVER_PATH="$path"
        echo "   ✅ Tìm thấy tại: $CHROMEDRIVER_PATH"
        break
    fi
done

if [ -z "$CHROMEDRIVER_PATH" ]; then
    echo "   ⚠️  Không tìm thấy ChromeDriver tại các vị trí thông thường"
    echo "   💡 Vui lòng chỉ định đường dẫn: ./fix-permission.sh /path/to/chromedriver-linux"
    
    # Nếu có argument, dùng argument đó
    if [ -n "$1" ]; then
        CHROMEDRIVER_PATH="$1"
        if [ ! -f "$CHROMEDRIVER_PATH" ]; then
            echo "   ❌ File không tồn tại: $CHROMEDRIVER_PATH"
            exit 1
        fi
    else
        echo "   ❌ Không thể tìm thấy ChromeDriver"
        exit 1
    fi
fi

# Kiểm tra quyền hiện tại
echo ""
echo "📋 [Fix Permission] Kiểm tra quyền hiện tại..."
CURRENT_PERM=$(stat -c "%a" "$CHROMEDRIVER_PATH" 2>/dev/null || stat -f "%OLp" "$CHROMEDRIVER_PATH" 2>/dev/null)
echo "   - Quyền hiện tại: $CURRENT_PERM"

# Kiểm tra xem đã có quyền execute chưa
if [ -x "$CHROMEDRIVER_PATH" ]; then
    echo "   ✅ File đã có quyền execute"
    echo "   💡 Nếu vẫn gặp lỗi, thử chạy với sudo: sudo ./fix-permission.sh"
    exit 0
fi

# Set quyền execute
echo ""
echo "🔐 [Fix Permission] Đang set quyền execute..."
if chmod +x "$CHROMEDRIVER_PATH" 2>/dev/null; then
    echo "   ✅ Đã set quyền execute thành công"
else
    echo "   ⚠️  Không thể set quyền (có thể cần sudo)"
    echo "   💡 Thử chạy: sudo chmod +x $CHROMEDRIVER_PATH"
    exit 1
fi

# Kiểm tra lại
NEW_PERM=$(stat -c "%a" "$CHROMEDRIVER_PATH" 2>/dev/null || stat -f "%OLp" "$CHROMEDRIVER_PATH" 2>/dev/null)
echo "   - Quyền mới: $NEW_PERM"

# Test xem có chạy được không
echo ""
echo "🧪 [Fix Permission] Test ChromeDriver..."
if "$CHROMEDRIVER_PATH" --version >/dev/null 2>&1; then
    VERSION=$("$CHROMEDRIVER_PATH" --version 2>/dev/null | head -n1)
    echo "   ✅ ChromeDriver hoạt động bình thường"
    echo "   📌 Version: $VERSION"
else
    echo "   ⚠️  ChromeDriver không chạy được (có thể thiếu dependencies)"
    echo "   💡 Kiểm tra:"
    echo "      - Chrome/Chromium đã được cài đặt chưa?"
    echo "      - ChromeDriver version có khớp với Chrome không?"
    echo "      - Đã cài đặt các dependencies: libnss3, libatk-bridge2.0-0, etc."
fi

echo ""
echo "✅ [Fix Permission] Hoàn thành!"


#!/bin/bash
# Script xóa cache Python (.pyc files và __pycache__ directories)
# Chạy khi code đã được update nhưng vẫn gặp lỗi về function signature

set -e

# Màu sắc
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🧹 Đang xóa cache Python...${NC}"

# Tìm và xóa tất cả __pycache__ directories
find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true

# Tìm và xóa tất cả .pyc files
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Tìm và xóa .pyo files
find . -type f -name "*.pyo" -delete 2>/dev/null || true

echo -e "${GREEN}✅ Đã xóa cache Python thành công!${NC}"
echo -e "${YELLOW}💡 Lưu ý: Nếu đang chạy Gunicorn, cần restart service:${NC}"
echo -e "${GREEN}   sudo supervisorctl restart giadungplus${NC}"


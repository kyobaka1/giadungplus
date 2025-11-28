#!/bin/bash
# Script tự động deploy GIADUNGPLUS lên server
# Sử dụng: ./deploy.sh

set -e  # Dừng nếu có lỗi

echo "🚀 Bắt đầu deploy GIADUNGPLUS..."

# Màu sắc cho output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Kiểm tra đang ở đúng thư mục
if [ ! -f "manage.py" ]; then
    echo -e "${RED}❌ Lỗi: Không tìm thấy manage.py. Hãy chạy script trong thư mục gốc của project.${NC}"
    exit 1
fi

# Activate virtual environment nếu có
if [ -d "venv" ]; then
    echo -e "${YELLOW}📦 Activating virtual environment...${NC}"
    source venv/bin/activate
fi

# Pull code mới (nếu dùng git)
if [ -d ".git" ]; then
    echo -e "${YELLOW}📥 Pulling latest code...${NC}"
    git pull origin main || git pull origin master
fi

# Cài đặt/update dependencies
if [ -f "requirements.txt" ]; then
    echo -e "${YELLOW}📦 Installing dependencies...${NC}"
    pip install -r requirements.txt --upgrade
else
    echo -e "${YELLOW}📦 Installing dependencies from rq.txt...${NC}"
    pip install django xlrd==1.2.0 requests lxml py3dbp==1.1.2 selenium selenium-wire pypdf2 htmlparser pillow python-barcode qrcode xlsxwriter pdfplumber fpdf reportlab BeautifulSoup4 django-sslserver setuptools pygame openpyxl gspread djangorestframework oauth2client blinker==1.7.0 whitenoise openai pandas "pydantic>=2.0.0" python-dateutil psycopg2-binary gunicorn --upgrade
fi

# Chạy migrations
echo -e "${YELLOW}🗄️  Running migrations...${NC}"
python manage.py migrate --noinput

# Collect static files
echo -e "${YELLOW}📁 Collecting static files...${NC}"
python manage.py collectstatic --noinput

# Restart Gunicorn service
echo -e "${YELLOW}🔄 Restarting Gunicorn service...${NC}"
sudo systemctl restart giadungplus || echo -e "${RED}⚠️  Không thể restart service. Hãy kiểm tra manually.${NC}"

# Kiểm tra status
echo -e "${YELLOW}✅ Checking service status...${NC}"
sudo systemctl status giadungplus --no-pager -l || true

echo -e "${GREEN}✨ Deploy hoàn tất!${NC}"
echo -e "${GREEN}📊 Xem logs: sudo journalctl -u giadungplus -f${NC}"


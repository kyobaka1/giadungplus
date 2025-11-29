#!/bin/bash
# Script tự động deploy GIADUNGPLUS lên server
# Sử dụng Supervisor để quản lý Gunicorn
# Sử dụng: ./deploy.sh

set -e  # Dừng nếu có lỗi

echo "🚀 Bắt đầu deploy GIADUNGPLUS..."

# Màu sắc cho output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Cấu hình
PROJECT_DIR="/var/www/giadungplus"
SUPERVISOR_CONF="/etc/supervisor/conf.d/giadungplus.conf"

# Kiểm tra đang ở đúng thư mục
if [ ! -f "manage.py" ]; then
    echo -e "${RED}❌ Lỗi: Không tìm thấy manage.py. Hãy chạy script trong thư mục gốc của project.${NC}"
    exit 1
fi

# Activate virtual environment nếu có
if [ -d "venv" ]; then
    echo -e "${YELLOW}📦 Activating virtual environment...${NC}"
    source venv/bin/activate
else
    echo -e "${YELLOW}📦 Tạo virtual environment...${NC}"
    python3.10 -m venv venv
    source venv/bin/activate
fi

# Pull code mới (nếu dùng git)
if [ -d ".git" ]; then
    echo -e "${YELLOW}📥 Pulling latest code...${NC}"
    
    # Xử lý lỗi Git ownership (khi chạy với user khác owner của repo)
    # Thêm safe.directory trước khi pull
    CURRENT_DIR=$(pwd)
    git config --global --add safe.directory "$CURRENT_DIR" 2>/dev/null || true
    git config --global --add safe.directory "/var/www/giadungplus" 2>/dev/null || true
    
    # Pull code
    if git pull origin main 2>/dev/null || git pull origin master 2>/dev/null; then
        echo -e "${GREEN}✅ Đã pull code thành công${NC}"
    else
        echo -e "${YELLOW}⚠️  Không thể pull code (có thể chưa có remote, không có thay đổi, hoặc đã up-to-date)${NC}"
    fi
fi

# Cài đặt/update dependencies
if [ -f "requirements.txt" ]; then
    echo -e "${YELLOW}📦 Installing dependencies...${NC}"
    pip install --upgrade pip
    pip install -r requirements.txt --upgrade
else
    echo -e "${YELLOW}📦 Installing dependencies from rq.txt...${NC}"
    pip install --upgrade pip
    pip install django xlrd==1.2.0 requests lxml py3dbp==1.1.2 selenium selenium-wire pypdf2 htmlparser pillow python-barcode qrcode xlsxwriter pdfplumber fpdf reportlab BeautifulSoup4 django-sslserver setuptools pygame openpyxl gspread djangorestframework oauth2client blinker==1.7.0 whitenoise openai pandas "pydantic>=2.0.0" python-dateutil psycopg2-binary gunicorn --upgrade
fi

# Chạy migrations
echo -e "${YELLOW}🗄️  Running migrations...${NC}"
python manage.py migrate --noinput --settings=GIADUNGPLUS.settings_production

# Collect static files
echo -e "${YELLOW}📁 Collecting static files...${NC}"
python manage.py collectstatic --noinput --settings=GIADUNGPLUS.settings_production

# Tạo file cấu hình Supervisor cho Gunicorn
echo -e "${YELLOW}⚙️  Cấu hình Supervisor...${NC}"

sudo tee ${SUPERVISOR_CONF} > /dev/null <<EOF
[program:giadungplus]
directory=${PROJECT_DIR}
command=${PROJECT_DIR}/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 --timeout 120 --access-logfile ${PROJECT_DIR}/logs/gunicorn-access.log --error-logfile ${PROJECT_DIR}/logs/gunicorn-error.log GIADUNGPLUS.wsgi:application
user=giadungplus
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stderr_logfile=${PROJECT_DIR}/logs/gunicorn-supervisor-error.log
stdout_logfile=${PROJECT_DIR}/logs/gunicorn-supervisor.log
environment=PATH="${PROJECT_DIR}/venv/bin",DJANGO_SETTINGS_MODULE="GIADUNGPLUS.settings_production"
EOF

# Tạo thư mục logs nếu chưa có
mkdir -p ${PROJECT_DIR}/logs
chown -R giadungplus:giadungplus ${PROJECT_DIR}/logs

# Reload và restart Supervisor
echo -e "${YELLOW}🔄 Reloading Supervisor configuration...${NC}"
sudo supervisorctl reread
sudo supervisorctl update

# Restart service
echo -e "${YELLOW}🔄 Restarting GIADUNGPLUS service...${NC}"
sudo supervisorctl restart giadungplus || sudo supervisorctl start giadungplus

# Kiểm tra status
echo -e "${YELLOW}✅ Checking service status...${NC}"
sudo supervisorctl status giadungplus

echo -e "${GREEN}✨ Deploy hoàn tất!${NC}"
echo -e "${GREEN}📊 Xem logs Supervisor: sudo supervisorctl tail -f giadungplus${NC}"
echo -e "${GREEN}📊 Xem logs Gunicorn: tail -f ${PROJECT_DIR}/logs/gunicorn-*.log${NC}"
echo -e "${GREEN}📊 Quản lý service: sudo supervisorctl {start|stop|restart} giadungplus${NC}"

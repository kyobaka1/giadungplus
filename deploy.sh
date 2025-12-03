#!/bin/bash
# Script tự động deploy GIADUNGPLUS lên server
# Hỗ trợ GitHub webhook để tự động deploy khi có push
# Sử dụng Supervisor để quản lý Gunicorn
# Sử dụng: ./deploy.sh [--force] [--skip-migrations]

set -e  # Dừng nếu có lỗi

# Màu sắc cho output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
FORCE_DEPLOY=false
SKIP_MIGRATIONS=false
for arg in "$@"; do
    case $arg in
        --force)
            FORCE_DEPLOY=true
            shift
            ;;
        --skip-migrations)
            SKIP_MIGRATIONS=true
            shift
            ;;
        *)
            ;;
    esac
done

# Cấu hình
PROJECT_DIR="/var/www/giadungplus"
SUPERVISOR_CONF="/etc/supervisor/conf.d/giadungplus.conf"
VENV_DIR="${PROJECT_DIR}/venv"
LOG_DIR="${PROJECT_DIR}/logs"

echo -e "${BLUE}🚀 Bắt đầu deploy GIADUNGPLUS...${NC}"

# Kiểm tra đang ở đúng thư mục
if [ ! -f "manage.py" ]; then
    echo -e "${RED}❌ Lỗi: Không tìm thấy manage.py. Hãy chạy script trong thư mục gốc của project.${NC}"
    exit 1
fi

# Kiểm tra quyền sudo (nếu cần)
if [ "$EUID" -ne 0 ] && [ "$FORCE_DEPLOY" = false ]; then
    echo -e "${YELLOW}⚠️  Chạy với quyền user thường. Một số lệnh có thể cần sudo.${NC}"
fi

# Activate virtual environment nếu có
if [ -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}📦 Activating virtual environment...${NC}"
    source "$VENV_DIR/bin/activate"
else
    echo -e "${YELLOW}📦 Tạo virtual environment...${NC}"
    python3.10 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
fi

# Pull code mới từ GitHub (nếu dùng git)
if [ -d ".git" ]; then
    echo -e "${YELLOW}📥 Pulling latest code from GitHub...${NC}"
    
    # Xử lý lỗi Git ownership (khi chạy với user khác owner của repo)
    CURRENT_DIR=$(pwd)
    git config --global --add safe.directory "$CURRENT_DIR" 2>/dev/null || true
    git config --global --add safe.directory "$PROJECT_DIR" 2>/dev/null || true
    
    # Lưu commit hash trước khi pull
    OLD_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "")
    
    # Pull code
    if git pull origin main 2>/dev/null || git pull origin master 2>/dev/null; then
        NEW_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "")
        if [ "$OLD_COMMIT" != "$NEW_COMMIT" ]; then
            echo -e "${GREEN}✅ Đã pull code mới (${NEW_COMMIT:0:7})${NC}"
        else
            echo -e "${YELLOW}ℹ️  Code đã là mới nhất${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  Không thể pull code (có thể chưa có remote, không có thay đổi, hoặc đã up-to-date)${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Không phát hiện Git repository. Bỏ qua bước pull code.${NC}"
fi

# Xóa cache Python trước khi deploy
echo -e "${YELLOW}🧹 Clearing Python cache...${NC}"
find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
echo -e "${GREEN}✅ Python cache cleared${NC}"

# Cài đặt/update dependencies
if [ -f "requirements.txt" ]; then
    echo -e "${YELLOW}📦 Installing/updating dependencies...${NC}"
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --upgrade --quiet
else
    echo -e "${YELLOW}📦 Installing dependencies from default list...${NC}"
    pip install --upgrade pip --quiet
    pip install django xlrd==1.2.0 requests lxml py3dbp==1.1.2 selenium selenium-wire pypdf2 htmlparser pillow python-barcode qrcode xlsxwriter pdfplumber fpdf reportlab BeautifulSoup4 django-sslserver setuptools pygame openpyxl gspread djangorestframework oauth2client blinker==1.6.3 whitenoise openai pandas "pydantic>=2.0.0" python-dateutil psycopg2-binary gunicorn --upgrade --quiet
fi

# Chạy migrations (trừ khi skip)
if [ "$SKIP_MIGRATIONS" = false ]; then
    echo -e "${YELLOW}🗄️  Running database migrations...${NC}"
    python manage.py migrate --noinput --settings=GIADUNGPLUS.settings_production
    
    # Kiểm tra xem có migration mới không
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Migrations completed successfully${NC}"
    else
        echo -e "${RED}❌ Migration failed! Please check the error above.${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⏭️  Skipping migrations (--skip-migrations flag)${NC}"
fi

# Tạo thư mục staticfiles trước khi collectstatic
echo -e "${YELLOW}📁 Creating staticfiles directory...${NC}"
mkdir -p ${PROJECT_DIR}/staticfiles
chmod 755 ${PROJECT_DIR}/staticfiles 2>/dev/null || true

# Collect static files
echo -e "${YELLOW}📁 Collecting static files...${NC}"
python manage.py collectstatic --noinput --settings=GIADUNGPLUS.settings_production
echo -e "${GREEN}✅ Static files collected${NC}"

# Tạo thư mục logs nếu chưa có
mkdir -p "$LOG_DIR"
if [ "$EUID" -eq 0 ]; then
    chown -R giadungplus:giadungplus "$LOG_DIR" 2>/dev/null || true
fi

# Tạo file cấu hình Supervisor cho Gunicorn
echo -e "${YELLOW}⚙️  Cấu hình Supervisor...${NC}"

if [ "$EUID" -eq 0 ]; then
    sudo tee ${SUPERVISOR_CONF} > /dev/null <<EOF
[program:giadungplus]
directory=${PROJECT_DIR}
command=${VENV_DIR}/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 --timeout 120 --access-logfile ${LOG_DIR}/gunicorn-access.log --error-logfile ${LOG_DIR}/gunicorn-error.log GIADUNGPLUS.wsgi:application
user=giadungplus
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stderr_logfile=${LOG_DIR}/gunicorn-supervisor-error.log
stdout_logfile=${LOG_DIR}/gunicorn-supervisor.log
environment=PATH="${VENV_DIR}/bin",DJANGO_SETTINGS_MODULE="GIADUNGPLUS.settings_production"
EOF
else
    echo -e "${YELLOW}⚠️  Cần quyền sudo để cập nhật Supervisor config. Bỏ qua bước này.${NC}"
fi

# Reload và restart Supervisor (nếu có quyền)
if [ "$EUID" -eq 0 ]; then
    echo -e "${YELLOW}🔄 Reloading Supervisor configuration...${NC}"
    sudo supervisorctl reread
    sudo supervisorctl update
    
    # Restart service
    echo -e "${YELLOW}🔄 Restarting GIADUNGPLUS service...${NC}"
    sudo supervisorctl restart giadungplus || sudo supervisorctl start giadungplus
    
    # Kiểm tra status
    echo -e "${YELLOW}✅ Checking service status...${NC}"
    sudo supervisorctl status giadungplus
else
    echo -e "${YELLOW}⚠️  Cần quyền sudo để restart service. Vui lòng chạy:${NC}"
    echo -e "${BLUE}   sudo supervisorctl restart giadungplus${NC}"
fi

echo -e "${GREEN}✨ Deploy hoàn tất!${NC}"
echo -e "${GREEN}📊 Xem logs Supervisor: sudo supervisorctl tail -f giadungplus${NC}"
echo -e "${GREEN}📊 Xem logs Gunicorn: tail -f ${LOG_DIR}/gunicorn-*.log${NC}"
echo -e "${GREEN}📊 Quản lý service: sudo supervisorctl {start|stop|restart} giadungplus${NC}"

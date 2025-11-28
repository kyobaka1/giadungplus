#!/bin/bash
# Script setup server Ubuntu 22.04 cho GIADUNGPLUS
# Chạy với quyền root: sudo bash setup_server.sh

set -e

echo "🚀 Bắt đầu setup server Ubuntu 22.04 cho GIADUNGPLUS..."

# Màu sắc
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Kiểm tra quyền root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Vui lòng chạy script với quyền root: sudo bash setup_server.sh${NC}"
    exit 1
fi

# 1. Cập nhật hệ thống
echo -e "${YELLOW}📦 Cập nhật hệ thống...${NC}"
apt update
apt upgrade -y

# 2. Cài đặt Python và dependencies
echo -e "${YELLOW}🐍 Cài đặt Python 3.10...${NC}"
apt install -y python3.10 python3.10-venv python3-pip python3-dev
apt install -y build-essential libssl-dev libffi-dev
apt install -y libpq-dev libjpeg-dev zlib1g-dev

# 3. Cài đặt PostgreSQL
echo -e "${YELLOW}🗄️  Cài đặt PostgreSQL...${NC}"
apt install -y postgresql postgresql-contrib
systemctl start postgresql
systemctl enable postgresql

# 4. Cài đặt Nginx
echo -e "${YELLOW}🌐 Cài đặt Nginx...${NC}"
apt install -y nginx
systemctl start nginx
systemctl enable nginx

# 5. Cài đặt Chrome cho Selenium
echo -e "${YELLOW}🌍 Cài đặt Chrome...${NC}"
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
apt update
apt install -y google-chrome-stable

# Cài dependencies cho headless Chrome
apt install -y xvfb x11vnc fluxbox wmctrl

# 6. Cài đặt các tools
echo -e "${YELLOW}🛠️  Cài đặt tools...${NC}"
apt install -y git curl wget unzip ufw

# 7. Cấu hình Firewall
echo -e "${YELLOW}🔥 Cấu hình Firewall...${NC}"
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

# 8. Tạo user cho ứng dụng
echo -e "${YELLOW}👤 Tạo user giadungplus...${NC}"
if ! id "giadungplus" &>/dev/null; then
    adduser --disabled-password --gecos "" giadungplus
    usermod -aG sudo giadungplus
    echo -e "${GREEN}✅ User giadungplus đã được tạo${NC}"
else
    echo -e "${YELLOW}⚠️  User giadungplus đã tồn tại${NC}"
fi

# 9. Tạo thư mục cho ứng dụng
echo -e "${YELLOW}📁 Tạo thư mục ứng dụng...${NC}"
mkdir -p /var/www/giadungplus
chown giadungplus:giadungplus /var/www/giadungplus

# 10. Tạo thư mục logs
mkdir -p /var/www/giadungplus/logs
chown giadungplus:giadungplus /var/www/giadungplus/logs

# 11. Cài đặt Certbot cho SSL
echo -e "${YELLOW}🔒 Cài đặt Certbot...${NC}"
apt install -y certbot python3-certbot-nginx

echo -e "${GREEN}✨ Setup server hoàn tất!${NC}"
echo -e "${GREEN}📝 Các bước tiếp theo:${NC}"
echo -e "   1. Upload code lên /var/www/giadungplus"
echo -e "   2. Tạo virtual environment: python3.10 -m venv venv"
echo -e "   3. Cài đặt dependencies"
echo -e "   4. Cấu hình database PostgreSQL"
echo -e "   5. Chạy migrations"
echo -e "   6. Cấu hình Nginx"
echo -e "   7. Cài đặt SSL: sudo certbot --nginx -d giadungplus.io.vn"
echo -e "   8. Tạo systemd service cho Gunicorn"
echo -e ""
echo -e "${YELLOW}📖 Xem hướng dẫn chi tiết trong file DEPLOYMENT_GUIDE.md${NC}"


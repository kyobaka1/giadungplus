#!/bin/bash
# Script setup server Ubuntu 22.04 cho GIADUNGPLUS
# Sử dụng Traefik (reverse proxy) và Supervisor (process manager)
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

# Cấu hình
DOMAIN="giadungplus.io.vn"
SERVER_IP="103.110.85.223"
DB_NAME="giadungplus_db"
DB_USER="giadungplus"
DB_PASSWORD="123122aC@"
PROJECT_DIR="/var/www/giadungplus"

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

# Tạo database và user
echo -e "${YELLOW}🗄️  Tạo database và user PostgreSQL...${NC}"

# Tạo user nếu chưa có
sudo -u postgres psql -c "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 || \
sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';"

# Tạo database nếu chưa có
sudo -u postgres psql -c "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 || \
sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"

# Cấp quyền và cấu hình
sudo -u postgres psql -c "ALTER ROLE ${DB_USER} SET client_encoding TO 'utf8';"
sudo -u postgres psql -c "ALTER ROLE ${DB_USER} SET default_transaction_isolation TO 'read committed';"
sudo -u postgres psql -c "ALTER ROLE ${DB_USER} SET timezone TO 'UTC';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};"

echo -e "${GREEN}✅ Database và user đã được tạo${NC}"

# 4. Cài đặt Traefik
echo -e "${YELLOW}🌐 Cài đặt Traefik...${NC}"

# Kiểm tra xem Traefik đã được cài đặt chưa
if command -v traefik &> /dev/null; then
    echo -e "${YELLOW}⚠️  Traefik đã được cài đặt, bỏ qua...${NC}"
else
    # Tạo thư mục cấu hình Traefik
    mkdir -p /etc/traefik
    mkdir -p /etc/traefik/dynamic
    mkdir -p /var/log/traefik

    # Tải Traefik binary
    TRAEFIK_VERSION="v2.11.31"
    TRAEFIK_URL="https://github.com/traefik/traefik/releases/download/${TRAEFIK_VERSION}/traefik_${TRAEFIK_VERSION}_linux_amd64.tar.gz"
    
    echo -e "${YELLOW}📥 Đang tải Traefik ${TRAEFIK_VERSION}...${NC}"
    cd /tmp
    
    # Thử tải với xử lý lỗi
    if wget --progress=bar:force -O traefik_${TRAEFIK_VERSION}_linux_amd64.tar.gz ${TRAEFIK_URL} 2>&1; then
        echo -e "${GREEN}✅ Đã tải Traefik thành công${NC}"
        
        # Giải nén
        echo -e "${YELLOW}📦 Đang giải nén Traefik...${NC}"
        if tar -xzf traefik_${TRAEFIK_VERSION}_linux_amd64.tar.gz 2>/dev/null; then
            # Tìm file traefik (có thể ở thư mục con)
            if [ -f "traefik" ]; then
                mv traefik /usr/local/bin/
            elif [ -f "traefik_${TRAEFIK_VERSION}_linux_amd64/traefik" ]; then
                mv traefik_${TRAEFIK_VERSION}_linux_amd64/traefik /usr/local/bin/
                rm -rf traefik_${TRAEFIK_VERSION}_linux_amd64
            else
                # Tìm file trong toàn bộ thư mục giải nén
                TRAEFIK_BINARY=$(find . -name "traefik" -type f 2>/dev/null | head -1)
                if [ -n "$TRAEFIK_BINARY" ]; then
                    mv "$TRAEFIK_BINARY" /usr/local/bin/traefik
                else
                    echo -e "${RED}❌ Không tìm thấy file traefik trong archive${NC}"
                    exit 1
                fi
            fi
            
            chmod +x /usr/local/bin/traefik
            rm -f traefik_${TRAEFIK_VERSION}_linux_amd64.tar.gz
            echo -e "${GREEN}✅ Traefik đã được cài đặt thành công${NC}"
        else
            echo -e "${RED}❌ Lỗi khi giải nén Traefik${NC}"
            exit 1
        fi
    else
        echo -e "${RED}❌ Không thể tải Traefik từ GitHub${NC}"
        echo -e "${YELLOW}🔄 Thử phương án cài đặt qua Snap...${NC}"
        
        # Thử cài đặt qua snap hoặc binary release mới nhất
        if command -v snap &> /dev/null; then
            snap install traefik
        else
            # Tải bản mới nhất
            echo -e "${YELLOW}🔄 Thử tải phiên bản mới nhất...${NC}"
            LATEST_URL="https://github.com/traefik/traefik/releases/latest/download/traefik_linux_amd64.tar.gz"
            if wget --progress=bar:force -O traefik_latest_linux_amd64.tar.gz ${LATEST_URL} 2>&1; then
                tar -xzf traefik_latest_linux_amd64.tar.gz
                find . -name "traefik" -type f -exec mv {} /usr/local/bin/traefik \;
                chmod +x /usr/local/bin/traefik
                rm -f traefik_latest_linux_amd64.tar.gz
                echo -e "${GREEN}✅ Traefik đã được cài đặt (phiên bản mới nhất)${NC}"
            else
                echo -e "${RED}❌ Không thể cài đặt Traefik. Vui lòng cài đặt thủ công.${NC}"
                exit 1
            fi
        fi
    fi
fi

# Kiểm tra lại sau khi cài đặt
if ! command -v traefik &> /dev/null; then
    echo -e "${RED}❌ Traefik chưa được cài đặt thành công${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Traefik đã sẵn sàng (version: $(traefik version 2>/dev/null | head -1 || echo 'unknown'))${NC}"

# Tạo file cấu hình Traefik
cat > /etc/traefik/traefik.yml <<'TRAEFIK_EOF'
global:
  checkNewVersion: false
  sendAnonymousUsage: false

api:
  dashboard: true
  insecure: true

entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
          permanent: true
  websecure:
    address: ":443"

providers:
  file:
    filename: /etc/traefik/dynamic/dynamic.yml
    watch: true

certificatesResolvers:
  letsencrypt:
    acme:
      email: admin@giadungplus.io.vn
      storage: /etc/traefik/acme.json
      httpChallenge:
        entryPoint: web
TRAEFIK_EOF

# Tạo file cấu hình động cho Traefik
echo -e "${YELLOW}⚙️  Tạo cấu hình Traefik...${NC}"
cat > /etc/traefik/dynamic/dynamic.yml <<EOF
http:
  routers:
    # Router cho domain với SSL
    giadungplus-router-https:
      rule: "Host(\`${DOMAIN}\`)"
      entryPoints:
        - websecure
      service: giadungplus-service
      tls:
        certResolver: letsencrypt
    
    # Router cho IP hoặc domain HTTP (không SSL)
    giadungplus-router-http:
      rule: "Host(\`${DOMAIN}\`) || Host(\`${SERVER_IP}\`)"
      entryPoints:
        - web
      service: giadungplus-service

  services:
    giadungplus-service:
      loadBalancer:
        servers:
          - url: "http://127.0.0.1:8000"
EOF

# Tạo file systemd service cho Traefik
echo -e "${YELLOW}⚙️  Tạo systemd service cho Traefik...${NC}"
cat > /etc/systemd/system/traefik.service <<'SERVICE_EOF'
[Unit]
Description=Traefik Reverse Proxy
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/traefik --configfile=/etc/traefik/traefik.yml
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE_EOF

# Tạo file acme.json và set permissions
echo -e "${YELLOW}⚙️  Tạo file acme.json cho SSL certificates...${NC}"
touch /etc/traefik/acme.json
chmod 600 /etc/traefik/acme.json

# Start và enable Traefik
echo -e "${YELLOW}🔄 Khởi động Traefik...${NC}"
systemctl daemon-reload

# Kiểm tra cấu hình trước khi start
if /usr/local/bin/traefik version > /dev/null 2>&1; then
    systemctl start traefik
    systemctl enable traefik
    
    # Chờ một chút để Traefik khởi động
    sleep 2
    
    # Kiểm tra status
    if systemctl is-active --quiet traefik; then
        echo -e "${GREEN}✅ Traefik đã được cài đặt và khởi động thành công${NC}"
    else
        echo -e "${RED}⚠️  Traefik service đã được enable nhưng có thể chưa chạy. Kiểm tra logs:${NC}"
        echo -e "${YELLOW}   sudo journalctl -u traefik -f${NC}"
    fi
else
    echo -e "${RED}❌ Lỗi: Không thể chạy traefik version. Kiểm tra lại cài đặt.${NC}"
    exit 1
fi

# 5. Cài đặt Supervisor
echo -e "${YELLOW}🔧 Cài đặt Supervisor...${NC}"
apt install -y supervisor

# Tạo thư mục cho supervisor configs
mkdir -p /etc/supervisor/conf.d

echo -e "${GREEN}✅ Supervisor đã được cài đặt${NC}"

# 6. Cài đặt Chrome cho Selenium
echo -e "${YELLOW}🌍 Cài đặt Chrome...${NC}"
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
apt update
apt install -y google-chrome-stable

# Cài dependencies cho headless Chrome
apt install -y xvfb x11vnc fluxbox wmctrl

# 7. Cài đặt các tools
echo -e "${YELLOW}🛠️  Cài đặt tools...${NC}"
apt install -y git curl wget unzip ufw

# 8. Cấu hình Firewall
echo -e "${YELLOW}🔥 Cấu hình Firewall...${NC}"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# 9. Tạo user cho ứng dụng
echo -e "${YELLOW}👤 Tạo user giadungplus...${NC}"
if ! id "giadungplus" &>/dev/null; then
    adduser --disabled-password --gecos "" giadungplus
    usermod -aG sudo giadungplus
    echo -e "${GREEN}✅ User giadungplus đã được tạo${NC}"
else
    echo -e "${YELLOW}⚠️  User giadungplus đã tồn tại${NC}"
fi

# 10. Tạo thư mục cho ứng dụng
echo -e "${YELLOW}📁 Tạo thư mục ứng dụng...${NC}"
mkdir -p ${PROJECT_DIR}
chown giadungplus:giadungplus ${PROJECT_DIR}

# Tạo thư mục logs
mkdir -p ${PROJECT_DIR}/logs
chown giadungplus:giadungplus ${PROJECT_DIR}/logs

# Tạo thư mục media và staticfiles
mkdir -p ${PROJECT_DIR}/media
mkdir -p ${PROJECT_DIR}/staticfiles
chown -R giadungplus:giadungplus ${PROJECT_DIR}/media
chown -R giadungplus:giadungplus ${PROJECT_DIR}/staticfiles

echo -e "${GREEN}✨ Setup server hoàn tất!${NC}"
echo -e "${GREEN}📝 Các bước tiếp theo:${NC}"
echo -e "   1. Upload code lên ${PROJECT_DIR}"
echo -e "   2. Tạo virtual environment: python3.10 -m venv venv"
echo -e "   3. Cài đặt dependencies từ requirements.txt"
echo -e "   4. Chạy migrations: python manage.py migrate"
echo -e "   5. Collect static files: python manage.py collectstatic"
echo -e "   6. Tạo superuser: python manage.py createsuperuser"
echo -e "   7. Cấu hình Supervisor cho Gunicorn (sẽ được tạo trong deploy.sh)"
echo -e "   8. Khởi động ứng dụng với Supervisor"
echo -e ""
echo -e "${YELLOW}📖 Xem hướng dẫn chi tiết trong file DEPLOYMENT_GUIDE.md${NC}"
echo -e ""
echo -e "${GREEN}🔗 Traefik Dashboard: http://${SERVER_IP}:8080${NC}"

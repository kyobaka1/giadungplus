# 🚀 Hướng dẫn Deploy GIADUNGPLUS lên Ubuntu Server 22.04

## 📋 Mục lục
1. [Chuẩn bị Server](#1-chuẩn-bị-server)
2. [Cài đặt Dependencies](#2-cài-đặt-dependencies)
3. [Cấu hình Database](#3-cấu-hình-database)
4. [Deploy Application](#4-deploy-application)
5. [Cấu hình Web Server (Nginx)](#5-cấu-hình-web-server-nginx)
6. [Cấu hình SSL (Let's Encrypt)](#6-cấu-hình-ssl-lets-encrypt)
7. [Cấu hình Systemd Service](#7-cấu-hình-systemd-service)
8. [Cấu hình Firewall](#8-cấu-hình-firewall)
9. [Kiểm tra và Troubleshooting](#9-kiểm-tra-và-troubleshooting)
10. [Cập nhật Code (Deploy mới)](#10-cập-nhật-code-deploy-mới)
11. [Backup](#11-backup)

---

## 🚀 Quick Start

Nếu bạn muốn setup nhanh, có thể sử dụng các script tự động:

1. **Setup Server:** `sudo bash setup_server.sh` - Tự động cài đặt tất cả dependencies
2. **Deploy Code:** `bash deploy.sh` - Tự động deploy code mới (sau khi upload code)
3. **Backup:** `sudo bash backup.sh` - Tự động backup database và files

### 📦 Các Script Có Sẵn

| Script | Mô tả | Cách sử dụng |
|--------|-------|--------------|
| `setup_server.sh` | Setup server Ubuntu 22.04, cài đặt tất cả dependencies | `sudo bash setup_server.sh` |
| `deploy.sh` | Deploy code mới, cập nhật dependencies, migrations, restart service | `bash deploy.sh` (trong thư mục project) |
| `backup.sh` | Backup database PostgreSQL và media/static files | `sudo bash backup.sh` |

**Lưu ý:** 
- `setup_server.sh` chỉ cần chạy 1 lần khi setup server lần đầu
- `deploy.sh` chạy mỗi khi có code mới cần deploy
- `backup.sh` có thể chạy thủ công hoặc cấu hình tự động qua crontab

Xem chi tiết từng bước bên dưới.

---

## 1. Chuẩn bị Server

### 1.1. Tạo SSH Key (nếu chưa có)

Trên máy Windows của bạn, mở PowerShell và chạy:

```powershell
# Kiểm tra xem đã có SSH key chưa
ls ~/.ssh

# Nếu chưa có, tạo SSH key mới
ssh-keygen -t ed25519 -C "your_email@example.com"

# Hoặc dùng RSA
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# Xem public key để thêm vào server
cat ~/.ssh/id_ed25519.pub
# Hoặc
cat ~/.ssh/id_rsa.pub
```

Copy toàn bộ nội dung public key và thêm vào server qua control panel.

### 1.2. Kết nối SSH vào Server

```bash
ssh root@YOUR_SERVER_IP
# Hoặc
ssh root@103.110.85.223
```

---

## 2. Cài đặt Dependencies

### 2.1. Sử dụng Script Tự Động (Khuyến nghị)

**Cách nhanh nhất:** Sử dụng script `setup_server.sh` để tự động cài đặt tất cả dependencies:

**Bước 1: Upload script lên server**

Có 2 cách:

**Cách A: Upload bằng SCP (từ máy Windows)**
```powershell
# Trên PowerShell
scp setup_server.sh root@103.110.85.223:/root/
```

**Cách B: Clone từ Git (nếu đã push lên repo)**
```bash
# Trên server
cd /root
git clone YOUR_REPO_URL
cd giadungplus-1
```

**Bước 2: Chạy script**
```bash
# Chạy với quyền root:
sudo bash setup_server.sh
# Hoặc nếu đã ở thư mục chứa script:
sudo bash /root/setup_server.sh
```

Script này sẽ tự động cài đặt:
- ✅ Python 3.10 và pip
- ✅ PostgreSQL
- ✅ Nginx
- ✅ Chrome (cho Selenium)
- ✅ Certbot (cho SSL)
- ✅ Các tools và dependencies cần thiết
- ✅ Tạo user `giadungplus`
- ✅ Tạo thư mục `/var/www/giadungplus`
- ✅ Cấu hình firewall

### 2.2. Cài đặt Thủ Công (Nếu không dùng script)

Nếu bạn muốn cài đặt thủ công từng bước:

```bash
# Cập nhật hệ thống
sudo apt update
sudo apt upgrade -y

# Cài đặt Python 3.10 và pip
sudo apt install -y python3.10 python3.10-venv python3-pip python3-dev
sudo apt install -y build-essential libssl-dev libffi-dev

# Cài đặt PostgreSQL
sudo apt install -y postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Cài đặt Nginx
sudo apt install -y nginx
sudo systemctl start nginx
sudo systemctl enable nginx

# Cài đặt Chrome cho Selenium
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update
sudo apt install -y google-chrome-stable
sudo apt install -y xvfb x11vnc fluxbox wmctrl

# Cài đặt các tools
sudo apt install -y git curl wget unzip ufw
sudo apt install -y libpq-dev libjpeg-dev zlib1g-dev

# Cài đặt Certbot
sudo apt install -y certbot python3-certbot-nginx

# Tạo user và thư mục
sudo adduser --disabled-password --gecos "" giadungplus
sudo usermod -aG sudo giadungplus
sudo mkdir -p /var/www/giadungplus
sudo chown giadungplus:giadungplus /var/www/giadungplus
sudo mkdir -p /var/www/giadungplus/logs
sudo chown giadungplus:giadungplus /var/www/giadungplus/logs

# Cấu hình firewall
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable
```

### 2.3. Cấu hình PostgreSQL

Sau khi cài đặt PostgreSQL (bằng script hoặc thủ công), cần tạo database và user:

```bash
# Tạo database và user
sudo -u postgres psql
```

Trong PostgreSQL shell:
```sql
CREATE DATABASE giadungplus_db;
CREATE USER giadungplus_user WITH PASSWORD 'your_strong_password_here';
ALTER ROLE giadungplus_user SET client_encoding TO 'utf8';
ALTER ROLE giadungplus_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE giadungplus_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE giadungplus_db TO giadungplus_user;
\q
```

**⚠️ Lưu ý:** Nhớ lưu lại password database để cấu hình trong settings.py sau này!

---

## 3. Cấu hình Database

### 3.1. Cài đặt PostgreSQL client cho Python

Sẽ được cài trong virtual environment ở bước sau.

---

## 4. Deploy Application

### 4.1. Upload code lên server

> **Lưu ý:** User `giadungplus` và thư mục `/var/www/giadungplus` đã được tạo tự động bởi script `setup_server.sh`. Nếu chưa chạy script, hãy tạo thủ công:
> ```bash
> sudo adduser --disabled-password --gecos "" giadungplus
> sudo usermod -aG sudo giadungplus
> sudo mkdir -p /var/www/giadungplus
> sudo chown giadungplus:giadungplus /var/www/giadungplus
> ```

**Cách 1: Dùng Git (khuyến nghị)**

```bash
cd /var/www/giadungplus
git clone YOUR_REPOSITORY_URL .
# Hoặc nếu chưa có git repo, upload code bằng SCP từ máy Windows
```

**Cách 2: Upload bằng SCP (từ máy Windows)**

Trên PowerShell của Windows:
```powershell
# Tạo file zip của project (trừ __pycache__, .git, db.sqlite3, etc.)
# Sau đó upload
scp -r D:\giadungplus\giadungplus-1\* root@103.110.85.223:/var/www/giadungplus/
```

### 4.4. Tạo Virtual Environment

```bash
cd /var/www/giadungplus
python3.10 -m venv venv
source venv/bin/activate
```

### 4.5. Cài đặt Dependencies

**Cách 1: Sử dụng requirements.txt (Khuyến nghị)**

```bash
# Nâng cấp pip
pip install --upgrade pip

# Cài đặt tất cả dependencies từ requirements.txt
pip install -r requirements.txt
```

**Cách 2: Cài đặt thủ công (nếu không có requirements.txt)**

```bash
# Nâng cấp pip
pip install --upgrade pip

# Cài đặt PostgreSQL adapter
pip install psycopg2-binary

# Cài đặt các packages từ rq.txt
pip install django
pip install xlrd==1.2.0
pip install requests
pip install lxml
pip install py3dbp==1.1.2
pip install selenium
pip install selenium-wire
pip install pypdf2
pip install htmlparser
pip install pillow
pip install python-barcode
pip install qrcode
pip install xlsxwriter
pip install pdfplumber
pip install fpdf
pip install reportlab
pip install BeautifulSoup4
pip install django-sslserver
pip install setuptools
pip install pygame
pip install openpyxl
pip install gspread
pip install djangorestframework
pip install oauth2client
pip install blinker==1.7.0
pip install whitenoise
pip install openai
pip install pandas
pip install "pydantic>=2.0.0"
pip install python-dateutil

# Cài đặt Gunicorn cho production
pip install gunicorn
```

### 4.7. Cấu hình Settings cho Production

Tạo file `GIADUNGPLUS/settings_production.py`:

```python
from .settings import *
import os

# Security settings
DEBUG = False
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-this')

ALLOWED_HOSTS = ['giadungplus.io.vn', '103.110.85.223', 'localhost']

# Database - PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'giadungplus_db',
        'USER': 'giadungplus_user',
        'PASSWORD': 'your_strong_password_here',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Static files
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'assets'),
]

# Media files (nếu có)
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = '/media/'

# Security
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Timezone
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_TZ = True
```

Hoặc sửa trực tiếp `settings.py`:

```bash
nano GIADUNGPLUS/settings.py
```

Cần sửa:
- `DEBUG = False`
- Thay đổi `SECRET_KEY` (dùng biến môi trường)
- Cấu hình PostgreSQL database
- Thêm `STATIC_ROOT`
- Bật các security settings

### 4.8. Chạy Migrations

```bash
python manage.py migrate
```

### 4.9. Tạo Superuser

```bash
python manage.py createsuperuser
```

### 4.10. Collect Static Files

```bash
python manage.py collectstatic --noinput
```

---

## 5. Cấu hình Web Server (Nginx)

### 5.1. Tạo Nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/giadungplus
```

Nội dung file:

```nginx
server {
    listen 80;
    server_name giadungplus.io.vn 103.110.85.223;

    # Redirect HTTP to HTTPS (sau khi có SSL)
    # return 301 https://$server_name$request_uri;

    # Tạm thời để HTTP để cài SSL
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /var/www/giadungplus/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /var/www/giadungplus/media/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    client_max_body_size 100M;
}
```

### 5.2. Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/giadungplus /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 6. Cấu hình SSL (Let's Encrypt)

### 6.1. Cài đặt Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 6.2. Lấy SSL Certificate

```bash
sudo certbot --nginx -d giadungplus.io.vn
```

Làm theo hướng dẫn:
- Nhập email
- Đồng ý điều khoản
- Chọn redirect HTTP to HTTPS

### 6.3. Auto-renewal

```bash
sudo certbot renew --dry-run
```

Certbot sẽ tự động renew, nhưng có thể thêm vào crontab:

```bash
sudo crontab -e
# Thêm dòng:
0 0,12 * * * certbot renew --quiet
```

### 6.4. Cập nhật Nginx config sau khi có SSL

Sau khi có SSL, uncomment dòng redirect trong nginx config:

```nginx
return 301 https://$server_name$request_uri;
```

Và thêm block server cho HTTPS:

```nginx
server {
    listen 443 ssl http2;
    server_name giadungplus.io.vn;

    ssl_certificate /etc/letsencrypt/live/giadungplus.io.vn/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/giadungplus.io.vn/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /var/www/giadungplus/staticfiles/;
    }

    location /media/ {
        alias /var/www/giadungplus/media/;
    }

    client_max_body_size 100M;
}
```

---

## 7. Cấu hình Systemd Service

### 7.1. Tạo Gunicorn Service

```bash
sudo nano /etc/systemd/system/giadungplus.service
```

Nội dung:

```ini
[Unit]
Description=GIADUNGPLUS Gunicorn daemon
After=network.target

[Service]
User=giadungplus
Group=www-data
WorkingDirectory=/var/www/giadungplus
Environment="PATH=/var/www/giadungplus/venv/bin"
ExecStart=/var/www/giadungplus/venv/bin/gunicorn \
    --workers 3 \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    GIADUNGPLUS.wsgi:application

[Install]
WantedBy=multi-user.target
```

### 7.2. Start và Enable Service

```bash
sudo systemctl daemon-reload
sudo systemctl start giadungplus
sudo systemctl enable giadungplus
sudo systemctl status giadungplus
```

### 7.3. Xem logs

```bash
sudo journalctl -u giadungplus -f
```

---

## 8. Cấu hình Firewall

### 8.1. Cấu hình UFW

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

---

## 9. Kiểm tra và Troubleshooting

### 9.1. Kiểm tra Services

```bash
# Kiểm tra Nginx
sudo systemctl status nginx

# Kiểm tra Gunicorn
sudo systemctl status giadungplus

# Kiểm tra PostgreSQL
sudo systemctl status postgresql
```

### 9.2. Kiểm tra Logs

```bash
# Nginx logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log

# Gunicorn logs
sudo journalctl -u giadungplus -n 50

# Django logs (nếu có cấu hình logging)
tail -f /var/www/giadungplus/logs/*.log
```

### 9.3. Test ứng dụng

```bash
# Test từ server
curl http://localhost:8000

# Test từ máy local
curl http://103.110.85.223
curl https://giadungplus.io.vn
```

### 9.4. Các lệnh hữu ích

```bash
# Restart services
sudo systemctl restart giadungplus
sudo systemctl restart nginx

# Reload config (không downtime)
sudo systemctl reload nginx

# Xem process
ps aux | grep gunicorn

# Kiểm tra port
sudo netstat -tlnp | grep :8000
```

### 9.5. Troubleshooting thường gặp

**Lỗi 502 Bad Gateway:**
- Kiểm tra Gunicorn có chạy không: `sudo systemctl status giadungplus`
- Kiểm tra logs: `sudo journalctl -u giadungplus -n 50`
- Kiểm tra permissions: `ls -la /var/www/giadungplus`

**Lỗi Static files không load:**
- Chạy lại: `python manage.py collectstatic --noinput`
- Kiểm tra permissions: `sudo chown -R giadungplus:www-data /var/www/giadungplus/staticfiles`
- Kiểm tra nginx config có đúng path không

**Lỗi Database connection:**
- Kiểm tra PostgreSQL: `sudo systemctl status postgresql`
- Test connection: `psql -U giadungplus_user -d giadungplus_db -h localhost`
- Kiểm tra settings.py có đúng credentials không

**Lỗi Permission denied:**
```bash
sudo chown -R giadungplus:www-data /var/www/giadungplus
sudo chmod -R 755 /var/www/giadungplus
```

---

## 10. Cập nhật Code (Deploy mới)

### 10.1. Sử dụng Script Deploy (Khuyến nghị)

**Cách nhanh nhất:** Sử dụng script `deploy.sh` để tự động deploy:

> **Lưu ý:** Script `deploy.sh` phải có trong thư mục project (`/var/www/giadungplus/`). Nếu chưa có, upload lên server cùng với code.

```bash
# SSH vào server
ssh root@103.110.85.223

# Chuyển sang user giadungplus
sudo su - giadungplus

# Vào thư mục project
cd /var/www/giadungplus

# Đảm bảo script có quyền thực thi
chmod +x deploy.sh

# Chạy script deploy
bash deploy.sh
```

Script `deploy.sh` sẽ tự động:
- ✅ Activate virtual environment
- ✅ Pull code mới (nếu dùng git)
- ✅ Cài đặt/update dependencies
- ✅ Chạy migrations
- ✅ Collect static files
- ✅ Restart Gunicorn service
- ✅ Hiển thị status

### 10.2. Deploy Thủ Công (Nếu không dùng script)

Nếu bạn muốn deploy thủ công từng bước:

```bash
# SSH vào server
ssh root@103.110.85.223

# Chuyển sang user giadungplus
sudo su - giadungplus

# Vào thư mục project
cd /var/www/giadungplus

# Pull code mới (nếu dùng git)
git pull origin main

# Activate virtual environment
source venv/bin/activate

# Cài đặt dependencies mới (nếu có)
pip install -r requirements.txt

# Chạy migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Restart service
sudo systemctl restart giadungplus

# Kiểm tra logs
sudo journalctl -u giadungplus -f
```

### 10.3. Lưu ý khi Deploy

- **Backup trước khi deploy:** Luôn backup database và code trước khi deploy code mới
- **Kiểm tra migrations:** Đảm bảo migrations không gây lỗi
- **Test sau deploy:** Kiểm tra ứng dụng hoạt động bình thường sau khi deploy
- **Rollback:** Giữ bản backup để có thể rollback nếu cần

---

## 11. Backup

### 11.1. Sử dụng Script Backup (Khuyến nghị)

**Cách nhanh nhất:** Sử dụng script `backup.sh` để tự động backup:

> **Lưu ý:** Script `backup.sh` phải có trong thư mục project (`/var/www/giadungplus/`). Nếu chưa có, upload lên server cùng với code.

```bash
# Đảm bảo script có quyền thực thi
chmod +x /var/www/giadungplus/backup.sh

# Chạy với quyền root hoặc sudo:
sudo bash /var/www/giadungplus/backup.sh
```

Script `backup.sh` sẽ tự động:
- ✅ Backup database PostgreSQL (nén gzip)
- ✅ Backup media files (nếu có)
- ✅ Backup static files (nếu cần)
- ✅ Xóa backup cũ hơn 7 ngày
- ✅ Hiển thị thông tin backup

Backup sẽ được lưu tại: `/var/backups/giadungplus/`

### 11.2. Cấu hình Backup Tự Động (Crontab)

Để backup tự động mỗi ngày, thêm vào crontab:

```bash
# Mở crontab
sudo crontab -e

# Thêm dòng sau để chạy backup mỗi ngày lúc 2h sáng
0 2 * * * /bin/bash /var/www/giadungplus/backup.sh >> /var/log/giadungplus-backup.log 2>&1
```

Hoặc nếu muốn backup nhiều lần trong ngày (ví dụ: 2h sáng và 2h chiều):

```bash
0 2,14 * * * /bin/bash /var/www/giadungplus/backup.sh >> /var/log/giadungplus-backup.log 2>&1
```

### 11.3. Backup Thủ Công (Nếu không dùng script)

Nếu bạn muốn backup thủ công:

```bash
# Tạo thư mục backup
sudo mkdir -p /var/backups/giadungplus

# Backup database
sudo -u postgres pg_dump giadungplus_db | gzip > /var/backups/giadungplus/db_$(date +%Y%m%d_%H%M%S).sql.gz

# Backup media files (nếu có)
tar -czf /var/backups/giadungplus/media_$(date +%Y%m%d_%H%M%S).tar.gz -C /var/www/giadungplus media

# Xóa backup cũ hơn 7 ngày
find /var/backups/giadungplus -type f -mtime +7 -delete
```

### 11.4. Restore từ Backup

Để restore database từ backup:

```bash
# Giải nén file backup (nếu đã nén)
gunzip /var/backups/giadungplus/db_YYYYMMDD_HHMMSS.sql.gz

# Restore database
sudo -u postgres psql giadungplus_db < /var/backups/giadungplus/db_YYYYMMDD_HHMMSS.sql
```

Hoặc restore trực tiếp từ file nén:

```bash
gunzip -c /var/backups/giadungplus/db_YYYYMMDD_HHMMSS.sql.gz | sudo -u postgres psql giadungplus_db
```

Để restore media files:

```bash
# Giải nén và restore
tar -xzf /var/backups/giadungplus/media_YYYYMMDD_HHMMSS.tar.gz -C /var/www/giadungplus
sudo chown -R giadungplus:www-data /var/www/giadungplus/media
```

---

## 📝 Checklist Deployment

### Setup Server
- [ ] Server Ubuntu 22.04 đã được tạo
- [ ] SSH key đã được thêm vào server
- [ ] Đã chạy script `setup_server.sh` hoặc cài đặt thủ công
- [ ] Python 3.10 và pip đã được cài đặt
- [ ] PostgreSQL đã được cài và cấu hình (database + user)
- [ ] Nginx đã được cài đặt
- [ ] Chrome đã được cài cho Selenium
- [ ] Firewall đã được cấu hình

### Deploy Application
- [ ] Code đã được upload lên `/var/www/giadungplus`
- [ ] Virtual environment đã được tạo (`python3.10 -m venv venv`)
- [ ] Dependencies đã được cài đặt (`pip install -r requirements.txt`)
- [ ] Settings đã được cấu hình cho production (DEBUG=False, PostgreSQL, etc.)
- [ ] Database đã được migrate (`python manage.py migrate`)
- [ ] Superuser đã được tạo (`python manage.py createsuperuser`)
- [ ] Static files đã được collect (`python manage.py collectstatic`)

### Cấu hình Web Server
- [ ] Nginx đã được cấu hình (`/etc/nginx/sites-available/giadungplus`)
- [ ] Nginx site đã được enable
- [ ] SSL certificate đã được cài đặt (`certbot --nginx`)
- [ ] Gunicorn service đã được tạo (`/etc/systemd/system/giadungplus.service`)
- [ ] Gunicorn service đã được start và enable
- [ ] Ứng dụng đã chạy thành công (kiểm tra qua browser)

### Backup & Maintenance
- [ ] Script backup đã được test (`sudo bash backup.sh`)
- [ ] Crontab đã được cấu hình cho backup tự động
- [ ] Đã test restore từ backup

---

## 🔒 Security Checklist

- [ ] `DEBUG = False` trong settings
- [ ] `SECRET_KEY` được lưu trong biến môi trường
- [ ] Database password mạnh
- [ ] SSL/HTTPS đã được bật
- [ ] Firewall đã được cấu hình
- [ ] SSH key authentication thay vì password
- [ ] Regular updates: `sudo apt update && sudo apt upgrade`

---

## 📞 Hỗ trợ

Nếu gặp vấn đề, kiểm tra:
1. Logs của Nginx: `/var/log/nginx/error.log`
2. Logs của Gunicorn: `sudo journalctl -u giadungplus`
3. Logs của Django (nếu có cấu hình)
4. Status của các services: `sudo systemctl status <service-name>`


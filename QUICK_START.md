# 🚀 Quick Start - Deploy GIADUNGPLUS

Hướng dẫn nhanh để deploy ứng dụng lên Ubuntu Server 22.04.

## 📋 Yêu cầu

- Server Ubuntu 22.04 LTS
- Quyền root hoặc sudo
- Domain name đã trỏ về IP server (cho SSL)
- SSH key đã được thêm vào server

## ⚡ Các bước nhanh

### 1. Setup Server (chạy trên server với quyền root)

```bash
# Upload file setup_server.sh lên server
sudo bash setup_server.sh
```

Script này sẽ tự động cài đặt:
- Python 3.10
- PostgreSQL
- Nginx
- Chrome (cho Selenium)
- Các dependencies cần thiết

### 2. Cấu hình Database

```bash
# Tạo database và user
sudo -u postgres psql
```

Trong PostgreSQL shell:
```sql
CREATE DATABASE giadungplus_db;
CREATE USER giadungplus_user WITH PASSWORD 'your_strong_password';
ALTER ROLE giadungplus_user SET client_encoding TO 'utf8';
ALTER ROLE giadungplus_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE giadungplus_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE giadungplus_db TO giadungplus_user;
\q
```

### 3. Upload Code

**Cách 1: Dùng Git (khuyến nghị)**
```bash
cd /var/www
sudo git clone YOUR_REPO_URL giadungplus
sudo chown -R giadungplus:giadungplus /var/www/giadungplus
```

**Cách 2: Upload bằng SCP (từ máy Windows)**
```powershell
# Trên PowerShell
scp -r D:\giadungplus\giadungplus-1\* root@103.110.85.223:/var/www/giadungplus/
```

### 4. Setup Application

```bash
# Chuyển sang user giadungplus
sudo su - giadungplus
cd /var/www/giadungplus

# Tạo virtual environment
python3.10 -m venv venv
source venv/bin/activate

# Cài đặt dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Cấu hình settings
# Copy .env.example và sửa thông tin
cp .env.example .env
nano .env  # Sửa SECRET_KEY, DB_PASSWORD, etc.

# Hoặc sửa trực tiếp settings.py
nano GIADUNGPLUS/settings.py
# Sửa: DEBUG=False, SECRET_KEY, DATABASES (PostgreSQL)

# Chạy migrations
python manage.py migrate

# Tạo superuser
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic --noinput
```

### 5. Cấu hình Nginx

```bash
sudo nano /etc/nginx/sites-available/giadungplus
```

Paste nội dung:
```nginx
server {
    listen 80;
    server_name giadungplus.io.vn 103.110.85.223;

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

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/giadungplus /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 6. Cài đặt SSL

```bash
sudo certbot --nginx -d giadungplus.io.vn
```

### 7. Tạo Systemd Service

```bash
sudo nano /etc/systemd/system/giadungplus.service
```

Paste:
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

Start service:
```bash
sudo systemctl daemon-reload
sudo systemctl start giadungplus
sudo systemctl enable giadungplus
sudo systemctl status giadungplus
```

### 8. Kiểm tra

```bash
# Kiểm tra services
sudo systemctl status nginx
sudo systemctl status giadungplus
sudo systemctl status postgresql

# Xem logs
sudo journalctl -u giadungplus -f
```

Truy cập: `https://giadungplus.io.vn`

## 🔄 Deploy mới (khi có code mới)

```bash
cd /var/www/giadungplus
sudo su - giadungplus
source venv/bin/activate
bash deploy.sh
```

Hoặc manual:
```bash
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart giadungplus
```

## 💾 Backup

```bash
sudo bash backup.sh
```

Backup sẽ được lưu tại `/var/backups/giadungplus/`

## 📚 Tài liệu chi tiết

Xem file `DEPLOYMENT_GUIDE.md` để biết chi tiết từng bước và troubleshooting.

## ⚠️ Lưu ý quan trọng

1. **SECRET_KEY**: Phải thay đổi SECRET_KEY trong production, không dùng key mặc định
2. **DEBUG**: Phải đặt `DEBUG = False` trong production
3. **Database Password**: Dùng password mạnh cho database
4. **Firewall**: Đã được cấu hình tự động, chỉ mở SSH và HTTP/HTTPS
5. **SSL**: Luôn dùng HTTPS trong production

## 🆘 Troubleshooting

**502 Bad Gateway:**
```bash
sudo systemctl status giadungplus
sudo journalctl -u giadungplus -n 50
```

**Static files không load:**
```bash
python manage.py collectstatic --noinput
sudo chown -R giadungplus:www-data /var/www/giadungplus/staticfiles
```

**Database connection error:**
```bash
sudo systemctl status postgresql
psql -U giadungplus_user -d giadungplus_db -h localhost
```


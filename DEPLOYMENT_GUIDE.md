# 🚀 Hướng dẫn Deploy GIADUNGPLUS lên Ubuntu Server 22.04

## 📋 Kiến trúc hệ thống

- **Domain**: giadungplus.io.vn
- **Server IP**: 103.110.85.223
- **Gunicorn** – WSGI server serving Django (chạy trên port 8000)
- **Supervisor** – Background process manager cho Gunicorn (auto-restart, logs)
- **Traefik** – Reverse proxy/load balancer, xử lý routing và HTTPS tự động
- **PostgreSQL** – Database server
- **Database**: giadungplus_db (user: giadungplus, password: 123122aC@)

---

## 📋 Mục lục
1. [Chuẩn bị Server](#1-chuẩn-bị-server)
2. [Cài đặt Dependencies](#2-cài-đặt-dependencies)
3. [Cấu hình Database](#3-cấu-hình-database)
4. [Deploy Application](#4-deploy-application)
5. [Cấu hình Traefik](#5-cấu-hình-traefik)
6. [Cấu hình Supervisor](#6-cấu-hình-supervisor)
7. [Cấu hình Firewall](#7-cấu-hình-firewall)
8. [Kiểm tra và Troubleshooting](#8-kiểm-tra-và-troubleshooting)
9. [Cập nhật Code (Deploy mới)](#9-cập-nhật-code-deploy-mới)
10. [Backup](#10-backup)

---

## 🚀 Quick Start

Nếu bạn muốn setup nhanh, có thể sử dụng các script tự động:

1. **Setup Server:** `sudo bash setup_server.sh` - Tự động cài đặt tất cả dependencies
2. **Deploy Code:** `bash deploy.sh` - Tự động deploy code mới (sau khi upload code)
3. **Backup:** `sudo bash backup.sh` - Tự động backup database và files

### 📦 Các Script Có Sẵn

| Script | Mô tả | Cách sử dụng |
|--------|-------|--------------|
| `setup_server.sh` | Setup server Ubuntu 22.04, cài đặt Traefik, Supervisor, PostgreSQL | `sudo bash setup_server.sh` |
| `deploy.sh` | Deploy code mới, cập nhật dependencies, migrations, restart Supervisor | `bash deploy.sh` (trong thư mục project) |
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
ssh root@103.110.85.223
```

---

## 2. Cài đặt Dependencies

### 2.1. Sử dụng Script Tự Động (Khuyến nghị)

**Cách nhanh nhất:** Sử dụng script `setup_server.sh` để tự động cài đặt tất cả dependencies:

**Bước 1: Upload script lên server**

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
- ✅ PostgreSQL (và tạo database + user tự động)
- ✅ Traefik (reverse proxy với HTTPS tự động)
- ✅ Supervisor (process manager)
- ✅ Chrome (cho Selenium)
- ✅ Các tools và dependencies cần thiết
- ✅ Tạo user `giadungplus`
- ✅ Tạo thư mục `/var/www/giadungplus`
- ✅ Cấu hình firewall

### 2.2. Cài đặt Thủ Công (Nếu không dùng script)

Nếu bạn muốn cài đặt thủ công từng bước, xem chi tiết trong script `setup_server.sh`.

**Lưu ý quan trọng:** Database và user PostgreSQL sẽ được tạo tự động bởi script với:
- Database: `giadungplus_db`
- User: `giadungplus`
- Password: `123122aC@`

---

## 3. Cấu hình Database

Database đã được tạo tự động bởi script `setup_server.sh`. Nếu cần tạo thủ công:

```bash
sudo -u postgres psql
```

Trong PostgreSQL shell:
```sql
CREATE DATABASE giadungplus_db;
CREATE USER giadungplus WITH PASSWORD '123122aC@';
ALTER ROLE giadungplus SET client_encoding TO 'utf8';
ALTER ROLE giadungplus SET default_transaction_isolation TO 'read committed';
ALTER ROLE giadungplus SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE giadungplus_db TO giadungplus;
\q
```

---

## 4. Deploy Application

### 4.1. Upload code lên server

> **Lưu ý:** User `giadungplus` và thư mục `/var/www/giadungplus` đã được tạo tự động bởi script `setup_server.sh`. Nếu thư mục đã có một số thư mục như `logs`, `media`, `staticfiles`, hãy làm theo hướng dẫn bên dưới.

**Cách 1: Dùng Git (khuyến nghị)**

Nếu thư mục `/var/www/giadungplus` đã có một số thư mục (logs, media, staticfiles), bạn có 2 lựa chọn:

**Phương án A: Clone vào thư mục tạm rồi di chuyển (Khuyến nghị - giữ lại dữ liệu cũ)**

```bash
cd /var/www
# Clone vào thư mục tạm
git clone https://github.com/kyobaka1/giadungplus.git giadungplus-temp

# Di chuyển nội dung vào thư mục chính
cd giadungplus-temp
mv * ../giadungplus/
mv .* ../giadungplus/ 2>/dev/null || true  # Di chuyển các file ẩn (.git, .gitignore, etc.)

# Xóa thư mục tạm
cd ..
rm -rf giadungplus-temp

# Cấp quyền
cd /var/www/giadungplus
sudo chown -R giadungplus:giadungplus /var/www/giadungplus
```

**Phương án B: Xóa các thư mục cũ và clone trực tiếp (Mất dữ liệu cũ)**

```bash
cd /var/www/giadungplus
# Backup các thư mục quan trọng (nếu cần)
# sudo tar -czf /tmp/old_data_backup.tar.gz logs media staticfiles

# Xóa các thư mục cũ
rm -rf logs media staticfiles

# Clone vào thư mục hiện tại
git clone https://github.com/kyobaka1/giadungplus.git .

# Cấp quyền
sudo chown -R giadungplus:giadungplus /var/www/giadungplus
```

**Cách 2: Upload bằng SCP (từ máy Windows)**

**Cách A: Sử dụng Script Tự Động (Khuyến nghị)**

Có 2 script sẵn có:
- `upload_to_server.bat` - Chạy trong Command Prompt
- `upload_to_server.ps1` - Chạy trong PowerShell

**PowerShell (Khuyến nghị):**
```powershell
# Chạy script
.\upload_to_server.ps1
```

**Command Prompt:**
```cmd
upload_to_server.bat
```

Script sẽ tự động:
- ✅ Upload tất cả code files
- ✅ Bỏ qua các thư mục không cần thiết (__pycache__, venv, .git, etc.)
- ✅ Cấp quyền đúng cho files
- ✅ Hiển thị hướng dẫn tiếp theo

**Cách B: Upload thủ công bằng SCP**

Trên PowerShell của Windows:
```powershell
# Upload tất cả files
scp -r D:\giadungplus\giadungplus-1\* root@103.110.85.223:/var/www/giadungplus/

# Hoặc upload từng phần (để tránh lỗi)
scp -r D:\giadungplus\giadungplus-1\GIADUNGPLUS root@103.110.85.223:/var/www/giadungplus/
scp -r D:\giadungplus\giadungplus-1\core root@103.110.85.223:/var/www/giadungplus/
scp -r D:\giadungplus\giadungplus-1\kho root@103.110.85.223:/var/www/giadungplus/
# ... tiếp tục với các thư mục khác
```

**Git Bash (Nếu dùng Git Bash):**
```bash
scp -r /d/giadungplus/giadungplus-1/* root@103.110.85.223:/var/www/giadungplus/
```

Sau khi upload, cấp quyền:
```bash
ssh root@103.110.85.223 "cd /var/www/giadungplus && sudo chown -R giadungplus:giadungplus . && sudo chmod +x deploy.sh"
```

### 4.2. Tạo Virtual Environment

```bash
cd /var/www/giadungplus
python3.10 -m venv venv
source venv/bin/activate
```

### 4.3. Cài đặt Dependencies

```bash
# Nâng cấp pip
pip install --upgrade pip

# Cài đặt tất cả dependencies từ requirements.txt
pip install -r requirements.txt
```

### 4.4. Cấu hình Settings cho Production

File `GIADUNGPLUS/settings_production.py` đã được cấu hình sẵn với:
- Database: giadungplus_db (user: giadungplus, password: 123122aC@)
- ALLOWED_HOSTS: giadungplus.io.vn, 103.110.85.223
- DEBUG: False (nên set True để test, sau đó đổi False)
- Security settings đã được bật

Để sử dụng production settings, export biến môi trường:
```bash
export DJANGO_SETTINGS_MODULE=GIADUNGPLUS.settings_production
```

Hoặc chỉnh sửa `manage.py` hoặc sử dụng khi chạy lệnh:
```bash
python manage.py migrate --settings=GIADUNGPLUS.settings_production
```

### 4.5. Chạy Migrations

```bash
cd /var/www/giadungplus
source venv/bin/activate
python manage.py migrate --settings=GIADUNGPLUS.settings_production
```

### 4.6. Tạo Superuser

```bash
python manage.py createsuperuser --settings=GIADUNGPLUS.settings_production
```

### 4.7. Collect Static Files

```bash
python manage.py collectstatic --noinput --settings=GIADUNGPLUS.settings_production
```

### 4.8. Sử dụng Script Deploy Tự Động (Khuyến nghị)

Thay vì làm thủ công các bước trên, bạn có thể sử dụng script `deploy.sh`:

```bash
cd /var/www/giadungplus
chmod +x deploy.sh
bash deploy.sh
```

Script này sẽ tự động:
- ✅ Activate virtual environment
- ✅ Pull code mới (nếu dùng git)
- ✅ Cài đặt/update dependencies
- ✅ Chạy migrations
- ✅ Collect static files
- ✅ Cấu hình Supervisor
- ✅ Restart service

---

## 5. Cấu hình Traefik

Traefik đã được cài đặt và cấu hình tự động bởi script `setup_server.sh`.

### 5.1. Cấu hình Traefik

File cấu hình chính: `/etc/traefik/traefik.yml`
File cấu hình động: `/etc/traefik/dynamic/dynamic.yml`

### 5.2. Kiểm tra Traefik

```bash
# Kiểm tra status
sudo systemctl status traefik

# Xem logs
sudo journalctl -u traefik -f

# Dashboard Traefik (truy cập qua IP:8080)
# http://103.110.85.223:8080
```

### 5.3. SSL Certificate tự động

Traefik sẽ tự động lấy SSL certificate từ Let's Encrypt cho domain `giadungplus.io.vn`. 
Certificate sẽ được tự động renew.

**Lưu ý:** Đảm bảo domain đã trỏ về IP `103.110.85.223` trước khi khởi động Traefik.

### 5.4. Restart Traefik

```bash
sudo systemctl restart traefik
```

---

## 6. Cấu hình Supervisor

Supervisor đã được cài đặt tự động. File cấu hình sẽ được tạo tự động bởi script `deploy.sh`.

### 6.1. File cấu hình Supervisor

File: `/etc/supervisor/conf.d/giadungplus.conf`

File này sẽ được tạo tự động khi chạy `deploy.sh`. Nếu cần tạo thủ công:

```bash
sudo nano /etc/supervisor/conf.d/giadungplus.conf
```

Nội dung:
```ini
[program:giadungplus]
directory=/var/www/giadungplus
command=/var/www/giadungplus/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 --timeout 120 --access-logfile /var/www/giadungplus/logs/gunicorn-access.log --error-logfile /var/www/giadungplus/logs/gunicorn-error.log GIADUNGPLUS.wsgi:application
user=giadungplus
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stderr_logfile=/var/www/giadungplus/logs/gunicorn-supervisor-error.log
stdout_logfile=/var/www/giadungplus/logs/gunicorn-supervisor.log
environment=PATH="/var/www/giadungplus/venv/bin"
```

### 6.2. Quản lý Service với Supervisor

```bash
# Reload config
sudo supervisorctl reread
sudo supervisorctl update

# Quản lý service
sudo supervisorctl start giadungplus
sudo supervisorctl stop giadungplus
sudo supervisorctl restart giadungplus
sudo supervisorctl status giadungplus

# Xem logs
sudo supervisorctl tail -f giadungplus
sudo supervisorctl tail -f giadungplus stderr
```

### 6.3. Xem Logs

```bash
# Logs Supervisor
sudo supervisorctl tail -f giadungplus

# Logs Gunicorn
tail -f /var/www/giadungplus/logs/gunicorn-access.log
tail -f /var/www/giadungplus/logs/gunicorn-error.log
tail -f /var/www/giadungplus/logs/gunicorn-supervisor.log
```

---

## 7. Cấu hình Firewall

Firewall đã được cấu hình tự động bởi script `setup_server.sh`:

```bash
# Kiểm tra firewall
sudo ufw status

# Nếu cần mở thêm port
sudo ufw allow 8080/tcp  # Cho Traefik dashboard (tùy chọn)
```

---

## 8. Kiểm tra và Troubleshooting

### 8.1. Kiểm tra Services

```bash
# Kiểm tra Traefik
sudo systemctl status traefik

# Kiểm tra Supervisor
sudo systemctl status supervisor

# Kiểm tra Gunicorn
sudo supervisorctl status giadungplus

# Kiểm tra PostgreSQL
sudo systemctl status postgresql
```

### 8.2. Kiểm tra Logs

```bash
# Traefik logs
sudo journalctl -u traefik -f

# Supervisor logs
sudo supervisorctl tail -f giadungplus

# Gunicorn logs
tail -f /var/www/giadungplus/logs/gunicorn-*.log

# Django logs (nếu có cấu hình logging)
tail -f /var/www/giadungplus/logs/*.log
```

### 8.3. Test ứng dụng

```bash
# Test từ server
curl http://localhost:8000

# Test từ máy local
curl http://103.110.85.223
curl https://giadungplus.io.vn
```

### 8.4. Các lệnh hữu ích

```bash
# Restart services
sudo supervisorctl restart giadungplus
sudo systemctl restart traefik

# Xem process
ps aux | grep gunicorn
ps aux | grep traefik

# Kiểm tra port
sudo netstat -tlnp | grep :8000
sudo netstat -tlnp | grep :80
sudo netstat -tlnp | grep :443
```

### 8.5. Troubleshooting thường gặp

**Lỗi 502 Bad Gateway:**
- Kiểm tra Gunicorn có chạy không: `sudo supervisorctl status giadungplus`
- Kiểm tra logs: `sudo supervisorctl tail -f giadungplus`
- Kiểm tra permissions: `ls -la /var/www/giadungplus`

**Lỗi Static files không load:**
- Chạy lại: `python manage.py collectstatic --noinput`
- Kiểm tra permissions: `sudo chown -R giadungplus:giadungplus /var/www/giadungplus/staticfiles`
- Kiểm tra Traefik config có đúng path không

**Lỗi Database connection:**
- Kiểm tra PostgreSQL: `sudo systemctl status postgresql`
- Test connection: `psql -U giadungplus -d giadungplus_db -h localhost`
- Kiểm tra settings_production.py có đúng credentials không

**Lỗi Permission denied:**
```bash
sudo chown -R giadungplus:giadungplus /var/www/giadungplus
sudo chmod -R 755 /var/www/giadungplus
```

**Lỗi SSL Certificate:**
- Đảm bảo domain đã trỏ về IP server
- Kiểm tra Traefik logs: `sudo journalctl -u traefik -f`
- Kiểm tra file `/etc/traefik/acme.json` có quyền đọc/ghi

---

## 9. Cập nhật Code (Deploy mới)

### 9.1. Sử dụng Script Deploy (Khuyến nghị)

**Cách nhanh nhất:** Sử dụng script `deploy.sh` để tự động deploy:

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
- ✅ Cấu hình Supervisor
- ✅ Restart Gunicorn service
- ✅ Hiển thị status

### 9.2. Deploy Thủ Công (Nếu không dùng script)

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
python manage.py migrate --settings=GIADUNGPLUS.settings_production

# Collect static files
python manage.py collectstatic --noinput --settings=GIADUNGPLUS.settings_production

# Restart service
sudo supervisorctl restart giadungplus

# Kiểm tra logs
sudo supervisorctl tail -f giadungplus
```

### 9.3. Lưu ý khi Deploy

- **Backup trước khi deploy:** Luôn backup database và code trước khi deploy code mới
- **Kiểm tra migrations:** Đảm bảo migrations không gây lỗi
- **Test sau deploy:** Kiểm tra ứng dụng hoạt động bình thường sau khi deploy
- **Rollback:** Giữ bản backup để có thể rollback nếu cần

---

## 10. Backup

### 10.1. Sử dụng Script Backup (Khuyến nghị)

**Cách nhanh nhất:** Sử dụng script `backup.sh` để tự động backup:

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
- ✅ Backup code (nếu dùng git)
- ✅ Backup cấu hình (Supervisor, Traefik, settings)
- ✅ Xóa backup cũ hơn 7 ngày
- ✅ Hiển thị thông tin backup

Backup sẽ được lưu tại: `/var/backups/giadungplus/`

### 10.2. Cấu hình Backup Tự Động (Crontab)

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

### 10.3. Backup Thủ Công (Nếu không dùng script)

```bash
# Tạo thư mục backup
sudo mkdir -p /var/backups/giadungplus

# Backup database
export PGPASSWORD="123122aC@"
pg_dump -U giadungplus -h localhost -d giadungplus_db | gzip > /var/backups/giadungplus/db_$(date +%Y%m%d_%H%M%S).sql.gz
unset PGPASSWORD

# Backup media files (nếu có)
tar -czf /var/backups/giadungplus/media_$(date +%Y%m%d_%H%M%S).tar.gz -C /var/www/giadungplus media

# Xóa backup cũ hơn 7 ngày
find /var/backups/giadungplus -type f -mtime +7 -delete
```

### 10.4. Restore từ Backup

**Restore database:**
```bash
# Giải nén file backup (nếu đã nén)
gunzip -c /var/backups/giadungplus/db_YYYYMMDD_HHMMSS.sql.gz | psql -U giadungplus -h localhost -d giadungplus_db

# Hoặc
gunzip -c /var/backups/giadungplus/db_YYYYMMDD_HHMMSS.sql.gz | sudo -u postgres psql giadungplus_db
```

**Restore media files:**
```bash
# Giải nén và restore
tar -xzf /var/backups/giadungplus/media_YYYYMMDD_HHMMSS.tar.gz -C /var/www/giadungplus
sudo chown -R giadungplus:giadungplus /var/www/giadungplus/media
```

---

## 📝 Checklist Deployment

### Setup Server
- [ ] Server Ubuntu 22.04 đã được tạo
- [ ] SSH key đã được thêm vào server
- [ ] Đã chạy script `setup_server.sh` hoặc cài đặt thủ công
- [ ] Python 3.10 và pip đã được cài đặt
- [ ] PostgreSQL đã được cài và cấu hình (database + user)
- [ ] Traefik đã được cài đặt và cấu hình
- [ ] Supervisor đã được cài đặt
- [ ] Chrome đã được cài cho Selenium
- [ ] Firewall đã được cấu hình
- [ ] Domain giadungplus.io.vn đã trỏ về IP server

### Deploy Application
- [ ] Code đã được upload lên `/var/www/giadungplus`
- [ ] Virtual environment đã được tạo (`python3.10 -m venv venv`)
- [ ] Dependencies đã được cài đặt (`pip install -r requirements.txt`)
- [ ] Settings đã được cấu hình cho production (DEBUG=False, PostgreSQL, etc.)
- [ ] Database đã được migrate (`python manage.py migrate`)
- [ ] Superuser đã được tạo (`python manage.py createsuperuser`)
- [ ] Static files đã được collect (`python manage.py collectstatic`)

### Cấu hình Services
- [ ] Traefik đã được cấu hình và khởi động
- [ ] SSL certificate đã được tạo tự động
- [ ] Supervisor đã được cấu hình cho Gunicorn
- [ ] Gunicorn service đã được start và chạy
- [ ] Ứng dụng đã chạy thành công (kiểm tra qua browser)

### Backup & Maintenance
- [ ] Script backup đã được test (`sudo bash backup.sh`)
- [ ] Crontab đã được cấu hình cho backup tự động
- [ ] Đã test restore từ backup

---

## 🔒 Security Checklist

- [ ] `DEBUG = False` trong settings_production.py
- [ ] `SECRET_KEY` được lưu trong biến môi trường (khuyến nghị)
- [ ] Database password mạnh (đã đặt: 123122aC@)
- [ ] SSL/HTTPS đã được bật (tự động bởi Traefik)
- [ ] Firewall đã được cấu hình
- [ ] SSH key authentication thay vì password
- [ ] Regular updates: `sudo apt update && sudo apt upgrade`
- [ ] Traefik dashboard chỉ truy cập nội bộ (port 8080)

---

## 📞 Hỗ trợ

Nếu gặp vấn đề, kiểm tra:
1. Logs của Traefik: `sudo journalctl -u traefik -f`
2. Logs của Supervisor: `sudo supervisorctl tail -f giadungplus`
3. Logs của Gunicorn: `tail -f /var/www/giadungplus/logs/gunicorn-*.log`
4. Logs của Django: `tail -f /var/www/giadungplus/logs/*.log`
5. Status của các services: `sudo systemctl status <service-name>`

---

## 🔗 Thông tin hữu ích

- **Traefik Dashboard**: http://103.110.85.223:8080
- **Domain**: https://giadungplus.io.vn
- **IP**: https://103.110.85.223
- **Project Directory**: `/var/www/giadungplus`
- **Backup Directory**: `/var/backups/giadungplus`
- **Logs Directory**: `/var/www/giadungplus/logs`

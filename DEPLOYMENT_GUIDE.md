# Hướng dẫn Deploy và Migrate Database

## 📋 Mục lục
1. [Tự động deploy với GitHub Webhook](#tự-động-deploy-với-github-webhook)
2. [Migrate Database từ SQLite sang PostgreSQL](#migrate-database-từ-sqlite-sang-postgresql)
3. [Cấu hình Supervisor cho Webhook Handler](#cấu-hình-supervisor-cho-webhook-handler)
4. [Troubleshooting](#troubleshooting)

---

## 🚀 Tự động deploy với GitHub Webhook

### Bước 1: Cài đặt dependencies

Trên server Ubuntu:
```bash
cd /var/www/giadungplus
source venv/bin/activate
pip install flask
```

### Bước 2: Cấu hình Webhook Secret

Tạo secret key mạnh:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Lưu secret vào environment variable:
```bash
# Thêm vào ~/.bashrc hoặc /etc/environment
export WEBHOOK_SECRET="your-secret-key-here"
export PROJECT_DIR="/var/www/giadungplus"
export WEBHOOK_PORT=9000
export WEBHOOK_HOST="127.0.0.1"  # Chỉ listen localhost, dùng nginx reverse proxy
```

### Bước 3: Tạo systemd service cho Webhook Handler

Tạo file `/etc/systemd/system/giadungplus-webhook.service`:

```ini
[Unit]
Description=GIADUNGPLUS GitHub Webhook Handler
After=network.target

[Service]
Type=simple
User=giadungplus
WorkingDirectory=/var/www/giadungplus
Environment="PROJECT_DIR=/var/www/giadungplus"
Environment="WEBHOOK_SECRET=your-secret-key-here"
Environment="WEBHOOK_PORT=9000"
Environment="WEBHOOK_HOST=127.0.0.1"
ExecStart=/var/www/giadungplus/venv/bin/python /var/www/giadungplus/webhook_handler.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Khởi động service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable giadungplus-webhook
sudo systemctl start giadungplus-webhook
sudo systemctl status giadungplus-webhook
```

### Bước 4: Cấu hình Nginx reverse proxy

Thêm vào cấu hình Nginx (ví dụ: `/etc/nginx/sites-available/giadungplus`):

```nginx
# Webhook endpoint
location /webhook {
    proxy_pass http://127.0.0.1:9000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Timeout cho deploy process
    proxy_read_timeout 300s;
    proxy_connect_timeout 300s;
}
```

Reload Nginx:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### Bước 5: Cấu hình GitHub Webhook

1. Vào repository trên GitHub
2. Settings → Webhooks → Add webhook
3. Cấu hình:
   - **Payload URL**: `https://giadungplus.io.vn/webhook`
   - **Content type**: `application/json`
   - **Secret**: Nhập secret key đã tạo ở bước 2
   - **Events**: Chọn "Just the push event"
   - **Active**: ✓

4. Save webhook

### Bước 6: Test webhook

Push code lên GitHub và kiểm tra logs:
```bash
# Xem logs webhook
tail -f /var/www/giadungplus/logs/webhook.log

# Xem logs deploy
tail -f /var/www/giadungplus/logs/gunicorn-supervisor.log
```

---

## 🗄️ Migrate Database từ SQLite sang PostgreSQL

### Phương pháp 1: Sử dụng script tự động (Khuyến nghị)

#### Trên Windows (Máy dev):

1. **Export data từ SQLite:**
```bash
# Chạy script migrate
bash migrate_db_to_postgresql.sh
```

Script sẽ:
- Backup SQLite database
- Export tất cả data ra file JSON
- Tạo script import cho server

2. **Copy files lên server:**
```bash
# Copy file export
scp /tmp/sqlite_data.json user@server:/tmp/

# Copy script import
scp /tmp/import_to_postgresql.py user@server:/tmp/
```

#### Trên Server Ubuntu:

1. **Tạo database và user PostgreSQL (nếu chưa có):**
```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE giadungplus_db;
CREATE USER giadungplus WITH PASSWORD '123122aC@';
ALTER ROLE giadungplus SET client_encoding TO 'utf8';
ALTER ROLE giadungplus SET default_transaction_isolation TO 'read committed';
ALTER ROLE giadungplus SET timezone TO 'Asia/Ho_Chi_Minh';
GRANT ALL PRIVILEGES ON DATABASE giadungplus_db TO giadungplus;
\q
```

2. **Chạy migrations để tạo schema:**
```bash
cd /var/www/giadungplus
source venv/bin/activate
python manage.py migrate --settings=GIADUNGPLUS.settings_production
```

3. **Import data:**
```bash
python /tmp/import_to_postgresql.py
```

### Phương pháp 2: Sử dụng script Python (Đơn giản nhất - Khuyến nghị)

#### Trên Windows (Máy dev):

1. **Export data từ SQLite:**
```bash
python export_sqlite_data.py db_backup.json
```

Script sẽ export tất cả data từ SQLite ra file JSON.

2. **Copy file lên server:**
```bash
scp db_backup.json user@server:/tmp/
```

#### Trên Server Ubuntu:

1. **Copy script import lên server:**
```bash
scp import_sqlite_to_postgresql.py user@server:/var/www/giadungplus/
```

2. **Chạy migrations để tạo schema:**
```bash
cd /var/www/giadungplus
source venv/bin/activate
python manage.py migrate --settings=GIADUNGPLUS.settings_production
```

3. **Import data:**
```bash
python import_sqlite_to_postgresql.py import /tmp/db_backup.json
```

### Phương pháp 3: Sử dụng Django dumpdata/loaddata

#### Trên Windows (Máy dev):

1. **Export data:**
```bash
python manage.py dumpdata --natural-foreign --natural-primary -o db_backup.json
```

2. **Copy file lên server:**
```bash
scp db_backup.json user@server:/tmp/
```

#### Trên Server Ubuntu:

1. **Chạy migrations:**
```bash
cd /var/www/giadungplus
source venv/bin/activate
python manage.py migrate --settings=GIADUNGPLUS.settings_production
```

2. **Import data:**
```bash
python manage.py loaddata /tmp/db_backup.json --settings=GIADUNGPLUS.settings_production
```

### Phương pháp 4: Sử dụng pgloader (Nâng cao)

Nếu muốn migrate trực tiếp từ SQLite sang PostgreSQL:

1. **Cài đặt pgloader:**
```bash
sudo apt-get update
sudo apt-get install pgloader
```

2. **Tạo file migration script:**
```bash
cat > migrate.load <<EOF
LOAD DATABASE
    FROM sqlite:///path/to/db.sqlite3
    INTO postgresql://giadungplus:123122aC@localhost/giadungplus_db

WITH include drop, create tables, create indexes, reset sequences

SET work_mem to '256MB', maintenance_work_mem to '512MB';
EOF
```

3. **Chạy migration:**
```bash
pgloader migrate.load
```

**Lưu ý:** pgloader có thể cần điều chỉnh type mapping cho một số field.

---

## ⚙️ Cấu hình Supervisor cho Webhook Handler

Nếu không dùng systemd, có thể dùng Supervisor:

Tạo file `/etc/supervisor/conf.d/giadungplus-webhook.conf`:

```ini
[program:giadungplus-webhook]
directory=/var/www/giadungplus
command=/var/www/giadungplus/venv/bin/python /var/www/giadungplus/webhook_handler.py
user=giadungplus
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stderr_logfile=/var/www/giadungplus/logs/webhook-error.log
stdout_logfile=/var/www/giadungplus/logs/webhook.log
environment=PROJECT_DIR="/var/www/giadungplus",WEBHOOK_SECRET="your-secret-key",WEBHOOK_PORT="9000",WEBHOOK_HOST="127.0.0.1"
```

Reload Supervisor:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start giadungplus-webhook
```

---

## 🔧 Troubleshooting

### Webhook không hoạt động

1. **Kiểm tra service đang chạy:**
```bash
sudo systemctl status giadungplus-webhook
# hoặc
sudo supervisorctl status giadungplus-webhook
```

2. **Kiểm tra logs:**
```bash
tail -f /var/www/giadungplus/logs/webhook.log
```

3. **Kiểm tra Nginx:**
```bash
sudo nginx -t
sudo tail -f /var/log/nginx/error.log
```

4. **Test webhook thủ công:**
```bash
curl -X POST http://localhost:9000/webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: push" \
  -d '{"ref":"refs/heads/main"}'
```

### Migration lỗi

1. **Kiểm tra kết nối PostgreSQL:**
```bash
psql -U giadungplus -d giadungplus_db -h localhost
```

2. **Xem migrations chưa apply:**
```bash
python manage.py showmigrations --settings=GIADUNGPLUS.settings_production
```

3. **Rollback migration nếu cần:**
```bash
python manage.py migrate app_name migration_number --settings=GIADUNGPLUS.settings_production
```

### Deploy script lỗi

1. **Kiểm tra quyền thực thi:**
```bash
chmod +x deploy.sh
```

2. **Chạy thủ công để xem lỗi:**
```bash
bash -x deploy.sh
```

3. **Kiểm tra virtual environment:**
```bash
which python
source venv/bin/activate
which python
```

---

## 📝 Lưu ý quan trọng

1. **Backup database trước khi migrate:**
```bash
# PostgreSQL
pg_dump -U giadungplus giadungplus_db > backup_$(date +%Y%m%d).sql
```

2. **Test trên staging trước khi deploy production**

3. **Giữ secret key an toàn, không commit vào Git**

4. **Kiểm tra logs thường xuyên:**
```bash
# Xem tất cả logs
tail -f /var/www/giadungplus/logs/*.log
```

5. **Monitor disk space:**
```bash
df -h
du -sh /var/www/giadungplus/*
```

---

## 🔐 Bảo mật

1. **Webhook secret phải mạnh và bảo mật**
2. **Chỉ expose webhook endpoint qua HTTPS**
3. **Sử dụng firewall để giới hạn IP truy cập (nếu cần)**
4. **Không commit credentials vào Git**
5. **Sử dụng environment variables cho sensitive data**

---

## 📞 Hỗ trợ

Nếu gặp vấn đề, kiểm tra:
- Logs trong `/var/www/giadungplus/logs/`
- Service status: `sudo systemctl status giadungplus-webhook`
- Supervisor status: `sudo supervisorctl status giadungplus-webhook`
- Nginx logs: `sudo tail -f /var/log/nginx/error.log`

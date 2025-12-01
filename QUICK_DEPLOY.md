# 🚀 Hướng dẫn nhanh Deploy và Migrate Database

## 📦 Tự động Deploy với GitHub Webhook

### Setup một lần (trên server Ubuntu):

```bash
# 1. Cài Flask
cd /var/www/giadungplus
source venv/bin/activate
pip install flask

# 2. Tạo secret key
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# Copy secret key này

# 3. Tạo systemd service
sudo nano /etc/systemd/system/giadungplus-webhook.service
# (Paste nội dung từ DEPLOYMENT_GUIDE.md)

# 4. Khởi động service
sudo systemctl daemon-reload
sudo systemctl enable giadungplus-webhook
sudo systemctl start giadungplus-webhook

# 5. Cấu hình Nginx (thêm vào config)
sudo nano /etc/nginx/sites-available/giadungplus
# (Thêm location /webhook như trong DEPLOYMENT_GUIDE.md)
sudo nginx -t
sudo systemctl reload nginx

# 6. Cấu hình GitHub Webhook
# Vào GitHub repo → Settings → Webhooks → Add webhook
# URL: https://giadungplus.io.vn/webhook
# Secret: (paste secret key từ bước 2)
# Events: Just the push event
```

**Xong!** Mỗi lần push code lên GitHub, server sẽ tự động deploy.

---

## 🗄️ Migrate Database từ SQLite → PostgreSQL

### Bước 1: Trên Windows (Máy dev)

```bash
# Export data từ SQLite
python export_sqlite_data.py db_backup.json

# Copy lên server
scp db_backup.json user@server:/tmp/
```

### Bước 2: Trên Server Ubuntu

```bash
cd /var/www/giadungplus
source venv/bin/activate

# 1. Chạy migrations để tạo schema
python manage.py migrate --settings=GIADUNGPLUS.settings_production

# 2. Copy script import (nếu chưa có)
# (Script đã có trong repo: import_sqlite_to_postgresql.py)

# 3. Import data
python import_sqlite_to_postgresql.py import /tmp/db_backup.json
```

**Xong!** Database đã được migrate.

---

## 🔧 Kiểm tra và Troubleshooting

### Kiểm tra webhook hoạt động:
```bash
# Xem logs
tail -f /var/www/giadungplus/logs/webhook.log

# Test thủ công
curl -X POST http://localhost:9000/webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: push" \
  -d '{"ref":"refs/heads/main"}'
```

### Kiểm tra deploy:
```bash
# Xem logs deploy
tail -f /var/www/giadungplus/logs/gunicorn-supervisor.log

# Kiểm tra service
sudo supervisorctl status giadungplus
```

### Kiểm tra database:
```bash
# Kết nối PostgreSQL
psql -U giadungplus -d giadungplus_db -h localhost

# Xem tables
\dt

# Đếm records
SELECT COUNT(*) FROM cskh_ticket;
```

---

## 📝 Lưu ý

1. **Backup trước khi migrate:**
   ```bash
   # SQLite
   cp db.sqlite3 db.sqlite3.backup
   
   # PostgreSQL
   pg_dump -U giadungplus giadungplus_db > backup.sql
   ```

2. **Test trên staging trước production**

3. **Giữ secret key an toàn**

4. **Xem hướng dẫn chi tiết:** `DEPLOYMENT_GUIDE.md`


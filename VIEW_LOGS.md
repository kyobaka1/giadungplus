# 📊 Hướng dẫn xem Logs Server

## 🚀 Xem Logs Nhanh

### 1. Kiểm tra Status Tất Cả Services

```bash
# Kiểm tra tất cả services
echo "=== TRAEFIK ===" && sudo systemctl status traefik --no-pager -l
echo ""
echo "=== SUPERVISOR ===" && sudo systemctl status supervisor --no-pager -l
echo ""
echo "=== GIADUNGPLUS (Gunicorn) ===" && sudo supervisorctl status giadungplus
echo ""
echo "=== POSTGRESQL ===" && sudo systemctl status postgresql --no-pager -l
```

---

## 📋 Chi Tiết Từng Loại Log

### 1. Traefik Logs (Reverse Proxy)

```bash
# Xem logs real-time (follow)
sudo journalctl -u traefik -f

# Xem 50 dòng cuối
sudo journalctl -u traefik -n 50 --no-pager

# Xem logs từ hôm nay
sudo journalctl -u traefik --since today

# Xem logs theo thời gian cụ thể
sudo journalctl -u traefik --since "2025-11-29 10:00:00" --until "2025-11-29 12:00:00"

# Chỉ xem errors
sudo journalctl -u traefik -p err -n 50
```

### 2. Supervisor Logs (Process Manager)

```bash
# Xem status của tất cả programs
sudo supervisorctl status

# Xem status của giadungplus
sudo supervisorctl status giadungplus

# Xem logs real-time (tất cả output)
sudo supervisorctl tail -f giadungplus

# Xem logs chỉ stderr (errors)
sudo supervisorctl tail -f giadungplus stderr

# Xem logs chỉ stdout
sudo supervisorctl tail -f giadungplus stdout

# Xem 1000 dòng cuối
sudo supervisorctl tail -1000 giadungplus
```

### 3. Gunicorn Logs (Django WSGI Server)

```bash
# Xem access log (requests)
tail -f /var/www/giadungplus/logs/gunicorn-access.log

# Xem error log
tail -f /var/www/giadungplus/logs/gunicorn-error.log

# Xem supervisor log cho gunicorn
tail -f /var/www/giadungplus/logs/gunicorn-supervisor.log
tail -f /var/www/giadungplus/logs/gunicorn-supervisor-error.log

# Xem tất cả logs gunicorn
tail -f /var/www/giadungplus/logs/gunicorn-*.log
```

### 4. Django Application Logs

```bash
# Xem Django log (nếu có cấu hình trong settings)
tail -f /var/www/giadungplus/logs/django.log

# Xem tất cả logs trong thư mục logs
tail -f /var/www/giadungplus/logs/*.log

# Xem logs của các app cụ thể (nếu có)
tail -f /var/www/giadungplus/logs/cskh.log
tail -f /var/www/giadungplus/logs/orders.log
```

### 5. PostgreSQL Logs

```bash
# Xem PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-*.log

# Hoặc
sudo journalctl -u postgresql -f
```

---

## 🔍 Kiểm Tra Nhanh Server Status

### Script Kiểm Tra Tất Cả

Tạo file `check_server.sh`:

```bash
#!/bin/bash
# Script kiểm tra nhanh tất cả services

echo "🔍 === KIỂM TRA SERVER STATUS ==="
echo ""

echo "📊 1. Traefik Status:"
sudo systemctl is-active traefik && echo "✅ Traefik: ACTIVE" || echo "❌ Traefik: INACTIVE"
echo ""

echo "📊 2. Supervisor Status:"
sudo systemctl is-active supervisor && echo "✅ Supervisor: ACTIVE" || echo "❌ Supervisor: INACTIVE"
echo ""

echo "📊 3. Gunicorn (giadungplus) Status:"
sudo supervisorctl status giadungplus
echo ""

echo "📊 4. PostgreSQL Status:"
sudo systemctl is-active postgresql && echo "✅ PostgreSQL: ACTIVE" || echo "❌ PostgreSQL: INACTIVE"
echo ""

echo "📊 5. Ports đang listen:"
echo "   Port 80 (HTTP):"
sudo lsof -i :80 2>/dev/null | head -2 || echo "   ⚠️  Không có process nào"
echo "   Port 443 (HTTPS):"
sudo lsof -i :443 2>/dev/null | head -2 || echo "   ⚠️  Không có process nào"
echo "   Port 8000 (Gunicorn):"
sudo lsof -i :8000 2>/dev/null | head -2 || echo "   ⚠️  Không có process nào"
echo ""

echo "📊 6. Test ứng dụng:"
curl -s -o /dev/null -w "   HTTP Status: %{http_code}\n" http://localhost:8000 || echo "   ❌ Không thể kết nối"
echo ""

echo "📊 7. Errors gần đây (5 dòng):"
echo "   Traefik errors:"
sudo journalctl -u traefik -p err -n 5 --no-pager | tail -3 || echo "   ✅ Không có errors"
echo "   Gunicorn errors:"
tail -5 /var/www/giadungplus/logs/gunicorn-error.log 2>/dev/null | tail -3 || echo "   ✅ Không có errors"
echo ""
```

Chạy script:
```bash
chmod +x check_server.sh
./check_server.sh
```

---

## 🐛 Debugging Các Vấn Đề Thường Gặp

### 1. Ứng dụng không truy cập được

```bash
# Kiểm tra Gunicorn có chạy không
sudo supervisorctl status giadungplus

# Kiểm tra port 8000
sudo netstat -tlnp | grep 8000

# Xem errors gần đây
tail -50 /var/www/giadungplus/logs/gunicorn-error.log

# Test từ server
curl -v http://localhost:8000
```

### 2. Traefik không route được

```bash
# Xem Traefik logs
sudo journalctl -u traefik -n 50 --no-pager

# Kiểm tra cấu hình
cat /etc/traefik/dynamic/dynamic.yml

# Test Traefik dashboard
curl http://localhost:8080
```

### 3. Database connection errors

```bash
# Xem Django/Gunicorn errors
tail -50 /var/www/giadungplus/logs/gunicorn-error.log | grep -i "database\|psycopg\|postgres"

# Test database connection
psql -U giadungplus -d giadungplus_db -h localhost -c "SELECT version();"

# Xem PostgreSQL logs
sudo tail -50 /var/log/postgresql/postgresql-*.log
```

### 4. Static files không load

```bash
# Kiểm tra static files đã được collect chưa
ls -la /var/www/giadungplus/staticfiles/

# Xem Gunicorn access log để xem requests
tail -50 /var/www/giadungplus/logs/gunicorn-access.log | grep static
```

---

## 📝 Lệnh Hữu Ích Khác

### Xem Logs Theo Thời Gian

```bash
# Logs từ 1 giờ trước
sudo journalctl -u traefik --since "1 hour ago"

# Logs từ hôm qua
sudo journalctl -u traefik --since yesterday

# Logs của tuần này
sudo journalctl -u traefik --since "1 week ago"
```

### Tìm Kiếm Trong Logs

```bash
# Tìm lỗi trong Traefik logs
sudo journalctl -u traefik | grep -i error

# Tìm request cụ thể trong Gunicorn access log
grep "GET /kho/" /var/www/giadungplus/logs/gunicorn-access.log

# Đếm số requests
wc -l /var/www/giadungplus/logs/gunicorn-access.log

# Tìm 10 IP truy cập nhiều nhất
awk '{print $1}' /var/www/giadungplus/logs/gunicorn-access.log | sort | uniq -c | sort -rn | head -10
```

### Xóa Logs Cũ

```bash
# Xóa logs cũ hơn 7 ngày (cẩn thận!)
find /var/www/giadungplus/logs/ -name "*.log" -mtime +7 -delete

# Rotate logs (tạo file mới và giữ file cũ)
# Có thể dùng logrotate hoặc script tự động
```

---

## 🔗 Truy Cập Logs Qua Browser (Nếu cần)

Nếu muốn xem logs qua web interface, có thể cài đặt một số tools như:
- **Grafana Loki** - Log aggregation
- **ELK Stack** - Elasticsearch, Logstash, Kibana
- Hoặc tạo một Django view đơn giản để xem logs

---

## 📞 Tổng Hợp Lệnh Nhanh

```bash
# ⚡ Xem tất cả logs real-time (4 terminals)
# Terminal 1:
sudo journalctl -u traefik -f

# Terminal 2:
sudo supervisorctl tail -f giadungplus

# Terminal 3:
tail -f /var/www/giadungplus/logs/gunicorn-error.log

# Terminal 4:
tail -f /var/www/giadungplus/logs/gunicorn-access.log
```


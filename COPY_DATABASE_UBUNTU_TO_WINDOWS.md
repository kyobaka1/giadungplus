# Hướng dẫn Copy Database từ Ubuntu về Windows

## Yêu cầu

- Đã cài đặt PostgreSQL trên cả Ubuntu (server) và Windows (local)
- Có quyền truy cập SSH vào server Ubuntu
- Có quyền truy cập database trên cả 2 môi trường

## Cách 1: Sử dụng pg_dump và pg_restore (Khuyến nghị)

### Bước 1: Export Database từ Ubuntu Server

1. **SSH vào Ubuntu server:**
   ```bash
   ssh user@103.110.85.223
   # hoặc IP của server Ubuntu của bạn
   ```

2. **Export database ra file dump:**
   ```bash
   # Tạo thư mục tạm để chứa file dump
   mkdir -p ~/db_backup
   cd ~/db_backup
   
   # Export database (format custom - nén và có thể restore dễ dàng)
   pg_dump -U giadungplus -h localhost -d giadungplus_db -F c -f giadungplus_db_backup.dump
   
   # Hoặc export ra file SQL thông thường (không nén)
   pg_dump -U giadungplus -h localhost -d giadungplus_db -f giadungplus_db_backup.sql
   ```

3. **Copy file về Windows:**
   
   **Cách A: Sử dụng SCP (từ Windows PowerShell hoặc CMD với OpenSSH)**
   ```powershell
   # Từ Windows PowerShell
   scp user@103.110.85.223:~/db_backup/giadungplus_db_backup.dump D:\giadungplus\giadungplus-1\
   ```
   
   **Cách B: Sử dụng WinSCP (GUI tool - Dễ hơn)**
   - Tải WinSCP: https://winscp.net/
   - Kết nối vào server Ubuntu
   - Download file `giadungplus_db_backup.dump` về thư mục dự án trên Windows
   
   **Cách C: Sử dụng FileZilla hoặc bất kỳ FTP/SFTP client nào**

### Bước 2: Import Database vào Windows PostgreSQL

1. **Mở Command Prompt hoặc PowerShell trên Windows**

2. **Tạo database trống (nếu chưa có):**
   ```cmd
   "C:\Program Files\PostgreSQL\15\bin\psql.exe" -U postgres
   ```
   Trong psql:
   ```sql
   -- Drop database cũ nếu có (CẨN THẬN - sẽ xóa hết dữ liệu)
   DROP DATABASE IF EXISTS giadungplus_db;
   
   -- Tạo database mới
   CREATE DATABASE giadungplus_db OWNER giadungplus;
   
   -- Thoát
   \q
   ```

3. **Restore database:**
   
   **Nếu dùng file .dump (format custom - khuyến nghị):**
   ```cmd
   cd D:\giadungplus\giadungplus-1
   "C:\Program Files\PostgreSQL\15\bin\pg_restore.exe" -U postgres -d giadungplus_db -c giadungplus_db_backup.dump
   ```
   
   **Nếu dùng file .sql:**
   ```cmd
   cd D:\giadungplus\giadungplus-1
   "C:\Program Files\PostgreSQL\15\bin\psql.exe" -U postgres -d giadungplus_db -f giadungplus_db_backup.sql
   ```

4. **Nhập mật khẩu PostgreSQL** khi được yêu cầu

5. **Cấp quyền cho user (nếu cần):**
   ```cmd
   "C:\Program Files\PostgreSQL\15\bin\psql.exe" -U postgres -d giadungplus_db
   ```
   ```sql
   GRANT ALL ON SCHEMA public TO giadungplus;
   GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO giadungplus;
   GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO giadungplus;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO giadungplus;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO giadungplus;
   \q
   ```

## Cách 2: Sử dụng pg_dump qua SSH và pipe trực tiếp (Không cần lưu file)

Nếu bạn muốn copy trực tiếp mà không cần lưu file trung gian:

```bash
# Từ Windows PowerShell (cần có SSH và PostgreSQL tools)
ssh user@103.110.85.223 "pg_dump -U giadungplus -h localhost -d giadungplus_db -F c" | "C:\Program Files\PostgreSQL\15\bin\pg_restore.exe" -U postgres -d giadungplus_db -c
```

## Cách 3: Sử dụng pgAdmin 4 (GUI - Dễ hơn cho người mới)

### Trên Ubuntu (Export):

1. **Kết nối pgAdmin 4 từ Windows đến Ubuntu:**
   - Mở pgAdmin 4 trên Windows
   - Right-click "Servers" → "Create" → "Server..."
   - Tab General:
     - Name: `Ubuntu Production`
   - Tab Connection:
     - Host: `103.110.85.223` (hoặc IP server)
     - Port: `5432`
     - Database: `postgres`
     - Username: `giadungplus`
     - Password: `123122aC@`
   - Click "Save"

2. **Backup database:**
   - Expand server → Databases → `giadungplus_db`
   - Right-click → "Backup..."
   - Filename: chọn nơi lưu (ví dụ: `D:\giadungplus\giadungplus-1\giadungplus_db_backup.dump`)
   - Format: `Custom`
   - Click "Backup"

### Trên Windows (Restore):

1. **Kết nối vào PostgreSQL local:**
   - Trong pgAdmin 4, bạn sẽ thấy server local (thường là "PostgreSQL 15")
   - Expand → Databases

2. **Restore database:**
   - Right-click vào database `giadungplus_db` (hoặc tạo mới nếu chưa có)
   - Chọn "Restore..."
   - Filename: chọn file `giadungplus_db_backup.dump` vừa backup
   - Click "Restore"

## Kiểm tra sau khi Restore

1. **Kiểm tra kết nối Django:**
   ```cmd
   cd D:\giadungplus\giadungplus-1
   python manage.py dbshell
   ```
   
   Trong dbshell:
   ```sql
   \dt  -- Liệt kê các bảng
   SELECT COUNT(*) FROM auth_user;  -- Test query
   \q
   ```

2. **Chạy migrations (nếu cần):**
   ```cmd
   python manage.py migrate
   ```

3. **Kiểm tra trong Django admin hoặc chạy server:**
   ```cmd
   python manage.py runserver
   ```

## Lưu ý quan trọng

1. **Backup trước khi restore:**
   - Luôn backup database Windows hiện tại trước khi restore
   - Nếu database Windows đang có dữ liệu quan trọng, hãy backup trước

2. **Xung đột dữ liệu:**
   - Nếu restore vào database đã có dữ liệu, có thể có xung đột
   - Tốt nhất là tạo database mới hoặc drop database cũ trước

3. **Permissions:**
   - Đảm bảo user `giadungplus` có đủ quyền trên database
   - Nếu gặp lỗi permission, dùng user `postgres` (superuser)

4. **Version compatibility:**
   - PostgreSQL version trên Ubuntu và Windows nên tương đương hoặc Windows cao hơn
   - Nếu version khác nhau nhiều, có thể gặp vấn đề

5. **Large databases:**
   - Với database lớn, quá trình dump/restore có thể mất nhiều thời gian
   - Format custom (.dump) thường nhanh hơn format SQL (.sql)

## Script tự động (Tùy chọn)

Bạn có thể tạo script để tự động hóa quá trình này:

**backup_from_ubuntu.bat** (Windows):
```batch
@echo off
echo Exporting database from Ubuntu...
ssh user@103.110.85.223 "pg_dump -U giadungplus -h localhost -d giadungplus_db -F c" > giadungplus_db_backup.dump

echo Restoring to local PostgreSQL...
"C:\Program Files\PostgreSQL\15\bin\pg_restore.exe" -U postgres -d giadungplus_db -c giadungplus_db_backup.dump

echo Done!
pause
```

## Troubleshooting

### Lỗi: "pg_dump: error: connection to server failed"
- Kiểm tra PostgreSQL service trên Ubuntu đang chạy
- Kiểm tra firewall đã mở port 5432
- Kiểm tra file `pg_hba.conf` cho phép kết nối local

### Lỗi: "permission denied" khi restore
- Dùng user `postgres` (superuser) để restore
- Hoặc cấp quyền cho user `giadungplus`

### Lỗi: "encoding mismatch"
- Export với encoding cụ thể:
  ```bash
  pg_dump -U giadungplus -d giadungplus_db --encoding=UTF8 -f backup.sql
  ```

### Lỗi: "schema already exists"
- Dùng option `-c` (clean) khi restore để drop các object trước:
  ```cmd
  pg_restore -U postgres -d giadungplus_db -c backup.dump
  ```


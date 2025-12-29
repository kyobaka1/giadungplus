# Hướng dẫn Copy Dữ liệu từ Production (Ubuntu/PostgreSQL) về Test (Windows/SQLite)

## Tổng quan

Hệ thống có 2 môi trường:
- **Production**: Ubuntu + PostgreSQL (settings_production.py)
- **Test**: Windows + SQLite (settings.py)

## Các bước thực hiện

### Bước 1: Export dữ liệu trên Ubuntu (Production)

1. SSH vào server Ubuntu
2. Di chuyển đến thư mục project:
   ```bash
   cd /var/www/giadungplus
   # hoặc đường dẫn tương ứng trên server của bạn
   ```

3. Cấp quyền thực thi cho script (nếu chưa có):
   ```bash
   chmod +x export_data.sh
   ```

4. Chạy script export:
   ```bash
   ./export_data.sh
   ```

5. Script sẽ tạo file backup trong thư mục `data_backup/` với tên:
   - `db_backup_YYYYMMDD_HHMMSS.json`

6. Copy file backup về máy Windows:
   - Sử dụng SCP, SFTP, hoặc bất kỳ phương thức nào bạn thường dùng
   - Ví dụ với SCP:
     ```bash
     scp user@server:/var/www/giadungplus/data_backup/db_backup_*.json ./
     ```

### Bước 2: Import dữ liệu trên Windows (Test)

**Cách 1: Sử dụng script batch (import_data.bat)**

1. Đặt file backup vào một trong các vị trí:
   - Thư mục `data_backup/` trong project
   - Thư mục gốc của project (cùng cấp với `manage.py`)

2. Chạy script:
   ```cmd
   import_data.bat
   ```

3. Script sẽ:
   - Tự động tìm file backup mới nhất
   - Hỏi xác nhận trước khi import
   - Backup database hiện tại (nếu có)
   - Xóa database cũ và tạo mới
   - Import dữ liệu từ file backup

**Cách 2: Sử dụng script Python (import_data.py)**

1. Đặt file backup vào một trong các vị trí:
   - Thư mục `data_backup/` trong project
   - Thư mục gốc của project (cùng cấp với `manage.py`)

2. Chạy script:
   ```cmd
   python import_data.py
   ```

3. Script sẽ hoạt động tương tự như script batch

## Lưu ý quan trọng

⚠️ **CẢNH BÁO**: 
- Khi import, toàn bộ dữ liệu hiện tại trong database SQLite sẽ bị **GHI ĐÈ**
- Script sẽ tự động backup database cũ trước khi import
- File backup có dạng: `db.sqlite3.backup_YYYYMMDD_HHMMSS`

## Xử lý lỗi

### Lỗi khi export trên Ubuntu

- **Lỗi kết nối database**: Kiểm tra PostgreSQL đang chạy và thông tin kết nối trong `settings_production.py`
- **Lỗi permission**: Đảm bảo user có quyền ghi vào thư mục `data_backup/`

### Lỗi khi import trên Windows

- **File không tìm thấy**: Đảm bảo file backup đã được copy đúng vị trí
- **Lỗi migrate**: Chạy `python manage.py migrate` trước khi import
- **Lỗi import**: Kiểm tra file backup có đầy đủ và không bị hỏng

### Restore database cũ

Nếu cần khôi phục database cũ:
```cmd
copy db.sqlite3.backup_YYYYMMDD_HHMMSS db.sqlite3
```

## Cấu trúc file

```
project/
├── export_data.sh          # Script export (Ubuntu)
├── import_data.bat          # Script import batch (Windows)
├── import_data.py           # Script import Python (Windows)
├── data_backup/            # Thư mục chứa file backup
│   ├── db_backup_*.json    # File backup dữ liệu
│   └── README.txt          # Hướng dẫn tự động
└── db.sqlite3              # Database SQLite (sẽ bị ghi đè)
```

## Tùy chỉnh

### Export chỉ một số apps cụ thể

Sửa file `export_data.sh`, thay đổi lệnh dumpdata:
```bash
python3 manage.py dumpdata \
    --settings=GIADUNGPLUS.settings_production \
    app1 app2 app3 \
    --natural-foreign \
    --natural-primary \
    --indent 2 \
    --output "$OUTPUT_FILE"
```

### Exclude một số models

Thêm `--exclude` vào lệnh dumpdata:
```bash
python3 manage.py dumpdata \
    --settings=GIADUNGPLUS.settings_production \
    --exclude auth.permission \
    --exclude sessions \
    --natural-foreign \
    --natural-primary \
    --indent 2 \
    --output "$OUTPUT_FILE"
```


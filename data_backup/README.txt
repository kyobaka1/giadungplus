HƯỚNG DẪN SỬ DỤNG BACKUP DATA
==============================

File backup: data_backup/db_backup_20251229_222702.json
Ngày tạo: Mon Dec 29 10:27:36 PM +07 2025

CÁCH SỬ DỤNG:
1. Copy file data_backup/db_backup_20251229_222702.json về máy Windows
2. Đặt file vào thư mục gốc của project (cùng cấp với manage.py)
3. Chạy script import_data.bat hoặc import_data.py trên Windows

LƯU Ý:
- File này chứa toàn bộ dữ liệu từ database production
- Khi import vào Windows, dữ liệu cũ sẽ bị ghi đè
- Nên backup database Windows trước khi import

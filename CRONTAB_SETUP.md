# Hướng dẫn setup Crontab cho Auto Xpress Push

## Tính năng
Tự động xử lý đơn hoả tốc mỗi 5 phút:
- Tìm lại shipper cho đơn đã chuẩn bị hàng (có tracking code)
- Tự động chuẩn bị hàng cho đơn chưa chuẩn bị (hơn 50 phút)

## Cài đặt Crontab

### 1. Mở crontab editor
```bash
crontab -e
```

### 2. Thêm dòng sau (chạy mỗi 5 phút)
```bash
*/5 * * * * cd /path/to/giadungplus-1 && /path/to/python manage.py auto_xpress_push >> /path/to/logs/auto_xpress_push.log 2>&1
```

### 3. Ví dụ cụ thể (tùy chỉnh theo môi trường của bạn)

#### Nếu dùng virtual environment:
```bash
*/5 * * * * cd /home/user/giadungplus-1 && /home/user/venv/bin/python manage.py auto_xpress_push >> /home/user/giadungplus-1/logs/auto_xpress_push.log 2>&1
```

#### Nếu dùng system Python:
```bash
*/5 * * * * cd /home/user/giadungplus-1 && /usr/bin/python3 manage.py auto_xpress_push >> /home/user/giadungplus-1/logs/auto_xpress_push.log 2>&1
```

#### Windows (dùng Task Scheduler):
1. Mở Task Scheduler
2. Tạo task mới
3. Trigger: Mỗi 5 phút
4. Action: Chạy script PowerShell hoặc batch file

Tạo file `run_auto_xpress_push.bat`:
```batch
@echo off
cd /d d:\giadungplus\giadungplus-1
python manage.py auto_xpress_push >> logs\auto_xpress_push.log 2>&1
```

## Kiểm tra

### Xem log:
```bash
tail -f logs/auto_xpress_push.log
```

### Test command thủ công:
```bash
python manage.py auto_xpress_push --limit 10
```

### Kiểm tra crontab đã được thêm:
```bash
crontab -l
```

## Lưu ý

1. **Đường dẫn**: Đảm bảo đường dẫn đến project và Python đúng
2. **Quyền**: Đảm bảo user có quyền chạy Django command
3. **Environment**: Nếu dùng virtual environment, phải activate hoặc dùng đường dẫn đầy đủ
4. **Log**: Tạo thư mục `logs` nếu chưa có
5. **HOME_PARAM**: Command sẽ tự động lọc theo HOME_PARAM (HN hoặc HCM)

## Troubleshooting

### Command không chạy:
- Kiểm tra đường dẫn Python và project
- Kiểm tra quyền thực thi
- Xem log trong `/var/log/cron` (Linux) hoặc Event Viewer (Windows)

### Lỗi import module:
- Đảm bảo đang ở đúng thư mục project
- Kiểm tra PYTHONPATH
- Activate virtual environment nếu có

### Không tìm thấy đơn:
- Kiểm tra connection_ids trong system_settings
- Kiểm tra shippingCarrierIds có đúng không
- Kiểm tra HOME_PARAM có đúng không

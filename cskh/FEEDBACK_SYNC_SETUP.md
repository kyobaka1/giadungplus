# Feedback Sync System - Setup Guide

## Tổng quan

Hệ thống sync feedback từ Shopee API với 2 chế độ:
- **Full Sync**: Sync toàn bộ feedbacks (200k từ 5 shops), chạy nền, có thể resume
- **Incremental Sync**: Chạy định kỳ 5 phút/lần để cập nhật feedbacks mới

## Cài đặt

### 1. Chạy Migration

```bash
python manage.py migrate cskh
```

### 2. Full Sync (Chạy 1 lần hoặc khi cần)

```bash
# Sync toàn bộ feedbacks (365 ngày gần nhất)
python manage.py sync_feedbacks_full --days 365 --page-size 50

# Sync với giới hạn số lượng mỗi shop
python manage.py sync_feedbacks_full --days 365 --page-size 50 --max-feedbacks-per-shop 10000

# Resume từ job đã bị dừng
python manage.py sync_feedbacks_full --resume-job-id <job_id>
```

### 3. Incremental Sync (Chạy định kỳ)

#### Windows (Task Scheduler)

1. Mở Task Scheduler
2. Tạo task mới:
   - **Trigger**: Mỗi 5 phút
   - **Action**: Start a program
   - **Program**: `python`
   - **Arguments**: `manage.py sync_feedbacks_incremental --batch-size 50`
   - **Start in**: `D:\giadungplus\giadungplus-1`

#### Linux/Mac (Cron)

Thêm vào crontab:

```bash
# Mở crontab
crontab -e

# Thêm dòng sau (chạy mỗi 5 phút)
*/5 * * * * cd /path/to/giadungplus-1 && /path/to/python manage.py sync_feedbacks_incremental --batch-size 50 >> /path/to/logs/incremental_sync.log 2>&1
```

#### Kiểm tra cron job

```bash
# Xem cron jobs
crontab -l

# Xem logs
tail -f /path/to/logs/incremental_sync.log
```

## Monitor Progress

### UI Dashboard

Truy cập: `/cskh/feedback/sync-status/`

Hiển thị:
- Thống kê tổng quan (tổng jobs, đang chạy, hoàn thành, thất bại)
- Danh sách jobs với progress bar
- Logs và errors chi tiết
- Auto-refresh cho jobs đang chạy

### API Endpoint

```bash
# Lấy status của job
GET /cskh/api/feedback/sync/status/<job_id>/
```

Response:
```json
{
  "id": 1,
  "sync_type": "full",
  "status": "running",
  "total_feedbacks": 200000,
  "processed_feedbacks": 50000,
  "synced_feedbacks": 45000,
  "updated_feedbacks": 5000,
  "error_count": 10,
  "progress_percentage": 25.0,
  "started_at": "2026-01-03T10:00:00Z",
  "recent_logs": [...],
  "recent_errors": [...]
}
```

## Logic Incremental Sync

1. Lấy feedback mới nhất từ DB (theo `create_time`)
2. Set `time_end = now`, `time_start = last_feedback.create_time - 1 giờ`
3. Quét từ page 1, mỗi batch 50 feedbacks
4. Với mỗi feedback:
   - Nếu đã có trong DB (check `feedback_id`) -> **DỪNG** (đã hết mới)
   - Nếu chưa có -> sync vào DB
5. Nếu batch có ít hơn 50 feedbacks -> dừng (đã hết)
6. Nếu batch đầy 50 và không có feedback trùng -> tiếp tục quét

## Error Handling

- Mỗi feedback được xử lý trong try-except riêng
- Lỗi được log vào `job.errors` nhưng không dừng process
- Job status được update sau mỗi batch
- **Resume Support**: 
  - Tự động lưu `current_page` và `current_cursor` sau mỗi batch
  - Resume theo shop: tiếp tục từ shop đang dở (`current_shop_index`)
  - Resume trong shop: tiếp tục từ page/cursor đã lưu (`current_page`, `current_cursor`)
  - Nếu job bị dừng đột ngột, dùng `update_job_resume_position` để update page/cursor

## Troubleshooting

### Job bị stuck ở status "running"

```bash
# Kiểm tra job
python manage.py shell
>>> from cskh.models import FeedbackSyncJob
>>> job = FeedbackSyncJob.objects.get(id=<job_id>)
>>> job.status = 'paused'
>>> job.save()
```

### Update resume position (page/cursor) khi job bị dừng đột ngột

Khi job bị dừng đột ngột (Ctrl+C), có thể chưa kịp lưu `current_page` và `current_cursor`. Dùng command sau để update:

#### Method 1: Từ Feedback ID cuối cùng (Khuyến nghị)

```bash
# Tự động tìm feedback_id cuối cùng từ DB và tìm page/cursor
python manage.py update_job_resume_position --job-id 1 --method from_feedback_id

# Hoặc chỉ định feedback_id cụ thể
python manage.py update_job_resume_position --job-id 1 --method from_feedback_id --feedback-id 54755172163
```

#### Method 2: Parse từ Logs

```bash
# Tìm page/cursor từ logs (tìm dòng "Page X | Cursor Y")
python manage.py update_job_resume_position --job-id 1 --method from_logs
```

#### Method 3: Manual set (nếu đã biết page/cursor)

```bash
# Set trực tiếp page và cursor
python manage.py update_job_resume_position --job-id 1 --method manual --page 100 --cursor 54755172163
```

#### Kiểm tra resume position hiện tại

```bash
python manage.py shell
>>> from cskh.models import FeedbackSyncJob
>>> job = FeedbackSyncJob.objects.get(id=1)
>>> print(f"Shop: {job.current_shop_name}")
>>> print(f"Page: {job.current_page}")
>>> print(f"Cursor: {job.current_cursor}")
>>> print(f"Connection ID: {job.current_connection_id}")
```

### Xóa jobs cũ

```bash
python manage.py shell
>>> from cskh.models import FeedbackSyncJob
>>> FeedbackSyncJob.objects.filter(status='completed').delete()
```

### Kiểm tra logs

```bash
# Xem logs của job
python manage.py shell
>>> from cskh.models import FeedbackSyncJob
>>> job = FeedbackSyncJob.objects.get(id=<job_id>)
>>> print('\n'.join(job.logs[-50:]))  # 50 logs gần nhất
```


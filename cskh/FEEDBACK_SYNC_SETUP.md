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
- Có thể resume job từ điểm dừng (lưu `current_connection_id`, `current_page`, `current_cursor`)

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


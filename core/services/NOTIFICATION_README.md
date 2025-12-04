# Hệ thống Notification - Hướng dẫn sử dụng

## Tổng quan

Hệ thống notification được xây dựng với 4 lớp:
1. **Business Layer** (Ticket, Đơn hàng, Kho, CSKH…) - Đã và đang xây dựng
2. **Notification Engine** - Xử lý "gửi cho ai / kênh nào / khi nào"
3. **Delivery** - Web Push, In-app
4. **Frontend** - Chuông thông báo + push trên PC/iPhone/Android

## Cấu trúc

### Models

- **Notification**: Lưu trữ thông báo
- **NotificationDelivery**: Lưu trữ việc gửi thông báo tới từng user qua từng kênh

### Services

- **`core/services/notify.py`**: Service tái sử dụng để gọi từ mọi app
- **`core/services/notification_engine.py`**: Engine xử lý routing và tạo bản ghi
- **`core/services/notification_delivery.py`**: Worker gửi notification thực sự

## Cách sử dụng

### 1. Gửi notification từ Business Layer

```python
from core.services.notify import notify

# Gửi cho group
notify.send(
    title="Ticket mới",
    body="Có ticket #123 cần xử lý",
    groups=["CSKHManager", "CSKHStaff"],
    link="/cskh/tickets/123",
    event_type="ticket_created",
    context={"ticket_id": 123, "order_code": "ORD001"},
)

# Gửi cho department
notify.send(
    title="Đơn hàng mới",
    body="Có đơn hàng #456 cần xử lý",
    departments=["KHO_HN"],
    link="/kho/orders/456",
)

# Gửi cho tất cả users
notify.send(
    title="Thông báo chung",
    body="Nội dung thông báo",
    groups="ALL",
)

# Gửi với action và sound
notify.send(
    title="Thông báo quan trọng",
    body="Cần xử lý ngay",
    action="boss_popup",
    sound="/static/sounds/alert.mp3",
    groups=["ALL"],
)

# Badge update với collapse_id (đè notify cũ)
notify.send(
    title="",
    body="",
    action="badge_update",
    count=5,
    collapse_id="ticket_count",
    groups=["CSKHStaff"],
)

# Hẹn giờ gửi
from datetime import datetime, timedelta
notify.send(
    title="Nhắc nhở",
    body="Nhắc nhở sau 1 giờ",
    scheduled_time=datetime.now() + timedelta(hours=1),
    groups=["ALL"],
)
```

### 2. Các tham số

#### Target Criteria (có thể dùng "ALL" để chọn tất cả)

- **groups**: Danh sách tên group hoặc "ALL"
  - Ví dụ: `["Admin", "CSKHManager"]` hoặc `"ALL"`
- **departments**: Danh sách department từ `user.last_name` hoặc "ALL"
  - Các giá trị: `CSKH`, `Marketing`, `QUẢN TRỊ VIÊN`, `KHO_HN`, `KHO_HCM`
- **shops**: Danh sách shop group hoặc "ALL"
  - Ví dụ: `["SHOP_GIADUNGPLUS", "SHOP_LTENG"]`
- **user_ids**: Danh sách user ID cụ thể hoặc 1 user ID
  - Ví dụ: `[1, 2, 3]` hoặc `1`

#### Notification Options

- **title**: Tiêu đề thông báo (bắt buộc)
- **body**: Nội dung thông báo
- **link**: URL khi click vào thông báo
- **action**: Loại hành động
  - `show_popup`: Hiển thị popup (mặc định)
  - `play_sound`: Phát âm thanh
  - `badge_update`: Cập nhật badge
  - `boss_popup`: Thông báo của sếp
- **sound**: Link sound ở `/static/` (nếu có)
- **count**: Số lượng cho `badge_update`
- **collapse_id**: ID để đè notify cũ bằng notify mới
- **tag**: Tag phân loại thông báo
- **scheduled_time**: Thời gian hẹn gửi (None = gửi ngay)
- **event_type**: Loại event từ business layer
- **context**: Dữ liệu context từ business layer (JSON dict)

## API Endpoints

### 1. Lấy danh sách notifications

```
GET /api/notifications/
```

Query params:
- `limit`: Số lượng (mặc định: 50)
- `offset`: Offset (mặc định: 0)
- `unread_only`: Chỉ lấy chưa đọc (true/false, mặc định: false)

Response:
```json
{
  "count": 100,
  "next": true,
  "previous": false,
  "results": [
    {
      "id": 1,
      "notification_id": 1,
      "title": "Ticket mới",
      "body": "Có ticket cần xử lý",
      "link": "/cskh/tickets/123",
      "action": "show_popup",
      "sound": "",
      "count": null,
      "tag": "",
      "event_type": "ticket_created",
      "context": {},
      "is_read": false,
      "read_at": null,
      "created_at": "2025-12-04T10:00:00Z"
    }
  ]
}
```

### 2. Lấy số lượng chưa đọc

```
GET /api/notifications/unread-count/
```

Response:
```json
{
  "count": 5
}
```

### 3. Đánh dấu đã đọc

```
POST /api/notifications/<delivery_id>/mark-read/
```

Response:
```json
{
  "success": true
}
```

### 4. Đánh dấu tất cả đã đọc

```
POST /api/notifications/mark-all-read/
```

Response:
```json
{
  "success": true,
  "updated": 10
}
```

## Management Commands

### Xử lý notifications

Chạy command này mỗi 10 phút bằng cron để:
- Gửi các scheduled notifications đã đến giờ
- Xử lý pending deliveries

```bash
python manage.py process_notifications
```

Cron job mẫu:
```bash
*/10 * * * * cd /path/to/project && python manage.py process_notifications
```

Options:
- `--limit`: Giới hạn số lượng deliveries xử lý
- `--notification-id`: Chỉ xử lý deliveries của notification này

## Ví dụ tích hợp

### Khi tạo ticket trong CSKH

```python
# cskh/views_api.py hoặc cskh/services/ticket_service.py
from core.services.notify import notify

def create_ticket(...):
    # ... tạo ticket ...
    
    # Gửi notification cho CSKH staff
    notify.send(
        title=f"Ticket mới: {ticket.title}",
        body=f"Ticket #{ticket.id} cần xử lý",
        groups=["CSKHManager", "CSKHStaff"],
        link=f"/cskh/tickets/{ticket.id}",
        event_type="ticket_created",
        context={
            "ticket_id": ticket.id,
            "order_code": ticket.order_code,
        },
    )
    
    return ticket
```

### Khi có đơn hàng mới trong Kho

```python
# kho/views/orders.py hoặc kho/services/order_service.py
from core.services.notify import notify

def process_new_order(...):
    # ... xử lý đơn hàng ...
    
    # Gửi notification cho kho tương ứng
    department = "KHO_HN" if location_id == 241737 else "KHO_HCM"
    notify.send(
        title=f"Đơn hàng mới: {order_code}",
        body=f"Đơn hàng {order_code} cần xử lý",
        departments=[department],
        link=f"/kho/orders/{order_id}",
        event_type="order_created",
        context={
            "order_id": order_id,
            "order_code": order_code,
        },
    )
```

### Cập nhật badge số lượng ticket chưa xử lý

```python
from core.services.notify import notify

def update_ticket_badge():
    count = Ticket.objects.filter(status='pending').count()
    
    notify.send(
        title="",
        body="",
        action="badge_update",
        count=count,
        collapse_id="ticket_count",  # Đè notify cũ
        groups=["CSKHStaff"],
    )
```

## Frontend Integration

### 1. Hiển thị chuông thông báo

Cần tạo component chuông thông báo trong frontend:
- Gọi API `/api/notifications/unread-count/` để lấy số lượng chưa đọc
- Hiển thị badge số lượng
- Khi click, hiển thị danh sách từ `/api/notifications/`

### 2. Đánh dấu đã đọc

Khi user click vào notification hoặc mở danh sách:
- Gọi API `/api/notifications/<delivery_id>/mark-read/`
- Cập nhật UI (xám đi, giảm badge count)

## Lưu ý

1. **Scheduled Notifications**: Cần chạy `process_notifications` command định kỳ (mỗi 10 phút)
2. **Web Push**: Cần user đã đăng ký subscription (tự động qua `push-setup.js`)
3. **Collapse ID**: Dùng để đè notify cũ bằng notify mới (ví dụ: badge count)
4. **Groups/Departments**: Có thể dùng "ALL" để gửi cho tất cả users


# Notification Bell - Frontend Component

## Tổng quan

Component chuông thông báo đã được tích hợp vào:
- `kho/templates/kho/base_kho.html` - Base template cho module Kho
- `core/templates/core/dashboard.html` - Dashboard chính

## Files

1. **`core/templates/core/notification_bell.html`** - HTML component
2. **`assets/js/notifications.js`** - JavaScript xử lý logic

## Tính năng

### 1. Badge số lượng chưa đọc
- Hiển thị badge đỏ với số lượng notifications chưa đọc
- Tự động cập nhật mỗi 30 giây (polling)
- Ẩn khi không có notification chưa đọc

### 2. Dropdown danh sách notifications
- Click vào chuông để mở dropdown
- Hiển thị tối đa 50 notifications mới nhất
- Phân biệt đã đọc/chưa đọc (màu sắc khác nhau)
- Hiển thị thời gian tương đối (ví dụ: "5 phút trước")

### 3. Đánh dấu đã đọc
- Tự động đánh dấu đã đọc khi click vào notification
- Nút "Đánh dấu tất cả đã đọc" khi có notifications chưa đọc
- Cập nhật badge ngay lập tức

### 4. Navigation
- Click vào notification để điều hướng đến link (nếu có)
- Nút "Xem tất cả thông báo" ở footer (có thể customize)

## API Endpoints sử dụng

- `GET /api/notifications/unread-count/` - Lấy số lượng chưa đọc
- `GET /api/notifications/?limit=50&offset=0` - Lấy danh sách notifications
- `POST /api/notifications/<id>/mark-read/` - Đánh dấu đã đọc
- `POST /api/notifications/mark-all-read/` - Đánh dấu tất cả đã đọc

## Cách sử dụng

### Tích hợp vào template mới

1. Include component:
```django
{% include 'core/notification_bell.html' %}
```

2. Load JavaScript:
```django
<script src="{% static 'js/notifications.js' %}"></script>
```

### Customize

#### Thay đổi polling interval

Trong `assets/js/notifications.js`:
```javascript
const CONFIG = {
    apiBaseUrl: '/api/notifications',
    pollInterval: 30000, // Thay đổi giá trị này (milliseconds)
    maxNotifications: 50,
};
```

#### Thay đổi số lượng notifications hiển thị

Trong `assets/js/notifications.js`:
```javascript
const CONFIG = {
    maxNotifications: 100, // Thay đổi giá trị này
};
```

#### Customize styling

Component sử dụng Tailwind CSS. Có thể override trong template:
```django
<style>
    #notificationBellContainer {
        /* Custom styles */
    }
</style>
```

## JavaScript API

Component expose một số functions để sử dụng từ bên ngoài:

```javascript
// Refresh unread count
window.NotificationBell.refresh();

// Load notifications list
window.NotificationBell.loadNotifications();

// Stop polling
window.NotificationBell.stopPolling();
```

## Responsive

- Mobile: Dropdown full width với max-height
- Desktop: Dropdown 320px (md) hoặc 384px (lg)
- Badge tự động điều chỉnh kích thước

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
- Mobile browsers (iOS Safari, Chrome Android)

## Troubleshooting

### Badge không hiển thị
- Kiểm tra console có lỗi không
- Kiểm tra API `/api/notifications/unread-count/` có trả về đúng không
- Kiểm tra user đã login chưa

### Dropdown không mở
- Kiểm tra JavaScript có load không
- Kiểm tra console có lỗi không
- Kiểm tra z-index (dropdown có z-50)

### Notifications không load
- Kiểm tra network tab xem API call có thành công không
- Kiểm tra authentication (user phải login)
- Kiểm tra CORS nếu dùng domain khác


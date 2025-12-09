# GDP Media Tracker Extension

Chrome Extension để track video/audio từ các trang web: tmall, douyin, 1688, taobao, xiaohongshu, pinterest.

## Cài đặt

1. Mở Chrome và vào `chrome://extensions/`
2. Bật "Developer mode" (góc trên bên phải)
3. Click "Load unpacked"
4. Chọn thư mục `assets/gdp_extension`
5. Extension sẽ được cài đặt

## Cấu hình

1. Click vào icon extension trên thanh toolbar
2. Click "Cài đặt" hoặc click chuột phải vào icon > Options
3. Nhập:
   - **Username**: Username của bạn (phải trùng với username trên Django admin)
   - **API URL**: Địa chỉ API endpoint (mặc định: http://127.0.0.1:8000/marketing/tools/get-videos/api/)
4. Click "Lưu cài đặt"

## Sử dụng

- Extension tự động track video/audio khi bạn lướt các trang web có chứa: tmall, douyin, 1688, taobao, xiaohongshu, pinterest
- Các file được track: .mp3, .mp4, .mov
- Dữ liệu sẽ được gửi tự động về Django backend
- Xem danh sách video đã track tại: http://127.0.0.1:8000/marketing/tools/get-videos/

## Icon Files

Extension cần các file icon:
- icon16.png (16x16)
- icon48.png (48x48)
- icon128.png (128x128)

Bạn có thể tạo các icon này hoặc sử dụng favicon.png từ assets/ và resize thành các kích thước trên.


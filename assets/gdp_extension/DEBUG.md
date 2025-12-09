# Debug Guide - GDP Media Tracker Extension

## Kiểm tra Extension có hoạt động không

### 1. Kiểm tra Console Logs

**Trong Content Script (trang web):**
1. Mở trang web (ví dụ: xiaohongshu.com)
2. Mở Developer Tools (F12)
3. Vào tab Console
4. Tìm các log bắt đầu bằng `[GDP Media Tracker]`

Bạn sẽ thấy:
- `[GDP Media Tracker] Tracking page: https://...`
- `[GDP Media Tracker] Scanning for media elements...`
- `[GDP Media Tracker] Found X video elements`
- `[GDP Media Tracker] Sending media: ...`

**Trong Background Script (Service Worker):**
1. Vào `chrome://extensions/`
2. Tìm "GDP Media Tracker Ext"
3. Click "service worker" hoặc "background page"
4. Xem console logs

Bạn sẽ thấy:
- `[GDP Media Tracker] Sending to backend: ...`
- `[GDP Media Tracker] Media tracked successfully: ...`
- Hoặc lỗi nếu có vấn đề

### 2. Kiểm tra API có nhận request không

**Trong Django console:**
Bạn sẽ thấy logs:
```
[GDP Media Tracker API] Received request: giadungplus - https://...
[GDP Media Tracker API] Successfully saved: ID=1, URL=...
```

Nếu không thấy logs này, có nghĩa là request chưa đến được Django.

### 3. Kiểm tra Network Requests

1. Mở Developer Tools (F12)
2. Vào tab Network
3. Filter: "get-videos" hoặc "api"
4. Reload trang
5. Xem có request nào đến `/marketing/tools/get-videos/api/` không

### 4. Các vấn đề thường gặp

**Vấn đề: Không thấy video nào được track**

Nguyên nhân có thể:
- Trang web không có video/audio elements trong DOM
- Video được load trong iframe (extension không thể truy cập)
- Video được load qua JavaScript động và chưa được scan
- URL video không có extension .mp4/.mp3/.mov trong URL

Giải pháp:
- Đợi vài giây để trang load xong
- Scroll trang để trigger lazy loading
- Kiểm tra console logs để xem có tìm thấy video elements không

**Vấn đề: Request không đến được Django**

Nguyên nhân có thể:
- API URL không đúng (kiểm tra trong options)
- CORS issue (đã fix, nhưng nếu vẫn lỗi thì kiểm tra lại)
- Django server không chạy
- Firewall/network blocking

Giải pháp:
- Kiểm tra API URL trong extension options
- Kiểm tra Django server đang chạy
- Kiểm tra console logs trong background script

**Vấn đề: Username không được gửi**

Nguyên nhân:
- Chưa cấu hình username trong extension options

Giải pháp:
- Mở extension options
- Nhập username và lưu
- Reload trang web

### 5. Test thủ công

Để test xem API có hoạt động không, bạn có thể dùng curl:

```bash
curl -X POST http://127.0.0.1:8000/marketing/tools/get-videos/api/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_name": "giadungplus",
    "page_url": "https://www.xiaohongshu.com/test",
    "page_title": "Test",
    "media_url": "https://example.com/test.mp4",
    "file_extension": "mp4",
    "mime_type": "video/mp4",
    "source_type": "video_tag"
  }'
```

Nếu thành công, bạn sẽ thấy response:
```json
{
  "success": true,
  "message": "Media tracked successfully",
  "id": 1,
  "created_at": "2025-12-09T..."
}
```


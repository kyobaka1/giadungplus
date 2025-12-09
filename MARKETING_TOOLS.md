You are a senior full-stack engineer specialized in:
- Python/Django
- Chrome Extension Manifest V3 (background service worker + content scripts)

Goal
=====
Xây dựng https://127.0.0.1:8000/marketing/tools/get-videos/ để giải quyết công việc như sau:

1. **Get Videos** Marketing app để nhận dữ liệu và hiển thị dữ liệu về web app.
2. A **Chrome Extension (Manifest V3)** that:
   - Monitors any pages the user opens (or specific hostnames if needed).
   - Detects and collects **all video/audio URLs** with file extensions:
     - `.mp3`, `.mp4`, `.mov`
   - Sends these URLs (plus metadata like page URL, title, tab id) to the Django backend via HTTP POST.

3. Lưu vào database đơn giản, lưu theo username để hiển thị ra danh sách video họ đã xem và gửi lên server.

Part 1 - View & Model Database
- Viết 1 api mở ra bên ngoài để nhận dữ liệu từ chrome extension gửi về.
- Viết models để lưu dữ liệu gửi về từ extension, ví dụ:
   - `id` (auto)
   - `created_at` (DateTimeField, auto_now_add)
   - `page_url` (URLField or TextField)
   - `page_title` (CharField, nullable)
   - `media_url` (TextField)  # the .mp3/.mp4/.mov URL
   - `file_extension` (CharField, e.g. "mp4", "mp3", "mov")
   - `mime_type` (CharField, nullable)
   - `source_type` (CharField, e.g. "video_tag", "audio_tag", "network_request")
   - `user_name` -> này là username được setup từ user trên extension, trùng với username của người đó được lưu trên admin.

- Show ra template dưới dạng danh sách video với các thông tin. Video cũng cần hiện ảnh dại diện để biết đó là video về cái gì.


Part 2 – Chrome Extension (Manifest V3)
- Chrome Extension name: `GDP Media Tracker Ext` -> Lưu vào /asset/gdp_extension/
=========================================
- Extension cơ bản để thực hiện yêu cầu.
- Người dùng lướt web có các URL có chứa các key sau thì mới tracking lại:
    + tmall
    + douyin
    + 1688
    + taobao
    + xiaohongshu
    + pinterest


Dưới đây là thông tin tham khảo.
=========================================
Create a Chrome Extension with (at minimum) these files:

- `manifest.json`
- `background.js` (service worker)
- `content.js`
- (optional) `options.html` + `options.js` to configure API URL & API key

1. **manifest.json** requirements:
   - `manifest_version`: 3
   - name: "Media Tracker Extension"
   - permissions: `["tabs", "scripting", "storage"]`
   - host_permissions: for now you can allow `"https://*/*", "http://*/*"` or restrict to some domains later.
   - background: service_worker = "background.js"
   - content_scripts:
     - matches: `["https://*/*", "http://*/*"]`
     - js: ["content.js"]
     - run_at: "document_idle"

   Example (you should write the full valid JSON):

   ```json
   {
     "manifest_version": 3,
     "name": "Media Tracker Extension",
     "version": "1.0.0",
     "permissions": ["tabs", "scripting", "storage"],
     "host_permissions": [
       "http://*/*",
       "https://*/*"
     ],
     "background": {
       "service_worker": "background.js"
     },
     "content_scripts": [
       {
         "matches": ["http://*/*", "https://*/*"],
         "js": ["content.js"],
         "run_at": "document_idle"
       }
     ],
     "options_page": "options.html"
   }

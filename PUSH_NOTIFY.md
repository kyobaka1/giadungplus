Bạn là kiến trúc sư hệ thống & senior developer (backend Django + frontend JS), nhiệm vụ của bạn là THIẾT KẾ VÀ VIẾT CODE HOÀN CHỈNH cho hệ thống Web Push Notification cho website app này, hoạt động trên:

- Android (Chrome, các browser hỗ trợ Web Push)
- iPhone / iOS 16.4+ (Safari với Web Push qua APNS)

Mục tiêu:  
Xây 1 hệ thống duy nhất, nhưng hỗ trợ cả Android lẫn iOS. Backend chỉ cần gửi 1 payload, FCM sẽ route tới đúng nền tảng (Android Web & iOS Web).

---

## Bối cảnh & Tech stack

- Website nội bộ: chạy HTTPS, domain cố định https://giadungplus.io.vn/
- Backend: **Python Django**
- Frontend: Javascript thuần (có thể dùng một chút ES6), không phụ thuộc framework nặng.
- Push nền tảng:
  - Sử dụng **Firebase Cloud Messaging (FCM)** làm “cổng” duy nhất.
  - FCM gửi:
    - Web Push cho Chrome/Android.
    - Web Push cho Safari/iOS thông qua APNS (Apple Push Notification Service).

## Yêu cầu OUTPUT

1. **Tổng quan kiến trúc hệ thống**
   - Mô tả kiến trúc logic:  
     - Trình duyệt (Android / iOS) → Service Worker → Backend Django → FCM → Browser.
     - Android Chrome Web Push vs iOS Safari Web Push.
     - Cần 1 backend (FCM) nhưng nhiều loại token.

2. **Cấu hình Firebase & APNS (mô tả chi tiết từng bước)**
   - Xem các file cấu hình ở settings/firebase/

3. **Frontend – Service Worker & đăng ký Web Push (Android + iOS)**

   ### 3.1. File font-end nhúng vào các base template.
   - Viết một file service worker hoàn chỉnh:
     - Import Firebase (nếu dùng CDN) hoặc giải pháp tương đương.
     - Lắng nghe sự kiện push (`self.addEventListener('push', ...)`) và hiển thị notification với `registration.showNotification(title, options)`.
     - Xử lý sự kiện `notificationclick` để:
       - Focus tab hiện có nếu đã mở.
       - Hoặc mở URL mới (`clients.openWindow`).
     - Có ví dụ payload `data` gồm:
       - `title`
       - `body`
       - `icon`
       - `url`
       - `tag` (để group notify)
   
   ### 3.2. Code JS trên frontend để:
   - Kiểm tra trình duyệt có hỗ trợ Push + Service Worker hay không.
   - Đăng ký service worker.
   - Xin quyền notification từ người dùng:
     - Nếu user cho phép → lấy token hoặc subscription.
     - Nếu user từ chối → hiển thị cách xử lý hợp lý.
   - Đăng ký cho **Chrome/Android**:
     - Ví dụ dùng Firebase Messaging: `messaging.getToken(...)`.
   - Đăng ký cho **Safari iOS 16.4+**:
     - Không dùng `messaging.getToken` trực tiếp, mà:
       - Sử dụng `navigator.serviceWorker.ready.then(reg => reg.pushManager.subscribe(...))`.
       - Dùng `applicationServerKey` (VAPID public key).
     - Giải thích cách phân biệt nền tảng bằng feature detection (ví dụ: kiểm tra `window.safari` hoặc `navigator.userAgent`).
   - Gửi token/subscription thu được về backend Django thông qua API:
     - POST `/api/push/register/`
     - Payload ví dụ:
       ```json
       {
         "device_type": "android_web" | "ios_web",
         "endpoint": "...",
         "keys": {
           "p256dh": "...",
           "auth": "..."
         },
         "fcm_token": "nếu có",
         "user_id": "tùy chọn"
       }
       ```

   Hãy viết code JS đầy đủ, có comment rõ ràng.

4. **Backend Django – Models, URLs, Views, Logic gửi Push**

   ### 4.1. Model lưu subscription/token
   - Tạo `notifications` trong /core
   - Tạo model, ví dụ: `WebPushSubscription` với các field:
     - `id`
     - `user` (ForeignKey, nullable – có thể null nếu chưa login)
     - `device_type` (`android_web`, `ios_web`, `unknown`)
     - `endpoint`
     - `p256dh`
     - `auth`
     - `fcm_token` (nếu dùng Firebase token)
     - `created_at`, `updated_at`, `is_active`
   - Viết model đầy đủ, có `__str__`.

   ### 4.2. API endpoint để nhận & lưu subscription
   - Sử dụng Django REST Framework (nếu tiện, bạn hãy setup tối giản).
   - Endpoint: `POST /api/push/register/`
     - Validate input.
     - Tìm subscription trùng endpoint → update.
     - Hoặc tạo mới nếu chưa có.
     - Trả về JSON thông tin cơ bản.
   - Nếu không dùng DRF, bạn có thể viết `@csrf_exempt` view với `JsonResponse`, nhưng hãy chọn một cách rõ ràng và đầy đủ.

   ### 4.3. Hàm gửi push notification từ Django qua FCM
   - Viết 1 module Python, ví dụ: `notifications/services.py`, trong đó có:
     - Hàm `send_webpush_to_subscription(subscription, title, body, data=None, icon=None, url=None)`:
       - Build payload JSON.
       - Gửi tới FCM HTTP v1 (hoặc legacy) endpoint.
       - Dùng thư viện `requests` hoặc `firebase_admin`.
     - Hàm `send_webpush_to_user(user, title, body, data=None)`:
       - Lấy tất cả subscription active của user.
       - Loop và gửi từng cái.
   - Viết code cụ thể để:
     - Cấu hình `FCM_SERVER_KEY` / `FIREBASE_SERVICE_ACCOUNT_JSON` qua biến môi trường.
     - Gửi request POST tới FCM (ghi rõ URL endpoint).
     - Xử lý lỗi cơ bản (in log hoặc raise exception).

   ### 4.4. Ví dụ trigger gửi notify
   - Viết **Django management command** hoặc function đơn giản (ví dụ trong `shell`) để:
     - Gửi test notification tới một subscription cụ thể.
   - Ví dụ: `python manage.py send_test_webpush --user_id=1`

5. **Phân biệt & xử lý khác nhau giữa Android Web & iOS Web**

   - Chỉ rõ trong code & giải thích:
     - Android Chrome:
       - Có thể dùng Firebase `messaging.getToken`.
     - Safari iOS:
       - Phải dùng `pushManager.subscribe` với VAPID.
     - Cách nhận dạng từng loại để gửi chuẩn dữ liệu.
   - Mô tả hạn chế:
     - Không custom âm thanh trên web push.
     - Hành vi khi thiết bị tắt màn hình (nhận notify nhưng không phát âm).

6. **Bảo mật & Best Practices**
   - Gợi ý cách bảo vệ API `/api/push/register/`:
     - CSRF, Auth (nếu user login), rate limit.
   - Lưu ý về:
     - Lưu token an toàn (không log private key).
     - Chỉ cho phép server tin cậy gửi push (server key/SA JSON để trong ENV).
   - Cách unsubscribe / tắt notify:
     - Code JS để `subscription.unsubscribe()`.
     - Update flag `is_active` trong DB.

7. **Ví dụ hoàn chỉnh – từ A đến Z**
   - Gộp lại:
     - 1 file `service-worker.js`.
     - 1 file JS frontend (ví dụ `push-setup.js`) với đầy đủ hàm:
       - `initPush()`, `subscribeUser()`, `sendSubscriptionToServer()`.
     - 1 model Django.
     - 1 serializer + view (hoặc function view).
     - 1 function/hàm trong `services.py` để gửi push.
   - Đảm bảo code **đủ chi tiết**, có thể copy về chỉnh sửa nhẹ là chạy được.

---

## Yêu cầu phong cách trả lời

- Viết bằng **tiếng Việt**, ngắn gọn nhưng **rõ ràng, có hệ thống**.
- Code phải:
  - Có comment giải thích các đoạn quan trọng.
- Ưu tiên cho ví dụ **thực thi được** (ít nhất ở mức cấu trúc), không trả lời kiểu lý thuyết chung chung.

Nếu bạn thấy có chỗ nào cần giả định thêm (ví dụ version Django, DRF đã cài chưa, cấu trúc project), hãy **tự đưa ra giả định hợp lý** và ghi rõ.

Bắt đầu trả lời theo đúng cấu trúc đã mô tả ở trên.

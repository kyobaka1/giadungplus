Hãy dựa vào hệ thống core push Notification đã xây dựng.

Xây dựng hệ thống lưu trữ thông báo tới người dùng.Xây hệ thống sẽ có 4 lớp:
 - Business (Ticket, Đơn hàng, Kho, CSKH…) -> Đã và đang xây dựng.
 - Notification Engine (xử lý “gửi cho ai / kênh nào / khi nào”)
 - Delivery (Web Push, In-app)
 - Frontend (chuông thông báo + push trên PC/iPhone/Android)

***Thông tin của người dùng***
# username
- first_name -> tên của client.
- last_name -> bộ phận (department) -> Hiện đang có: CSKH, Marketing, QUẢN TRỊ VIÊN, KHO_HN, KHO_HCM

# GROUP: 
  Admin -> full quyền
	CSKHManager -> quản trị cskh
	CSKHStaff -> nhân viên cskh
	MarketingManager -> quản trị marketing
	MarketingStaff -> nhân viên marketing
	WarehouseManager -> quản lý kho hàng
	WarehousePacker -> nhân viên đóng gói.

  Tách biệt với 3 group (có thể bổ sung sau này):
  SHOP_GIADUNGPLUS -> có liên quan đến brand: Gia Dụng Plus
	SHOP_LTENG -> có liên quan đến brand: lteng
	SHOP_PHALEDO -> có liên quan đến brand: phaledo

***Xây dựng notify dưới dạng core/service để tái sử dụng***
- Có thể dùng ở mọi apps.
- Gọi với các input điền vào như sau:
  + Gửi cho group nào, department nào, shop nào? Có thể chọn ALL để lựa tất cả.
  + Link (nếu có) -> Click mở
  + Action: show_popup, play_sound, badge_update
            boss_popup: hiển thị thông báo của sếp gửi cho toàn nhân viên.


  + sound (nếu có): link sound ở /static/
  + count (nếu là badge_update)
  + Dùng cùng ID/collapse/tag để đè notify cũ bằng notify mới.

***Xây dựng notify dưới dạng hẹn giờ, đặt lịch***
- Thêm vào database hoặc file .log
- Dùng contab để lên lịch gửi mỗi 10 phút, nếu đến thông báo nào thì gửi thông báo đó.
-> service cần thêm 1 input time (nếu có) -> xử lý lưu riêng.

***Xây dựng thêm nơi lưu trữ notify dưới dạng Thông báo In-web font-end***
- Mỗi base xây dựng thêm 1 hình cái chuông + số thông báo đã nhận chưa đọc.
- Khi click vào thì hiện ra danh sách thông báo / đã đọc thì xám đi.
- Áp dụng riêng cho mỗi user.

**Luồng làm việc***
- Runtime – Khi một việc xảy ra, ví dụ như 1 ticket được tạo.
- Business (Ticket/Order) gọi: → emit_event(event_type, context)
- Notification Engine:
    + Đọc rule & setting.
    + Quyết định ai nhận, kênh nào.
    + Tạo bản ghi Notification (lịch sử).
    + Tạo NotificationDelivery cho từng channel.
- Delivery worker:
    +Thực sự gửi FCM, email, v.v.
    +Log kết quả.

- Frontend
  - “Chuông thông báo” đọc từ bảng Notification.
  - Badge, list, lịch sử = tất cả từ DB.
  - Push web/mobile: click → mở trang + mark-read.


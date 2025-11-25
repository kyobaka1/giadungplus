# CSKH App Specification Builder

## 1. Tổng quan & Mục tiêu

*Mô tả ngắn gọn mục đích chính của module này. Ví dụ: Quản lý khiếu nại, kích hoạt bảo hành điện tử, hay thu thập đánh giá khách hàng.*
> Xây dựng tools công cụ hỗ trợ nhân viên CSKH, nhân viên sales trong việc tra cứu thông tin, chăm sóc khách hàng, bán hàng, bảo hành, thu thập thông tin khách hàng. Đây chỉ là nền tảng hỗ trợ, các thông tin về khách hàng/đơn hàng/ sản phẩm... vẫn được lưu trên Sapo.


## 2. Chi tiết các tính năng
Hãy mô tả cụ thể những gì bạn muốn hiển thị và thao tác ở từng màn hình.

### 2.1. Dashboard (Tổng quan)
*Màn hình này dành cho ai? Tất cả nhân viên CSKH, Sales, Marketing, và Quản lý.*
*Các chỉ số (Metrics) cần hiển thị:*
- [x] Số lượng Ticket (Mới, Đang xử lý, Quá hạn)
- [x] Chỉ số đánh giá (Review rating trung bình)
- [x] Thống kê bảo hành (Sắp hết hạn, Mới kích hoạt)
- [x] Biểu đồ (Chart): (Ví dụ: Số lượng ticket theo ngày, Tỷ lệ hài lòng...)
> Lấy dữ liệu tạm, chưa cần điền số liệu cụ thể.

### 2.2. Ticket (Hệ thống vé hỗ trợ)
**Tổng quan:**
- Màn hình này dành cho ai? Tất cả nhân viên CSKH, Manager, Quản Lý.
* Các chỉ số cần hiển thị:
- Số lượng ticket chưa xử lý
- Số lượng ticket quá hạn SLA.
- Biểu đồ phân tích các phân loại của ticket.
> Lấy dữ liệu tạm, chưa cần điền số liệu cụ thể.

**Danh sách ticket**
- Tạo ticket mới
- Cần hiển thị những thông tin gì ở danh sách? (Mã ticket, Phân Loại, Đơn Hàng, Tiêu đề, Khách hàng, Độ ưu tiên, Trạng thái, Người phụ trách...)
- Có cần bộ lọc (Filter) nào? Theo trạng thái
- Có search tất cả thông tin ticket.

**Chi tiết Ticket:**
- Các trường thông tin cần thiết: (Tiêu đề, Nội dung, File đính kèm, Loại yêu cầu...)
- Quy trình xử lý (Workflow): Mới -> Đang xử lý -> Chờ phản hồi -> Hoàn thành -> Đóng?
- Có cần tính năng chat/comment trong ticket không?
- Có cần gửi email/thông báo tự động khi trạng thái thay đổi không?
> Tạm thời làm mẫu trước, chi tiết sau.

### 2.3. Warranty (Bảo hành)
**Tổng quan:**
- Tất cả nhân viên CSKH, Manager, Quản Lý.
- Danh sách bảo hành hiển thị theo: Đơn hàng

**Quy trình:**
- Kích hoạt bảo hành: Tự động từ đơn hàng
- Tra cứu bảo hành: Tra cứu theo SĐT, Mã đơn hàng, tên khách...
- Chính sách bảo hành: Tính theo thời gian mua hàng
- Xử lý yêu cầu bảo hành: Tạo phiếu tiếp nhận, Theo dõi sửa chữa, Trả hàng...
> Tạm thời làm mẫu trước, chi tiết sau.

### 2.4. Review (Đánh giá & Phản hồi)
**Tổng quan:**
- Nguồn đánh giá từ đâu? Shopee
- Hiển thị: Sao (1-5), Nội dung, Hình ảnh.

**Hành động:**
- Có cần tính năng trả lời đánh giá trực tiếp từ App không? -> Có -> Tích hợp thêm AI gợi ý.
- Có cần phân loại đánh giá (Tích cực/Tiêu cực) để xử lý riêng không? -> Có
> Tạm thời làm mẫu trước, chi tiết sau.

### 2.5. Orders & Shipment (Đơn hàng & Vận chuyển)
*Module này liên kết với dữ liệu đơn hàng hiện có như thế nào?*
- Chỉ hiển thị để tham chiếu khi xử lý Ticket/Bảo hành?
- Hay cần thao tác xử lý đơn hàng (Đổi trả, Hoàn tiền) ngay tại đây?
- Thông tin vận chuyển cần theo dõi chi tiết đến mức nào?
> Tạm thời làm mẫu trước, chi tiết sau.

### 2.6. Products (Sản phẩm)
- Thông tin sản phẩm phục vụ CSKH: (Hướng dẫn sử dụng, Câu hỏi thường gặp - FAQ, Linh kiện thay thế...)
- Có cần liên kết sản phẩm với chính sách bảo hành cụ thể không?
> Tạm thời làm mẫu trước, chi tiết sau.

## 3. Câu hỏi kỹ thuật & Tích hợp (Cần trả lời)
Để tôi có thể code chính xác, vui lòng trả lời các câu hỏi sau:

1.  **Dữ liệu Khách hàng (Customer):**
    - /customer
    - Dùng chung
2.  **Dữ liệu Đơn hàng (Order):**
    - /orders


3.  **Phân quyền (Permissions):**
    - Nhân viên có được xem ticket của nhau không? Có

4.  **Thông báo (Notifications):**
    - Cần thông báo qua kênh nào? Web Push

*** YÊU CẦU ***
- Tham khảo ở /thamkhao
- Xây dựng hệ thống có  tính seriable để phát triển về sau.
- Ko tạo thêm database mới. Nếu cái nào chưa có dữ liệu cứ điền đại diện vào thôi.
- Ứng dụng các model trong /customer /orders /products để dùng.


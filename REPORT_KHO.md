SỬA LẠI THỐNG KÊ KHO HÀNG với yêu cầu và bố cục như sau:


# HÀNG NGANG ĐẦU TIÊN
# HÀNG NGANG THỨ HAI
# HÀNG DỮ LIỆU THỨ 3
# HÀNG DỮ LIỆU THỨ 4

Hiệu suất nhân sự
Giám sát hiệu quả sử dụng nhân sự

Tên nhân sự	Giờ làm	Gói được	Doanh số	Hiệu suất	Xu hướng gói
Kho Hà Nội
KHO_HN: Hương Giang	0	265	41.283.893	0 /h	
Thuỷ tinh
63%
Móc nhỏ
22%
Phụ kiện
6%
KHO_HN: Phương Mai	0	125	21.819.782	0 /h	
Thanh móc
62%
Kệ sắt, nhôm
32%
Móc nhỏ
4%
KHO_HN: Mỹ Kim	0	92	19.284.179	0 /h	
Kệ sắt, nhôm
32%
Thuỷ tinh
24%
Thanh móc
22%
NO-SCAN	0	76	18.163.737	0 /h	
Thuỷ tinh
31%
Móc nhỏ
20%
Tấm chắn dầu
16%
KHO_HN: Kiều Trinh	0	25	14.323.820	0 /h	
Thuỷ tinh
88%
Kệ sắt, nhôm
6%
Thanh móc
5%
KHO_HN: PART Ngô Tâm	0	119	13.004.859	0 /h	
Thuỷ tinh
85%
Thanh móc
8%
Kệ sắt, nhôm
5%
KHO_HN: Đoàn Anh	0	44	12.035.494	0 /h	
Tấm chắn dầu
39%
Thùng rác, gạo
33%
Kệ sắt, nhôm
9%

**THAM KHẢO**
- thamkhao/views.py

**TÔI MUỐN THỂ HIỆN**
1. Doanh số gói được cửa từng người / số đơn / số sản phẩm / doanh số và hiệu suất gói hàng trên giờ - Xu hướng gói TOP3 (phân theo doanh mục).
2. Thời gian làm việc hiện tại của từng người: Ghi nhận từ đơn bắn đầu tiên tới đơn bắn cuối cùng trong hôm nay.
    + Trưa sẽ nghỉ từ 12h đến 2h chiều.
    + Thời gian làm việc mặc định bắt đầu từ 8:00 sáng (nếu trước giờ đó bắn thì vẫn ghi nhận là 8h sáng).
    + Nếu trong thời gian đó vẫn gói hàng (bắn > 15 đơn hàng thì tính cho họ thời gian thêm giờ cho họ tới lúc bắn đơn cuối cùng vào giờ trưa.) Ví dụ: 12h là nghỉ trưa, nhưng từ lúc 12h đến 12h30 vẫn bắn > 15 đơn hàng -> giờ làm vẫn được tính thêm 30 phút. KPI là 15 đơn / 30 phút.
    + Giờ nghỉ buổi chiều sẽ là 18h. Vẫn áp dụng tính việc gói hàng thêm giờ cho họ nếu gói hơn 15 đơn hàng trong 30 phút.
    + Làm tròn giờ làm về float 1.1 1.2 giờ.


**THIẾT KẾ**
- Mỗi người là 1 ô div phân bổ cục thể các số liệu theo logic để xem xét hiệu suất cho họ, bạn hãy cho ra 1 thiết kế gọn gàng, rõ ràng với các số liệu trên.
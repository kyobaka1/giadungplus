Xây dựng hệ thống ABC/Pareto SYSTEM vào : products/sales-forecast/

** LOGIC HỆ THỐNG **
- Hãy đọc và tìm hiểu về ABC/Pareto về logic và cách tính của nó.
- Phân nhóm như sau:
    Nhóm A = nhóm sản phẩm chiếm 70–80% doanh thu
    Nhóm B = nhóm sản phẩm chiếm 15–25% doanh thu
    Nhóm C = nhóm sản phẩm chiếm 5–10% doanh thu

** ÁP DỤNG LOGIC VÀO LUỒNG CODE **
- Khi chạy hệ thống quét đơn hàng 30 ngày (bỏ qua 10 ngày) thì lấy cả phần doanh thu và ASP (Average Selling Price). Cách tính như sau:
    + Doanh thu của từng sản phẩm = cộng line_amount.
    + Số lượng bán ra = cộng quantity.

- Sau khi quét toàn bộ số đơn hàng thì đã có doanh thu của từng phân loại sản phẩm trong list variants.
    + Cộng tổng lại tính tổng doanh thu
    + Tính % của từng SKU trên tổng doanh thu.
    + Tính % tích luỹ cộng dồn từ cao nhất đến thấp nhất.
-> Suy ra sản phẩm phân loại A hay B, C
-> Lưu lại để lần sau có thể load ra mà không cần tính toán.
-> Hiển thị ra -> thêm vào template html

** Logic tham khảo **
Bước 1: Tính doanh thu của từng SKU trong khoảng (30 ngày)
Bước 2: Sort từ cao xuống thấp (SKU bán ra nhiều tiền nhất → ít tiền nhất).
Bước 3: Tính % tích lũy (cumulative percentage).
Bước 4: Dựa vào % tích lũy → chia thành A / B / C.

** Ví dụ về cách tính **
Bước 1 – Tính tổng doanh thu
= 122.5 triệu.

Bước 2 – Tính % từng SKU

SKU 1 = 30M / 122.5M ≈ 24.5%
SKU 2 = 25M / 122.5M ≈ 20.4%
SKU 3 = 22M / 122.5M ≈ 18%
SKU 4 = 18M / 122.5M ≈ 14.7%
…

Bước 3 – Tính % tích lũy

SKU 1 = 24.5%
SKU 2 = 24.5 + 20.4 = 44.9%
SKU 3 = 44.9 + 18 = 62.9%
SKU 4 = 62.9 + 14.7 = 77.6%
…

Vậy:

👉 4 SKU đầu tiên chiếm 77.6% doanh thu
→ chính là nhóm A.

Số còn lại:
Nhóm B = SKU tiếp theo cho đến khi đạt 95% doanh thu
Nhóm C = phần còn lại (<5%)


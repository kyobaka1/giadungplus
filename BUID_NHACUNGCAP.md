Xây dựng thêm tính năng cho apps /products/

-> NHẬP HÀNG
- Overview 
- Sản phẩm
- Đơn đặt hàng
- Container
- Tài chính

** Giờ bắt tay vào xây dựng: Sản phẩm
- Là tính năng quản trị việc nhập hàng theo từng phân loại sản phẩm (PHÂN LOẠI). Với các tính năng chính sau:

** Dự báo bán hàng & cảnh báo tồn kho (x ngày -> tạm thời là 7 ngày)
    - Có 1 nút refesh data -> Bấm vào thì mới tính toán (vì khối lượng tính toán khá nhiều).

    - Tính toán tốc độ bán dựa trên lượt bán hiện tại của shop trong x ngày gần nhất:    
        + Lọc theo Sapo created_on_max, create_on_min: https://sisapsan.mysapogo.com/admin/orders.json?created_on_max=2025-12-07T16%3A59%3A59Z&created_on_min=2025-11-30T17%3A00%3A00Z
        + Lấy tất cả đơn hàng trạng thái Đang giao dịch/Hoàn thành. Bỏ đơn Huỷ, chưa duyệt (Đặt hàng).
        + Covert sang DTO -> lấy real_items() -> Bỏ qua combo, packed nhiều sản phẩm -> Chỉ tính trên từng phân loại đơn.
        + Lấy list toàn bộ phân loại từ Sapo về (lưu trữ dùng 1 lần).
        + Duyệt đơn hàng để tính tổng lượt bán của toàn bộ SKU trong thời gian lấy đơn ngày đó -> Dựa vào variant_id.
        + Suy ra tốc độ bán hàng là: số lượt bán / x ngày.
        + Số ngày còn bán được = Tồn kho hiện tại (stock 2 kho HN và SG cộng lại) / Tốc độ bán trung bình

    - Lưu dữ liệu bán hàng tạm thời vào product descreption GPDMETA cho từng phân loại. (Chỉ lưu tổng lượt bán trong thời gian nào)
    - Hiển thị ra dạng danh sách, có thể sắp xếp từng cột (tăng dần, giảm dần theo số liệu).

** Nếu ko bấm refesh data -> Lấy dữ liệu từ product descreption GPDMETA -> Lấy tổng lượt bán ra -> Tính toán lại -> Hiển thị ra cho người dùng.

** Cảnh báo **
    - Báo đỏ những SKU < 30 ngày
    - Báo vàng 30–60 ngày
    - Báo xanh > 60 ngày

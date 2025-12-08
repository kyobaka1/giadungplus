# Thiết Kế Hệ Thống Quản Lý PO (Purchase Order)

## Tổng Quan

Hệ thống quản lý PO độc lập, cho phép:
- PO có thể chuyển giữa các SPO mà vẫn giữ nguyên thông tin
- Theo dõi trạng thái giao hàng PO
- Quản lý thanh toán và chi phí cho PO
- Tính toán tự động tổng cần thanh toán và đã thanh toán

## Cấu Trúc Models

### 1. PurchaseOrder (Độc Lập)
**Mục đích:** Lưu trữ thông tin PO độc lập, không phụ thuộc vào SPO.

**Các trường chính:**
- `sapo_order_supplier_id`: ID từ Sapo (unique)
- `sapo_code`: Mã PO từ Sapo
- `supplier_id`, `supplier_name`, `supplier_code`: Thông tin NSX
- `delivery_status`: Trạng thái giao hàng (ordered → sent_label → production → delivered)
- `expected_delivery_date`: Dự kiến giao hàng (để sắp xếp với lịch đóng container)
- `delivery_timeline`: JSON lưu timeline trạng thái
- `product_amount_cny`: Tiền hàng (CNY) - tính từ giá mua trung quốc của variants
- `total_amount_cny`: Tổng cần thanh toán (CNY) = product_amount + costs
- `paid_amount_cny`: Số tiền đã thanh toán (CNY) - tự động tính từ payments

**Quan hệ:**
- `costs`: One-to-Many với PurchaseOrderCost
- `payments`: One-to-Many với PurchaseOrderPayment
- `spo_relations`: Many-to-Many với SPO qua SPOPurchaseOrder

### 2. SPOPurchaseOrder (Quan Hệ)
**Mục đích:** Quan hệ many-to-many giữa SPO và PO.

**Các trường:**
- `sum_purchase_order`: ForeignKey đến SumPurchaseOrder
- `purchase_order`: ForeignKey đến PurchaseOrder

**Lợi ích:**
- Cho phép chuyển PO giữa các SPO
- PO vẫn giữ nguyên thông tin khi chuyển

### 3. PurchaseOrderCost (Chi Phí)
**Mục đích:** Lưu các chi phí cho PO (nhân dân tệ).

**Các trường:**
- `purchase_order`: ForeignKey đến PurchaseOrder
- `cost_type`: Loại chi phí (domestic_shipping_cn, packing_fee, other)
- `amount_cny`: Số tiền (CNY)
- `cbm`: Mét khối (để phân bổ chi phí)
- `description`: Mô tả

**Loại chi phí:**
- `domestic_shipping_cn`: Giao hàng nội địa TQ
- `packing_fee`: Phí đóng hàng
- `other`: Chi phí khác

### 4. PurchaseOrderPayment (Thanh Toán)
**Mục đích:** Lưu thông tin thanh toán cho PO (NSX).

**Các trường:**
- `purchase_order`: ForeignKey đến PurchaseOrder
- `payment_type`: Loại thanh toán (deposit, payment)
- `amount_cny`: Số tiền (CNY)
- `amount_vnd`: Số tiền VNĐ đã bỏ
- `exchange_rate`: Tỷ giá CNY/VNĐ (tự động tính = amount_vnd / amount_cny)
- `payment_date`: Ngày thanh toán
- `description`: Mô tả

**Loại thanh toán:**
- `deposit`: Cọc sản xuất
- `payment`: Thanh toán đơn hàng

**Tự động:**
- Khi save, tự động tính `exchange_rate` nếu có `amount_vnd` và `amount_cny`
- Sau khi save, tự động cập nhật `paid_amount_cny` của PO

## Luồng Hoạt Động

### 1. Tạo PO từ Sapo
1. Lấy PO từ Sapo API (order_supplier)
2. Tạo hoặc cập nhật `PurchaseOrder` với thông tin cơ bản
3. Tính `product_amount_cny` từ giá mua trung quốc của variants trong PO
4. Thêm PO vào SPO qua `SPOPurchaseOrder`

### 2. Cập Nhật Trạng Thái Giao Hàng
1. Gọi `purchase_order.update_delivery_status(new_status, date, note)`
2. Tự động thêm vào `delivery_timeline`
3. Cập nhật `expected_delivery_date` nếu status = 'delivered'

### 3. Thêm Chi Phí
1. Tạo `PurchaseOrderCost` với loại và số tiền
2. Gọi `purchase_order.calculate_total_amount()` để cập nhật tổng

### 4. Thêm Thanh Toán
1. Tạo `PurchaseOrderPayment` với số tiền CNY và VNĐ (nếu có)
2. Tự động tính tỷ giá và cập nhật `paid_amount_cny` của PO

### 5. Chuyển PO Giữa Các SPO
1. Xóa `SPOPurchaseOrder` cũ
2. Tạo `SPOPurchaseOrder` mới với SPO mới
3. PO vẫn giữ nguyên tất cả thông tin (costs, payments, timeline)

## Tính Toán Tự Động

### Tổng Cần Thanh Toán
```python
total_amount_cny = product_amount_cny + sum(cost.amount_cny for cost in costs)
```

### Số Tiền Đã Thanh Toán
```python
paid_amount_cny = sum(payment.amount_cny for payment in payments)
```

### Tỷ Giá
```python
exchange_rate = amount_vnd / amount_cny  # Nếu có cả hai
```

## API Endpoints (Dự Kiến)

### PO Management
- `GET /products/purchase-orders/` - Danh sách PO
- `GET /products/purchase-orders/<po_id>/` - Chi tiết PO
- `POST /products/purchase-orders/<po_id>/update-delivery-status/` - Cập nhật trạng thái
- `POST /products/purchase-orders/<po_id>/calculate-product-amount/` - Tính lại tiền hàng từ variants

### Costs
- `POST /products/purchase-orders/<po_id>/costs/` - Thêm chi phí
- `PUT /products/purchase-orders/<po_id>/costs/<cost_id>/` - Cập nhật chi phí
- `DELETE /products/purchase-orders/<po_id>/costs/<cost_id>/` - Xóa chi phí

### Payments
- `POST /products/purchase-orders/<po_id>/payments/` - Thêm thanh toán
- `PUT /products/purchase-orders/<po_id>/payments/<payment_id>/` - Cập nhật thanh toán
- `DELETE /products/purchase-orders/<po_id>/payments/<payment_id>/` - Xóa thanh toán

### SPO Relations
- `POST /products/sum-purchase-orders/<spo_id>/add-po/` - Thêm PO vào SPO (tạo PurchaseOrder nếu chưa có)
- `DELETE /products/sum-purchase-orders/<spo_id>/remove-po/<po_id>/` - Xóa PO khỏi SPO (không xóa PO)

## Migration Strategy

### Bước 1: Tạo Models Mới
- Tạo `PurchaseOrder`, `PurchaseOrderCost`, `PurchaseOrderPayment`
- Cập nhật `SPOPurchaseOrder` thành quan hệ với `PurchaseOrder`

### Bước 2: Migrate Dữ Liệu Cũ
- Tạo script để migrate dữ liệu từ `SPOPurchaseOrder` cũ sang `PurchaseOrder` mới
- Giữ nguyên `SPOPurchaseOrder` nhưng thay đổi quan hệ

### Bước 3: Cập Nhật Code
- Cập nhật services và views để sử dụng model mới
- Cập nhật templates để hiển thị thông tin mới

## Lưu Ý

1. **Độc Lập:** PO hoàn toàn độc lập với SPO, có thể chuyển giữa các SPO
2. **Tự Động Tính Toán:** Tổng cần thanh toán và đã thanh toán được tính tự động
3. **Tỷ Giá:** Tự động tính và lưu khi có cả số tiền CNY và VNĐ
4. **Timeline:** Tự động lưu timeline khi cập nhật trạng thái
5. **Giá Mua Trung Quốc:** Lấy từ `variant.gdp_metadata.import_info.china_price_cny`

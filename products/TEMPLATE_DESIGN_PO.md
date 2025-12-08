# Thiết Kế Giao Diện Quản Lý PO

## Tổng Quan

Đã thiết kế lại giao diện quản lý PO trong SPO detail page với đầy đủ tính năng:
- Hiển thị trạng thái giao hàng và timeline
- Quản lý chi phí (Costs)
- Quản lý thanh toán (Payments)
- Tính toán tự động tổng cần thanh toán và đã thanh toán

## Cấu Trúc Giao Diện

### 1. PO Card (Thay thế Table cũ)

**Header:**
- Thông tin PO: Supplier name, Sapo code
- Trạng thái giao hàng: Badge màu theo trạng thái
- Dự kiến giao hàng: Hiển thị ngày nếu có
- Tóm tắt tài chính:
  - Tiền hàng (CNY)
  - Tổng cần thanh toán (CNY)
  - Đã thanh toán (CNY)
  - Còn lại (CNY) - hiển thị màu đỏ nếu > 0
- CBM
- Actions: Cập nhật trạng thái, Expand, Xóa

**Details (Collapsible):**
- Timeline giao hàng: Hiển thị lịch sử trạng thái
- Costs & Payments Grid (2 cột):
  - Chi phí: Danh sách costs với nút thêm/xóa
  - Thanh toán: Danh sách payments với nút thêm/xóa

### 2. Modals

#### Update Delivery Status Modal
- Form: Trạng thái mới, Ngày, Ghi chú
- Endpoint: `POST /products/purchase-orders/<po_id>/update-delivery-status/`

#### Add Cost Modal
- Form: Loại chi phí, Số tiền (CNY), CBM (tùy chọn), Mô tả
- Endpoint: `POST /products/purchase-orders/<po_id>/costs/`

#### Add Payment Modal
- Form: Loại thanh toán, Số tiền (CNY), Số tiền VNĐ (tùy chọn), Ngày, Mô tả
- Endpoint: `POST /products/purchase-orders/<po_id>/payments/`

### 3. JavaScript Functions

- `expand-po-btn`: Expand/collapse PO details
- `update-delivery-status-btn`: Mở modal cập nhật trạng thái
- `add-cost-btn`: Mở modal thêm chi phí
- `delete-cost-btn`: Xóa chi phí
- `add-payment-btn`: Mở modal thêm thanh toán
- `delete-payment-btn`: Xóa thanh toán
- `remove-po-btn`: Xóa PO khỏi SPO

## API Endpoints Cần Tạo

### 1. Update Delivery Status
```
POST /products/purchase-orders/<po_id>/update-delivery-status/
Body: {
    delivery_status: "ordered" | "sent_label" | "production" | "delivered",
    date: "2025-01-01",
    note: "Ghi chú"
}
```

### 2. Costs Management
```
POST /products/purchase-orders/<po_id>/costs/
Body: {
    cost_type: "domestic_shipping_cn" | "packing_fee" | "other",
    amount_cny: 100.00,
    cbm: 5.5 (optional),
    description: "Mô tả"
}

DELETE /products/purchase-orders/<po_id>/costs/<cost_id>/
```

### 3. Payments Management
```
POST /products/purchase-orders/<po_id>/payments/
Body: {
    payment_type: "deposit" | "payment",
    amount_cny: 1000.00,
    amount_vnd: 3500000 (optional),
    payment_date: "2025-01-01",
    description: "Mô tả"
}

DELETE /products/purchase-orders/<po_id>/payments/<payment_id>/
```

### 4. Remove PO from SPO
```
DELETE /products/sum-purchase-orders/<spo_id>/remove-po/<po_id>/
```

## View Updates

### `sum_purchase_order_detail` View
Đã cập nhật để:
- Lấy thông tin từ `PurchaseOrder` model
- Prefetch `costs` và `payments`
- Tính toán `remaining_amount_cny`
- Truyền đầy đủ dữ liệu vào template

## Template Structure

```html
<!-- PO Card -->
<div data-po-id="{{ po.po_id }}">
    <!-- Header -->
    <div>...</div>
    
    <!-- Details (Collapsible) -->
    <div class="po-details hidden">
        <!-- Timeline -->
        <!-- Costs & Payments Grid -->
    </div>
</div>

<!-- Modals -->
<div id="update-delivery-status-modal">...</div>
<div id="add-cost-modal">...</div>
<div id="add-payment-modal">...</div>
```

## Tính Năng

✅ Hiển thị trạng thái giao hàng với badge màu
✅ Hiển thị dự kiến giao hàng
✅ Timeline giao hàng
✅ Quản lý chi phí (thêm/xóa)
✅ Quản lý thanh toán (thêm/xóa)
✅ Tính toán tự động tổng cần thanh toán
✅ Tính toán tự động đã thanh toán
✅ Hiển thị số tiền còn lại
✅ Expand/collapse PO details
✅ Modal forms cho tất cả actions

## Next Steps

1. Tạo các view functions cho API endpoints
2. Thêm URLs vào `products/urls.py`
3. Test các chức năng
4. Cập nhật service để tính `product_amount_cny` từ variants

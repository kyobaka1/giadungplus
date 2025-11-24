# Ghi chú Implementation - Module KHO

## Đã hoàn thành

### 1. Views đã tạo (skeleton với templates mẫu):
- ✅ `sapo_orders` - Đơn Sapo (đơn sỉ, giao ngoài, Facebook/Zalo, khách quay lại)
- ✅ `pickup_orders` - Wave pickup thông minh
- ✅ `packing_orders` - Scan barcode đóng gói
- ✅ `connect_shipping` - Liên kết đơn gửi bù
- ✅ `sos_shopee` - Quản lý trạng thái đơn (đã di chuyển từ management)
- ✅ `packing_cancel` - Đơn đã gói nhưng bị huỷ (đã di chuyển từ management)
- ✅ `return_orders` - Quản lý đơn hoàn
- ✅ `sorry_letter` - Thư cảm ơn/xin lỗi (đổi tên từ return_letter)
- ✅ `product_barcode` - In barcode sản phẩm

### 2. Templates đã tạo:
- ✅ `kho/overview.html` - Dashboard với KPI cards
- ✅ `kho/orders/sapo_orders.html`
- ✅ `kho/orders/pickup.html`
- ✅ `kho/orders/packing_orders.html` (với UI scanner)
- ✅ `kho/orders/connect_shipping.html`
- ✅ `kho/orders/sos_shopee.html`
- ✅ `kho/orders/packing_cancel.html`
- ✅ `kho/orders/return_orders.html`
- ✅ `kho/printing/sorry_letter.html`
- ✅ `kho/printing/product_barcode.html`
- ✅ `kho/tickets/ticket_list.html`
- ✅ `kho/tickets/ticket_detail.html`
- ✅ `kho/tickets/ticket_confirm.html`

### 3. Models đã tạo:
- ✅ `Ticket` - Model cho ticket khiếu nại
- ✅ `TicketComment` - Model cho comments trong ticket

### 4. URLs đã cập nhật:
- ✅ Tất cả routes mới đã được thêm vào `kho/urls.py`
- ✅ Routes cũ đã được di chuyển theo cấu trúc README

### 5. Menu đã cập nhật:
- ✅ `base_kho.html` - Menu sidebar đã được cập nhật với tất cả các tính năng mới

## Cần restore implementation đầy đủ

### Views cần restore logic:
1. **express_orders** - Implementation đầy đủ đã có trong codebase gốc (khoảng 100+ dòng)
2. **shopee_orders** - Implementation đầy đủ đã có trong codebase gốc (khoảng 200+ dòng)
3. **print_now** - Implementation đầy đủ đã có trong codebase gốc (khoảng 600+ dòng)

**Lưu ý**: Các views này đã hoạt động tốt trong codebase gốc. Cần restore từ git history hoặc từ backup.

## Cần bổ sung logic cho các views mới

Tất cả các views mới hiện chỉ có skeleton. Cần bổ sung:

1. **sapo_orders**: Logic lấy đơn từ Sapo Core API
2. **pickup_orders**: Logic wave pickup thông minh
3. **packing_orders**: Logic scan barcode + API endpoints
4. **connect_shipping**: Logic liên kết đơn gửi bù
5. **sos_shopee**: Logic lấy đơn có vấn đề
6. **packing_cancel**: Logic lấy đơn đã packed nhưng bị cancelled
7. **return_orders**: Logic lấy đơn hoàn từ Sapo
8. **tickets**: Logic CRUD cho tickets
9. **sorry_letter**: Logic generate PDF
10. **product_barcode**: Logic generate barcode từ SKU

## Cần tạo API endpoints

- Update packing status
- Mark as picked up
- Confirm ticket error
- Scan barcode (packing_orders)

## Next Steps

1. Restore implementation đầy đủ cho express_orders, shopee_orders, print_now
2. Bổ sung logic cho các views mới
3. Tạo API endpoints cho các actions
4. Test và hoàn thiện


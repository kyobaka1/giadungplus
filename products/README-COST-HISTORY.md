# Cost History - Lịch sử Giá vốn

## Tổng quan

`CostHistory` là model lưu trữ lịch sử giá vốn cho từng variant tại từng location và thời điểm nhập hàng. Hệ thống sử dụng phương pháp **bình quân gia quyền liên tục** để tính giá vốn.

## Mục đích

1. **Lưu trữ giá vốn**: Lưu trữ giá vốn đã tính toán cho mỗi lần nhập hàng
2. **Tính bình quân gia quyền**: Tính giá vốn trung bình dựa trên tồn kho cũ và giá vốn mới
3. **Truy vết**: Theo dõi lịch sử giá vốn để tính toán chính xác cho các lần nhập sau
4. **Phân tích**: Cung cấp dữ liệu để phân tích chi phí và giá vốn theo thời gian

## Cấu trúc Database

### Model: `CostHistory`

```python
class CostHistory(models.Model):
    # Liên kết
    sum_purchase_order = ForeignKey(SumPurchaseOrder)  # SPO (container)
    purchase_order = ForeignKey(PurchaseOrder)         # PO (đơn nhập hàng)
    tkhq_code = CharField                              # Mã tờ khai hải quan
    
    # Thông tin variant và location
    variant_id = BigIntegerField                       # Sapo Variant ID
    location_id = BigIntegerField                     # Sapo Location ID (kho hàng)
    sku = CharField                                    # SKU của variant
    sku_model_xnk = CharField                         # SKU MODEL NHẬP KHẨU
    
    # Thông tin nhập hàng
    receipt_code = CharField                          # Mã phiếu nhập kho
    import_date = DateField                           # Ngày nhập kho (completed_on của PO)
    import_quantity = DecimalField                    # Số lượng nhập mới
    
    # Giá vốn cũ (trước khi nhập)
    old_quantity = DecimalField                       # Tồn kho cũ
    old_cost_price = DecimalField                     # Giá vốn cũ
    
    # Giá vốn mới (sau khi tính toán)
    new_cost_price = DecimalField                     # Giá vốn mới (chưa bình quân)
    average_cost_price = DecimalField                  # Giá vốn trung bình (bình quân gia quyền)
    
    # Chi tiết tính toán giá vốn mới
    price_cny = DecimalField                          # Giá nhập CNY (từ price_tq)
    exchange_rate_avg = DecimalField                  # Tỷ giá CNY trung bình
    import_tax_per_unit = DecimalField                # Thuế NK đơn chiếc (VNĐ)
    vat_per_unit = DecimalField                       # Thuế GTGT đơn chiếc (VNĐ)
    po_cost_per_unit = DecimalField                   # Chi phí PO phân bổ đơn chiếc (VNĐ)
    spo_cost_per_unit = DecimalField                  # Chi phí SPO phân bổ đơn chiếc (VNĐ)
    cpm_per_unit = DecimalField                       # CBM của 1 đơn vị sản phẩm
    
    # Trạng thái sync
    synced_to_sapo = BooleanField                     # Đã sync lên Sapo (không dùng nữa)
    sapo_price_adjustment_id = BigIntegerField       # ID price_adjustment trên Sapo
    synced_at = DateTimeField                         # Thời điểm sync
```

## Công thức Tính Giá vốn

### 1. Giá vốn mới (new_cost_price)

```
new_cost_price = (price_cny * exchange_rate_avg) 
                 + import_tax_per_unit 
                 + vat_per_unit 
                 + po_cost_per_unit 
                 + spo_cost_per_unit
```

**Chi tiết các thành phần:**

- **price_cny**: Giá nhập CNY từ variant metadata (`price_tq`)
- **exchange_rate_avg**: Tỷ giá CNY trung bình từ các khoản thanh toán PO
- **import_tax_per_unit**: Thuế nhập khẩu đơn chiếc (từ Packing List, match theo `sku_model_xnk`)
- **vat_per_unit**: Thuế GTGT đơn chiếc (từ Packing List, match theo `sku_model_xnk`)
- **po_cost_per_unit**: Chi phí PO phân bổ đơn chiếc
  ```
  po_cost_per_unit = (po_total_costs_vnd * cpm_per_unit) / po_total_cbm
  ```
- **spo_cost_per_unit**: Chi phí SPO phân bổ đơn chiếc
  ```
  spo_cost_per_unit = (spo_total_costs_vnd * cpm_per_unit) / spo_total_cbm
  ```

### 2. Giá vốn trung bình (average_cost_price)

**Logic:**
- **Nếu không có giá vốn cũ** (`old_cost_price = 0`):
  ```
  average_cost_price = new_cost_price
  ```
  
- **Nếu có giá vốn cũ** (`old_cost_price > 0`):
  ```
  average_cost_price = (old_quantity * old_cost_price + import_quantity * new_cost_price) 
                       / (old_quantity + import_quantity)
  ```

Đây là công thức **bình quân gia quyền liên tục** (continuous weighted average).

## Quy trình Tính toán

### Bước 1: Tìm tồn kho cũ và giá vốn cũ

```python
old_quantity, old_cost_price = find_old_inventory(
    variant_id=variant_id,
    location_id=location_id,
    before_date=import_date,
    receipt_code=receipt_code
)
```

**Logic tìm tồn kho cũ:**
1. Lấy lịch sử tồn kho từ Sapo API: `/reports/inventories/variants/{variant_id}.json`
2. Tìm trace có `trans_object_code == receipt_code` hoặc trace trước `before_date`
3. Tính `old_quantity = onhand - onhand_adj` (nếu < 0 thì set = 0)
4. Tìm `CostHistory` gần nhất trước `before_date` để lấy `old_cost_price`
5. Nếu không tìm thấy từ inventory, lấy từ `CostHistory` gần nhất

### Bước 2: Tính giá vốn mới

```python
cost_calc = calculate_new_cost_price(
    variant_id=variant_id,
    spo=spo,
    po=po,
    quantity=quantity,
    cpm_per_unit=cpm_per_unit,
    sku_model_xnk=sku_model_xnk,
    po_total_cbm=po_total_cbm
)
```

**Các bước:**
1. Lấy `price_cny` từ variant metadata (`price_tq`)
2. Lấy `exchange_rate_avg` từ các khoản thanh toán PO
3. Lấy `import_tax_per_unit` và `vat_per_unit` từ Packing List (match theo `sku_model_xnk`)
4. Tính `po_cost_per_unit` từ chi phí PO (phân bổ theo CBM)
5. Tính `spo_cost_per_unit` từ chi phí SPO (phân bổ theo CBM)
6. Tính `new_cost_price` = tổng tất cả các thành phần

### Bước 3: Tạo hoặc cập nhật CostHistory

```python
cost_history = calculate_and_save_cost_history(
    spo=spo,
    po=po,
    variant_id=variant_id,
    location_id=location_id,
    quantity=quantity,
    cpm_per_unit=cpm_per_unit,
    import_date=import_date,  # completed_on của PO
    receipt_code=receipt_code,
    sku=sku,
    sku_model_xnk=sku_model_xnk,
    po_total_cbm=po_total_cbm
)
```

**Logic:**
1. Tìm `CostHistory` hiện có (theo `variant_id`, `location_id`, `import_date`, `purchase_order`)
2. Nếu có: cập nhật các trường
3. Nếu không: tạo mới
4. Tính `average_cost_price` bằng `calculate_average_cost_price()`
5. Lưu vào database

## Sử dụng

### Tính toán giá vốn cho SPO

```python
# POST /products/sum-purchase-orders/{spo_id}/calculate-cost-price/
# Query params: ?debug=true (để bật debug print)

from products.services.cost_price_service import CostPriceService

cost_service = CostPriceService(debug=True)  # Bật debug mode
# Tự động tính toán cho tất cả line items trong SPO
```

### Xem lịch sử giá vốn

```python
from products.models import CostHistory

# Lấy lịch sử giá vốn cho một variant
cost_histories = CostHistory.objects.filter(
    variant_id=123456,
    location_id=548744
).order_by('-import_date')

for cost in cost_histories:
    print(f"{cost.import_date}: {cost.average_cost_price}")
```

### Tính giá vốn cho một variant cụ thể

```python
from products.services.cost_price_service import CostPriceService
from products.models import SumPurchaseOrder, PurchaseOrder

cost_service = CostPriceService(debug=True)
spo = SumPurchaseOrder.objects.get(id=1)
po = PurchaseOrder.objects.get(id=1)

cost_history = cost_service.calculate_and_save_cost_history(
    spo=spo,
    po=po,
    variant_id=123456,
    location_id=548744,
    quantity=Decimal('100'),
    cpm_per_unit=Decimal('0.01'),
    import_date=date(2025, 12, 24),
    receipt_code='REC-001',
    sku='SKU-001',
    sku_model_xnk='SKU-MODEL-XNK',
    po_total_cbm=Decimal('10.5')
)
```

## Lưu ý quan trọng

### 1. Ngày nhập hàng (import_date)

- **Lấy từ `completed_on` của PO** (order_supplier), không phải ngày hiện tại
- Mỗi PO có thể có ngày nhập khác nhau
- Dùng để tìm tồn kho cũ chính xác

### 2. Location ID

- Giá vốn khác nhau cho từng kho hàng
- Phải lấy từ PO (order_supplier có `location_id`)
- Fallback: từ line_item hoặc receipt

### 3. Tồn kho cũ

- **Tồn kho cũ = tồn kho TRƯỚC ngày nhập**, không phải tồn kho hiện tại
- Nếu `old_quantity < 0`, tự động set về `0`
- Tìm từ Sapo inventory history API

### 4. Giá vốn cũ = 0

- Nếu `old_cost_price = 0` (lần nhập đầu tiên):
  - `average_cost_price = new_cost_price` (không tính bình quân)
- Nếu `old_cost_price > 0`:
  - Tính bình quân gia quyền như bình thường

### 5. Chi phí PO và SPO

- **Chi phí PO**: Lấy từ `po.costs` (model `PurchaseOrderCost`)
  - Phân bổ theo CBM: `po_cost_per_unit = (po_total_costs_vnd * cpm_per_unit) / po_total_cbm`
- **Chi phí SPO**: Lấy từ `spo.costs` (model `SPOCost`)
  - Chi phí VNĐ: `cost_side == 'vietnam'` và `amount_vnd`
  - Chi phí CNY: `cost_side == 'china'` và `amount_cny` (quy đổi sang VNĐ)
  - Phân bổ theo CBM: `spo_cost_per_unit = (spo_total_costs_vnd * cpm_per_unit) / spo_total_cbm`

### 6. Không sync lên Sapo

- **Tất cả dữ liệu lưu trong database nội bộ**
- Không còn sync lên Sapo `price_adjustments` nữa
- Các trường `synced_to_sapo`, `sapo_price_adjustment_id` vẫn tồn tại nhưng không được sử dụng

## Debug Mode

Để bật debug print, thêm `?debug=true` vào URL:

```
POST /products/sum-purchase-orders/1/calculate-cost-price/?debug=true
```

Hoặc khi khởi tạo service:

```python
cost_service = CostPriceService(debug=True)
```

Debug print sẽ hiển thị:
- Quá trình tìm tồn kho cũ
- Các bước tính giá vốn mới
- Chi tiết từng thành phần (price_cny, exchange_rate, taxes, costs)
- Kết quả tính toán cuối cùng

## Ví dụ

### Ví dụ 1: Lần nhập đầu tiên

```
variant_id = 123456
location_id = 548744
import_quantity = 100
old_quantity = 0
old_cost_price = 0
new_cost_price = 50000

→ average_cost_price = 50000 (không tính bình quân)
```

### Ví dụ 2: Lần nhập thứ 2

```
variant_id = 123456
location_id = 548744
import_quantity = 50
old_quantity = 80 (tồn còn lại từ lần 1)
old_cost_price = 50000 (từ lần 1)
new_cost_price = 55000

→ average_cost_price = (80 * 50000 + 50 * 55000) / (80 + 50) = 51923.08
```

## API Endpoints

### Tính toán giá vốn

```
POST /products/sum-purchase-orders/{spo_id}/calculate-cost-price/
Query params: ?debug=true (optional)
```

**Response:**
```json
{
  "status": "success",
  "message": "Đã tính toán giá vốn: 29 thành công, 0 thất bại",
  "results": {
    "success": 29,
    "failed": 0,
    "errors": []
  }
}
```

## Files liên quan

- **Model**: `products/models.py` - Class `CostHistory`
- **Service**: `products/services/cost_price_service.py` - Class `CostPriceService`
- **View**: `products/views.py` - Function `calculate_cost_price()`
- **Template**: `products/templates/products/sum_purchase_order_detail.html` - Hiển thị bảng phân bổ giá vốn



# 📦 HỆ THỐNG QUẢN LÝ NHẬP HÀNG - CONTAINER & ĐƠN ĐẶT HÀNG

## 🎯 TỔNG QUAN

Hệ thống quản lý nhập hàng từ Trung Quốc về Việt Nam, bao gồm:
- **Container Templates**: Mẫu container tái sử dụng
- **Sum Purchase Order (SPO)**: Đợt nhập container gộp nhiều PO
- **Purchase Order (PO)**: Đơn đặt hàng từ nhà sản xuất
- **Tracking Timeline**: Theo dõi tiến độ từ tạo SPO đến về kho

---

## 📁 CẤU TRÚC DATABASE

### 1. **ContainerTemplate** (`products/models.py`)
```python
# Mẫu container tái sử dụng
- code: CharField (unique)  # CONT-01
- name: CharField
- container_type: CharField (40ft/20ft)
- volume_cbm: FloatField (default=65.0)
- default_supplier_id/code/name: Supplier mặc định
- ship_time_avg_hn/hcm: IntegerField (ngày)
- departure_port: CharField
- avg_import_cycle_days: IntegerField
- is_active: BooleanField
```

### 2. **ContainerTemplateSupplier** (`products/models.py`)
```python
# Quan hệ nhiều-nhiều: Container <-> Suppliers
- container_template: ForeignKey
- supplier_id/code/name: Sapo supplier info
- supplier_logo_path: CharField
- priority: IntegerField
```

### 3. **SumPurchaseOrder (SPO)** (`products/models.py`)
```python
# Đợt nhập container
- code: CharField (unique)  # CON-SH-2025-HCM-01 (auto-generated)
- name: CharField
- container_template: ForeignKey
- status: CharField (draft → created → supplier_confirmed → ... → completed)
- destination_port: CharField (hcm/haiphong)
- expected_arrival_date: DateField (min 12 days from today)
- timeline: JSONField  # [{"stage": "...", "planned_date": "...", "actual_date": "...", "note": "..."}]
- shipping_cn_vn, customs_processing_vn, other_costs, port_to_warehouse, loading_unloading: DecimalField
- total_cbm: DecimalField
- tags: JSONField
```

**Status Flow:**
```
draft → created → supplier_confirmed → producing → waiting_packing → 
packed → departed_cn → arrived_vn → customs_cleared → 
arrived_warehouse_hn/hcm → completed
```

### 4. **PurchaseOrder (PO)** (`products/models.py`)
```python
# Đơn đặt hàng từ Sapo
- sapo_order_supplier_id: BigIntegerField (unique)
- sapo_code: CharField  # CN-2025-S87
- supplier_id/code/name: Sapo supplier info
- sum_purchase_order: ForeignKey (nullable)
- domestic_shipping_cn, packing_fee: DecimalField
- total_cbm: DecimalField
- total_amount, total_quantity: DecimalField/IntegerField
- tags: JSONField  # ["CN", "TEMP_HCM"]
- status: CharField
```

### 5. **PurchaseOrderLineItem** (`products/models.py`)
```python
# Chi tiết SKU trong PO
- purchase_order: ForeignKey
- sapo_line_item_id, product_id, variant_id: BigIntegerField
- sku, product_name, variant_name: CharField
- quantity, price, total_amount: IntegerField/DecimalField
- domestic_shipping_cn, packing_fee: DecimalField
- shipping_cn_vn_allocated, customs_processing_allocated, ...: DecimalField (phân bổ từ SPO)
- vat, import_tax: DecimalField
- cbm: DecimalField
```

---

## 🔧 SERVICES

### **ContainerTemplateService** (`products/services/container_template_service.py`)
```python
class ContainerTemplateService:
    def create_template(data) -> ContainerTemplate
    def update_template(template_id, data) -> ContainerTemplate
    def add_supplier(template_id, supplier_id) -> ContainerTemplateSupplier
    def remove_supplier(template_id, supplier_id)
    def set_default_supplier(template_id, supplier_id)
```

### **SumPurchaseOrderService** (`products/services/sum_purchase_order_service.py`)
```python
class SumPurchaseOrderService:
    def create_spo(container_template_id, destination_port, expected_arrival_date) -> SumPurchaseOrder
        # Auto-generate name: CON-SH-{YEAR}-{PORT}-{NUMBER}
        # Validate expected_arrival_date (min 12 days)
        # Initialize timeline (chỉ warehouse stage phù hợp với destination_port)
    
    def sync_po_from_sapo(sapo_order_supplier_id) -> PurchaseOrder
        # Sync từ Sapo API: GET /admin/order_suppliers/{id}.json
        # Update/Create PO và line_items
    
    def add_po_to_spo(spo_id, po_ids=None, tag=None)
        # Tìm PO theo IDs hoặc tag
        # Gán vào SPO
        # Recalculate SPO total_cbm
    
    def allocate_costs(spo_id)
        # Phân bổ chi phí chung theo CBM:
        #   - SPO → PO (theo po.total_cbm / spo.total_cbm)
        #   - PO → LineItem (theo item.cbm / po.total_cbm)
    
    def _initialize_timeline(spo)
        # Khởi tạo timeline với warehouse stage phù hợp:
        #   - destination_port='hcm' → chỉ 'arrived_warehouse_hcm'
        #   - destination_port='haiphong' → chỉ 'arrived_warehouse_hn'
    
    def _recalculate_spo_cbm(spo)
    def _recalculate_po_cbm(po)
```

---

## 🌐 VIEWS & URLS

### **Container Templates**
- `GET /products/container-templates/` → `container_template_list()`
- `GET /products/container-templates/{id}/` → `container_template_detail()`
- `POST /products/container-templates/create/` → `create_container_template()`
- `POST /products/container-templates/{id}/update/` → `update_container_template()`
- `POST /products/container-templates/add-supplier/` → `add_supplier_to_container()`
- `POST /products/container-templates/remove-supplier/` → `remove_supplier_from_container()`
- `GET /products/container-templates/get-suppliers/` → `get_suppliers_for_select()` (API lấy suppliers active với logo)
- `POST /products/container-templates/{id}/set-default-supplier/` → `set_default_supplier()`

### **Sum Purchase Orders**
- `GET /products/sum-purchase-orders/` → `sum_purchase_order_list()` (Grid layout với cards)
- `GET /products/sum-purchase-orders/{id}/` → `sum_purchase_order_detail()`
- `POST /products/sum-purchase-orders/create/` → `create_sum_purchase_order()`
- `POST /products/sum-purchase-orders/add-po/` → `add_po_to_spo()`
- `POST /products/sum-purchase-orders/sync-po/` → `sync_po_from_sapo()`
- `POST /products/sum-purchase-orders/update-status/` → `update_spo_status()`
- `POST /products/sum-purchase-orders/update-planned-date/` → `update_timeline_planned_date()`
- `POST /products/sum-purchase-orders/allocate-costs/` → `allocate_costs()`

---

## 🎨 TEMPLATES & UI

### **Container Template List** (`container_template_list.html`)
- **Table**: Code, Name, Type, Volume, Default Supplier, Suppliers (full list), Actions
- **Modal "Thêm NSX"**: Fetch suppliers từ `get_suppliers_for_select`, hiển thị logo
- **Dropdown "NSX Mặc định"**: Chọn từ suppliers đã thêm, gọi `set_default_supplier`
- **Dynamic UI**: Thêm supplier không cần reload, update dropdown tự động

### **SPO List** (`sum_purchase_order_list.html`)
- **Grid Layout**: Cards với status color strip
- **Card Info**: Code, Name, Date, Container Template, Status badge
- **Route Display**: Từ Trung Quốc → Đến (HCM/Hải Phòng) với icon
- **Capacity Progress**: CBM / Volume với progress bar (đỏ >90%, cam >70%, xanh)
- **Stats Grid**: Giá trị hàng, Chi phí dự kiến, Số PO, Tổng sản phẩm
- **Expected Date**: Dự kiến về với icon
- **Empty State**: Hướng dẫn tạo SPO mới

### **SPO Detail** (`sum_purchase_order_detail.html`)

#### **Thông tin SPO (2 cột)**
- **Cột 1 - Thông tin chung**: Mã SPO, Container Template, Cảng đến, Dự kiến ngày hàng về (từ warehouse stage), Ngày tạo
- **Cột 2 - Hàng hóa đóng gói**: Tổng CBM, Số kiện, Số lượng, Tổng số tiền hàng

#### **Tracking Timeline (Progress Bar)**
- **Full width 100%**: Timeline dài full div
- **Progress Bar**: Thanh màu xanh lá từ đầu đến trạng thái hiện tại
- **Stages**: 
  - Tạo SPO, NSX xác nhận, Đang sản xuất, Đợi đóng, Đóng xong
  - Rời cảng TQ, Về cảng VN, Thông quan
  - Về kho HN/HCM (chỉ 1 trong 2, dựa trên `destination_port`)
- **Icons**:
  - ✓ (xanh lá): Có actual_date hoặc trạng thái hiện tại
  - 📅 (xanh dương): Có planned_date
  - ➕ (xám): Chưa có date (click để thêm)
- **Nút Check (✓) màu đỏ**: 
  - Vị trí: Center (theo chiều dọc) của trạng thái tiếp theo
  - Click: Cập nhật trạng thái sang bước tiếp theo
- **Connector Lines**: Màu xanh lá đến trạng thái hiện tại, xám sau đó
- **Date Format**: `dd-MM-yyyy` (06-12-2025)
- **Deadline Warning**: 
  - Đỏ: Trễ deadline > 2 ngày
  - Xanh lá: Còn 0-2 ngày đến deadline
  - Hiển thị "Trễ X ngày" nếu trễ

#### **Purchase Orders**
- **Table**: Mã PO, Nhà sản xuất, Trạng thái, Tổng tiền, CBM
- **Actions**: Sync từ Sapo, Thêm PO

#### **Chi phí chung**
- **Form**: Vận chuyển TQ-VN, Xử lý Hải Quan, Phí phát sinh, Cảng → kho, Bốc xếp
- **Nút "Phân bổ chi phí"**: Tự động phân bổ theo CBM

#### **Line Items**
- **Table**: SKU, Sản phẩm, Số lượng, Giá, CBM, Chi phí phân bổ

---

## 🔄 WORKFLOW CHÍNH

### **1. Tạo SPO**
```
1. User: Chọn Container Template, Cảng đến, Dự kiến ngày về
2. System: Auto-generate name (CON-SH-2025-HCM-01)
3. Service: create_spo() → Tạo SPO với status='draft'
4. Service: _initialize_timeline() → Khởi tạo timeline (chỉ warehouse phù hợp)
5. Redirect: → SPO detail page
```

### **2. Thêm PO vào SPO**
```
1. User: Sync PO từ Sapo hoặc thêm từ tags
2. Service: sync_po_from_sapo() → Sync từ Sapo API
3. Service: add_po_to_spo() → Gán PO vào SPO
4. Service: _recalculate_spo_cbm() → Tính lại CBM
```

### **3. Cập nhật Timeline**
```
1. User: Click nút check (✓) ở trạng thái tiếp theo
2. API: update_spo_status() → Cập nhật status và actual_date
3. Model: spo.update_status() → Log vào timeline
4. Redirect: Reload page
```

### **4. Phân bổ chi phí**
```
1. User: Nhập chi phí chung vào SPO
2. User: Click "Phân bổ chi phí"
3. Service: allocate_costs() → Phân bổ theo CBM:
   - SPO → PO (ratio = po.total_cbm / spo.total_cbm)
   - PO → LineItem (ratio = item.cbm / po.total_cbm)
```

---

## 📊 TÍNH TOÁN CHI PHÍ

### **Phân bổ theo CBM:**
```
1. Tỷ lệ PO: ratio_po = po.total_cbm / spo.total_cbm
2. Chi phí PO: cost_po = cost_spo * ratio_po
3. Tỷ lệ Item: ratio_item = item.cbm / po.total_cbm
4. Chi phí Item: cost_item = cost_po * ratio_item
```

### **Tổng chi phí mỗi SKU:**
```
total_cost = 
    item.total_amount +                    # Giá mua
    item.domestic_shipping_cn +            # Vận chuyển nội địa TQ
    item.packing_fee +                     # Phí đóng hàng
    item.shipping_cn_vn_allocated +        # Vận chuyển TQ-VN (phân bổ)
    item.customs_processing_allocated +    # Xử lý Hải Quan (phân bổ)
    item.other_costs_allocated +           # Phí phát sinh (phân bổ)
    item.port_to_warehouse_allocated +     # Cảng → kho (phân bổ)
    item.loading_unloading_allocated +     # Bốc xếp (phân bổ)
    item.vat +                             # VAT
    item.import_tax                        # Thuế nhập khẩu
```

---

## 🎯 KEY FEATURES

### **1. Auto-naming SPO**
- Format: `CON-SH-{YEAR}-{PORT}-{NUMBER}`
- PORT: HCM → HCM, haiphong → HN
- NUMBER: Auto-increment theo năm và port

### **2. Timeline Logic**
- Chỉ hiển thị warehouse stage phù hợp với `destination_port`
- Progress bar: Màu xanh lá đến trạng thái hiện tại
- Nút check (✓) đỏ ở trạng thái tiếp theo (center theo chiều dọc)

### **3. Date Formatting**
- Format: `dd-MM-yyyy` (06-12-2025)
- Planned date: Màu xanh dương (đỏ nếu trễ > 2 ngày)
- Actual date: Màu xanh lá

### **4. Cost Allocation**
- Tự động phân bổ theo CBM
- 2 cấp: SPO → PO → LineItem

### **5. Supplier Management**
- Thêm supplier vào container template từ list page (modal)
- Set default supplier từ dropdown
- Hiển thị full list suppliers (không truncate)

---

## 📝 NOTES

- **SPO Code**: Auto-generated `CON-SH-{YEAR}-{PORT}-{NUMBER}`
- **Timeline**: JSONField với stages, planned_date, actual_date, note
- **Warehouse Stage**: Chỉ 1 trong 2 (HN/HCM) dựa trên `destination_port`
- **CBM Calculation**: Từ product metadata hoặc manual input
- **Sync PO**: Từ Sapo API `/admin/order_suppliers/{id}.json`
- **Validation**: `expected_arrival_date` phải cách ngày hôm nay tối thiểu 12 ngày

---

## 🚀 PHÁT TRIỂN TIẾP

### **Có thể mở rộng:**
1. **Export/Import**: Excel cho SPO, PO, LineItems
2. **Notifications**: Cảnh báo khi trễ deadline
3. **Reports**: Báo cáo chi phí, thời gian vận chuyển
4. **Integration**: Tự động sync PO từ Sapo theo schedule
5. **CBM Auto-calculation**: Từ product dimensions
6. **Multi-currency**: Hỗ trợ nhiều loại tiền tệ
7. **Document Management**: Upload invoices, contracts

# PLAN: Xây dựng lại Order DTO với Real Items (Qui đổi Combo/Packsize)

## 📋 TỔNG QUAN

Xây dựng lại logic xử lý đơn hàng để:
1. Tích hợp với Products/Variants DTO từ `/products`
2. Qui đổi các sản phẩm combo/packsize thành sản phẩm đơn lẻ
3. Xử lý ở cấp độ DTO lúc init để có tính kế thừa và phát triển

---

## 🎯 MỤC TIÊU

### Input:
- Order từ Sapo với `order_line_items` có thể chứa:
  - Sản phẩm thường (`product_type="normal"`, `is_packsize=False`)
  - Sản phẩm packsize (`product_type="normal"`, `is_packsize=True`)
  - Sản phẩm composite (`product_type="composite"`)

### Output:
- `OrderDTO.real_items`: Danh sách sản phẩm đã được qui đổi thành đơn lẻ
- Mỗi item trong `real_items` có:
  - `variant_id`: ID variant đơn lẻ
  - `old_id`: ID variant gốc (combo/packsize) - để track nguồn gốc
  - `quantity`: Số lượng đã qui đổi
  - `sku`, `variant_options`, `unit`, etc.

---

## 📐 KIẾN TRÚC

### Phase 1: Mở rộng OrderLineItemDTO

**File:** `orders/services/dto.py`

**Thêm các field:**
```python
class OrderLineItemDTO(BaseDTO):
    # ... existing fields ...
    
    # Packsize fields
    is_packsize: bool = False
    pack_size_quantity: Optional[int] = None      # Số lượng trong pack
    pack_size_root_id: Optional[int] = None       # Variant ID gốc (đơn lẻ)
    
    # Composite fields
    composite_item_domains: List[Dict[str, Any]] = Field(default_factory=list)
```

**Lưu ý:**
- Các field này có thể None/empty cho sản phẩm thường
- Cần parse từ raw JSON của Sapo API

---

### Phase 2: Tạo RealItemDTO

**File:** `orders/services/dto.py`

**Tạo DTO mới:**
```python
class RealItemDTO(BaseDTO):
    """
    Sản phẩm đơn lẻ sau khi qui đổi từ combo/packsize.
    Dùng cho việc đóng gói, in phiếu, tracking.
    """
    variant_id: int                    # ID variant đơn lẻ
    old_id: int = 0                    # ID variant gốc (combo/packsize) - 0 nếu là sản phẩm thường
    product_id: Optional[int] = None
    sku: str
    barcode: Optional[str] = None
    variant_options: Optional[str] = None
    quantity: float
    unit: str = "cái"
    product_name: str = ""             # Tên sản phẩm (lấy từ product_name, split '/')
    
    # Reference to ProductVariantDTO (optional, lazy load)
    variant_dto: Optional[ProductVariantDTO] = None
```

---

### Phase 3: Thêm Real Items vào OrderDTO

**File:** `orders/services/dto.py`

**Thêm vào OrderDTO:**
```python
class OrderDTO(BaseDTO):
    # ... existing fields ...
    
    # Real items (qui đổi từ combo/packsize)
    real_items: List[RealItemDTO] = Field(default_factory=list)
    total_quantity: int = 0            # Tổng số lượng (exclude SKU='KEO')
```

**Computed property:**
```python
@computed_field
@property
def total_quantity(self) -> int:
    """Tổng số lượng sản phẩm (exclude SKU='KEO')"""
    return sum(
        int(item.quantity) 
        for item in self.real_items 
        if item.sku != 'KEO'
    )
```

---

### Phase 4: Logic Qui Đổi trong OrderDTOFactory

**File:** `orders/services/order_builder.py`

**Thêm method mới:**
```python
class OrderDTOFactory:
    def _build_real_items(
        self, 
        order_line_items: List[OrderLineItemDTO],
        variant_service: Optional[Any] = None  # ProductVariantService để fetch variant info
    ) -> List[RealItemDTO]:
        """
        Qui đổi order_line_items thành real_items (sản phẩm đơn lẻ).
        
        Logic:
        1. Normal + is_packsize=False: Giữ nguyên, add vào real_items
        2. Normal + is_packsize=True: Qui đổi theo pack_size_quantity, add pack_size_root_id
        3. Composite: Lấy từ composite_item_domains, add vào real_items
        
        Returns:
            List[RealItemDTO] đã được gộp theo variant_id và sắp xếp theo SKU
        """
        real_items_map: Dict[int, RealItemDTO] = {}  # {variant_id: RealItemDTO}
        
        for line_item in order_line_items:
            # Extract product_name (lấy phần trước '/')
            pr_name = ""
            if line_item.product_name and '/' in line_item.product_name:
                pr_name = line_item.product_name.split('/')[0]
            
            unit = line_item.unit or "cái"
            
            # Case 1: Normal + is_packsize=False
            if line_item.product_type == "normal" and not line_item.is_packsize:
                variant_id = line_item.variant_id
                if variant_id:
                    if variant_id in real_items_map:
                        # Cộng dồn số lượng
                        real_items_map[variant_id].quantity += line_item.quantity
                    else:
                        # Tạo mới
                        real_items_map[variant_id] = RealItemDTO(
                            variant_id=variant_id,
                            old_id=0,  # Sản phẩm thường không có old_id
                            product_id=line_item.product_id,
                            sku=line_item.sku,
                            barcode=line_item.barcode,
                            variant_options=line_item.variant_options,
                            quantity=line_item.quantity,
                            unit=unit,
                            product_name=pr_name
                        )
            
            # Case 2: Normal + is_packsize=True
            elif line_item.product_type == "normal" and line_item.is_packsize:
                if not line_item.pack_size_root_id:
                    # Không có pack_size_root_id -> skip
                    continue
                
                root_variant_id = line_item.pack_size_root_id
                converted_quantity = int(line_item.quantity * (line_item.pack_size_quantity or 1))
                
                if root_variant_id in real_items_map:
                    real_items_map[root_variant_id].quantity += converted_quantity
                else:
                    # Fetch variant info từ Sapo API
                    variant_info = self._fetch_variant_info(root_variant_id, variant_service)
                    
                    real_items_map[root_variant_id] = RealItemDTO(
                        variant_id=root_variant_id,
                        old_id=line_item.variant_id,  # Lưu variant_id gốc (packsize)
                        product_id=variant_info.get("product_id"),
                        sku=variant_info.get("sku", ""),
                        barcode=variant_info.get("barcode"),
                        variant_options=variant_info.get("opt1"),
                        quantity=converted_quantity,
                        unit="cái",  # Packsize luôn qui đổi về "cái"
                        product_name=pr_name
                    )
            
            # Case 3: Composite
            elif line_item.product_type == "composite":
                for composite_item in line_item.composite_item_domains:
                    comp_variant_id = composite_item.get("variant_id")
                    comp_quantity = int(composite_item.get("quantity", 0))
                    
                    if not comp_variant_id:
                        continue
                    
                    if comp_variant_id in real_items_map:
                        real_items_map[comp_variant_id].quantity += comp_quantity
                    else:
                        # Fetch variant info từ Sapo API
                        variant_info = self._fetch_variant_info(comp_variant_id, variant_service)
                        
                        real_items_map[comp_variant_id] = RealItemDTO(
                            variant_id=comp_variant_id,
                            old_id=line_item.variant_id,  # Lưu variant_id gốc (composite)
                            product_id=variant_info.get("product_id"),
                            sku=variant_info.get("sku", ""),
                            barcode=variant_info.get("barcode"),
                            variant_options=variant_info.get("opt1"),
                            quantity=comp_quantity,
                            unit="cái",
                            product_name=pr_name
                        )
        
        # Convert dict to list
        real_items = list(real_items_map.values())
        
        # Sắp xếp theo SKU (phần số trước dấu '-')
        real_items.sort(key=lambda item: self._get_sku_sort_key(item.sku))
        
        return real_items
    
    def _fetch_variant_info(self, variant_id: int, variant_service: Optional[Any]) -> Dict[str, Any]:
        """
        Fetch variant info từ Sapo API hoặc cache.
        Fallback về empty dict nếu không fetch được.
        """
        if not variant_service:
            return {}
        
        try:
            variant = variant_service.get_variant(variant_id)
            return {
                "product_id": variant.product_id,
                "sku": variant.sku,
                "barcode": variant.barcode,
                "opt1": variant.opt1
            }
        except Exception:
            return {}
    
    def _get_sku_sort_key(self, sku: str) -> float:
        """
        Lấy phần số từ SKU trước dấu '-' để sort.
        Returns float('inf') nếu không phải số.
        """
        try:
            sku_number = sku.split('-')[0]
            if sku_number.isdigit():
                return int(sku_number)
            return float('inf')
        except Exception:
            return float('inf')
```

---

### Phase 5: Cập nhật OrderDTOFactory.from_sapo_json()

**File:** `orders/services/order_builder.py`

**Cập nhật method:**
```python
def from_sapo_json(
    self, 
    raw_order: Dict[str, Any],
    variant_service: Optional[Any] = None
) -> OrderDTO:
    # ... existing code ...
    
    # Build order_line_items (cần parse thêm is_packsize, composite_item_domains)
    order_line_items = self._build_order_line_items(raw_order.get("line_items", []))
    
    # Build real_items (qui đổi từ order_line_items)
    real_items = self._build_real_items(order_line_items, variant_service)
    
    # Create OrderDTO
    order = OrderDTO(
        # ... existing fields ...
        order_line_items=order_line_items,
        real_items=real_items,
        # ... rest of fields ...
    )
    
    return order
```

**Cập nhật `_build_order_line_items()` để parse thêm fields:**
```python
def _build_order_line_items(self, data_list: List[Dict[str, Any]]) -> List[OrderLineItemDTO]:
    result = []
    
    for d in (data_list or []):
        # ... existing parsing ...
        
        # Parse packsize fields
        is_packsize = bool(d.get("is_packsize", False))
        pack_size_quantity = d.get("pack_size_quantity")
        pack_size_root_id = d.get("pack_size_root_id")
        
        # Parse composite fields
        composite_item_domains = d.get("composite_item_domains", [])
        
        result.append(OrderLineItemDTO(
            # ... existing fields ...
            is_packsize=is_packsize,
            pack_size_quantity=pack_size_quantity,
            pack_size_root_id=pack_size_root_id,
            composite_item_domains=composite_item_domains,
        ))
    
    return result
```

---

### Phase 6: Tích hợp với Products DTO

**File:** `orders/services/order_builder.py`

**Option 1: Lazy load ProductVariantDTO**
```python
def _enrich_real_items_with_product_dto(
    self,
    real_items: List[RealItemDTO],
    product_service: Optional[Any] = None
) -> List[RealItemDTO]:
    """
    Enrich real_items với ProductVariantDTO từ /products module.
    Optional - chỉ load khi cần.
    """
    if not product_service:
        return real_items
    
    for item in real_items:
        try:
            # Fetch product + variant từ /products
            variant_dto = product_service.get_variant_dto(item.variant_id)
            item.variant_dto = variant_dto
        except Exception:
            pass  # Skip nếu không fetch được
    
    return real_items
```

**Option 2: Inject vào RealItemDTO**
```python
class RealItemDTO(BaseDTO):
    # ... existing fields ...
    
    # Optional: Reference to ProductVariantDTO
    variant_dto: Optional[ProductVariantDTO] = None
```

---

## 🔄 WORKFLOW

### Khi init OrderDTO:

1. **Parse raw JSON từ Sapo API**
   - Extract `order_line_items` với đầy đủ fields (is_packsize, composite_item_domains)

2. **Build OrderLineItemDTO**
   - Parse từng line item
   - Lưu các field packsize/composite

3. **Build RealItemDTO**
   - Qui đổi từ OrderLineItemDTO
   - Gộp theo variant_id
   - Fetch variant info nếu cần (packsize/composite)

4. **Sort RealItemDTO**
   - Sắp xếp theo SKU (phần số trước dấu '-')

5. **Attach vào OrderDTO**
   - `order.real_items = [...]`
   - `order.total_quantity = computed`

---

## 📝 TEST CASES

### Test Case 1: Packsize
**Input:**
```json
{
  "order_line_items": [
    {
      "variant_id": 123,
      "sku": "SQ-0101-CB2",
      "quantity": 2,
      "product_type": "normal",
      "is_packsize": true,
      "pack_size_quantity": 2,
      "pack_size_root_id": 456
    }
  ]
}
```

**Expected Output:**
```python
real_items = [
    RealItemDTO(
        variant_id=456,
        old_id=123,
        sku="SQ-0101-BS",
        quantity=4,  # 2 * 2
        unit="cái"
    )
]
```

### Test Case 2: Composite
**Input:**
```json
{
  "order_line_items": [
    {
      "variant_id": 789,
      "sku": "CB-0306",
      "quantity": 1,
      "product_type": "composite",
      "composite_item_domains": [
        {"variant_id": 101, "quantity": 1},
        {"variant_id": 102, "quantity": 1},
        {"variant_id": 103, "quantity": 2}
      ]
    }
  ]
}
```

**Expected Output:**
```python
real_items = [
    RealItemDTO(variant_id=101, old_id=789, sku="JX-0306-S3", quantity=1),
    RealItemDTO(variant_id=102, old_id=789, sku="JX-0306-S4", quantity=1),
    RealItemDTO(variant_id=103, old_id=789, sku="JX-0306-S5", quantity=2),
]
```

### Test Case 3: Mixed (Packsize + Normal)
**Input:**
```json
{
  "order_line_items": [
    {
      "variant_id": 123,
      "sku": "SQ-0101-CB2",
      "quantity": 2,
      "product_type": "normal",
      "is_packsize": true,
      "pack_size_quantity": 2,
      "pack_size_root_id": 456
    },
    {
      "variant_id": 456,
      "sku": "SQ-0101-BS",
      "quantity": 2,
      "product_type": "normal",
      "is_packsize": false
    }
  ]
}
```

**Expected Output:**
```python
real_items = [
    RealItemDTO(
        variant_id=456,
        old_id=0,  # Từ sản phẩm thường
        sku="SQ-0101-BS",
        quantity=6  # 2 (packsize) + 4 (qui đổi từ packsize)
    )
]
```

---

## 🚀 IMPLEMENTATION STEPS

### Step 1: Mở rộng DTOs (1-2 giờ)
- [ ] Thêm fields vào `OrderLineItemDTO`
- [ ] Tạo `RealItemDTO`
- [ ] Thêm `real_items` vào `OrderDTO`

### Step 2: Logic Qui Đổi (3-4 giờ)
- [ ] Implement `_build_real_items()`
- [ ] Implement `_fetch_variant_info()`
- [ ] Implement `_get_sku_sort_key()`
- [ ] Update `_build_order_line_items()` để parse thêm fields

### Step 3: Tích hợp (2-3 giờ)
- [ ] Update `from_sapo_json()` để gọi `_build_real_items()`
- [ ] Test với các test cases
- [ ] Handle edge cases (missing data, API errors)

### Step 4: Tích hợp Products DTO (Optional, 2-3 giờ)
- [ ] Implement `_enrich_real_items_with_product_dto()`
- [ ] Inject `ProductVariantDTO` vào `RealItemDTO`
- [ ] Test integration

### Step 5: Testing & Documentation (2-3 giờ)
- [ ] Unit tests cho từng case
- [ ] Integration tests
- [ ] Update documentation
- [ ] Code review

---

## ⚠️ LƯU Ý

1. **Performance:**
   - Fetch variant info có thể chậm nếu nhiều packsize/composite
   - Cân nhắc cache hoặc batch fetch

2. **Error Handling:**
   - Nếu không fetch được variant info -> fallback về empty/default
   - Không block việc tạo OrderDTO nếu thiếu data

3. **Backward Compatibility:**
   - `order_line_items` vẫn giữ nguyên (không thay đổi)
   - `real_items` là field mới, optional

4. **old_id Tracking:**
   - Quan trọng để track nguồn gốc khi in phiếu/kiện hàng
   - Cần lưu đúng variant_id gốc (combo/packsize)

---

## 📚 REFERENCES

- Code tham khảo: `TODOLIST.md` (lines 26-129)
- Products DTO: `products/services/dto.py`
- Order Builder: `orders/services/order_builder.py`

---

## ✅ CHECKLIST

- [ ] Phase 1: Mở rộng OrderLineItemDTO
- [ ] Phase 2: Tạo RealItemDTO
- [ ] Phase 3: Thêm Real Items vào OrderDTO
- [ ] Phase 4: Logic Qui Đổi
- [ ] Phase 5: Cập nhật OrderDTOFactory
- [ ] Phase 6: Tích hợp Products DTO (optional)
- [ ] Testing
- [ ] Documentation


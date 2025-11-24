# Products Module

## Tổng Quan

Module `/products` quản lý sản phẩm với Sapo, Sapo MP, và Shopee KNB. Module này lưu trữ metadata mở rộng (không có trong Sapo standard fields) bằng cách nhúng JSON vào `product.description` field với format `[GDP_META]...[/GDP_META]`.

## Cấu Trúc

```
products/
├── services/
│   ├── __init__.py
│   ├── dto.py                    # Pydantic DTOs cho Product/Variant + metadata
│   ├── metadata_helper.py        # Utilities để parse/inject GDP_META
│   └── sapo_product_service.py   # Business logic cho products
├── models.py
├── views.py
└── urls.py
```

## DTOs

### Product & Variant DTOs

- `ProductDTO`: Sản phẩm với đầy đủ thông tin Sapo + GDP metadata
- `ProductVariantDTO`: Phân loại sản phẩm với metadata mở rộng
- `VariantPriceDTO`: Giá theo price list
- `VariantInventoryDTO`: Tồn kho theo location
- `VariantImageDTO`: Hình ảnh

### Metadata DTOs

- `ProductMetadataDTO`: Metadata của product (web_product_id, custom_description, variants)
- `VariantMetadataDTO`: Metadata của variant (import_info, packaging_info, website_info)
- `ImportInfoDTO`: Thông tin nhập hàng (giá CNY, supplier SKU, import model SKU)
- `PackagingInfoDTO`: Thông tin đóng gói (kích thước hộp/thùng, trọng lượng)
- `WebsiteInfoDTO`: Thông tin website (danh sách web_variant_ids)

## Metadata Storage

GDP metadata được lưu trong `product.description` field với format:

```
Mô tả sản phẩm gốc...

[GDP_META]{"web_product_id":"123","custom_description":"...","variants":[{"id":62457516,"import_info":{...}}]}[/GDP_META]
```

### Ưu điểm:
- Không cần thay đổi database schema của Sapo
- Single source of truth
- Dễ sync và backup

### Metadata Fields

#### Product Level:
- `web_product_id`: ID sản phẩm trên website
- `custom_description`: Mô tả tùy chỉnh

#### Variant Level:
- **Import Info**: Giá Trung Quốc (CNY), SKU nhà sản xuất, SKU-MODEL nhập khẩu
- **Packaging Info**: Kích thước hộp/thùng, trọng lượng có/không bì, số lượng/thùng
- **Website Info**: Danh sách web_variant_id

## Usage Examples

### 1. Fetch Product với Metadata

```python
from core.sapo_client import get_sapo_client
from products.services.sapo_product_service import SapoProductService

# Get Sapo client
sapo_client = get_sapo_client()

# Initialize service
product_service = SapoProductService(sapo_client)

# Fetch product
product = product_service.get_product(42672265)

# Access product info
print(product.name)  # "Kệ chén/ bát dán tường"
print(product.variant_count)  # 2
print(product.original_description)  # Description without GDP_META

# Access GDP metadata
if product.gdp_metadata:
    print(product.gdp_metadata.web_product_id)
    
# Access variant metadata
for variant in product.variants:
    print(f"{variant.name} - SKU: {variant.sku}")
    if variant.gdp_metadata and variant.gdp_metadata.import_info:
        print(f"  China Price: {variant.gdp_metadata.import_info.china_price_cny} CNY")
```

### 2. Initialize Empty Metadata

```python
# Initialize metadata structure for a product
success = product_service.init_product_metadata(42672265)
# This creates empty metadata for product and all its variants
```

### 3. Update Variant Metadata

```python
from products.services.dto import VariantMetadataDTO, ImportInfoDTO, PackagingInfoDTO

# Create variant metadata
variant_meta = VariantMetadataDTO(
    id=62457516,
    import_info=ImportInfoDTO(
        china_price_cny=50.0,
        supplier_sku="TG-0201-FACTORY",
        import_model_sku="MODEL-TG-0201"
    ),
    packaging_info=PackagingInfoDTO(
        box_length_cm=30.0,
        box_width_cm=20.0,
        box_height_cm=10.0,
        weight_with_box_g=900.0,
        weight_without_box_g=800.0,
        units_per_carton=20
    )
)

# Update variant metadata
success = product_service.update_variant_metadata_only(
    product_id=42672265,
    variant_id=62457516,
    variant_metadata=variant_meta
)
```

### 4. Update Product Metadata

```python
from products.services.dto import ProductMetadataDTO, VariantMetadataDTO

# Get current product
product = product_service.get_product(42672265)

# Create/update metadata
metadata = ProductMetadataDTO(
    web_product_id="WEB-123",
    custom_description="Premium quality",
    variants=[
        VariantMetadataDTO(id=62457516),
        VariantMetadataDTO(id=62457517)
    ]
)

# Save metadata
success = product_service.update_product_metadata(
    product_id=42672265,
    metadata=metadata,
    preserve_description=True  # Keep original description
)
```

### 5. List Products

```python
# Fetch products with pagination
products = product_service.list_products(page=1, limit=50, status='active')

for product in products:
    print(f"{product.name} - {product.variant_count} variants")
    print(f"  Total inventory: {product.total_inventory_all_variants}")
```

## Metadata Helper Functions

```python
from products.services.metadata_helper import (
    extract_gdp_metadata,
    inject_gdp_metadata,
    update_description_metadata,
    init_empty_metadata,
    get_variant_metadata,
    update_variant_metadata
)

# Extract metadata from description
metadata, original_desc = extract_gdp_metadata(product.description)

# Inject metadata into description
new_description = inject_gdp_metadata(original_desc, metadata)

# Get specific variant metadata
variant_meta = get_variant_metadata(product_metadata, variant_id=62457516)

# Update specific variant in product metadata
updated_metadata = update_variant_metadata(
    product_metadata, 
    variant_id=62457516, 
    updated_variant_metadata
)
```

## API Endpoints (Sapo Core)

- `GET /admin/products/{id}.json` - Lấy product với variants
- `GET /admin/products.json` - List products
- `PUT /admin/products/{id}.json` - Update product (description)
- `GET /admin/variants/{id}.json` - Lấy variant detail

## Computed Fields

### ProductDTO:
- `original_description`: Description không có GDP_META marker
- `variant_count`: Số lượng variants
- `total_inventory_all_variants`: Tổng tồn kho

### ProductVariantDTO:
- `total_inventory`: Tổng tồn kho tất cả locations
- `total_available`: Tổng tồn kho khả dụng

## Logging

Module sử dụng Python logging với logger name `products.services.*`:

```python
import logging
logger = logging.getLogger(__name__)
```

Log levels:
- `DEBUG`: API calls, metadata parsing
- `INFO`: Successful operations
- `WARNING`: Invalid JSON, missing data
- `ERROR`: Failed operations, exceptions

## Future Enhancements

- [ ] Quản trị xuất/nhập khẩu
- [ ] Model sản phẩm hải quan (HSCode, thuế)
- [ ] Update giá vốn
- [ ] Gợi ý nhập hàng
- [ ] Phân tích bán hàng theo sản phẩm
- [ ] Tỉ lệ đánh giá tốt/xấu

## Notes

- Metadata được validate tự động qua Pydantic
- Tất cả DTOs support JSON serialization/deserialization
- GDP_META marker không case-sensitive trong parsing
- Empty/null metadata fields sẽ được exclude khi serialize (tiết kiệm space)

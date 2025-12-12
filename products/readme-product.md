# README - Cấu Trúc và Cách Đọc Dữ Liệu Product GDP Meta

## Tổng Quan

Module `products` quản lý sản phẩm với Sapo và lưu trữ metadata mở rộng (không có trong Sapo standard fields) bằng cách nhúng JSON vào `product.description` field với format `[GDP_META]...[/GDP_META]`.

## Cấu Trúc Lưu Trữ Dữ Liệu

### 1. Vị Trí Lưu Trữ

GDP metadata được lưu trong `product.description` field của Sapo với format:

```
Mô tả sản phẩm gốc...

[GDP_META]{"variants":[{"id":123,"price_tq":50.0,"box_info":{...}}]}[/GDP_META]
```

### 2. Cấu Trúc JSON Metadata

```json
{
  "description": "<html>...</html>",
  "videos": [{"url": "...", "title": "..."}],
  "video_primary": {"url": "...", "title": "..."},
  "nhanphu_info": {"vi_name": "...", "en_name": "...", ...},
  "warranty_months": 12,
  "variants": [
    {
      "id": 123,
      "price_tq": 50.0,
      "sku_tq": "...",
      "name_tq": "...",
      "box_info": {
        "full_box": 20,
        "length_cm": 30.0,
        "width_cm": 20.0,
        "height_cm": 10.0
      },
      "packed_info": {
        "length_cm": 15.0,
        "width_cm": 10.0,
        "height_cm": 5.0,
        "weight_with_box_g": 900.0,
        "weight_without_box_g": 800.0,
        "converted_weight_g": 750.0
      },
      "sku_model_xnk": "...",
      "web_variant_id": ["web1", "web2"],
      "shopee_connections": [
        {
          "connection_id": 134366,
          "variation_id": "297209457630",
          "item_id": "55152258387"
        }
      ],
      "sales_forecast": {
        "variant_id": 123,
        "total_sold": 100,
        "total_sold_previous_period": 80,
        "period_days": 30,
        "sales_rate": 3.33,
        "growth_percentage": 25.0,
        "revenue": 5000000.0,
        "revenue_percentage": 2.5,
        "abc_category": "A",
        "priority_score": 8.5
      },
      "plan_tags": ["clear_stock", "stop_import"]
    }
  ]
}
```

## Cách Đọc Dữ Liệu

### ⚠️ QUAN TRỌNG: Chiến Lược Đọc Dữ Liệu

**KHÔNG request từng phân loại (variant) một. Thay vào đó:**

1. **Đọc toàn bộ products một lần** với limit 250 products/request
2. **Lưu vào JSON** hoặc memory để sử dụng
3. **Load từ JSON/memory** khi cần, không request lại

### 1. Đọc Dữ Liệu Variants (Giá Mua TQ, Thông Tin Thùng)

#### Code Tham Khảo: `products/views.py` - `variant_list()`

```python
from core.sapo_client import get_sapo_client
from products.services.sapo_product_service import SapoProductService

# Khởi tạo service
sapo_client = get_sapo_client()
product_service = SapoProductService(sapo_client)

# Lấy tất cả products (limit 250 mỗi request)
all_products = []
page = 1
limit = 250  # ⚠️ LIMIT TỐI ĐA: 250 products/request

while True:
    products_response = sapo_client.core.list_products_raw(
        page=page,
        limit=limit,
        status="active"
    )
    products_data = products_response.get("products", [])
    
    if not products_data:
        break
    
    # Parse từng product để lấy metadata
    for product_data in products_data:
        product_id = product_data.get("id")
        
        # Parse product với metadata
        product = product_service.get_product(product_id)
        if product and product.gdp_metadata:
            # Lưu vào all_products để dùng sau
            all_products.append(product)
    
    if len(products_data) < limit:
        break
    
    page += 1

# Sau khi có all_products, truy cập variant metadata
for product in all_products:
    for variant in product.variants:
        variant_meta = variant.gdp_metadata
        
        if variant_meta:
            # Giá mua hàng TQ (CNY)
            price_tq = variant_meta.price_tq  # float hoặc None
            
            # SKU TQ
            sku_tq = variant_meta.sku_tq  # str hoặc None
            
            # Tên/mô tả TQ
            name_tq = variant_meta.name_tq  # str hoặc None
            
            # Thông tin thùng (box_info)
            if variant_meta.box_info:
                full_box = variant_meta.box_info.full_box  # Số cái/thùng
                length_cm = variant_meta.box_info.length_cm  # Chiều dài (cm)
                width_cm = variant_meta.box_info.width_cm  # Chiều rộng (cm)
                height_cm = variant_meta.box_info.height_cm  # Chiều cao (cm)
            
            # Thông tin đóng gói 1 chiếc (packed_info)
            if variant_meta.packed_info:
                packed_length = variant_meta.packed_info.length_cm
                packed_width = variant_meta.packed_info.width_cm
                packed_height = variant_meta.packed_info.height_cm
                weight_with_box = variant_meta.packed_info.weight_with_box_g
                weight_without_box = variant_meta.packed_info.weight_without_box_g
            
            # SKU-MODEL-XNK (nhập khẩu)
            sku_model_xnk = variant_meta.sku_model_xnk
```

#### Các Trường Dữ Liệu Chính:

**VariantMetadataDTO** (`products/services/dto.py`):
- `price_tq` (float): Giá nhân dân tệ (CNY) - giá mua hàng TQ
- `sku_tq` (str): SKU của nhà sản xuất (SKU phân loại TQ)
- `name_tq` (str): Tên/mô tả sản phẩm TQ
- `box_info` (BoxInfoDTO): Thông tin thùng
  - `full_box` (int): Số cái/thùng
  - `length_cm` (float): Chiều dài (cm)
  - `width_cm` (float): Chiều rộng (cm)
  - `height_cm` (float): Chiều cao (cm)
- `packed_info` (PackedInfoDTO): Thông tin đóng gói 1 chiếc
  - `length_cm`, `width_cm`, `height_cm`: Kích thước (cm)
  - `weight_with_box_g`: Trọng lượng cả hộp (g)
  - `weight_without_box_g`: Trọng lượng không hộp (g)
  - `converted_weight_g`: Trọng lượng quy đổi (g)
- `sku_model_xnk` (str): SKU-MODEL-XNK (nhập khẩu)

### 2. Đọc Dữ Liệu Sales Forecast (Tốc Độ Bán 30N, 10N, So Sánh Cùng Kỳ)

#### Code Tham Khảo: `products/views.py` - `sales_forecast_list()`

```python
from products.services.sales_forecast_service import SalesForecastService

# Khởi tạo service
sapo_client = get_sapo_client()
forecast_service = SalesForecastService(sapo_client)

# Load dữ liệu cho 30 ngày và 10 ngày (KHÔNG force refresh - load từ DB)
forecast_map_30, all_products_30, all_variants_map_30 = forecast_service.calculate_sales_forecast(
    days=30,
    force_refresh=False  # ⚠️ Load từ database, không tính lại
)

forecast_map_10, all_products_10, all_variants_map_10 = forecast_service.calculate_sales_forecast(
    days=10,
    force_refresh=False  # ⚠️ Load từ database, không tính lại
)

# Truy cập forecast data
for variant_id, forecast_30 in forecast_map_30.items():
    # Tốc độ bán 30 ngày
    sales_rate_30 = forecast_30.sales_rate  # Số lượng/ngày
    
    # Tổng lượt bán 30 ngày hiện tại
    total_sold_30 = forecast_30.total_sold
    
    # Tổng lượt bán 30 ngày cùng kỳ trước
    total_sold_previous_30 = forecast_30.total_sold_previous_period
    
    # % tăng trưởng so với cùng kỳ
    growth_percentage_30 = forecast_30.growth_percentage
    
    # Doanh thu (chỉ có khi period_days=30 hoặc 10)
    revenue_30 = forecast_30.revenue
    
    # ABC Analysis (chỉ có khi period_days=30)
    abc_category = forecast_30.abc_category  # "A", "B", hoặc "C"
    abc_rank = forecast_30.abc_rank  # Thứ hạng trong nhóm
    revenue_percentage = forecast_30.revenue_percentage  # % doanh thu
    cumulative_percentage = forecast_30.cumulative_percentage  # % tích lũy
    
    # Priority Score (chỉ có khi period_days=30)
    priority_score = forecast_30.priority_score  # 0-10
    velocity_stability_score = forecast_30.velocity_stability_score  # 0-12
    velocity_score = forecast_30.velocity_score  # 2, 4, 6, 8, 10
    stability_bonus = forecast_30.stability_bonus  # 0, 1, 2
    asp_score = forecast_30.asp_score  # 2, 4, 6, 8, 10
    revenue_contribution_score = forecast_30.revenue_contribution_score  # 4, 7, 10

# Tương tự cho 10 ngày
for variant_id, forecast_10 in forecast_map_10.items():
    sales_rate_10 = forecast_10.sales_rate
    total_sold_10 = forecast_10.total_sold
    total_sold_previous_10 = forecast_10.total_sold_previous_period
    growth_percentage_10 = forecast_10.growth_percentage
    revenue_10 = forecast_10.revenue
```

#### Các Trường Dữ Liệu Sales Forecast:

**SalesForecastDTO** (`products/services/dto.py`):
- `total_sold` (int): Tổng lượt bán kỳ hiện tại (x ngày gần nhất)
- `total_sold_previous_period` (int): Tổng lượt bán kỳ trước (x ngày cùng kỳ)
- `period_days` (int): Số ngày tính toán (7, 10, 30)
- `sales_rate` (float): Tốc độ bán (số lượng/ngày) = total_sold / period_days
- `growth_percentage` (float): % tăng trưởng so với kỳ trước
- `revenue` (float): Tổng doanh thu (chỉ có khi period_days=30 hoặc 10)
- `revenue_percentage` (float): % doanh thu trên tổng (chỉ có khi period_days=30)
- `cumulative_percentage` (float): % tích lũy cộng dồn (chỉ có khi period_days=30)
- `abc_category` (str): "A", "B", hoặc "C" (chỉ có khi period_days=30)
- `abc_rank` (int): Thứ hạng trong nhóm (chỉ có khi period_days=30)
- `priority_score` (float): Điểm ưu tiên 0-10 (chỉ có khi period_days=30)
- `velocity_stability_score` (float): 0-12 (chỉ có khi period_days=30)
- `velocity_score` (int): 2, 4, 6, 8, 10 (chỉ có khi period_days=30)
- `stability_bonus` (int): 0, 1, 2 (chỉ có khi period_days=30)
- `asp_score` (int): 2, 4, 6, 8, 10 (chỉ có khi period_days=30)
- `revenue_contribution_score` (int): 4, 7, 10 (chỉ có khi period_days=30)

## Helper Functions

### Parse Metadata từ Description

```python
from products.services.metadata_helper import extract_gdp_metadata

# Extract metadata từ product.description
description = product.description  # String chứa [GDP_META]...[/GDP_META]
metadata, original_desc = extract_gdp_metadata(description)

# metadata là ProductMetadataDTO hoặc None
if metadata:
    # Truy cập variants metadata
    for variant_meta in metadata.variants:
        variant_id = variant_meta.id
        price_tq = variant_meta.price_tq
        box_info = variant_meta.box_info
        sales_forecast = variant_meta.sales_forecast
```

### Inject Metadata vào Description

```python
from products.services.metadata_helper import inject_gdp_metadata

# Inject metadata vào description
new_description = inject_gdp_metadata(original_desc, metadata)
# new_description sẽ chứa [GDP_META]...[/GDP_META]
```

## Lưu Ý Quan Trọng

### 1. Limit Mỗi Request

- **Limit tối đa: 250 products/request**
- Không được vượt quá 250 để tránh lỗi API
- Code tham khảo: `products/services/sales_forecast_service.py` - `_get_all_products()`

### 2. Chiến Lược Đọc Dữ Liệu

**✅ ĐÚNG:**
```python
# Đọc toàn bộ products một lần
all_products = []
page = 1
limit = 250
while True:
    products = fetch_products(page=page, limit=limit)
    all_products.extend(products)
    if len(products) < limit:
        break
    page += 1

# Lưu vào JSON hoặc memory
save_to_json(all_products)

# Load từ JSON khi cần
products = load_from_json()
for product in products:
    # Truy cập variant metadata
    variant_meta = product.variants[0].gdp_metadata
```

**❌ SAI:**
```python
# KHÔNG request từng variant một
for variant_id in variant_ids:
    variant = fetch_variant(variant_id)  # ❌ Quá nhiều requests
    metadata = fetch_metadata(variant_id)  # ❌ Quá nhiều requests
```

### 3. Cách Lưu Trữ Sales Forecast

Sales forecast được lưu trong:
1. **Database**: Model `VariantSalesForecast` (products/models.py)
2. **GDP Meta**: Trong `variant.sales_forecast` (optional, có thể không có)

**Khi load:**
- `force_refresh=False`: Load từ Database (nhanh)
- `force_refresh=True`: Tính toán lại từ orders (chậm, chỉ dùng khi cần refresh)

### 4. Cấu Trúc Dữ Liệu

- **Product Level**: Metadata chung cho product (videos, nhanphu_info, warranty_months)
- **Variant Level**: Metadata riêng cho từng variant (price_tq, box_info, sales_forecast)
- Mỗi variant có một entry trong `metadata.variants[]` với `id` là variant_id

## Files Tham Khảo

1. **DTOs**: `products/services/dto.py`
   - `ProductMetadataDTO`: Metadata của product
   - `VariantMetadataDTO`: Metadata của variant
   - `BoxInfoDTO`: Thông tin thùng
   - `PackedInfoDTO`: Thông tin đóng gói
   - `SalesForecastDTO`: Dữ liệu dự báo bán hàng

2. **Helper Functions**: `products/services/metadata_helper.py`
   - `extract_gdp_metadata()`: Parse metadata từ description
   - `inject_gdp_metadata()`: Inject metadata vào description

3. **Service**: `products/services/sapo_product_service.py`
   - `SapoProductService.get_product()`: Lấy product với metadata
   - `SapoProductService.list_products()`: List products với metadata

4. **Sales Forecast Service**: `products/services/sales_forecast_service.py`
   - `SalesForecastService.calculate_sales_forecast()`: Tính toán/load forecast
   - `SalesForecastService._get_all_products()`: Lấy tất cả products (limit 250)

5. **Views**: `products/views.py`
   - `variant_list()`: Cách lấy variant metadata (giá TQ, box_info)
   - `sales_forecast_list()`: Cách lấy sales forecast data (30N, 10N, so sánh cùng kỳ)

## Ví Dụ Hoàn Chỉnh

```python
from core.sapo_client import get_sapo_client
from products.services.sapo_product_service import SapoProductService
from products.services.sales_forecast_service import SalesForecastService

# 1. Khởi tạo services
sapo_client = get_sapo_client()
product_service = SapoProductService(sapo_client)
forecast_service = SalesForecastService(sapo_client)

# 2. Lấy tất cả products (limit 250/request)
all_products = []
page = 1
limit = 250

while True:
    response = sapo_client.core.list_products_raw(
        page=page,
        limit=limit,
        status="active"
    )
    products_data = response.get("products", [])
    
    if not products_data:
        break
    
    # Parse products với metadata
    for product_data in products_data:
        product_id = product_data.get("id")
        product = product_service.get_product(product_id)
        if product:
            all_products.append(product)
    
    if len(products_data) < limit:
        break
    
    page += 1

# 3. Load sales forecast từ database
forecast_map_30, _, _ = forecast_service.calculate_sales_forecast(
    days=30,
    force_refresh=False
)

forecast_map_10, _, _ = forecast_service.calculate_sales_forecast(
    days=10,
    force_refresh=False
)

# 4. Truy cập dữ liệu
for product in all_products:
    for variant in product.variants:
        variant_id = variant.id
        variant_meta = variant.gdp_metadata
        
        if variant_meta:
            # Giá mua hàng TQ
            price_tq = variant_meta.price_tq
            
            # Thông tin thùng
            if variant_meta.box_info:
                full_box = variant_meta.box_info.full_box
                box_size = f"{variant_meta.box_info.length_cm}x{variant_meta.box_info.width_cm}x{variant_meta.box_info.height_cm}"
            
            # Sales forecast 30 ngày
            forecast_30 = forecast_map_30.get(variant_id)
            if forecast_30:
                sales_rate_30 = forecast_30.sales_rate
                growth_30 = forecast_30.growth_percentage
                abc_category = forecast_30.abc_category
            
            # Sales forecast 10 ngày
            forecast_10 = forecast_map_10.get(variant_id)
            if forecast_10:
                sales_rate_10 = forecast_10.sales_rate
                growth_10 = forecast_10.growth_percentage
```

## Tóm Tắt

1. **Lưu trữ**: GDP metadata trong `product.description` với format `[GDP_META]{JSON}[/GDP_META]`
2. **Đọc dữ liệu**: Đọc toàn bộ products một lần (limit 250), lưu vào JSON/memory, load từ đó
3. **Variant metadata**: `variant.gdp_metadata` chứa `price_tq`, `box_info`, `packed_info`, `sku_tq`, etc.
4. **Sales forecast**: Load từ Database (không tính lại), có `forecast_map_30` và `forecast_map_10`
5. **Limit**: Tối đa 250 products/request, không được vượt quá


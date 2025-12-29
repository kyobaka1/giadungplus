# Tài liệu về Giá Vốn (Cost Price) và Price Adjustments trên Sapo API

Tài liệu này mô tả cách hệ thống cũ xử lý giá vốn thông qua Sapo API `price_adjustments`, dựa trên code tham khảo trong `THAMKHAO/`.

## 1. Phân bổ giá vốn - Cách lưu trữ trên Sapo API

### 1.1. Cấu trúc Price Adjustment trên Sapo

Price Adjustment trên Sapo được sử dụng để lưu trữ giá vốn (cost price) cho từng variant. Cấu trúc như sau:

**Endpoint:** `/admin/price_adjustments.json`

**Cấu trúc dữ liệu:**
```json
{
  "price_adjustment": {
    "id": 12345,
    "code": "SUPFINAL",  // Mã định danh (query string để tìm)
    "location_id": 548744,  // ID kho hàng
    "note": "",
    "tags": [],
    "line_items": [
      {
        "product_id": 123456,
        "variant_id": 789012,
        "price": 50000,  // Giá vốn (cost price)
        "product_type": "normal",
        "note": "{\"vid\":789012,\"pid\":123456,\"p\":\"PO001\",\"s\":\"SKU001\",\"gt\":100000,\"s1\":10,\"s2\":5,\"tg\":1.0,\"tv\":5000,\"tn\":2000,\"pu\":50000,\"np\":60000,\"nq\":100,\"date\":\"15/01/2024\",\"op\":45000,\"oq\":50,\"li\":548744,\"rc\":\"REC001\"}"
      }
    ]
  }
}
```

### 1.2. Logic lưu trữ giá vốn

**Tham khảo:** `THAMKHAO/views.py:2776-2863` (hàm `updategiavon`)

**Cách hoạt động:**
1. **Dữ liệu metadata trong `note` field:**
   - Dữ liệu chi tiết về giá vốn được lưu dưới dạng JSON string trong field `note` của mỗi `line_item`
   - Format: JSON string (không có spaces để tiết kiệm dung lượng)
   - Các trường quan trọng:
     - `vid`: variant_id
     - `pid`: product_id
     - `pu`: Giá vốn đã tính toán (price unit - giá vốn trung bình)
     - `np`: Giá mới (new price)
     - `nq`: Số lượng mới (new quantity)
     - `op`: Giá cũ (old price)
     - `oq`: Số lượng cũ (old quantity)
     - `date`: Ngày áp dụng giá vốn (format: "dd/mm/yyyy")
     - `li`: location_id (kho hàng)
     - `rc`: Receipt code

2. **Công thức tính giá vốn trung bình (`pu`):**
   ```python
   pu = (oq * op + nq * np) / (nq + oq)
   ```
   - `oq`: Số lượng tồn kho cũ
   - `op`: Giá vốn cũ
   - `nq`: Số lượng nhập mới
   - `np`: Giá vốn mới
   - `pu`: Giá vốn trung bình sau khi nhập hàng

3. **Query và tìm Price Adjustment:**
   - Sử dụng query parameter `query` với mã code (ví dụ: "SUPFINAL")
   - Nếu chưa có, tạo mới với `POST /price_adjustments.json`
   - Nếu đã có, cập nhật với `PUT /price_adjustments/{id}.json`

### 1.3. Logic sử dụng giá vốn từ Sapo API

**Tham khảo:** `THAMKHAO/functions.py:349-387`

**Cách hoạt động:**
1. Lấy tất cả price adjustments có code "SUPFINAL"
2. Parse dữ liệu từ field `note` (JSON string) thành object
3. Nhóm theo `variant_id` và sắp xếp theo ngày (`date`)
4. Khi cần tìm giá vốn, tìm trong danh sách đã sắp xếp theo thời gian

## 2. Cách lấy giá vốn về cho từng phân loại và tính tỉ lệ

### 2.1. Hàm `get_list_giavon()` - Lấy danh sách giá vốn

**Tham khảo:** `THAMKHAO/functions.py:349-366`

```python
def get_list_giavon():
    LGV = {}
    # Lấy tất cả price adjustments có code "SUPFINAL"
    ALL_PA = js_get_url(
        "https://sisapsan.mysapogo.com/admin/price_adjustments.json?query=SUPFINAL&page=1&limit=250"
    )["price_adjustments"]
    
    # Parse từng line_item
    for PA in ALL_PA:
        for line in PA["line_items"]:
            line['data'] = json.loads(line['note'])  # Parse JSON từ note field
            
            # Nhóm theo variant_id
            if line['variant_id'] not in LGV:
                LGV[line['variant_id']] = []
            LGV[line['variant_id']].append(line['data'])
    
    # Sắp xếp theo ngày (date) cho mỗi variant
    for key in LGV.keys():
        LGV[key] = sorted(
            LGV[key], 
            key=lambda x: datetime.datetime.strptime(x['date'].strip(), "%d/%m/%Y")
        )
    
    return LGV  # Dict: {variant_id: [list of giavon records sorted by date]}
```

**Kết quả:**
- `LGV` là dictionary với key là `variant_id`
- Mỗi value là list các record giá vốn, đã sắp xếp theo ngày tăng dần
- Mỗi record chứa: `pu` (giá vốn), `date` (ngày áp dụng), `li` (location_id), ...

### 2.2. Hàm `find_giavon()` - Tìm giá vốn cho một variant tại thời điểm cụ thể

**Tham khảo:** `THAMKHAO/functions.py:368-387`

```python
def find_giavon(variant_id, created_on, location_id, LGV, line_amount):
    """
    Tìm giá vốn cho variant tại thời điểm created_on.
    
    Args:
        variant_id: ID của variant
        created_on: datetime - thời điểm cần tìm giá vốn
        location_id: ID kho hàng
        LGV: Dictionary từ get_list_giavon()
        line_amount: Giá bán (fallback nếu không tìm thấy)
    
    Returns:
        int: Giá vốn
    """
    flag = 0
    if variant_id in LGV:
        # Tìm trong danh sách đã sắp xếp
        for giavon_item in LGV[variant_id]:
            if giavon_item['li'] == location_id:  # Kiểm tra location_id
                giavon_date = datetime.datetime.strptime(
                    giavon_item['date'].strip(), 
                    "%d/%m/%Y"
                )
                # Tìm giá vốn áp dụng trước thời điểm created_on
                if created_on < giavon_date:
                    giavon = int(giavon_item['pu'])
                    flag = 1
                    break
                else:
                    # Lấy giá vốn mới nhất
                    giavon = int(giavon_item['pu'])
                    flag = 1
    else:
        # Không tìm thấy, dùng fallback: 35% giá bán
        giavon = int(line_amount * 0.35)
    
    if flag == 0:
        # Không tìm thấy, dùng fallback: 35% giá bán
        giavon = int(line_amount * 0.35)
    
    return giavon
```

**Logic tìm giá vốn:**
1. Kiểm tra `variant_id` có trong `LGV` không
2. Lọc theo `location_id` (kho hàng)
3. Tìm giá vốn có `date` gần nhất nhưng không vượt quá `created_on`
4. Nếu không tìm thấy, dùng fallback: 35% của `line_amount` (giá bán)

### 2.3. Tính tỉ lệ giá vốn cho đơn hàng

**Tham khảo:** `THAMKHAO/views.py:2865-2968` (hàm `ptgiavon`)

**Cách tính:**
```python
# Với mỗi đơn hàng
giavonx = 0  # Tổng giá vốn của đơn hàng

for line in order["order_line_items"]:
    # Tính giá bán (sau khi trừ discount)
    line_price = (line['line_amount'] / line["quantity"] - 
                  line['distributed_discount_amount'] / line["quantity"])
    
    # Tìm giá vốn
    giavon = find_giavon(
        line['variant_id'], 
        created_on,  # Thời điểm tạo đơn
        order['location_id'], 
        LGV,
        line_price
    )
    
    # Cộng vào tổng giá vốn
    giavonx += giavon * line['quantity']

# Tính tỉ lệ giá vốn
tile = (giavonx / order['total']) * 100
```

**Kết quả:**
- `tile`: Tỉ lệ giá vốn so với tổng giá trị đơn hàng (%)
- Ví dụ: `tile = 60` nghĩa là giá vốn chiếm 60% giá trị đơn hàng

## 3. Cách tạo Price Adjustments trên Sapo thông qua API

### 3.1. Tạo mới Price Adjustment

**Tham khảo:** `THAMKHAO/views.py:2838-2847`

```python
# Kiểm tra xem đã có price adjustment chưa
TRAVE = js_get_url(
    f"https://sisapsan.mysapogo.com/admin/price_adjustments.json?query={code}"
)

if len(TRAVE["price_adjustments"]) > 0:
    # Đã có, lấy record đầu tiên
    TRAVE = TRAVE["price_adjustments"][0]
else:
    # Chưa có, tạo mới
    TRAVE = {
        "location_id": location_id,
        "code": code,  # Mã định danh (ví dụ: "SUPFINAL")
        "tags": [],
        "note": "",
        "line_items": []
    }
    # POST để tạo mới
    response = loginss.post(
        f"{MAIN_URL}/price_adjustments.json", 
        json={"price_adjustment": TRAVE}
    )
    TRAVE = json.loads(response.text)["price_adjustment"]
```

### 3.2. Cập nhật Price Adjustment với line_items

**Tham khảo:** `THAMKHAO/views.py:2849-2861`

```python
# Chuẩn bị dữ liệu
PD_JSON = {
    "price_adjustment": {
        "code": TRAVE["code"],
        "note": "",
        "line_items": []
    }
}

# Thêm từng line_item
for line in all_lines:
    # Tạo metadata JSON string (không có spaces)
    line_string = json.dumps(line).replace(" ", "", 2000)
    
    # Tạo line_item
    LINE_JSON = {
        "product_id": line['pid'],
        "variant_id": line['vid'],
        "note": line_string,  # Metadata JSON string
        "price": int(line['pu']),  # Giá vốn
        "product_type": "normal"
    }
    
    PD_JSON["price_adjustment"]["line_items"].append(LINE_JSON)

# PUT để cập nhật
rs = loginss.put(
    f"https://sisapsan.mysapogo.com/admin/price_adjustments/{TRAVE['id']}.json",
    json=PD_JSON
)

# Kiểm tra kết quả
if len(rs.text) < 200:
    # Lỗi
    error_message = rs.text
else:
    # Thành công
    success = True
```

### 3.3. Cấu trúc line_item metadata

**Tham khảo:** `THAMKHAO/views.py:2816-2835`

Mỗi `line_item` trong price adjustment cần có metadata trong field `note`:

```python
line_info = {
    'vid': variant_id,
    'pid': product_id,
    'p': po_code,  # Mã đơn nhập hàng
    's': sku,
    'gt': gia_tri,
    's1': so_luong_1,
    's2': so_luong_2,
    'tg': ty_gia,
    'tv': tien_van_chuyen,
    'tn': tien_nhap,
    'pu': price_unit,  # Giá vốn trung bình (đã tính)
    'np': new_price,  # Giá mới
    'nq': new_quantity,  # Số lượng mới
    'date': date_string,  # "dd/mm/yyyy"
    'op': old_price,  # Giá cũ
    'oq': old_quantity,  # Số lượng cũ
    'li': location_id,  # Kho hàng
    'rc': receipt_code,  # Mã phiếu nhập
}
```

## 4. Tóm tắt API Endpoints

### 4.1. Lấy danh sách Price Adjustments
```
GET /admin/price_adjustments.json?query={code}&page={page}&limit={limit}
```

### 4.2. Tạo mới Price Adjustment
```
POST /admin/price_adjustments.json
Body: {
  "price_adjustment": {
    "location_id": 123,
    "code": "SUPFINAL",
    "tags": [],
    "note": "",
    "line_items": []
  }
}
```

### 4.3. Cập nhật Price Adjustment
```
PUT /admin/price_adjustments/{id}.json
Body: {
  "price_adjustment": {
    "code": "SUPFINAL",
    "note": "",
    "line_items": [
      {
        "product_id": 123,
        "variant_id": 456,
        "note": "{...json metadata...}",
        "price": 50000,
        "product_type": "normal"
      }
    ]
  }
}
```

## 5. Lưu ý quan trọng

1. **Query code:** Code "SUPFINAL" được dùng để query tất cả price adjustments liên quan đến giá vốn
2. **Metadata trong note:** Dữ liệu chi tiết được lưu dưới dạng JSON string trong field `note`, không có spaces để tiết kiệm dung lượng
3. **Sắp xếp theo ngày:** Khi lấy giá vốn, cần sắp xếp theo `date` để tìm giá vốn đúng thời điểm
4. **Location_id:** Giá vốn có thể khác nhau giữa các kho hàng, cần kiểm tra `location_id`
5. **Fallback:** Nếu không tìm thấy giá vốn, hệ thống cũ dùng 35% giá bán làm giá vốn mặc định
6. **Pagination:** API có thể trả về nhiều page, cần lặp qua các page để lấy hết dữ liệu

## 6. Ví dụ sử dụng trong code mới

Khi implement trong code mới, có thể tham khảo:

1. **Service layer:** Tạo `PriceAdjustmentService` trong `products/services/`
2. **Repository:** Thêm methods vào `SapoCoreRepository` để gọi API
3. **DTO:** Tạo DTO cho Price Adjustment và Line Item
4. **Helper functions:** 
   - `get_list_giavon()` → Lấy danh sách giá vốn
   - `find_giavon()` → Tìm giá vốn cho variant tại thời điểm cụ thể
   - `calculate_cost_price_ratio()` → Tính tỉ lệ giá vốn cho đơn hàng


## CSKH Feedback – Luồng xử lý & triển khai

Tài liệu này mô tả **toàn bộ luồng làm việc của module Feedback Center**, để khi deploy / debug bạn nắm rõ hệ thống đang làm gì và tại sao có thể chạy lâu.

---

## 1. Tổng quan kiến trúc

- **Model chính**: `cskh.models.Feedback`
  - Key từ Shopee: `comment_id` (duy nhất, `BigIntegerField`, index).
  - Một số field quan trọng:
    - Shopee: `connection_id`, `item_id`, `product_id`, `model_id`, `rating`, `comment`, `images`, `user_name`, `user_portrait`, `submit_time`, `ctime`, `mtime`, `low_rating_reasons`, `can_follow_up`, `follow_up`, `is_hidden`, `status`.
    - Link Sapo: `sapo_order_id`, `sapo_customer_id`, `sapo_product_id`, `sapo_variant_id`.
    - Liên kết Ticket CSKH: `ticket` (FK sang `Ticket`).

- **Service chính**: `cskh/services/feedback_service.py` (`FeedbackService`)
  - Làm 2 việc lớn:
    1. **Legacy**: Sync feedbacks từ **Sapo Marketplace API** (cũ).
    2. **Mới**: Sync feedbacks trực tiếp từ **Shopee API**.
  - Ngoài ra còn:
    - Link feedback với đơn Sapo & variant.
    - Tự động tạo ticket từ bad review.
    - (Tuỳ chọn) Đẩy `user_portrait` lên Sapo `customer.note`.

- **API layer**: `cskh/views_api.py`
  - Endpoint sync: `api_sync_feedbacks` (`/cskh/api/feedback/sync/`).
  - Endpoint reply, tạo ticket, AI gợi ý… không liên quan tới performance sync chính.

- **UI layer** (Django template):
  - `cskh/templates/cskh/feedback/overview.html`
  - `cskh/templates/cskh/feedback/list.html`
  - Cả 2 đều có **nút “Sync từ Shopee API”** gọi vào `api_sync_feedbacks`.

---

## 2. Entry point: API `/cskh/api/feedback/sync/`

File: `cskh/views_api.py`, hàm `api_sync_feedbacks`.

### 2.1. Logic phân nhánh

```python
data = json.loads(request.body)
use_shopee_api = data.get("use_shopee_api", True)
tenant_id = data.get("tenant_id")
```

- **Nhánh Shopee API (mặc định)**:
  - Điều kiện: `use_shopee_api == True` **và** `tenant_id` **không được gửi lên**.
  - Gọi:
    ```python
    result = feedback_service.sync_feedbacks_from_shopee(days=days, page_size=page_size)
    ```

- **Nhánh Sapo MP (legacy)**:
  - Điều kiện: `tenant_id` có giá trị (ví dụ: 1262).
  - Gọi:
    ```python
    result = feedback_service.sync_feedbacks(
        tenant_id=tenant_id,
        connection_ids=connection_ids,
        rating=rating,
        max_feedbacks=max_feedbacks,
        num_threads=num_threads,
    )
    ```

**Kết luận**:  
Nếu body request **không** có `tenant_id` và có `use_shopee_api: true` ⇒ luôn đi vào luồng Shopee API mới.

---

## 3. UI – Cách các nút Sync gọi API

### 3.1. Feedback List – `feedback/list.html`

- Nút ở block `overview`:

```html
<button onclick="syncFeedbacks()"
        class="px-4 py-2 bg-brand text-white rounded-lg hover:bg-red-700 transition text-sm font-semibold">
    🔄 Sync từ Shopee API
</button>
```

- JS gọi API:

```js
const response = await fetch('/cskh/api/feedback/sync/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify({
        // Dùng Shopee API mặc định (không cần tenant_id)
        use_shopee_api: true,
        days: 7,       // Lấy 7 ngày gần nhất
        page_size: 50  // Mỗi lần gọi 50 feedbacks
    })
});
```

⇒ **Luôn ép use_shopee_api = true, không gửi tenant_id ⇒ đi Shopee API.**

### 3.2. Feedback Overview – `feedback/overview.html`

- Nút quick action:

```html
<button onclick="syncFeedbacks()" 
        class="flex-1 px-4 py-2 bg-white border-2 border-brand text-brand rounded-lg hover:bg-brandlight transition text-center text-sm font-semibold">
    🔄 Sync từ Shopee API
</button>
```

- JS:

```js
const response = await fetch("{% url 'cskh:api_sync_feedbacks' %}", {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': ...,
    },
    body: JSON.stringify({
        use_shopee_api: true,
        days: 7,
        page_size: 50
    })
});
```

⇒ Cũng **ép đi luồng Shopee API** giống list.

---

## 4. Luồng Shopee API – `sync_feedbacks_from_shopee`

File: `cskh/services/feedback_service.py`

### 4.1. Bước 1 – Tính khoảng thời gian cần crawl

- Dùng timezone VN:

```python
tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
now_vn = datetime.now(tz_vn)
time_end = int(now_vn.timestamp())
time_start = int((now_vn - timedelta(days=days)).timestamp())
```

⇒ Lấy ratings từ **`days` ngày gần nhất** (default 7) theo timestamp Shopee.

### 4.2. Bước 2 – Lấy danh sách shop

- Hàm: `load_shopee_shops_detail()` từ `core.system_settings`.
- Trả về dict: `{ shop_name: { "shop_connect": connection_id, ...}, ... }`.
- Mỗi entry tương ứng 1 shop Shopee (mapping với Sapo connection).

### 4.3. Bước 3 – Crawl ratings cho từng shop

Vòng lặp theo shop:

1. Lấy `connection_id` từ cấu hình.
2. Khởi tạo `ShopeeClient(shop_key=connection_id)`.
3. Gọi **probe** lần đầu để biết `total`:
   ```python
   probe_response = shopee_client.repo.get_shop_ratings_raw(
       rating_star="5,4,3,2,1",
       time_start=time_start,
       time_end=time_end,
       page_number=1,
       page_size=page_size,
       cursor=0,
       from_page_number=1,
       language="vi"
   )
   total = int(page_info.get("total", 0) or 0)
   total_pages = max(1, math.ceil(total / page_size))
   ```
4. Gọi `crawl_shopee_ratings(...)` để đi qua từng trang:
   - Dùng `cursor` = `last_comment_id` (Shopee yêu cầu).
   - Mỗi vòng:
     - Gọi `get_shop_ratings_raw` với `page_number`, `from_page_number`, `cursor`.
     - Lấy `data["list"]` (danh sách đánh giá).
     - Append vào `all_ratings`.
     - Cập nhật `cursor = last.comment_id`.
5. Sau khi crawl xong 1 shop:
   - Gắn thêm `rating["connection_id"] = connection_id`.
   - Append vào `all_feedbacks` lớn (gộp tất cả shops).

**Log bạn thấy** kiểu:

- `🛍️ Đang xử lý shop: ...`
- `📊 Shop ...: Tổng X đánh giá`
- `📄 Shop ...: Cần crawl Y trang`
- `✅ Shop ...: Đã crawl Z đánh giá`
- `📦 Tổng cộng: 1027 đánh giá từ tất cả shops`

chính là từ đoạn này.

### 4.4. Bước 4 – Xử lý 1027 feedbacks (multi-thread)

Sau khi có `all_feedbacks` (list các dict Shopee), service:

1. Chia thành batches:
   - `num_threads = 10`.
   - `batch_size = len(all_feedbacks) // num_threads` (tối thiểu 1).
   - Tạo list `batches = [(feedback_batch, batch_num), ...]`.
2. Dùng `ThreadPoolExecutor(max_workers=num_threads)`:
   - Submit `process_feedback_batch(feedback_batch, batch_num)` cho từng batch.
   - `as_completed(futures)` để chờ các thread hoàn thành.

Mỗi batch:

```python
for feedback_data in feedback_batch:
    updated = self._process_feedback_from_shopee(feedback_data)
    batch_synced += 1
    if updated:
        batch_updated += 1
```

Và log định kỳ:

- `Thread {batch_num}: Đã xử lý {batch_synced}/{len(batch)} (Tổng: {total_synced}/{len(all_feedbacks)})`
- Cuối mỗi batch: `Thread {batch_num} hoàn thành: ...`

Cuối cùng:

- Tổng hợp counters: `synced`, `updated`, `errors`.
- Log summary:  
  `✅ Hoàn thành sync: {synced} synced, {updated} updated, {errors_len} errors`.

Nếu bạn thấy log **chỉ dừng ở**:

- `📦 Tổng cộng: 1027 đánh giá từ tất cả shops`
- `🔄 Bắt đầu xử lý 1027 feedbacks...`
- `📦 Chia thành 11 batches, mỗi batch ~102 feedbacks`

và **không thấy log Thread...** ⇒ rất có thể bị “treo” trong `_process_feedback_from_shopee` (mỗi item) do gọi thêm API Sapo nặng.

---

## 5. `_process_feedback_from_shopee` – Chi tiết & tối ưu

Hàm: `FeedbackService._process_feedback_from_shopee`.

### 5.1. Map dữ liệu Shopee → model

- Đầu vào: `feedback_data` (1 dict từ Shopee).
- Lấy `comment_id`, `connection_id`, `item_id`, `product_id`, `order_sn`, `user_name`, `user_portrait`, `rating_star`, `comment`, `images`, `ctime`, `mtime`, `submit_time`, `low_rating_reasons`, v.v.
- `get_or_create` theo `comment_id`:
  - Nếu **chưa tồn tại**:
    - Tạo `Feedback` mới với toàn bộ `defaults` map từ Shopee.
  - Nếu **đã tồn tại**:
    - So sánh các field quan trọng (`rating`, `comment`, `reply`, `user_portrait`…) và update nếu thay đổi.

### 5.2. Link Sapo order / product / variant

- Sau khi tạo/cập nhật xong, gọi:

```python
self._link_sapo_data_from_shopee(feedback, feedback_data)
```

`_link_sapo_data_from_shopee`:

1. Nếu `feedback.channel_order_number` (order_sn) có mà `sapo_order_id` chưa có:
   - Dùng `SapoOrderService`:
     - `raw_order = sapo_client.core.get_order_by_reference_number(order_sn)`
     - `order = order_service.get_order_by_reference(order_sn)` (trả về `OrderDTO`).
   - Gắn: `feedback.sapo_order_id = order.id`, `feedback.sapo_customer_id = order.customer_id`.
2. Nếu có `feedback.item_id`:
   - Gọi `_find_variant_ids_from_order(raw_order, item_id, connection_id)`:
     - Duyệt `line_items` / `order_line_items` trong raw order.
     - Tìm `variant_id` match trực tiếp với `item_id` hoặc qua `gdp_metadata.shopee_connections`.
   - Gắn `sapo_variant_id`, `sapo_product_id` cho feedback (qua `get_variant_raw`).

Tất cả bước này gọi qua Sapo, nhưng:

- Chỉ chạy **khi đã có order_sn**.
- Đã có try/except + log warning, không chặn toàn bộ sync nếu lỗi.

### 5.3. Push `user_portrait` lên Sapo customer (đã được GIẢM TẢI)

Trước khi tối ưu, mỗi feedback có `user_portrait` + `sapo_customer_id` sẽ:

1. `CustomerService.get_customer(...)` (Sapo Core API).
2. Đọc `customer.note` (string).
3. Parse JSON, gắn thêm `"user_portrait": "..."`
4. `update_customer_info(customer_id, note=...)` (Sapo update API).

Điều này rất nặng khi có **hàng trăm feedback** trong một lần sync.

**ĐÃ TỐI ƯU**:

- Trong `_process_feedback_from_shopee` hiện tại:

```python
try:
    if (
        os.getenv("CSKH_PUSH_USER_PORTRAIT", "0") == "1"
        and feedback.user_portrait
        and feedback.sapo_customer_id
    ):
        self._push_user_portrait_to_customer(feedback)
except Exception as e:
    logger.warning(
        f"Error pushing user_portrait to customer {feedback.sapo_customer_id}: {e}"
    )
```

- Mặc định **CSKH_PUSH_USER_PORTRAIT = "0"** ⇒ KHÔNG gọi `_push_user_portrait_to_customer` trong sync Shopee.
- Kết quả:
  - Sync Shopee chỉ tạo/cập nhật `Feedback` + link order/variant.
  - Không còn spam call Sapo update customer, giảm rất nhiều thời gian chờ / nguy cơ “treo”.
- Nếu cần job riêng để cập nhật avatar khách hàng, có thể:
  - Chạy một script management command riêng, hoặc
  - Chạy `runserver`/gunicorn với env `CSKH_PUSH_USER_PORTRAIT=1` chỉ cho job đó.

---

## 6. Luồng Sapo Marketplace (Legacy) – `sync_feedbacks`

Chỉ tóm tắt ngắn, vì hiện tại UI mới **không** gọi luồng này nữa (trừ khi bạn dùng script/tools cũ).

1. Khởi tạo cấu hình:
   - `tenant_id`
   - `connection_ids` (chuỗi shop IDs)
   - `rating` (lọc theo sao)
   - `limit_per_page` (mặc định 250)
   - `max_feedbacks` (mặc định 5000)
   - `num_threads` (mặc định 25)
2. Đọc `log_feedback.log` để biết `last_page` ⇒ có thể **tiếp tục từ page đang dở**.
3. Vòng `while` theo `page`:
   - Gọi `_fetch_feedbacks_with_retry`:
     - Dùng `mp_repo.list_feedbacks_raw(...)`.
     - Retry tối đa 5 lần, delay 3s.
   - Lưu metadata:
     - `metadata.total`, `metadata.page`, `metadata.limit`.
   - Append vào `all_feedbacks`, tăng `feedbacks_fetched_this_run`.
   - Ghi `last_page` vào `log_feedback.log`.
   - Dừng nếu:
     - Hết data.
     - Đạt `max_feedbacks` (5000).
     - Hết trang (`current_page >= total_pages`).
4. Sau đó xử lý `all_feedbacks` bằng `_process_feedback` (luồng cũ Sapo MP) với multi-thread tương tự Shopee.

**Log đặc trưng** của luồng này:  
`[FeedbackService] 📊 Metadata: total=..., page=..., limit=..., fetched=...`  
`[FeedbackService] 📄 Đang fetch page ... với limit=250...`  
`[SapoMarketplaceRepo] Request limit=250 but API returned limit=15 in metadata`

---

## 7. Migration & cột `comment_id`

- Mục tiêu: dùng `comment_id` (Shopee) làm key chính thay cho các legacy ID.

### 7.1. Migrations liên quan

- `0014_add_shopee_fields_to_feedback.py`
  - Migration thủ công cho SQLite:
    - Dùng `PRAGMA table_info(cskh_feedback)` để xem cột hiện có.
    - `ALTER TABLE ... ADD COLUMN ...` cho các field Shopee (`comment_id`, `product_id`, `model_id`, `user_portrait`, `is_hidden`, `can_follow_up`, `low_rating_reasons`, `ctime`, `mtime`, `submit_time`, v.v.) **nếu thiếu**.
    - Tạo index cho `comment_id` nếu chưa có.

- `0015_feedback_can_follow_up_feedback_comment_id_and_more.py`
  - Được chỉnh lại để:
    1. `ensure_columns_exist`: đảm bảo mọi cột (kể cả `comment_id`) đã tồn tại trong DB (an toàn cho SQLite).
    2. `populate_comment_id`: 
       - Với bản ghi cũ thiếu `comment_id`, thử dùng `feedback_id` hoặc `cmt_id` để lấp.
       - Nếu không có, generate `comment_id` âm (để không đụng giá trị Shopee thật).
    3. `AlterField` + `AddIndex` để đồng bộ state Django cho `comment_id` (unique, indexed) mà không cố gắng `ALTER TABLE` lần nữa trên cột đã được thêm bằng SQL thô.

### 7.2. Trường hợp lỗi thường gặp

- `OperationalError: no such column: cskh_feedback.comment_id`
  - Xảy ra khi:
    - DB cũ không có cột `comment_id`.
    - Migration 0014/0015 chưa chạy hết hoặc fail giữa chừng.
  - Cách xử lý:
    - Đảm bảo đã chạy:
      - `python manage.py migrate cskh`
    - Nếu vẫn báo không có cột:
      - Kiểm tra `PRAGMA table_info(cskh_feedback)` để xác nhận schema thực tế.
      - Có thể cần script riêng hoặc điều chỉnh migration (như đã làm) để `ALTER TABLE` an toàn cho SQLite.

---

## 8. Gợi ý debug khi thấy sync chạy lâu / đứng

1. **Xác định đang ở luồng nào**:
   - Shopee API:
     - Log có shop name, `Tổng X đánh giá trong 7 ngày`, `Cần crawl Y trang`, `Tổng cộng: N đánh giá từ tất cả shops`.
   - Sapo MP:
     - Log có `tenant_id`, `max_feedbacks=5000`, `SapoMarketplaceRepo`, `limit=250 but API returned limit=15`.

2. **Theo dõi log sau dòng**:
   - `📦 Tổng cộng: N đánh giá từ tất cả shops`
   - `🔄 Bắt đầu xử lý N feedbacks...`
   - `📦 Chia thành X batches, mỗi batch ~Y feedbacks`

   Nếu **không thấy**:
   - `Thread 1: Đã xử lý ...`
   - `Thread ... hoàn thành ...`
   - `✅ Hoàn thành sync ...`

   ⇒ Có thể đang “kẹt” ở xử lý từng feedback.

3. **Kiểm tra `_process_feedback_from_shopee`**:
   - Hiện tại đã:
     - Tắt `user_portrait` push mặc định (qua env).
     - Bọc `try/except` quanh `_push_user_portrait_to_customer`.
   - Nếu vẫn chậm:
     - Tạm tắt `_link_sapo_data_from_shopee` (để test) xem tốc độ cải thiện không.

4. **Kiểm tra network tới Shopee/Sapo**:
   - Nếu API Sapo/ Shopee timeout hoặc trả chậm, multi-thread vẫn phải chờ.
   - Có thể giảm `num_threads` hoặc thêm timeout ở client nếu cần.

---

## 9. Tóm tắt các điểm “nhạy” về hiệu năng

- **Shopee API sync**:
  - Crawl nhiều shop × nhiều trang = nhiều request Shopee.
  - Sau khi crawl, xử lý từng feedback:
    - Ghi DB (`get_or_create`, `save`).
    - (Có thể) gọi Sapo: get order, get variant, v.v.
  - Đã tắt push `user_portrait` mặc định để tránh hàng trăm update khách hàng trong một lần sync.

- **Sapo MP sync (legacy)**:
  - Dùng nhiều thread (25) + mỗi page 250 items + tối đa 5000 feedbacks/lần.
  - Phù hợp cho sync one-shot / batch riêng, **không nên** dùng trong UI thường xuyên.

Với tài liệu này, bạn có thể lần theo từng bước log để xem sync đang dừng ở phần **crawl Shopee**, **chia batch**, hay **xử lý từng feedback / gọi Sapo** và quyết định tối ưu thêm (ví dụ: giảm số API gọi Sapo trong luồng sync, hoặc tách thành job riêng).  



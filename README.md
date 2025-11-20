# 📦 GIA DỤNG PLUS - HỆ THỐNG QUẢN LÝ BÁN HÀNG & KHO

> **Hệ thống quản lý tích hợp E-commerce, Kho vận, và Chăm sóc khách hàng**

## 🏗️ Tổng quan kiến trúc

**Gia Dụng Plus** là một hệ thống Django hoàn chỉnh được thiết kế để quản lý toàn bộ quy trình bán hàng từ A-Z, từ nhập kho, quản lý sản phẩm, đến đơn hàng trên các sàn TMĐT (Shopee, Lazada, Tiki, TikTok) và chăm sóc khách hàng.

### 📊 Công nghệ sử dụng

- **Backend**: Django 4.1.4 + Django REST Framework
- **Database**: SQLite3
- **Frontend**: HTML, JavaScript (vanilla), CSS
- **Web Server**: Django development server + SSL support (django-sslserver)
- **Static Files**: WhiteNoise
- **Browser Automation**: Selenium + Selenium Wire
- **AI Integration**: OpenAI API
- **Reporting**: PDF (ReportLab, FPDF, PyPDF2), Excel (openpyxl, xlsxwriter)
- **Barcode/QR**: python-barcode, qrcode
- **External APIs**: Shopee API, Sapo API, Google Sheets (gspread)

## 🗂️ Cấu trúc thư mục

```
d:\APP\
├── GIADUNGPLUS/          # Django project settings
│   ├── settings.py       # Cấu hình chính
│   ├── urls.py          # URL routing chính
│   └── middleware/      # Custom middleware
│
├── core/                 # Core app - Tích hợp API & Settings
│   ├── shopee_client.py # Shopee API client
│   ├── system_settings.py # Cấu hình hệ thống (Sapo, Shopee, Kho)
│   ├── sapo_client/     # Sapo ERP integration
│   └── services/        # Business logic services
│
├── orders/              # Quản lý đơn hàng
│   ├── management/      # Django management commands
│   └── services/        # Order processing services
│
├── kho/                 # Quản lý kho hàng
│   ├── templates/kho/   # Templates cho kho
│   ├── views/          # Views xử lý kho
│   └── middleware.py    # Kho switcher middleware (HN/HCM)
│
├── quantri/             # Quản trị & Kinh doanh
│   ├── models.py        # Models: Order, Product, Purchase_Order, etc.
│   └── templates/       # 80+ templates cho quản trị
│       ├── kd_*.html    # Templates kinh doanh
│       ├── kho_*.html   # Templates kho
│       └── mkt_*.html   # Templates marketing
│
├── marketing/           # Marketing & Content
│   └── views.py
│
├── cskh/               # Chăm sóc khách hàng (CSKH)
│   └── views.py
│
├── service/            # Dịch vụ bổ sung
│   └── views.py
│
├── assets/             # Static files (CSS, JS, images)
├── logs/               # Logs & temp files
│   ├── shopee_shops.json  # Cấu hình các shop Shopee
│   ├── raw_cookie/     # Shopee cookies
│   ├── print-cover/    # PDF vận đơn
│   └── bill/           # Hóa đơn
│
├── GHOSTSCRIPT/        # Ghostscript library (PDF processing)
├── db.sqlite3          # SQLite database
└── manage.py           # Django management script
```

## 📱 Modules chính

### 1. 🛒 **CORE** - Tích hợp & Cấu hình hệ thống

**Chức năng:**
- Tích hợp Shopee API (lấy đơn, in vận đơn, tìm vị trí hàng)
- Tích hợp Sapo ERP (quản lý đơn hàng, khách hàng, sản phẩm)
- Quản lý cấu hình hệ thống (kho, shop, địa chỉ lấy hàng)

**File quan trọng:**
- `shopee_client.py`: ShopeeClient class - Xử lý tất cả API Shopee
  - Switch shop động
  - Load headers từ cookie file
  - Tìm vị trí hàng (pickup), in bill, restart shipment
- `system_settings.py`: Cấu hình SAPO, Shopee shops, warehouse location IDs

**Shopee Integration:**
```python
# Khởi tạo client theo shop
client = ShopeeClient("giadungplus_official")  # hoặc connection_id

# Đổi shop
client.switch_shop("phaledo")

# Get order ID từ order serial number
shopee_order_id = client._get_shopee_order_id("210707ABC123")
```

### 2. 📦 **KHO** - Quản lý kho vận

**Chức năng:**
- Quản lý 2 kho: **KHO_GELEXIMCO** (Hà Nội - ID: 241737) & **KHO_TOKY** (HCM - ID: 548744)
- Quy trình đóng gói (packing), phân hàng, bàn giao
- In tem barcode, QR code thanh toán
- Quản lý pickup, vận đơn
- Thống kê theo ngày, báo cáo kho

**Templates chính:**
- `kho_start.html` - Dashboard kho
- `kho_packing.html` - Đóng gói hàng
- `kho_phanhang.html` - Phân hàng
- `kho_pickup.html` - Quản lý pickup Shopee
- `kho_bangiao.html` - Bàn giao đơn vị vận chuyển
- `kho_thongke.html` - Thống kê kho
- `kho_scanpacking.html` - Scan barcode đóng gói

**Middleware:**
- `KhoSwitcherMiddleware` - Tự động chuyển kho theo HOME_PARAM (HN/HCM)

### 3. 🛍️ **QUANTRI** - Quản trị & Kinh doanh

**Chức năng:**
- Quản lý sản phẩm, giá vốn, thông tin nhập khẩu
- Quản lý đơn nhập hàng từ Trung Quốc
- Xử lý đánh giá sản phẩm (Review automation với AI)
- Quản lý Q&A, nội dung sản phẩm
- Bảng báo giá, giá sỉ, giá lẻ

**Models quan trọng:**

**Templates đặc biệt:**

#### 📝 Review Management (AI-powered)
- `kd_repall.html` - Quản lý đánh giá tổng hợp
  - **Bước 1**: Select Name - Lấy danh sách khách hàng cần rep
  - **Bước 2**: Xuất file JSON cho ChatGPT AI tạo nội dung rep
  - Upload file AI trả về và gửi lên Shopee
  
- `kd_repauto.html` - Tạo đánh giá tự động
- `kd_tenkhach.html` - Update giới tính & tên khách
  
**Loading Logic:**
```javascript
// kd_repall.html - JavaScript loading pattern
function generateName() {
    showLoading('nameLoading');
    fetch(`/quantri/kd_repauto?make_name=ok&soluong=${soluong}&shop_name=${shop_name}`)
        .then(res => res.json())
        .then(data => showNameTable(data))
        .catch(error => showError(error))
        .finally(() => hideLoading('nameLoading'));
}

function generateReview() {
    // Xuất file JSON để send cho AI
    fetch(`/quantri/kd_repauto?makerep=ok`)
        .then(res => res.json())
        .then(data => {
            // Download link: /static/openai/new-comment.json
        });
}

function sendShopee() {
    // Gửi đánh giá lên Shopee
    fetch(`/quantri/kd_repauto?send_shopee=ok`)
        .then(res => res.json())
        .then(data => console.log('Success'));
}
```

#### 📦 Sản phẩm & Giá
- `kd_sanpham.html` - Quản lý sản phẩm & giá bán
- `kd_giaovan.html` - Tính giá vốn
- `kd_giasi.html` - Giá sỉ
- `kd_giale.html` - Giá lẻ
- `kd_bangbaogia.html` - Bảng báo giá

#### 📋 Orders & Tickets
- `kd_ticketprocess.html` - Xử lý ticket khách hàng (CSKH)
- `kd_showdon.html` - Hiển thị chi tiết đơn hàng

### 4. 📢 **MARKETING** - Marketing & Content

**Chức năng:**
- Copy ảnh sản phẩm từ Shopee
- Quản lý danh sách sản phẩm marketing
- Hướng content, copywriting

**Templates:**
- `mkt_listproduct.html` - Danh sách sản phẩm
- `mkt_copyanhshopee.html` - Copy ảnh từ Shopee
- `mkt_huongcontent.html` - Hướng dẫn content

### 5. 💬 **CSKH** - Chăm sóc khách hàng

**Chức năng:**
- Xử lý khiếu nại, đổi trả
- Hỗ trợ khách hàng qua các kênh
- Ticket system

### 6. 🔧 **SERVICE** - Dịch vụ bổ sung

**Chức năng:**
- Các dịch vụ hỗ trợ khác
- Utils và helpers

## 🔐 Authentication & Middleware

### Middleware Stack:
1. **SecurityMiddleware** - Django security
2. **SessionMiddleware** - Session management
3. **CsrfViewMiddleware** - CSRF protection
4. **AuthenticationMiddleware** - User authentication
5. **PortRedirectMiddleware** (Custom) - Port redirect logic
6. **KhoSwitcherMiddleware** (Custom) - Warehouse switcher (HN/HCM)

### Login Configuration:
```python
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/kho/"
LOGOUT_REDIRECT_URL = "login"
```

## 🌐 API Endpoints & Integration

### Shopee API
**Base URL**: `https://banhang.shopee.vn/api/v3`

**Key Endpoints sử dụng:**
- `/order/get_order_list_search_bar_hint` - Tìm order_id theo order_sn
- `/order/get_package` - Lấy thông tin package
- `/shipment/get_pickup` - Lấy thông tin pickup
- `/shipment/update_shipment_group_info` - Update thông tin shipment

**Authentication:** Cookie-based (lưu trong `logs/raw_cookie/`)

### Sapo API
**Config:**
```python
SAPO_BASIC = {
    'MAIN_URL': 'https://sisapsan.mysapogo.com/admin',
    'USERNAME': '0988700162',
    'PASSWORD': 'giadungPlus2@@4'
}
```

**Chức năng:**
- Đồng bộ đơn hàng
- Quản lý inventory
- Customer management

### Internal APIs (Django REST Framework)

**Pattern:**
```
/quantri/kd_repauto?action=value
```

**Actions:**
- `make_name=ok` - Generate customer names
- `makerep=ok` - Generate review content
- `send_shopee=ok` - Send reviews to Shopee
- `update=1&cmt_id=xxx` - Update review reply

## 📂 Data Flow

### Order Processing Flow:
```
1. Đơn hàng từ Shopee/Lazada/Tiki
   ↓
2. Sync vào Sapo ERP (core.sapo_client)
   ↓
3. Import vào DB (quantri.Order model)
   ↓
4. Xử lý trong KHO module
   ↓ 
5. Packing → Print → Pickup → Bàn giao ĐVVC
   ↓
6. Đối soát (ketoan)
```

### Review AI Workflow:
```
1. Lấy danh sách đánh giá cần rep (kd_repall.html)
   ↓
2. Select Name → Generate full_name, gender, short_name
   ↓
3. Export JSON file → Send to ChatGPT AI
   ↓
4. AI trả về JSON với suggested replies
   ↓
5. Upload file → Review & Edit
   ↓
6. Send to Shopee API
```

## 🗃️ Database Schema

### Channel Mapping:
```python
channel_map = {
    1880152: 'Shopee',
    1880147: 'Facebook', 
    1880146: 'Website',
    1880148: 'Zalo',
    1880149: 'Lazada',
    1880150: 'Tiki',
    1880151: 'Pos',
    6510687: 'Tiktok',
    7239422: 'CSKH',
    4893087: 'Sỉ / Đại Lý',
    4864539: 'Bồi hoàn',
    4339735: 'Đổi trả'
}
```

### Warehouse IDs:
```python
KHO_GELEXIMCO = 241737  # Hà Nội
KHO_TOKY = 548744       # HCM
```

## 🚀 Cài đặt & Chạy

### Requirements:
```bash
pip install -r rq.txt
```

### Khởi chạy:
```bash
# Development server
python manage.py runserver

# SSL server (HTTPS)
python manage.py runsslserver

# With custom HOME parameter
python manage.py runserver --home=HN   # Chạy cho kho HN
python manage.py runserver --home=HCM  # Chạy cho kho HCM
```

### Environment Variables:
```bash
# Sapo Config
SAPO_MAIN_URL=https://sisapsan.mysapogo.com/admin
SAPO_USERNAME=your_username
SAPO_PASSWORD=your_password

# System Config
GDPLUS_HOME_PARAM=HN  # HN hoặc HCM hoặc CSKH
GDPLUS_HOATOC_HN_ON=1
GDPLUS_HOATOC_HCM_ON=1
```

### Shopee Shops Config:
File `logs/shopee_shops.json`:
```json
{
  "shops": [
    {
      "name": "giadungplus_official",
      "shop_connect": 10925,
      "seller_shop_id": 123456,
      "address_geleximco": 29719283,
      "address_toky": 200025624,
      "headers_file": "logs/raw_cookie/giadungplus_cookie.txt"
    }
  ]
}
```

## 📝 Workflows quan trọng

### 1. In vận đơn Shopee

```python
from core.shopee_client import ShopeeClient

# Khởi tạo client
client = ShopeeClient("giadungplus_official")

# Lấy order ID
order_id = client._get_shopee_order_id("210707ABC123")

# Lấy package info
client._get_packed_list()

# Restart ship (tìm tài xế mới)
client._restart_express_shipping()
```

### 2. Đồng bộ đơn hàng từ Sapo

```python
from core.sapo_client.client import SapoClient

sapo = SapoClient()
sapo.ensure_core_login()

# Lấy đơn hàng
orders = sapo.core_get_orders(limit=100)

# Import vào DB
for order_data in orders:
    order = Order()
    order.load_from(order_data)
    order.save()
```

### 3. Quy trình đóng gói

1. Vào `kho_packing.html`
2. Scan barcode đơn hàng
3. Hệ thống check sản phẩm
4. In tem (nếu cần)
5. Đánh dấu đã đóng gói
6. Chuyển sang bàn giao

## 🛠️ Tools & Utilities

### PDF Generation:
- ReportLab - Tạo PDF phức tạp
- FPDF - PDF đơn giản
- PyPDF2 - Merge/split PDF

### Barcode/QR:
- `python-barcode` - Generate barcode
- `qrcode` - Generate QR code

### Excel:
- `openpyxl` - Read/write .xlsx
- `xlsxwriter` - Write .xlsx advanced
- `xlwt` - Write .xls (legacy)

### Browser Automation:
- Selenium - Web automation
- Selenium Wire - Intercept HTTP requests

## 🔒 Security Notes

⚠️ **Quan trọng:**
- File `system_settings.py` chứa credentials → **KHÔNG** commit lên Git
- Cookie files trong `logs/raw_cookie/` → **KHÔNG** share public
- Database `db.sqlite3` → Backup thường xuyên
- SECRET_KEY trong `settings.py` → Đổi khi deploy production

## 📊 Performance Tips

1. **Database**: Nên chuyển sang PostgreSQL khi scale
2. **Static Files**: Dùng CDN cho production
3. **Caching**: Redis cho session & cache
4. **Background Tasks**: Celery cho xử lý nặng
5. **API Rate Limit**: Shopee API có limit → cần queue

## 🤝 Contributing

Contact: Gia Dụng Plus Team

## 📄 License

Proprietary - Internal use only

---

**Phiên bản**: 1.0  
**Cập nhật lần cuối**: 2025-11-20  
**Django Version**: 4.1.4  
**Python Version**: 3.10+

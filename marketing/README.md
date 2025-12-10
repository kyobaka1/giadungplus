# TikTok Booking Center - Database Schema & Import System

## Tổng quan

Hệ thống **Booking Center** quản lý toàn bộ quy trình booking KOC/KOL cho các chiến dịch marketing trên TikTok và các platform khác. Hệ thống bao gồm:

- **Dashboard / Overview**: Query và báo cáo tổng quan
- **Campaigns**: Quản lý chiến dịch marketing
- **KOC/KOL Database**: Database creators với thông tin chi tiết
- **Bookings**: Quản lý booking với creators
- **Videos & Performance**: Tracking video và metrics
- **Finance & Payment**: Quản lý thanh toán
- **Rules & Templates**: Templates và business rules tự động hóa

## Cấu trúc Database

### Core Models

#### Brand
- `code` (unique): Mã thương hiệu
- `name`: Tên thương hiệu
- `description`: Mô tả

#### Product
- `brand` (FK): Thương hiệu
- `code` (unique within brand): Mã sản phẩm
- `name`: Tên sản phẩm
- `category`: Danh mục
- `sapo_product_id`: ID từ Sapo (optional)
- `shopee_id`: ID từ Shopee (optional)
- `is_active`: Trạng thái hoạt động

### Creator Models

#### Creator
- `name`: Tên creator
- `alias`: Tên gọi khác
- `gender`: Giới tính
- `dob`: Ngày sinh
- `location`: Địa điểm
- `niche`: Lĩnh vực (beauty, fashion, tech, etc.)
- `status`: active/watchlist/blacklist
- `priority_score`: Điểm ưu tiên (1-10)
- `note_internal`: Ghi chú nội bộ

#### CreatorChannel
- `creator` (FK): Creator
- `platform`: tiktok/youtube/instagram/shopee_live/other
- `handle`: Username/handle trên platform
- `external_id`: ID từ platform API
- `follower_count`: Số lượng followers
- `avg_view_10`: Average views trong 10 video gần nhất
- `avg_engagement_rate`: % engagement rate

#### CreatorContact
- `creator` (FK): Creator
- `contact_type`: owner/manager/agency
- `name`: Tên người liên hệ
- `phone`, `zalo`, `email`, `wechat`: Thông tin liên hệ
- `is_primary`: Liên hệ chính

#### CreatorTag, CreatorTagMap
- Tags để phân loại creators
- Many-to-many relationship

#### CreatorNote
- Ghi chú về creator (call, meeting, complaint, etc.)
- Hỗ trợ markdown content

#### CreatorRateCard
- Bảng giá của creator cho các loại deliverable
- `deliverable_type`: video_single/series/live/combo/other
- `price`, `currency`: Giá và loại tiền
- `valid_from`, `valid_to`: Thời gian hiệu lực

### Campaign Models

#### Campaign
- `code` (unique): Mã campaign
- `brand` (FK): Thương hiệu
- `channel`: tiktok/multi
- `objective`: awareness/traffic/sale/launch/clearance
- `start_date`, `end_date`: Thời gian
- `budget_planned`, `budget_actual`: Budget
- `kpi_view`, `kpi_order`, `kpi_revenue`: KPI
- `status`: draft/planned/running/paused/finished/canceled
- `owner` (FK): Người phụ trách

#### CampaignProduct
- `campaign` (FK), `product` (FK)
- `priority`: Độ ưu tiên
- `note`: Ghi chú

#### CampaignCreator
- `campaign` (FK), `creator` (FK)
- `role`: main/supporting/trial
- `note`: Ghi chú

### Booking Models

#### Booking
- `code` (unique): Mã booking
- `campaign` (FK): Campaign
- `creator` (FK): Creator
- `channel` (FK): CreatorChannel (optional)
- `brand` (FK), `product_focus` (FK): Sản phẩm focus
- `booking_type`: video_only/live/combo/barter/affiliate_only
- `brief_summary`: Tóm tắt brief
- `contract_file`: File hợp đồng (URL/text)
- `start_date`, `end_date`: Thời gian
- `total_fee_agreed`, `currency`: Phí thỏa thuận
- `deliverables_count_planned`: Số lượng deliverables
- `status`: negotiating/confirmed/in_progress/completed/canceled
- `internal_note`: Ghi chú nội bộ

#### BookingDeliverable
- `booking` (FK): Booking
- `deliverable_type`: video_feed/video_story/live/series/short/other
- `title`: Tiêu đề
- `script_link`: Link script
- `requirements`: Yêu cầu
- `deadline_shoot`, `deadline_post`: Deadline
- `quantity`: Số lượng
- `fee`: Phí
- `status`: planned/shooting/waiting_approve/scheduled/posted/rejected/canceled

#### BookingStatusHistory
- Lịch sử thay đổi status của booking
- `from_status`, `to_status`: Trạng thái
- `changed_by` (FK): Người thay đổi
- `changed_at`: Thời gian thay đổi

### Video & Performance Models

#### Video
- `booking_deliverable` (FK): Deliverable (optional)
- `booking` (FK): Booking (optional nhưng khuyến nghị)
- `campaign` (FK): Campaign
- `creator` (FK): Creator
- `channel`: tiktok/other
- `platform_video_id`: ID từ platform
- `url`: URL video
- `title`: Tiêu đề
- `post_date`: Ngày đăng
- `thumbnail_url`: URL thumbnail
- `status`: posted/deleted/hidden/pending

#### VideoMetricSnapshot
- Snapshot metrics của video tại một thời điểm
- `video` (FK): Video
- `snapshot_time`: Thời điểm snapshot
- `view_count`, `like_count`, `comment_count`, `share_count`, `save_count`: Metrics
- `engagement_rate`: % engagement
- `data_raw`: Raw data (JSON)

### Tracking & Attribution Models

#### TrackingAsset
- Tracking asset (voucher code, link, referral code)
- `campaign` (FK): Campaign
- `booking` (FK): Booking (optional)
- `creator` (FK): Creator (optional)
- `code_type`: voucher/link/referral_code
- `code_value`: Giá trị code
- `platform`: tiktok_shop/web/shopee/other
- `target_url`: URL đích
- `is_active`: Trạng thái hoạt động

#### TrackingConversion
- Conversion từ tracking asset
- `tracking_asset` (FK): Tracking asset
- `order_code`: Mã đơn hàng
- `order_id_external`: ID đơn hàng từ platform
- `order_date`: Ngày đơn hàng
- `revenue`, `currency`: Doanh thu
- `source_platform`: Platform nguồn
- `product` (FK): Sản phẩm (optional)
- `quantity`: Số lượng
- `data_raw`: Raw data (JSON)

### Finance & Payment Models

#### Payment
- Thanh toán cho creator
- `booking` (FK): Booking
- `creator` (FK): Creator
- `campaign` (FK): Campaign
- `amount`, `currency`: Số tiền và loại tiền
- `exchange_rate`: Tỷ giá (optional)
- `amount_vnd`: Số tiền VND (computed)
- `payment_date`: Ngày thanh toán
- `payment_method`: bank_transfer/cash/other
- `status`: planned/pending/paid/canceled
- `invoice_number`: Số hóa đơn (optional)
- `note`: Ghi chú
- `created_by` (FK): Người tạo

### Rules & Templates Models

#### Template
- Templates cho brief, chat message, email, contract, etc.
- `name`: Tên template
- `template_type`: brief/chat_message/email/contract/internal_note
- `channel`: tiktok/general
- `content`: Nội dung (markdown/text)
- `variables`: Available variables (JSON)
- `is_active`: Trạng thái hoạt động

#### Rule
- Business rules để tự động hóa
- `name`: Tên rule
- `description`: Mô tả
- `scope`: campaign/booking/video/finance/creator
- `condition_json`: Condition logic (JSON)
- `action_json`: Action to execute (JSON)
- `is_active`: Trạng thái hoạt động

#### RuleLog
- Log khi rule được trigger
- `rule` (FK): Rule
- `target_type`: campaign/booking/video/creator/payment
- `target_id`: ID target (UUID stored as text)
- `result`: matched/not_matched/executed
- `detail`: Chi tiết (JSON)

## Quan hệ giữa các Models

```
Brand
  └── Product
      └── CampaignProduct
          └── Campaign
              ├── CampaignCreator
              │   └── Creator
              │       ├── CreatorChannel
              │       ├── CreatorContact
              │       ├── CreatorTagMap
              │       ├── CreatorNote
              │       └── CreatorRateCard
              ├── Booking
              │   ├── BookingDeliverable
              │   │   └── Video
              │   │       └── VideoMetricSnapshot
              │   └── Payment
              ├── TrackingAsset
              │   └── TrackingConversion
              └── Video
```

## Management Commands

### 1. Seed Data

Tạo sample data để test:

```bash
python manage.py seed_tiktok_booking
```

Tạo:
- 2 brands, 6 products
- 6 creators với channels và contacts
- 2 campaigns với products và creators
- Bookings + deliverables + videos + snapshots
- Payments (planned + paid)
- Templates và rules

### 2. Import Data

Import data từ CSV/Excel files:

```bash
python manage.py import_tiktok_booking --path ./marketing/import_templates --format auto --create-missing
```

**Options:**
- `--path`: Đường dẫn tới folder chứa files import (required)
- `--format`: Format file: `auto` (detect), `csv`, `xlsx` (default: auto)
- `--create-missing`: Tạo records thiếu khi FK reference không tồn tại
- `--dry-run`: Chạy thử không lưu vào database

**Idempotent Logic:**
- Chạy nhiều lần không tạo duplicate rows
- Sử dụng "natural keys" để upsert:
  - Brand: `code`
  - Product: `(brand.code, product.code)`
  - Creator: `name` hoặc `creator_key`
  - CreatorChannel: `(platform, handle)` hoặc `(platform, external_id)`
  - Campaign: `code`
  - Booking: `code`
  - BookingDeliverable: `(booking.code, deliverable_type, title, deadline_post)`
  - Video: `(channel, platform_video_id)` hoặc `url`
  - TrackingAsset: `(platform, code_type, code_value)`
  - TrackingConversion: `(tracking_asset natural key + order_code)`
  - Payment: `(booking.code + payment_date + amount + status)` hoặc `payment_ref`

**Transaction Safety:**
- Mỗi file được import trong một transaction
- Nếu có lỗi, rollback toàn bộ file đó
- Summary report hiển thị created/updated/skipped/errors

## Import File Formats

Tất cả templates nằm trong `marketing/import_templates/`:

### 1. brands.csv
```csv
code,name,description
BRAND1,Thương hiệu A,Mô tả
```

### 2. products.csv
```csv
brand_code,code,name,category,sapo_id,shopee_id
BRAND1,P001,Tên sản phẩm,Danh mục,1001,SP001
```

### 3. creators.csv
```csv
creator_key,name,alias,gender,dob,location,niche,status,priority_score,note_internal
creator_a,Nguyễn Văn A,alias,male,1995-05-15,Hà Nội,beauty,active,9,Ghi chú
```

### 4. creator_channels.csv
```csv
creator_key,platform,handle,profile_url,external_id,follower_count,avg_view_10,avg_engagement_rate
creator_a,tiktok,handle,https://...,tiktok_123,500000,50000,5.50
```

### 5. creator_contacts.csv
```csv
creator_key,contact_type,name,phone,zalo,email,wechat,is_primary,note
creator_a,owner,Tên,0900000001,zalo,email@example.com,,True,Ghi chú
```

### 6. campaigns.csv
```csv
code,name,brand_code,channel,objective,description,start_date,end_date,budget_planned,kpi_view,kpi_order,kpi_revenue,status,owner_username
CAMP001,Tên campaign,BRAND1,tiktok,sale,Mô tả,2024-01-01,2024-03-31,50000000,1000000,500,200000000,running,admin
```

### 7. campaign_products.csv
```csv
campaign_code,brand_code,product_code,priority,note
CAMP001,BRAND1,P001,1,Ghi chú
```

### 8. campaign_creators.csv
```csv
campaign_code,creator_key,role,note
CAMP001,creator_a,main,Ghi chú
```

### 9. bookings.csv
```csv
code,campaign_code,brand_code,creator_key,platform,handle,product_code,booking_type,brief_summary,start_date,end_date,total_fee_agreed,currency,deliverables_count_planned,status,internal_note
BOOK001,CAMP001,BRAND1,creator_a,tiktok,handle,P001,combo,Tóm tắt,2024-01-15,2024-02-15,15000000,VND,3,in_progress,Ghi chú
```

### 10. booking_deliverables.csv
```csv
booking_code,deliverable_type,title,script_link,requirements,deadline_shoot,deadline_post,quantity,fee,status
BOOK001,video_feed,Title,https://...,Yêu cầu,2024-01-20 10:00:00,2024-01-25 18:00:00,1,5000000,shooting
```

### 11. videos.csv
```csv
booking_code,deliverable_title,channel,platform_video_id,url,title,post_date,thumbnail_url,status
BOOK001,Title,tiktok,tiktok_video_001,https://...,Tiêu đề,2024-01-25 18:00:00,https://...,posted
```

### 12. video_snapshots.csv
```csv
channel,platform_video_id,snapshot_time,view_count,like_count,comment_count,share_count,save_count,engagement_rate
tiktok,tiktok_video_001,2024-01-26 10:00:00,50000,5000,500,200,1000,14.00
```

### 13. tracking_assets.csv
```csv
campaign_code,booking_code,creator_key,code_type,code_value,platform,target_url,note,is_active
CAMP001,BOOK001,creator_a,voucher,GIADUNG10,tiktok_shop,https://...,Ghi chú,True
```

### 14. conversions.csv
```csv
platform,code_type,code_value,order_code,order_id_external,order_date,revenue,currency,source_platform,brand_code,product_code,quantity
tiktok_shop,voucher,GIADUNG10,ORD001,ext_001,2024-01-26 14:30:00,500000,VND,tiktok_shop,BRAND1,P001,1
```

### 15. payments.csv
```csv
booking_code,campaign_code,creator_key,amount,currency,exchange_rate,amount_vnd,payment_date,payment_method,status,invoice_number,note,created_by_username
BOOK001,CAMP001,creator_a,5000000,VND,1.0,5000000,2024-01-20,bank_transfer,paid,INV001,Ghi chú,admin
```

## Django Admin

Truy cập Django Admin để quản lý:

- **Creator**: List, search, filter với inline channels và contacts
- **Campaign**: List, search, filter với inline products và creators
- **Booking**: List, search, filter với inline deliverables
- **Video**: List, search, filter với inline snapshots
- **Payment**: List, search, filter

## Tests

Chạy tests:

```bash
python manage.py test marketing.tests
```

Tests bao gồm:
1. Import idempotency: Chạy import 2 lần không tạo duplicate
2. FK mapping: Mapping creator_key và campaign_code hoạt động đúng
3. Dry-run: --dry-run không persist data

## Migrations

Tạo migrations:

```bash
python manage.py makemigrations marketing
python manage.py migrate marketing
```

## Future Extensions

### API Sync
- Sync data từ TikTok API
- Auto-update video metrics
- Sync creator follower counts

### Dashboards
- Campaign performance dashboard
- Creator performance dashboard
- ROI tracking dashboard

### Automation
- Auto-update campaign budget từ payments
- Auto-send notifications khi booking status thay đổi
- Auto-create tracking assets khi booking confirmed

## Notes

- Sử dụng `Decimal` cho tất cả fields tiền tệ
- Sử dụng `choices` enums cho statuses/types
- Indexes được tạo trên các fields thường query
- Soft delete với `is_active` và `deleted_at`
- Timestamps tự động với `created_at` và `updated_at`


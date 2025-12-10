Thiết kế database cho BOOKING CENTER (marketing)

You are a senior Django engineer working inside my existing Django monorepo.

GOAL
Implement a complete, future-proof database schema + import logic + seed/sample data for the system:
Booking Center
- Dashboard / Overview (query only)
- Campaigns
- KOC/KOL Database
- Bookings
- Videos & Performance
- Finance & Payment
- Rules & Templates

TECH CONSTRAINTS
- Use Django ORM models + migrations (PostgreSQL preferred; use JSONField where needed).
- Write clean, production-ready code. Favor explicit constraints + indexes.
- Ensure idempotent imports (upsert) and safe transactions.
- No UI required in this task (admin is ok).
- Provide documentation + file templates for import.

DELIVERABLES (must implement all)
1) Full models as described below (with constraints, indexes, soft delete, timestamps).
2) Django admin registrations for key models (Creator, Campaign, Booking, Video, Payment).
3) Management commands:
   - `seed_tiktok_booking` : creates sample brands/products/creators/campaigns/bookings/videos/payments
   - `import_tiktok_booking` : imports CSV/Excel files from a folder with mapping rules
4) Import templates + examples (CSV) placed in `tiktok_booking/import_templates/`
5) A README at `marketing/tiktok_booking/README.md` describing:
   - domain overview
   - model relationships
   - how to run seed + import
   - file formats and required columns
7) Basic tests for import idempotency and FK mapping.

PROJECT INTEGRATION
- If the project already has a BaseModel with timestamps/soft delete, reuse it; otherwise create:
  `BaseModel` with fields: id(UUID), created_at, updated_at, is_active(bool), deleted_at(nullable datetime)
- Prefer UUID primary keys for new tables (unless project standards require BigAutoField; follow repo conventions).

DATABASE MODELS (Implement these models)
A) Core
- Brand: code(unique), name, description
- Product: brand(FK), code(unique within brand), name, category, sapo_product_id(optional), is_active

B) Creators (KOC/KOL)
- Creator: name, alias, gender(optional), dob(optional), location, niche, note_internal, priority_score(1-10), status(active/watchlist/blacklist)
- CreatorChannel: creator(FK), platform(enum: tiktok/youtube/instagram/shopee_live/other), handle, profile_url, external_id, follower_count, avg_view_10, avg_engagement_rate, data_raw(JSON)
  Constraints: unique(platform, handle) and/or unique(platform, external_id) if not null
- CreatorContact: creator(FK), contact_type(owner/manager/agency), name, phone, zalo, email, wechat(optional), note, is_primary
- CreatorTag: name(unique), description
- CreatorTagMap: creator(FK), tag(FK) unique_together(creator, tag)
- CreatorNote: creator(FK), user(FK optional), title, content(markdown), note_type(call/meeting/complaint/compliment)

(Optional but implement for future-proofing)
- CreatorRateCard: creator(FK), channel(FK optional), deliverable_type(video_single/series/live/combo/other), description, price, currency, valid_from, valid_to

C) Campaigns
- Campaign: code(unique), name, brand(FK), channel(enum tiktok/multi), objective(enum awareness/traffic/sale/launch/clearance), description, start_date, end_date,
           budget_planned, budget_actual(denormalized but computed), kpi_view, kpi_order, kpi_revenue, status(draft/planned/running/paused/finished/canceled), owner(FK optional)
  Indexes: (brand, start_date), (status, start_date)
- CampaignProduct: campaign(FK), product(FK), priority, note unique_together(campaign, product)
- CampaignCreator: campaign(FK), creator(FK), role(main/supporting/trial), note unique_together(campaign, creator)

D) Bookings
- Booking: code(unique), campaign(FK), creator(FK), channel(FK CreatorChannel optional), brand(FK), product_focus(FK Product optional),
           booking_type(enum video_only/live/combo/barter/affiliate_only),
           brief_summary, contract_file(optional URL/text), start_date, end_date,
           total_fee_agreed, currency, deliverables_count_planned, status(negotiating/confirmed/in_progress/completed/canceled), internal_note
  Indexes: (campaign, status), (creator, status)
- BookingDeliverable: booking(FK), deliverable_type(enum video_feed/video_story/live/series/short/other), title, script_link, requirements,
                     deadline_shoot(optional), deadline_post(optional), quantity, fee(optional), status(planned/shooting/waiting_approve/scheduled/posted/rejected/canceled)
- BookingStatusHistory: booking(FK), from_status, to_status, changed_by(FK optional), note, changed_at

E) Videos & Performance
- Video: booking_deliverable(FK optional), booking(FK optional but recommended for easier queries), campaign(FK), creator(FK),
        channel(enum tiktok/other), platform_video_id, url, title, post_date, thumbnail_url, status(posted/deleted/hidden/pending)
  Constraints: unique(channel, platform_video_id) when platform_video_id is not null
  Index: (campaign, post_date), (creator, post_date)
- VideoMetricSnapshot: video(FK), snapshot_time, view_count, like_count, comment_count, share_count, save_count, engagement_rate(optional), data_raw(JSON)
  Index: (video, snapshot_time)

Tracking / Attribution
- TrackingAsset: campaign(FK), booking(FK optional), creator(FK optional), code_type(voucher/link/referral_code), code_value, platform(tiktok_shop/web/shopee/other),
               target_url(optional), note, is_active
  Constraints: unique(platform, code_type, code_value)
- TrackingConversion: tracking_asset(FK), order_code, order_id_external(optional), order_date, revenue, currency, source_platform,
                     product(FK optional), quantity(optional), data_raw(JSON)
  Index: (tracking_asset, order_date)

F) Finance & Payment
- Payment: booking(FK), creator(FK), campaign(FK), amount, currency, exchange_rate(optional), amount_vnd(optional computed),
          payment_date, payment_method(bank_transfer/cash/other), status(planned/pending/paid/canceled), invoice_number(optional), note,
          created_by(FK optional)
  Index: (campaign, payment_date), (creator, payment_date), (status, payment_date)

G) Rules & Templates
- Template: name, template_type(brief/chat_message/email/contract/internal_note), channel(tiktok/general),
           content(markdown/text), variables(JSON), is_active
- Rule: name, description, scope(campaign/booking/video/finance/creator), condition_json(JSON), action_json(JSON), is_active
- RuleLog: rule(FK), target_type(campaign/booking/video/creator/payment), target_id(UUID stored as text), result(matched/not_matched/executed),
          created_at, detail(JSON)

IMPORT LOGIC (Management command: import_tiktok_booking)
Implement a robust importer supporting CSV and XLSX. Prefer pandas if available; otherwise openpyxl/csv.
- CLI:
  python manage.py import_tiktok_booking --path ./data_import --format auto --create-missing --dry-run
- Must be idempotent: running multiple times does not duplicate rows.
- Use these "natural keys" for upsert:
  Brand: code
  Product: (brand.code, product.code)
  Creator: name OR (platform handle) if provided; prefer a stable `creator_key` column in import files
  CreatorChannel: (platform, handle) or (platform, external_id)
  Campaign: code
  Booking: code
  BookingDeliverable: (booking.code, deliverable_type, title, deadline_post) as a composite key (or allow deliverable_code column)
  Video: (channel, platform_video_id) else url
  TrackingAsset: (platform, code_type, code_value)
  TrackingConversion: (tracking_asset natural key + order_code)
  Payment: (booking.code + payment_date + amount + status) OR allow payment_ref column
- Validate FK references; if missing and --create-missing is enabled, create minimal placeholder records (with note "AUTO-CREATED BY IMPORT").
- Wrap each file import in a transaction; on failure, rollback.
- Provide a summary report (created/updated/skipped/errors) printed to console.

IMPORT FILES (templates to create)
In `tiktok_booking/import_templates/`, create:
1) brands.csv
   columns: code,name,description
2) products.csv
   columns: brand_code,code,name,category,sapo_id,shopee_id
3) creators.csv
   columns: creator_key,name,alias,gender,dob,location,niche,status,priority_score,note_internal
4) creator_channels.csv
   columns: creator_key,platform,handle,profile_url,external_id,follower_count,avg_view_10,avg_engagement_rate
5) creator_contacts.csv
   columns: creator_key,contact_type,name,phone,zalo,email,wechat,is_primary,note
6) campaigns.csv
   columns: code,name,brand_code,channel,objective,description,start_date,end_date,budget_planned,kpi_view,kpi_order,kpi_revenue,status,owner_username
7) campaign_products.csv
   columns: campaign_code,brand_code,product_code,priority,note
8) campaign_creators.csv
   columns: campaign_code,creator_key,role,note
9) bookings.csv
   columns: code,campaign_code,brand_code,creator_key,platform,handle,product_code,booking_type,brief_summary,start_date,end_date,total_fee_agreed,currency,deliverables_count_planned,status,internal_note
10) booking_deliverables.csv
    columns: booking_code,deliverable_type,title,script_link,requirements,deadline_shoot,deadline_post,quantity,fee,status
11) videos.csv
    columns: booking_code,deliverable_title,channel,platform_video_id,url,title,post_date,thumbnail_url,status
12) video_snapshots.csv
    columns: channel,platform_video_id,snapshot_time,view_count,like_count,comment_count,share_count,save_count,engagement_rate
13) tracking_assets.csv
    columns: campaign_code,booking_code,creator_key,code_type,code_value,platform,target_url,note,is_active
14) conversions.csv
    columns: platform,code_type,code_value,order_code,order_id_external,order_date,revenue,currency,source_platform,brand_code,product_code,quantity
15) payments.csv
    columns: booking_code,campaign_code,creator_key,amount,currency,exchange_rate,amount_vnd,payment_date,payment_method,status,invoice_number,note,created_by_username

Each template must include 2-3 sample rows.

SEED DATA (Management command: seed_tiktok_booking)
- Create 2 brands, 6 products.
- Create 6 creators with tiktok channels and contacts.
- Create 2 campaigns with campaign_products and campaign_creators.
- Create bookings + deliverables + videos + a few snapshots.
- Create payments (planned + paid).
- Create templates and rules.

ADMIN
- Use list_display, search_fields, list_filter for:
  Creator, Campaign, Booking, Video, Payment
- Add inline for BookingDeliverable under Booking; Video snapshots inline under Video.

TESTS
- Tests for:
  1) Import running twice does not duplicate (idempotency).
  2) FK mapping using creator_key and campaign_code works.
  3) --dry-run does not persist.
  Use Django TestCase + temporary folder with csv files.

DOCUMENTATION
- README with:
  - ER overview in text
  - command examples
  - import file mapping rules
  - future extension notes (API sync, dashboards)

IMPLEMENTATION NOTES
- Use Decimal for money.
- Use choices enums for statuses/types.
- Add indexes on high-query fields as listed.
- Keep code modular: split models into multiple files if large (models/creator.py, models/campaign.py, ...).
- Ensure migrations are generated and committed.

Now implement all of the above in this repo.
Return: a concise file tree + key code excerpts + how to run commands.
Do not ask me questions; make reasonable assumptions and proceed.

You are a senior Django + product engineer working inside my existing Django monorepo. Hãy tuỳ biến những mô tả dưới đây cho phù hợp với project hiện tại -> marketing / BOOKING CENTER

TASK
Write a complete, sequential, and developer-actionable SPEC for the module:
"Campaigns" (part of TikTok Booking system).

IMPORTANT
- Database schema for Campaigns and related mapping tables already exists (defined below). Do NOT redesign it.
- Your output must be easy to understand, step-by-step, and implementable.
- Include: requirements, features, user flows, views/templates (Django), permissions, validations, computed metrics, alerts/health rules, and acceptance criteria.
- No UI code required, but the view/template spec must be detailed enough that a dev can implement without guessing.
- This module must be operational even before Bookings/Videos/Payments exist (show placeholders and progressive enhancement).
- Hãy tuỳ biến những mô tả dưới đây cho phù hợp với project hiện tại -> marketing / BOOKING CENTER

MODULE CONTEXT
TikTok Booking system modules:
- KOC/KOL Database (already built first)
- Campaigns (this task)
- Bookings
- Videos & Performance
- Finance & Payment
- Dashboard / Overview (query only)
- Rules & Templates

GOAL OF CAMPAIGNS MODULE
Campaign = the “frame” that groups KOC/booking/video/cost into a single goal.
Campaigns must allow us to:
- plan and track a campaign end-to-end (objective, dates, products, creators)
- monitor progress and risk (deadlines, deliverables posted vs planned)
- control budgets (planned vs committed vs paid)
- evaluate results (views/orders/revenue/ROAS) once other modules exist
- capture insights/postmortem notes for future learning

EXISTING DATABASE MODELS (do not change)
A) Campaign
- fields:
  code(unique), name,
  brand(FK), channel(enum tiktok/multi),
  objective(enum awareness/traffic/sale/launch/clearance),
  description (brief tổng),
  start_date, end_date,
  budget_planned, budget_actual (denormalized but computed),
  kpi_view, kpi_order, kpi_revenue,
  status(draft/planned/running/paused/finished/canceled),
  owner(FK optional)

B) CampaignProduct
- fields: campaign(FK), product(FK), priority, note
- constraint: unique_together(campaign, product)

C) CampaignCreator
- fields: campaign(FK), creator(FK), role(main/supporting/trial), note
- constraint: unique_together(campaign, creator)

(Assume these exist from earlier schema)
- Brand, Product
- Creator (KOC database)

NOTE
Bookings/Videos/Payments exist in later modules. In this Campaigns spec:
- Design for progressive enhancement: show “planned metrics” now, and “actual metrics” later.
- Any computed metrics must gracefully degrade to 0/empty if related data not present yet.

NON-FUNCTIONAL REQUIREMENTS
- Suitable for 1,000+ campaigns over time, tens of thousands of related records later.
- Strong filtering, fast list views with indexes.
- Clear auditability: who changed campaign status, budget, dates (can use a simple activity log approach in spec, but do NOT add new DB tables unless they already exist).

==================================================
1) MODULE GOALS (Business outcomes)
==================================================
Write 6 bullet outcomes:
- planning, staffing, budget control, progress monitoring, reporting, learnings

==================================================
2) PERSONAS & PERMISSIONS (RBAC)
==================================================
Define roles:
- Admin: full control, can finish/cancel campaigns, change budgets, delete (soft)
- Marketing/Booking Lead: create/edit campaigns, assign creators/products, update status, edit KPI, add insights
- Finance: view campaigns + budget, see committed/paid (when finance module exists)
- Viewer: read-only

Provide a permission matrix by feature:
Campaign CRUD, status transitions, budget edits, assign creators, assign products, export, insights editing.

==================================================
3) CAMPAIGN LIFECYCLE & STATES
==================================================
Define state transitions and rules:
draft -> planned -> running -> finished
draft/planned/running -> paused -> running
any -> canceled
finished/canceled are terminal (edits limited)

Define validation rules per state:
- planned/running must have start/end dates
- running must have at least 1 creator OR 1 product assigned (configurable; default: require at least 1 creator)
- finished requires a postmortem note (stored in description or a dedicated note section in UI without DB change)

==================================================
4) FUNCTIONAL REQUIREMENTS (Features)
==================================================

4.1 Campaign CRUD
- Create/edit/view/soft delete
- Unique code rules
- Owner assignment
- Brand/channel/objective
- Date range + status

4.2 Campaign Products (CampaignProduct)
- Add products to campaign with priority + note
- Bulk add from product list
- Unique constraint handling
- Display product cards with priority sorting

4.3 Campaign Creators (CampaignCreator)
- Add creators to campaign with role + note
- Bulk add from KOC filter results
- Unique constraint handling
- Display creator cards (with status badge from KOC DB)
- Show “watchlist/blacklist” warnings

4.4 Campaign Brief & Assets (within existing fields)
- Use Campaign.description as “brief tổng”
- In UI, structure it with sections (key message, do/don’t, hashtags, CTA)
- Optional: store structured brief as JSON inside description using a convention (specify how), or keep plain markdown.
(Do not add DB fields.)

4.5 Budget & KPI Tracking
- budget_planned editable by permitted roles
- budget_actual is computed from Payments (later module) OR shown as 0 when no Payment data
- Define “committed budget” as sum of Booking.total_fee_agreed (later) OR 0 now
- KPIs: view/order/revenue targets, used in progress computations later

4.6 Progress & Health (Alerts)
Define computed “health flags” shown in UI:
- OVER_BUDGET: budget_actual > budget_planned
- AT_RISK_DEADLINE: any deliverables overdue (later module)
- LOW_PERFORMANCE: ROAS < target after N days (later)
- CREATOR_RISK: creator has many rejections/delays (later)
For now, implement flags that can run without other modules:
- MISSING_CREATOR: campaign planned/running has 0 creators
- MISSING_PRODUCT: campaign planned/running has 0 products (optional)
- DATE_INVALID: end_date < start_date
- KPI_MISSING: KPI all null while objective is sale/traffic (configurable)
Describe how flags are computed and displayed (badges + count).

4.7 Reporting/Export
- Export campaign list with filters to CSV/XLSX
- Export campaign detail summary (products + creators) to CSV

==================================================
5) COMPUTED METRICS (Service layer spec)
==================================================
Define a `CampaignMetricsService` (spec only) that returns:
- budget_actual_paid (sum of Payment paid)
- budget_committed (sum of Booking fees)
- creators_count, products_count
- bookings_count_by_status (later)
- deliverables_total/posted/overdue (later)
- videos_posted (later)
- views_latest_total (later via snapshots)
- orders_attributed, revenue_attributed (later via conversions)
- ROAS, CPO, CPV (later)
- progress_percent:
  - now: planning progress = (has_dates + has_creators + has_products + has_budget) / 4
  - later: execution progress = posted_deliverables / planned_deliverables

Must gracefully degrade if later tables not present or no data.

==================================================
6) VIEW/TEMPLATE SPEC (Django templates)
==================================================
Provide detailed screens, components, and URLs.

6.1 Campaign List Screen
- Filters:
  - search (code/name)
  - brand
  - channel
  - objective
  - status
  - date range (start/end)
  - owner
  - has_creators, has_products toggles
- Table columns:
  - code, name
  - brand, status badge
  - date range
  - budget planned vs actual (actual may be 0 now)
  - creators count / products count
  - health flags badge count
  - quick actions: view, edit, duplicate (optional)
- Sorting: newest, start_date, budget_planned

6.2 Campaign Create/Edit Screen
- Sections:
  1) Basic info (code, name, brand, channel, objective, owner, status)
  2) Dates (start/end)
  3) Budget & KPI (budget_planned, kpi_view/order/revenue)
  4) Brief (description markdown with suggested headings)
- Validation messages and inline help
- Save as draft vs save & set planned

6.3 Campaign Detail Screen (the command center)
Tabs:
- Overview:
  - status, date range, owner
  - budget widget (planned/actual/committed)
  - KPI widget (targets vs actual; actual placeholders if no data)
  - Health flags panel
  - Quick buttons: edit, change status, export
- Creators:
  - list creators with role + note
  - warnings if creator status is watchlist/blacklist
  - bulk add creators (search + filter drawer; integrate with KOC DB filters)
- Products:
  - list products with priority + note
  - bulk add products
- Brief:
  - render description as markdown with sections
- Insights / Postmortem:
  - use description sub-section or a dedicated “insights” UI block stored inside description with markers:
    e.g., append:
    "## Postmortem\n- What worked:\n- What didn’t:\n- Next time:\n"
  - require this section before finishing campaign (validation rule)

6.4 Campaign Creator Picker (modal/drawer spec)
- Search creators
- Filter by status, tags, follower range, avg view range, location, niche
- Select multiple, assign role in bulk, add note in bulk
- Confirm adds CampaignCreator rows

6.5 Campaign Product Picker (modal/drawer spec)
- Search products, filter by brand/category
- Select multiple, set priority (bulk), note (optional)

==================================================
7) USER FLOWS (Step-by-step)
==================================================
Write flows:
- Create a campaign draft
- Add products + creators
- Move draft -> planned -> running
- Pause/resume
- Finish campaign with required postmortem section
- Duplicate a campaign (copy basic info + products + creators, reset dates/status)
- Export campaign list and details

==================================================
8) VALIDATIONS & EDGE CASES
==================================================
List validations:
- code unique
- end_date >= start_date
- status transition checks
- planned/running require start/end and at least 1 creator (default)
- creator blacklist warning and permission gates
- unique constraints on product/creator mapping with friendly messages
- prevent deleting campaign with linked future data (spec: soft delete only)

==================================================
9) ACCEPTANCE CRITERIA (Definition of Done)
==================================================
Provide testable acceptance criteria:
- Can create/edit/view campaigns with products and creators
- Filters and search work
- Health flags appear correctly
- Status transitions enforce rules
- Duplicate campaign works
- Export outputs correct filtered rows
- Performance/budget widgets show placeholders gracefully when later modules absent

==================================================
10) OUTPUT FORMAT
==================================================
Return the spec as a structured Markdown document with headings exactly as above.
Include suggested URL routes:
- /tiktok_booking/campaigns/
- /tiktok_booking/campaigns/new/
- /tiktok_booking/campaigns/<id>/
- /tiktok_booking/campaigns/<id>/edit/
- /tiktok_booking/campaigns/<id>/export/

Now produce the full SPEC.
Do not ask me questions; make reasonable assumptions and proceed.

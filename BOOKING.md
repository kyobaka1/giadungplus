You are a senior Django + product engineer working inside my existing Django monorepo.

TASK
Write a complete, production-ready SPEC + implementation plan for the module:
"KOC/KOL Database" (part of marketing app BOOKING CENTER)


IMPORTANT
- Xây dựng trong marketing -> BOOKING Center -> KOC/KOL Database
- Dưới đây chỉ là tham khảo, nếu có sai đường dẫn hay logic thì sửa lại phù hợp cho project hiện tại.
- Database schema already exists as described below. Do NOT redesign it.
- Your output must be easy to understand, sequential, and actionable for developers.
- Include: requirements, features, user flows, views/templates (Django), permissions, validations, import/export formats, and acceptance criteria.
- No UI code is required in this task, but the view/template spec must be detailed enough that a frontend/dev can implement it without guessing.

SCOPE (only this module)
KOC/KOL Database includes:
- Creator (KOC/KOL)
- CreatorChannel
- CreatorContact
- CreatorTag + CreatorTagMap
- CreatorNote
- (Optional but required for future-proof): CreatorRateCard
- Import/Export center
- Tag management screen

EXISTING DATABASE MODELS (do not change, only reference)
A) Creator (KOC/KOL)
- fields: name, alias, gender(optional), dob(optional), location, niche, note_internal, priority_score(1-10), status(active/watchlist/blacklist)

B) CreatorChannel
- fields: creator(FK), platform(enum: tiktok/youtube/instagram/shopee_live/other), handle, profile_url, external_id, follower_count, avg_view_10, avg_engagement_rate, data_raw(JSON)
- constraints: unique(platform, handle) and/or unique(platform, external_id) when external_id is not null

C) CreatorContact
- fields: creator(FK), contact_type(owner/manager/agency), name, phone, zalo, email, wechat(optional), note, is_primary

D) CreatorTag
- fields: name(unique), description

E) CreatorTagMap
- fields: creator(FK), tag(FK), unique_together(creator, tag)

F) CreatorNote
- fields: creator(FK), user(FK optional), title, content(markdown/text), note_type(call/meeting/complaint/compliment), created_at

G) CreatorRateCard
- fields: creator(FK), channel(FK optional), deliverable_type(video_single/series/live/combo/other), description, price, currency, valid_from, valid_to

GENERAL NON-FUNCTIONAL REQUIREMENTS
- Must support large-scale ops (thousands of creators).
- Must prevent duplicates and keep data consistent.
- Must be usable by a marketing/booking team without Excel/Zalo dependency.
- Must support soft delete + audit trail (status history can be via CreatorNote; do not add new models).
- Must support import/export with idempotent upsert.

========================================
1) MODULE GOALS (Business outcomes)
========================================
Explain in 6 bullets what this module must enable:
1) build a creator pool, 2) filter/select creators fast, 3) manage contacts, 4) track collaboration history,
5) manage price/rate expectations, 6) standardize operations via tags/notes/import.

========================================
2) PERSONAS & PERMISSIONS (RBAC)
========================================
Define roles and permissions:
- Admin: full CRUD, can manage tags, can set blacklist, can import/export.
- Booking/Marketing user: CRUD creators, channels, contacts, notes; cannot delete tags; cannot blacklist without permission.
- Viewer: read-only.
Include permission matrix by feature (Creator, Channel, Contact, Notes, Tags, Import).

========================================
3) FUNCTIONAL REQUIREMENTS (Features)
========================================
Describe all features in a clear list, grouped by entity:

3.1 Creator (KOC/KOL)
- Create/Edit/View/Soft delete
- Status management: active/watchlist/blacklist
- Priority score (1-10) validation
- Duplicate detection rules:
  - strongest: CreatorChannel (platform+handle) match
  - second: (platform+external_id)
  - fallback: name+location warning only
- Auto-created placeholders: allow minimal Creator records created during import with note "AUTO-CREATED BY IMPORT"
- Actions: quick add note, open profile, copy primary contact
- Restriction: if status=blacklist, show warning and disable Create Booking button (future placeholder)

3.2 CreatorChannel
- Manage multiple channels per creator
- Unique constraints behavior and error messages
- Fields displayed prominently: platform, handle, followers, avg_view_10, avg_engagement_rate, profile_url
- Quick action: open profile URL

3.3 CreatorContact
- Manage multiple contacts per creator (owner/manager/agency)
- Must allow one and only one primary contact per creator (is_primary)
- When set a new primary, auto-unset previous
- Click-to-copy fields: phone, zalo, email

3.4 Tags (CreatorTag + Map)
- CRUD tags (admin)
- Assign/unassign tags to creators (marketing)
- Multi-select filters on list screen
- Tag hygiene: warn on similar/duplicate names (case-insensitive)

3.5 Notes (CreatorNote)
- Add notes with type call/meeting/complaint/compliment
- Timeline view, filter by type, search inside notes
- Optional “important” behavior using title prefix or content convention (do not change DB)

3.6 Rate Card (CreatorRateCard)
- Add multiple price entries per creator
- Validity range (valid_from/to)
- Prefer newest active entry when suggesting prices
- Optional: allow channel-specific rate

3.7 Import/Export Center
- Import CSV/XLSX creators/channels/contacts
- Dry-run mode with preview summary
- Idempotent upsert based on natural keys:
  - Creator: creator_key (preferred) else channel(platform+handle)
  - Channel: platform+handle or platform+external_id
  - Contact: creator_key + phone/email + contact_type (or allow contact_key)
- Error report per row, and summary created/updated/skipped/errors
- Export creators with current filters to CSV/XLSX

========================================
4) VIEW/TEMPLATE SPEC (Django templates)
========================================
Provide detailed screens and components.
No actual code, but specify layout, data, interactions, and URLs.

4.1 Creator List Screen (KOC Dashboard)
- Purpose: filter and select fast
- Filters (top or left panel):
  - search: name/alias/handle/phone/email
  - status multi-select
  - platform filter
  - tags multi-select
  - location, niche
  - follower range, avg_view range
  - priority_score range
- Results table/card fields:
  - name+alias, status badge, primary TikTok handle + followers
  - avg_view_10, tags chips, priority_score
  - last interaction (latest CreatorNote)
  - quick actions: open profile, copy primary contact, add note
- Pagination and sorting:
  - sort by priority_score, followers, avg_view_10, last_interaction

4.2 Creator Detail Screen (Profile 360)
Use tabs:
- Overview tab:
  - basic info + internal note
  - tags
  - status + priority_score
  - quick buttons: edit, add note, copy primary contact, open profile
  - optional: mini stats placeholders (campaign count, etc.) with "coming from other modules"
- Channels tab:
  - list channels and stats, add/edit
- Contacts tab:
  - list contacts, set primary, click copy
- Rate Card tab:
  - list entries, add/edit
- Notes/Timeline tab:
  - timeline with filters, markdown editor, search
- (Future) History tab placeholder for bookings/videos

4.3 Tag Management Screen
- list tags, usage count (# creators)
- add/edit tag
- merge tag concept (spec only, optional)
- prevent deletion if used unless admin confirms

4.4 Import Center Screen
- upload/select file
- choose import type (creators, channels, contacts)
- toggle dry-run
- show results summary + error table
- download templates

========================================
5) USER FLOWS (Step-by-step)
========================================
Write step-by-step flows:
- Add new creator from scratch
- Add creator discovered on TikTok with manager contact
- Tagging and shortlisting for a campaign
- Mark as watchlist/blacklist and record reason note
- Import 200 creators safely (dry-run then import)
- Export a filtered list for outreach

========================================
6) VALIDATIONS & DATA QUALITY RULES
========================================
List validations:
- required fields and formats (phone/email)
- unique channel constraints and friendly errors
- primary contact uniqueness
- priority_score bounds
- status transitions and warnings
- blacklist restrictions

========================================
7) ACCEPTANCE CRITERIA (Done definition)
========================================
Provide clear acceptance tests for the module:
- Can create/edit creator with channels/contacts/tags/notes
- Filters return correct results under 10k creators
- Duplicate prevention works for channel handle
- Only one primary contact enforced
- Import dry-run shows preview without saving
- Import is idempotent (running twice does not create duplicates)
- Export respects filters
- Permissions enforced as matrix

========================================
8) DELIVERABLE FORMAT
========================================
Return the spec as:
- A structured Markdown document with headings exactly as above.
- Include example UI wire text (field labels and placeholders).
- Include URL/route suggestions (e.g., /tiktok_booking/creators/, /creators/<id>/).

Now produce the full SPEC.
Do not ask me questions; make reasonable assumptions and proceed.

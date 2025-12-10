# KOC/KOL Database - Booking Center Implementation

## Overview
Complete implementation of the KOC/KOL Database module for the Booking Center as specified in BOOKING.md.

## Files Created/Modified

### Views
- `marketing/views_booking.py` - Complete booking center views (800+ lines)
  - Creator list with advanced filtering
  - Creator detail with tabs (Overview, Channels, Contacts, Rate Card, Notes)
  - CRUD operations for all entities
  - Tag management
  - Import/Export functionality

### Services
- `marketing/services/booking_import_export.py` - Import/Export service
  - CSV and XLSX support
  - Idempotent upsert logic
  - Dry-run mode
  - Error reporting

### Templates
- `marketing/templates/marketing/booking/creator_list.html` - Creator dashboard/list
- `marketing/templates/marketing/booking/creator_detail.html` - Creator profile 360 view
- `marketing/templates/marketing/booking/creator_form.html` - Create/Edit creator form
- `marketing/templates/marketing/booking/tag_list.html` - Tag management screen
- `marketing/templates/marketing/booking/import_export.html` - Import/Export center

### URLs
- Updated `marketing/urls.py` with all booking center routes

### Navigation
- Updated `marketing/templates/marketing/base_marketing.html` to include KOC/KOL Database link

## Features Implemented

### 1. Creator Management
- ✅ List view with advanced filters (search, status, platform, tags, location, niche, follower range, avg_view range, priority_score)
- ✅ Detail view with tabbed interface
- ✅ Create/Edit/Delete (soft delete) creators
- ✅ Status management (active/watchlist/blacklist)
- ✅ Priority score validation (1-10)
- ✅ Duplicate detection (by channel handle or name+location)
- ✅ Blacklist restrictions

### 2. Channel Management
- ✅ Multiple channels per creator
- ✅ Unique constraint handling (platform+handle)
- ✅ Channel stats display (followers, avg_view, engagement rate)
- ✅ Quick actions (open profile URL)

### 3. Contact Management
- ✅ Multiple contacts per creator
- ✅ Primary contact enforcement (only one primary)
- ✅ Contact types (owner/manager/agency)
- ✅ Click-to-copy functionality (phone, zalo, email)

### 4. Tag Management
- ✅ CRUD tags (admin can delete, marketing can create)
- ✅ Assign/unassign tags to creators
- ✅ Multi-select filters on list screen
- ✅ Tag usage count display
- ✅ Duplicate name warning (case-insensitive)

### 5. Notes/Timeline
- ✅ Add notes with types (call/meeting/complaint/compliment)
- ✅ Timeline view with filters
- ✅ Markdown content support
- ✅ User attribution

### 6. Rate Card
- ✅ Multiple rate card entries per creator
- ✅ Channel-specific rates (optional)
- ✅ Validity date ranges
- ✅ Deliverable types (video_single/series/live/combo)

### 7. Import/Export
- ✅ CSV and XLSX import support
- ✅ Dry-run mode with preview
- ✅ Idempotent upsert based on natural keys
- ✅ Error reporting per row
- ✅ Export with current filters
- ✅ Template downloads

## Permissions (RBAC)

### Admin
- Full CRUD on all entities
- Can manage tags (create/delete)
- Can set blacklist status
- Can import/export

### MarketingManager/MarketingStaff
- CRUD creators, channels, contacts, notes
- Can create tags (cannot delete)
- Cannot blacklist without admin permission
- Can import/export (MarketingManager only)

### Viewer
- Read-only access (via permission decorator)

## URL Routes

All routes are under `/marketing/booking/`:

- `creators/` - Creator list
- `creators/create/` - Create creator
- `creators/<id>/` - Creator detail
- `creators/<id>/edit/` - Edit creator
- `creators/<id>/delete/` - Delete creator
- `creators/<id>/channels/create/` - Add channel
- `creators/<id>/channels/<id>/delete/` - Delete channel
- `creators/<id>/contacts/create/` - Add contact
- `creators/<id>/contacts/<id>/set-primary/` - Set primary contact
- `creators/<id>/contacts/<id>/delete/` - Delete contact
- `creators/<id>/tags/assign/` - Assign tags
- `creators/<id>/notes/create/` - Add note
- `creators/<id>/notes/<id>/delete/` - Delete note
- `creators/<id>/ratecards/create/` - Add rate card
- `creators/<id>/ratecards/<id>/delete/` - Delete rate card
- `tags/` - Tag management
- `tags/create/` - Create tag
- `tags/<id>/delete/` - Delete tag
- `import-export/` - Import/Export center
- `import/process/` - Process import (API)
- `export/` - Export creators
- `export/template/` - Download template

## Data Validation

- Priority score: 1-10 range enforced
- Status transitions: warnings for blacklist
- Primary contact: only one per creator (auto-unset previous)
- Channel uniqueness: platform+handle must be unique
- Required fields: name (creator), platform+handle (channel), name (contact)

## Import/Export Format

### Creators CSV
Columns: `creator_key`, `name`, `alias`, `gender`, `dob`, `location`, `niche`, `priority_score`, `status`, `note_internal`

### Channels CSV
Columns: `creator_key`, `platform`, `handle`, `profile_url`, `external_id`, `follower_count`, `avg_view_10`, `avg_engagement_rate`

### Contacts CSV
Columns: `creator_key`, `contact_type`, `name`, `phone`, `zalo`, `email`, `wechat`, `note`, `is_primary`

## Next Steps

1. Test the implementation with sample data
2. Add any missing validations based on testing
3. Consider adding bulk operations (bulk tag assignment, bulk status change)
4. Add analytics/stats dashboard (optional)
5. Integrate with booking/video tracking modules (future)

## Notes

- All models use soft delete (is_active, deleted_at)
- All timestamps are automatically managed (created_at, updated_at)
- Import uses creator_key for idempotent upsert
- Export respects current filter settings from list view
- Templates use Tailwind CSS for styling
- All forms include CSRF protection
- Permission checks are enforced at view level


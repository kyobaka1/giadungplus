from django.contrib import admin
from django.utils.html import format_html
from marketing.models import (
    MediaTrack,
    Brand, Product,
    Creator, CreatorChannel, CreatorContact, CreatorTag, CreatorTagMap, CreatorNote, CreatorRateCard,
    Campaign, CampaignProduct, CampaignCreator,
    Booking, BookingDeliverable, BookingStatusHistory,
    Video, VideoMetricSnapshot,
    TrackingAsset, TrackingConversion,
    Payment,
    Template, Rule, RuleLog,
)


# ============================================================================
# EXISTING ADMIN
# ============================================================================

@admin.register(MediaTrack)
class MediaTrackAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_name', 'page_title', 'file_extension', 'source_type', 'created_at')
    list_filter = ('file_extension', 'source_type', 'created_at', 'user_name')
    search_fields = ('user_name', 'page_title', 'page_url', 'media_url')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('user_name', 'created_at')
        }),
        ('Thông tin trang web', {
            'fields': ('page_url', 'page_title', 'tab_id')
        }),
        ('Thông tin media', {
            'fields': ('media_url', 'file_extension', 'mime_type', 'source_type', 'thumbnail_url')
        }),
    )


# ============================================================================
# CORE MODELS ADMIN
# ============================================================================

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('code', 'name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'brand', 'category', 'is_active', 'created_at')
    list_filter = ('brand', 'category', 'is_active', 'created_at')
    search_fields = ('code', 'name', 'brand__name')
    readonly_fields = ('created_at', 'updated_at')


# ============================================================================
# CREATOR MODELS ADMIN
# ============================================================================

class CreatorChannelInline(admin.TabularInline):
    model = CreatorChannel
    extra = 0
    fields = ('platform', 'handle', 'follower_count', 'avg_view_10', 'avg_engagement_rate')


class CreatorContactInline(admin.TabularInline):
    model = CreatorContact
    extra = 0
    fields = ('contact_type', 'name', 'phone', 'zalo', 'email', 'is_primary')


@admin.register(Creator)
class CreatorAdmin(admin.ModelAdmin):
    list_display = ('name', 'alias', 'niche', 'status', 'priority_score', 'created_at')
    list_filter = ('status', 'niche', 'gender', 'priority_score', 'created_at')
    search_fields = ('name', 'alias', 'location', 'niche')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [CreatorChannelInline, CreatorContactInline]
    
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('name', 'alias', 'gender', 'dob', 'location', 'niche')
        }),
        ('Đánh giá', {
            'fields': ('status', 'priority_score', 'note_internal')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'is_active', 'deleted_at')
        }),
    )


@admin.register(CreatorChannel)
class CreatorChannelAdmin(admin.ModelAdmin):
    list_display = ('creator', 'platform', 'handle', 'follower_count', 'avg_view_10', 'avg_engagement_rate')
    list_filter = ('platform', 'created_at')
    search_fields = ('creator__name', 'handle', 'external_id')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CreatorContact)
class CreatorContactAdmin(admin.ModelAdmin):
    list_display = ('creator', 'contact_type', 'name', 'phone', 'zalo', 'email', 'is_primary')
    list_filter = ('contact_type', 'is_primary')
    search_fields = ('creator__name', 'name', 'phone', 'email')


@admin.register(CreatorTag)
class CreatorTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name', 'description')


@admin.register(CreatorNote)
class CreatorNoteAdmin(admin.ModelAdmin):
    list_display = ('creator', 'title', 'note_type', 'user', 'created_at')
    list_filter = ('note_type', 'created_at')
    search_fields = ('creator__name', 'title', 'content')
    readonly_fields = ('created_at', 'updated_at')


# ============================================================================
# CAMPAIGN MODELS ADMIN
# ============================================================================

class CampaignProductInline(admin.TabularInline):
    model = CampaignProduct
    extra = 0
    fields = ('product', 'priority', 'note')


class CampaignCreatorInline(admin.TabularInline):
    model = CampaignCreator
    extra = 0
    fields = ('creator', 'role', 'note')


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'brand', 'channel', 'objective', 'status', 'start_date', 'budget_planned', 'owner')
    list_filter = ('channel', 'objective', 'status', 'start_date', 'created_at')
    search_fields = ('code', 'name', 'brand__name')
    readonly_fields = ('created_at', 'updated_at', 'budget_actual')
    inlines = [CampaignProductInline, CampaignCreatorInline]
    
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('code', 'name', 'brand', 'channel', 'objective', 'description', 'owner')
        }),
        ('Thời gian', {
            'fields': ('start_date', 'end_date')
        }),
        ('Budget & KPI', {
            'fields': ('budget_planned', 'budget_actual', 'kpi_view', 'kpi_order', 'kpi_revenue')
        }),
        ('Trạng thái', {
            'fields': ('status',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'is_active', 'deleted_at')
        }),
    )


# ============================================================================
# BOOKING MODELS ADMIN
# ============================================================================

class BookingDeliverableInline(admin.TabularInline):
    model = BookingDeliverable
    extra = 0
    fields = ('deliverable_type', 'title', 'deadline_post', 'quantity', 'fee', 'status')
    readonly_fields = ('created_at',)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('code', 'campaign', 'creator', 'booking_type', 'status', 'total_fee_agreed', 'currency', 'start_date')
    list_filter = ('booking_type', 'status', 'campaign', 'created_at')
    search_fields = ('code', 'campaign__code', 'creator__name', 'brand__name')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [BookingDeliverableInline]
    
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('code', 'campaign', 'creator', 'channel', 'brand', 'product_focus', 'booking_type')
        }),
        ('Nội dung', {
            'fields': ('brief_summary', 'contract_file', 'internal_note')
        }),
        ('Thời gian', {
            'fields': ('start_date', 'end_date')
        }),
        ('Tài chính', {
            'fields': ('total_fee_agreed', 'currency', 'deliverables_count_planned')
        }),
        ('Trạng thái', {
            'fields': ('status',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'is_active', 'deleted_at')
        }),
    )


@admin.register(BookingStatusHistory)
class BookingStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('booking', 'from_status', 'to_status', 'changed_by', 'changed_at')
    list_filter = ('to_status', 'changed_at')
    search_fields = ('booking__code', 'note')
    readonly_fields = ('changed_at', 'created_at')


# ============================================================================
# VIDEO MODELS ADMIN
# ============================================================================

class VideoMetricSnapshotInline(admin.TabularInline):
    model = VideoMetricSnapshot
    extra = 0
    fields = ('snapshot_time', 'view_count', 'like_count', 'comment_count', 'share_count', 'engagement_rate')
    readonly_fields = ('snapshot_time',)


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('id', 'creator', 'campaign', 'channel', 'title', 'post_date', 'status', 'view_count_display')
    list_filter = ('channel', 'status', 'post_date', 'created_at')
    search_fields = ('creator__name', 'campaign__code', 'title', 'platform_video_id', 'url')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [VideoMetricSnapshotInline]
    
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('booking_deliverable', 'booking', 'campaign', 'creator', 'channel')
        }),
        ('Video', {
            'fields': ('platform_video_id', 'url', 'title', 'post_date', 'thumbnail_url', 'status')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'is_active', 'deleted_at')
        }),
    )
    
    def view_count_display(self, obj):
        latest = obj.snapshots.first()
        return latest.view_count if latest else 0
    view_count_display.short_description = 'Views'


@admin.register(VideoMetricSnapshot)
class VideoMetricSnapshotAdmin(admin.ModelAdmin):
    list_display = ('video', 'snapshot_time', 'view_count', 'like_count', 'comment_count', 'engagement_rate')
    list_filter = ('snapshot_time',)
    search_fields = ('video__title', 'video__creator__name')
    readonly_fields = ('created_at', 'updated_at')


# ============================================================================
# TRACKING MODELS ADMIN
# ============================================================================

@admin.register(TrackingAsset)
class TrackingAssetAdmin(admin.ModelAdmin):
    list_display = ('code_value', 'code_type', 'platform', 'campaign', 'creator', 'is_active')
    list_filter = ('code_type', 'platform', 'is_active', 'created_at')
    search_fields = ('code_value', 'campaign__code', 'creator__name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TrackingConversion)
class TrackingConversionAdmin(admin.ModelAdmin):
    list_display = ('order_code', 'tracking_asset', 'order_date', 'revenue', 'currency', 'product')
    list_filter = ('currency', 'source_platform', 'order_date')
    search_fields = ('order_code', 'order_id_external', 'tracking_asset__code_value')
    readonly_fields = ('created_at', 'updated_at')


# ============================================================================
# PAYMENT ADMIN
# ============================================================================

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'booking', 'creator', 'amount', 'currency', 'payment_date', 'status', 'payment_method')
    list_filter = ('status', 'payment_method', 'currency', 'payment_date', 'created_at')
    search_fields = ('booking__code', 'creator__name', 'campaign__code', 'invoice_number')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('booking', 'creator', 'campaign', 'created_by')
        }),
        ('Thanh toán', {
            'fields': ('amount', 'currency', 'exchange_rate', 'amount_vnd', 'payment_method', 'payment_date')
        }),
        ('Trạng thái', {
            'fields': ('status', 'invoice_number', 'note')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'is_active', 'deleted_at')
        }),
    )


# ============================================================================
# TEMPLATE & RULE ADMIN
# ============================================================================

@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'template_type', 'channel', 'is_active', 'created_at')
    list_filter = ('template_type', 'channel', 'is_active', 'created_at')
    search_fields = ('name', 'content')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'scope', 'is_active', 'created_at')
    list_filter = ('scope', 'is_active', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(RuleLog)
class RuleLogAdmin(admin.ModelAdmin):
    list_display = ('rule', 'target_type', 'target_id', 'result', 'created_at')
    list_filter = ('target_type', 'result', 'created_at')
    search_fields = ('rule__name', 'target_id')
    readonly_fields = ('created_at', 'updated_at')


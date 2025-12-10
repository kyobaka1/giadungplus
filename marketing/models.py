from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal


# ============================================================================
# BASE MODEL
# ============================================================================

class BaseModel(models.Model):
    """
    Base model với timestamps và soft delete.
    """
    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']


# ============================================================================
# MEDIA TRACKING MODEL
# ============================================================================

class MediaTrack(models.Model):
    """
    Track media (video/audio) từ web pages qua extension.
    """
    SOURCE_TYPE_CHOICES = [
        ('video_tag', 'Video Tag'),
        ('audio_tag', 'Audio Tag'),
        ('network_request', 'Network Request'),
    ]

    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    page_url = models.TextField(help_text="URL của trang web chứa media")
    page_title = models.CharField(max_length=500, blank=True, null=True)
    media_url = models.TextField(help_text="URL của file video/audio (.mp3, .mp4, .mov)")
    file_extension = models.CharField(max_length=10, help_text="mp4, mp3, mov")
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    source_type = models.CharField(
        max_length=50,
        choices=SOURCE_TYPE_CHOICES,
        default='video_tag',
        help_text="Nguồn phát hiện media"
    )
    user_name = models.CharField(
        max_length=150,
        db_index=True,
        help_text="Username được setup từ extension, trùng với username trên admin"
    )
    tab_id = models.IntegerField(blank=True, null=True, help_text="Chrome tab ID")
    thumbnail_url = models.TextField(blank=True, null=True, help_text="URL ảnh đại diện video")

    class Meta:
        verbose_name = "Media Track"
        verbose_name_plural = "Media Tracks"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_name', '-created_at']),
            models.Index(fields=['file_extension']),
        ]

    def __str__(self):
        return f"{self.user_name} - {self.page_title or self.page_url} ({self.file_extension})"


# ============================================================================
# CORE MODELS (Brand, Product)
# ============================================================================

class Brand(BaseModel):
    """
    Thương hiệu sản phẩm.
    """
    code = models.CharField(max_length=50, unique=True, db_index=True, help_text="Mã thương hiệu")
    name = models.CharField(max_length=200, help_text="Tên thương hiệu")
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Brand"
        verbose_name_plural = "Brands"
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Product(BaseModel):
    """
    Sản phẩm thuộc thương hiệu.
    """
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name='products')
    code = models.CharField(max_length=100, db_index=True, help_text="Mã sản phẩm (unique within brand)")
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True, null=True)
    sapo_product_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    shopee_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        unique_together = [['brand', 'code']]
        indexes = [
            models.Index(fields=['brand', 'code']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['brand', 'name']

    def __str__(self):
        return f"{self.brand.code}/{self.code} - {self.name}"


# ============================================================================
# CREATOR MODELS (KOC/KOL)
# ============================================================================

class Creator(BaseModel):
    """
    Creator (KOC/KOL) database.
    """
    GENDER_CHOICES = [
        ('male', 'Nam'),
        ('female', 'Nữ'),
        ('other', 'Khác'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('watchlist', 'Watchlist'),
        ('blacklist', 'Blacklist'),
    ]

    name = models.CharField(max_length=200, db_index=True)
    alias = models.CharField(max_length=200, blank=True, null=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True, null=True)
    dob = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True, null=True)
    niche = models.CharField(max_length=100, blank=True, null=True, help_text="Lĩnh vực: beauty, fashion, tech, etc.")
    note_internal = models.TextField(blank=True, null=True)
    priority_score = models.IntegerField(default=5, help_text="Điểm ưu tiên 1-10")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)

    class Meta:
        verbose_name = "Creator"
        verbose_name_plural = "Creators"
        indexes = [
            models.Index(fields=['status', 'priority_score']),
            models.Index(fields=['niche']),
        ]
        ordering = ['-priority_score', 'name']

    def __str__(self):
        return f"{self.name} ({self.status})"


class CreatorChannel(BaseModel):
    """
    Kênh của creator trên các platform.
    """
    PLATFORM_CHOICES = [
        ('tiktok', 'TikTok'),
        ('youtube', 'YouTube'),
        ('instagram', 'Instagram'),
        ('shopee_live', 'Shopee Live'),
        ('other', 'Other'),
    ]

    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='channels')
    platform = models.CharField(max_length=50, choices=PLATFORM_CHOICES, db_index=True)
    handle = models.CharField(max_length=200, db_index=True, help_text="Username/handle trên platform")
    profile_url = models.URLField(blank=True, null=True)
    external_id = models.CharField(max_length=200, blank=True, null=True, db_index=True, help_text="ID từ platform API")
    follower_count = models.BigIntegerField(default=0, help_text="Số lượng followers")
    avg_view_10 = models.IntegerField(default=0, help_text="Average views trong 10 video gần nhất")
    avg_engagement_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text="% engagement rate")
    data_raw = models.JSONField(default=dict, blank=True, help_text="Raw data từ platform API")

    class Meta:
        verbose_name = "Creator Channel"
        verbose_name_plural = "Creator Channels"
        unique_together = [
            ['platform', 'handle'],
        ]
        indexes = [
            models.Index(fields=['platform', 'external_id']),
            models.Index(fields=['creator', 'platform']),
        ]

    def __str__(self):
        return f"{self.creator.name} - {self.platform}/{self.handle}"


class CreatorContact(BaseModel):
    """
    Thông tin liên hệ của creator.
    """
    CONTACT_TYPE_CHOICES = [
        ('owner', 'Owner (Chủ kênh)'),
        ('manager', 'Manager (Quản lý)'),
        ('agency', 'Agency'),
    ]

    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='contacts')
    contact_type = models.CharField(max_length=50, choices=CONTACT_TYPE_CHOICES, default='owner')
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=50, blank=True, null=True)
    zalo = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    wechat = models.CharField(max_length=100, blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    is_primary = models.BooleanField(default=False, db_index=True)

    class Meta:
        verbose_name = "Creator Contact"
        verbose_name_plural = "Creator Contacts"
        indexes = [
            models.Index(fields=['creator', 'is_primary']),
        ]

    def __str__(self):
        return f"{self.creator.name} - {self.contact_type}: {self.name}"


class CreatorTag(BaseModel):
    """
    Tags để phân loại creators.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Creator Tag"
        verbose_name_plural = "Creator Tags"
        ordering = ['name']

    def __str__(self):
        return self.name


class CreatorTagMap(BaseModel):
    """
    Mapping giữa Creator và Tag.
    """
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='tag_maps')
    tag = models.ForeignKey(CreatorTag, on_delete=models.CASCADE, related_name='creator_maps')

    class Meta:
        verbose_name = "Creator Tag Map"
        verbose_name_plural = "Creator Tag Maps"
        unique_together = [['creator', 'tag']]

    def __str__(self):
        return f"{self.creator.name} - {self.tag.name}"


class CreatorNote(BaseModel):
    """
    Ghi chú về creator (call, meeting, complaint, etc.).
    """
    NOTE_TYPE_CHOICES = [
        ('call', 'Call'),
        ('meeting', 'Meeting'),
        ('complaint', 'Complaint'),
        ('compliment', 'Compliment'),
        ('other', 'Other'),
    ]

    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='notes')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='creator_notes')
    title = models.CharField(max_length=200)
    content = models.TextField(help_text="Markdown content")
    note_type = models.CharField(max_length=50, choices=NOTE_TYPE_CHOICES, default='other')

    class Meta:
        verbose_name = "Creator Note"
        verbose_name_plural = "Creator Notes"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.creator.name} - {self.title}"


class CreatorRateCard(BaseModel):
    """
    Bảng giá của creator cho các loại deliverable.
    """
    DELIVERABLE_TYPE_CHOICES = [
        ('video_single', 'Video Single'),
        ('series', 'Series'),
        ('live', 'Live'),
        ('combo', 'Combo'),
        ('other', 'Other'),
    ]

    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='rate_cards')
    channel = models.ForeignKey(CreatorChannel, on_delete=models.SET_NULL, null=True, blank=True, related_name='rate_cards')
    deliverable_type = models.CharField(max_length=50, choices=DELIVERABLE_TYPE_CHOICES)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=10, default='VND')
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Creator Rate Card"
        verbose_name_plural = "Creator Rate Cards"
        ordering = ['-valid_from', 'creator']

    def __str__(self):
        return f"{self.creator.name} - {self.deliverable_type}: {self.price} {self.currency}"


# ============================================================================
# CAMPAIGN MODELS
# ============================================================================

class Campaign(BaseModel):
    """
    Chiến dịch marketing.
    """
    CHANNEL_CHOICES = [
        ('tiktok', 'TikTok'),
        ('multi', 'Multi-platform'),
    ]

    OBJECTIVE_CHOICES = [
        ('awareness', 'Awareness'),
        ('traffic', 'Traffic'),
        ('sale', 'Sale'),
        ('launch', 'Launch'),
        ('clearance', 'Clearance'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('planned', 'Planned'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('finished', 'Finished'),
        ('canceled', 'Canceled'),
    ]

    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name='campaigns')
    channel = models.CharField(max_length=50, choices=CHANNEL_CHOICES, default='tiktok')
    objective = models.CharField(max_length=50, choices=OBJECTIVE_CHOICES)
    description = models.TextField(blank=True, null=True)
    start_date = models.DateField(null=True, blank=True, db_index=True)
    end_date = models.DateField(null=True, blank=True)
    budget_planned = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    budget_actual = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), help_text="Denormalized, computed from payments")
    kpi_view = models.BigIntegerField(default=0, help_text="KPI số lượt xem")
    kpi_order = models.IntegerField(default=0, help_text="KPI số đơn hàng")
    kpi_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), help_text="KPI doanh thu")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='draft', db_index=True)
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_campaigns')

    class Meta:
        verbose_name = "Campaign"
        verbose_name_plural = "Campaigns"
        indexes = [
            models.Index(fields=['brand', 'start_date']),
            models.Index(fields=['status', 'start_date']),
        ]
        ordering = ['-start_date', 'name']

    def __str__(self):
        return f"{self.code} - {self.name} ({self.status})"


class CampaignProduct(BaseModel):
    """
    Sản phẩm trong campaign.
    """
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='campaign_products')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='campaigns')
    priority = models.IntegerField(default=1, help_text="Độ ưu tiên (1 = cao nhất)")
    note = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Campaign Product"
        verbose_name_plural = "Campaign Products"
        unique_together = [['campaign', 'product']]
        ordering = ['priority', 'product']

    def __str__(self):
        return f"{self.campaign.code} - {self.product.name}"


class CampaignCreator(BaseModel):
    """
    Creator tham gia campaign.
    """
    ROLE_CHOICES = [
        ('main', 'Main'),
        ('supporting', 'Supporting'),
        ('trial', 'Trial'),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='campaign_creators')
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='campaigns')
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='main')
    note = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Campaign Creator"
        verbose_name_plural = "Campaign Creators"
        unique_together = [['campaign', 'creator']]

    def __str__(self):
        return f"{self.campaign.code} - {self.creator.name} ({self.role})"


# ============================================================================
# BOOKING MODELS
# ============================================================================

class Booking(BaseModel):
    """
    Booking với creator.
    """
    BOOKING_TYPE_CHOICES = [
        ('video_only', 'Video Only'),
        ('live', 'Live'),
        ('combo', 'Combo'),
        ('barter', 'Barter'),
        ('affiliate_only', 'Affiliate Only'),
    ]

    STATUS_CHOICES = [
        ('negotiating', 'Negotiating'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('canceled', 'Canceled'),
    ]

    code = models.CharField(max_length=50, unique=True, db_index=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='bookings')
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='bookings')
    channel = models.ForeignKey(CreatorChannel, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name='bookings')
    product_focus = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    booking_type = models.CharField(max_length=50, choices=BOOKING_TYPE_CHOICES)
    brief_summary = models.TextField(blank=True, null=True)
    contract_file = models.TextField(blank=True, null=True, help_text="URL hoặc text path")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    total_fee_agreed = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=10, default='VND')
    deliverables_count_planned = models.IntegerField(default=0)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='negotiating', db_index=True)
    internal_note = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Booking"
        verbose_name_plural = "Bookings"
        indexes = [
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['creator', 'status']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.code} - {self.creator.name} ({self.status})"


class BookingDeliverable(BaseModel):
    """
    Deliverable trong booking (video, live, etc.).
    """
    DELIVERABLE_TYPE_CHOICES = [
        ('video_feed', 'Video Feed'),
        ('video_story', 'Video Story'),
        ('live', 'Live'),
        ('series', 'Series'),
        ('short', 'Short'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('shooting', 'Shooting'),
        ('waiting_approve', 'Waiting Approve'),
        ('scheduled', 'Scheduled'),
        ('posted', 'Posted'),
        ('rejected', 'Rejected'),
        ('canceled', 'Canceled'),
    ]

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='deliverables')
    deliverable_type = models.CharField(max_length=50, choices=DELIVERABLE_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    script_link = models.URLField(blank=True, null=True)
    requirements = models.TextField(blank=True, null=True)
    deadline_shoot = models.DateTimeField(null=True, blank=True)
    deadline_post = models.DateTimeField(null=True, blank=True)
    quantity = models.IntegerField(default=1)
    fee = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='planned', db_index=True)

    class Meta:
        verbose_name = "Booking Deliverable"
        verbose_name_plural = "Booking Deliverables"
        ordering = ['deadline_post', 'title']

    def __str__(self):
        return f"{self.booking.code} - {self.title} ({self.status})"


class BookingStatusHistory(BaseModel):
    """
    Lịch sử thay đổi status của booking.
    """
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='status_history')
    from_status = models.CharField(max_length=50, blank=True, null=True)
    to_status = models.CharField(max_length=50)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField(blank=True, null=True)
    changed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Booking Status History"
        verbose_name_plural = "Booking Status Histories"
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.booking.code}: {self.from_status} -> {self.to_status}"


# ============================================================================
# VIDEO & PERFORMANCE MODELS
# ============================================================================

class Video(BaseModel):
    """
    Video đã được post.
    """
    CHANNEL_CHOICES = [
        ('tiktok', 'TikTok'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('posted', 'Posted'),
        ('deleted', 'Deleted'),
        ('hidden', 'Hidden'),
        ('pending', 'Pending'),
    ]

    booking_deliverable = models.ForeignKey(BookingDeliverable, on_delete=models.SET_NULL, null=True, blank=True, related_name='videos')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='videos')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='videos')
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='videos')
    channel = models.CharField(max_length=50, choices=CHANNEL_CHOICES, default='tiktok', db_index=True)
    platform_video_id = models.CharField(max_length=200, blank=True, null=True, db_index=True, help_text="ID từ platform")
    url = models.URLField(blank=True, null=True)
    title = models.CharField(max_length=500, blank=True, null=True)
    post_date = models.DateTimeField(null=True, blank=True, db_index=True)
    thumbnail_url = models.URLField(blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='posted', db_index=True)

    class Meta:
        verbose_name = "Video"
        verbose_name_plural = "Videos"
        indexes = [
            models.Index(fields=['campaign', 'post_date']),
            models.Index(fields=['creator', 'post_date']),
            models.Index(fields=['channel', 'platform_video_id']),
        ]
        ordering = ['-post_date']

    def __str__(self):
        return f"{self.creator.name} - {self.title or self.platform_video_id}"


class VideoMetricSnapshot(BaseModel):
    """
    Snapshot metrics của video tại một thời điểm.
    """
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='snapshots')
    snapshot_time = models.DateTimeField(db_index=True)
    view_count = models.BigIntegerField(default=0)
    like_count = models.BigIntegerField(default=0)
    comment_count = models.BigIntegerField(default=0)
    share_count = models.BigIntegerField(default=0)
    save_count = models.BigIntegerField(default=0)
    engagement_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    data_raw = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Video Metric Snapshot"
        verbose_name_plural = "Video Metric Snapshots"
        indexes = [
            models.Index(fields=['video', 'snapshot_time']),
        ]
        ordering = ['-snapshot_time']

    def __str__(self):
        return f"{self.video} - {self.snapshot_time} ({self.view_count} views)"


# ============================================================================
# TRACKING & ATTRIBUTION MODELS
# ============================================================================

class TrackingAsset(BaseModel):
    """
    Tracking asset (voucher code, link, referral code) để đo lường conversion.
    """
    CODE_TYPE_CHOICES = [
        ('voucher', 'Voucher Code'),
        ('link', 'Link'),
        ('referral_code', 'Referral Code'),
    ]

    PLATFORM_CHOICES = [
        ('tiktok_shop', 'TikTok Shop'),
        ('web', 'Web'),
        ('shopee', 'Shopee'),
        ('other', 'Other'),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='tracking_assets')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='tracking_assets')
    creator = models.ForeignKey(Creator, on_delete=models.SET_NULL, null=True, blank=True, related_name='tracking_assets')
    code_type = models.CharField(max_length=50, choices=CODE_TYPE_CHOICES, db_index=True)
    code_value = models.CharField(max_length=200, db_index=True)
    platform = models.CharField(max_length=50, choices=PLATFORM_CHOICES, db_index=True)
    target_url = models.URLField(blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Tracking Asset"
        verbose_name_plural = "Tracking Assets"
        unique_together = [['platform', 'code_type', 'code_value']]
        indexes = [
            models.Index(fields=['campaign', 'is_active']),
            models.Index(fields=['creator', 'is_active']),
        ]

    def __str__(self):
        return f"{self.platform}/{self.code_type}: {self.code_value}"


class TrackingConversion(BaseModel):
    """
    Conversion từ tracking asset (order, revenue).
    """
    tracking_asset = models.ForeignKey(TrackingAsset, on_delete=models.CASCADE, related_name='conversions')
    order_code = models.CharField(max_length=100, db_index=True)
    order_id_external = models.CharField(max_length=200, blank=True, null=True, db_index=True)
    order_date = models.DateTimeField(db_index=True)
    revenue = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=10, default='VND')
    source_platform = models.CharField(max_length=50, blank=True, null=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='conversions')
    quantity = models.IntegerField(null=True, blank=True)
    data_raw = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Tracking Conversion"
        verbose_name_plural = "Tracking Conversions"
        indexes = [
            models.Index(fields=['tracking_asset', 'order_date']),
            models.Index(fields=['order_code']),
        ]
        ordering = ['-order_date']

    def __str__(self):
        return f"{self.tracking_asset} - {self.order_code} ({self.revenue} {self.currency})"


# ============================================================================
# FINANCE & PAYMENT MODELS
# ============================================================================

class Payment(BaseModel):
    """
    Thanh toán cho creator.
    """
    PAYMENT_METHOD_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('cash', 'Cash'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('canceled', 'Canceled'),
    ]

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='payments')
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='payments')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=10, default='VND')
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    amount_vnd = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, help_text="Computed amount in VND")
    payment_date = models.DateField(null=True, blank=True, db_index=True)
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHOD_CHOICES, default='bank_transfer')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='planned', db_index=True)
    invoice_number = models.CharField(max_length=100, blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_payments')

    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        indexes = [
            models.Index(fields=['campaign', 'payment_date']),
            models.Index(fields=['creator', 'payment_date']),
            models.Index(fields=['status', 'payment_date']),
        ]
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        return f"{self.booking.code} - {self.amount} {self.currency} ({self.status})"


# ============================================================================
# RULES & TEMPLATES MODELS
# ============================================================================

class Template(BaseModel):
    """
    Templates cho brief, chat message, email, contract, etc.
    """
    TEMPLATE_TYPE_CHOICES = [
        ('brief', 'Brief'),
        ('chat_message', 'Chat Message'),
        ('email', 'Email'),
        ('contract', 'Contract'),
        ('internal_note', 'Internal Note'),
    ]

    CHANNEL_CHOICES = [
        ('tiktok', 'TikTok'),
        ('general', 'General'),
    ]

    name = models.CharField(max_length=200)
    template_type = models.CharField(max_length=50, choices=TEMPLATE_TYPE_CHOICES)
    channel = models.CharField(max_length=50, choices=CHANNEL_CHOICES, default='general')
    content = models.TextField(help_text="Markdown/text content")
    variables = models.JSONField(default=dict, blank=True, help_text="Available variables for template")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Template"
        verbose_name_plural = "Templates"
        ordering = ['template_type', 'name']

    def __str__(self):
        return f"{self.template_type} - {self.name}"


class Rule(BaseModel):
    """
    Business rules để tự động hóa (ví dụ: auto-update status, send notification).
    """
    SCOPE_CHOICES = [
        ('campaign', 'Campaign'),
        ('booking', 'Booking'),
        ('video', 'Video'),
        ('finance', 'Finance'),
        ('creator', 'Creator'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    scope = models.CharField(max_length=50, choices=SCOPE_CHOICES)
    condition_json = models.JSONField(default=dict, help_text="Condition logic (JSON)")
    action_json = models.JSONField(default=dict, help_text="Action to execute (JSON)")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Rule"
        verbose_name_plural = "Rules"
        ordering = ['scope', 'name']

    def __str__(self):
        return f"{self.scope} - {self.name}"


class RuleLog(BaseModel):
    """
    Log khi rule được trigger.
    """
    TARGET_TYPE_CHOICES = [
        ('campaign', 'Campaign'),
        ('booking', 'Booking'),
        ('video', 'Video'),
        ('creator', 'Creator'),
        ('payment', 'Payment'),
    ]

    RESULT_CHOICES = [
        ('matched', 'Matched'),
        ('not_matched', 'Not Matched'),
        ('executed', 'Executed'),
    ]

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE, related_name='logs')
    target_type = models.CharField(max_length=50, choices=TARGET_TYPE_CHOICES)
    target_id = models.CharField(max_length=100, db_index=True, help_text="UUID stored as text")
    result = models.CharField(max_length=50, choices=RESULT_CHOICES)
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Rule Log"
        verbose_name_plural = "Rule Logs"
        indexes = [
            models.Index(fields=['rule', 'target_type', 'target_id']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.rule.name} - {self.target_type}#{self.target_id} ({self.result})"

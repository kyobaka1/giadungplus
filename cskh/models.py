from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json


class Ticket(models.Model):
    """
    Ticket quản trị vấn đề CSKH - theo mô hình Sapo orders
    """
    
    # Ticket status
    STATUS_CHOICES = [
        ('new', 'Mới'),
        ('processing', 'Đang xử lý'),
        ('waiting_customer', 'Chờ khách'),
        ('waiting_warehouse', 'Chờ kho'),
        ('resolved', 'Đã xử lý'),
        ('closed', 'Đóng'),
    ]
    
    # Ticket type - loại vấn đề
    TICKET_TYPE_CHOICES = [
        ('bad_review', 'Đánh giá xấu'),
        ('return_exchange', 'Đổi trả'),
        ('warranty', 'Bảo hành'),
        ('damaged', 'Hỏng vỡ'),
        ('customer_request', 'Khách yêu cầu'),
        ('wrong_delivery', 'Giao sai, thiếu'),
        ('wrong_order', 'Lên đơn sai'),
    ]
    
    # Source ticket - nguồn tạo ticket
    SOURCE_CHOICES = [
        ('cskh_created', 'CSKH tạo'),
        ('customer_request', 'Khách request'),
        ('automation', 'Hệ thống tự tạo'),
    ]
    
    # Department - bộ phận xử lý
    DEPART_CHOICES = [
        ('cskh', 'CSKH'),
        ('warehouse', 'Kho'),
    ]
    
    # Core fields
    ticket_number = models.CharField(max_length=50, unique=True, db_index=True)  # Mã ticket tự động
    order_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # Sapo order ID
    order_code = models.CharField(max_length=50, blank=True, db_index=True)  # SON code
    reference_number = models.CharField(max_length=100, blank=True, db_index=True)  # Mã đơn sàn TMĐT

    # Đơn xử lý (order_process) - đơn hàng được tạo ra để xử lý vấn đề của đơn gốc
    process_order_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # Sapo order ID của đơn xử lý
    process_order_code = models.CharField(max_length=50, blank=True, db_index=True)  # SON code của đơn xử lý
    process_reference_number = models.CharField(max_length=100, blank=True, db_index=True)  # Mã đơn sàn của đơn xử lý
    
    # Order info (lưu từ order khi tạo ticket)
    customer_id = models.BigIntegerField(null=True, blank=True)
    customer_name = models.CharField(max_length=200, blank=True)
    customer_phone = models.CharField(max_length=50, blank=True)
    location_id = models.IntegerField(null=True, blank=True)  # Để biết kho nào
    shop = models.CharField(max_length=100, blank=True)  # Shop name
    
    # Variants issue - danh sách variant_id có vấn đề (JSON list)
    variants_issue = models.JSONField(default=list, blank=True)
    
    # Rating - đánh giá từ khách hàng (1-5 sao) - dùng cho ticket từ bad review
    rating = models.IntegerField(null=True, blank=True, db_index=True)  # 1-5 sao
    
    # Ticket metadata
    ticket_type = models.CharField(max_length=50, choices=TICKET_TYPE_CHOICES, blank=True)
    ticket_status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='new')
    source_ticket = models.CharField(max_length=50, choices=SOURCE_CHOICES, default='cskh_created')
    depart = models.CharField(max_length=50, choices=DEPART_CHOICES, default='cskh')
    
    # Reason - 2 cấp độ
    source_reason = models.CharField(max_length=100, blank=True)  # Lỗi kho, Lỗi sản phẩm, Lỗi vận chuyển, etc.
    reason_type = models.CharField(max_length=100, blank=True)  # gói thiếu, gói sai màu, vỡ, nứt, etc.
    
    # User tracking
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cskh_tickets_created')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cskh_tickets_assigned')
    
    # Người chịu trách nhiệm cho lỗi sai
    responsible_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cskh_tickets_responsible', verbose_name='Người chịu trách nhiệm')
    responsible_department = models.CharField(max_length=100, blank=True, verbose_name='Bộ phận chịu trách nhiệm')
    responsible_note = models.TextField(blank=True, verbose_name='Ghi chú trách nhiệm')
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    # Notes
    note = models.TextField(blank=True)
    
    # Images/Videos - lưu danh sách file paths
    images = models.JSONField(default=list, blank=True)  # List of file paths
    
    # Sugget process - hướng xử lý đề xuất cho ticket (JSON)
    # {
    #   "user_id": int,
    #   "user_name": str,
    #   "sugget_main": str,
    #   "description": str,
    #   "time": ISO datetime string
    # }
    sugget_process = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['ticket_status', '-created_at']),
            models.Index(fields=['order_id']),
            models.Index(fields=['order_code']),
            models.Index(fields=['reference_number']),
            models.Index(fields=['process_order_id']),
            models.Index(fields=['process_order_code']),
            models.Index(fields=['ticket_number']),
        ]
    
    def __str__(self):
        return f"Ticket {self.ticket_number} - {self.order_code or self.reference_number}"
    
    def save(self, *args, **kwargs):
        # Tự động tạo ticket_number nếu chưa có
        if not self.ticket_number:
            # Format: TK + số tự động (vd: TK0001, TK0002)
            last_ticket = Ticket.objects.order_by('-id').first()
            if last_ticket and last_ticket.ticket_number:
                try:
                    last_num = int(last_ticket.ticket_number.replace('TK', ''))
                    next_num = last_num + 1
                except:
                    next_num = 1
            else:
                next_num = 1
            self.ticket_number = f"TK{next_num:04d}"
        super().save(*args, **kwargs)


class TicketCost(models.Model):
    """
    Chi phí thiệt hại của ticket - có thể thêm nhiều cost
    """
    
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='costs')
    cost_type = models.CharField(max_length=100)  # Loại chi phí (từ settings)
    amount = models.DecimalField(max_digits=15, decimal_places=2)  # Số tiền thiệt hại (có thể chỉnh tay)
    note = models.TextField(blank=True)  # Ghi chú

    # Thông tin sản phẩm áp dụng cho các loại chi phí liên quan hàng hóa
    # Đặc biệt dùng cho loại "Hàng hỏng vỡ"
    variant_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    product_name = models.CharField(max_length=255, blank=True)
    variant_name = models.CharField(max_length=255, blank=True)
    sku = models.CharField(max_length=100, blank=True)
    quantity = models.IntegerField(null=True, blank=True)
    unit_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # Ngày thanh toán cho khoản chi phí này
    payment_date = models.DateField(null=True, blank=True, default=timezone.now)

    # Ảnh chứng từ (bill hoàn tiền, chứng minh thiệt hại...)
    # Lưu path relative từ thư mục static, vd: "billhoantien/20251126_....jpg"
    images = models.JSONField(default=list, blank=True)

    person = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)  # Người thêm cost
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Cost {self.cost_type} - {self.amount} for Ticket {self.ticket.ticket_number}"


class TicketReason(models.Model):
    """
    Model để lưu reason settings (có thể dùng để quản lý danh sách reason)
    Hoặc có thể dùng file settings thay vì model này
    """
    source_reason = models.CharField(max_length=100)  # Lỗi kho, Lỗi sản phẩm, etc.
    reason_type = models.CharField(max_length=100)  # gói thiếu, vỡ, etc.
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = [['source_reason', 'reason_type']]
        ordering = ['source_reason', 'reason_type']
    
    def __str__(self):
        return f"{self.source_reason} - {self.reason_type}"


class TicketEvent(models.Model):
    """
    Trouble & Event cho ticket.
    Lưu lại các lần làm việc với khách: nội dung, tags, thời gian, nhân viên.
    """
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='events')
    content = models.TextField()  # Nội dung event
    tags = models.CharField(max_length=255, blank=True)  # Ví dụ: 'Gọi điện, Chờ khách phản hồi'
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Event for {self.ticket.ticket_number} at {self.created_at}"

    @property
    def tag_list(self):
        """Trả về list các tag đã được strip, bỏ tag rỗng."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',') if t.strip()]


class TicketTransfer(models.Model):
    """
    Lưu lịch sử chuyển bộ phận xử lý của ticket (ví dụ: CSKH -> KHO).
    """
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='transfers')
    from_depart = models.CharField(max_length=50, choices=Ticket.DEPART_CHOICES)
    to_depart = models.CharField(max_length=50, choices=Ticket.DEPART_CHOICES)
    reason = models.CharField(max_length=255, blank=True)  # Ví dụ: 'Check lại thông tin', 'Hoả tốc ngoài sàn', ...
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Transfer {self.from_depart} -> {self.to_depart} for {self.ticket.ticket_number}"

class VariantImageCache(models.Model):
    """Cache image_url cho từng variant để tránh gọi API Sapo lặp lại."""
    variant_id = models.BigIntegerField(unique=True, db_index=True)
    image_url = models.URLField(max_length=500)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"VariantImageCache({self.variant_id})"


class TicketView(models.Model):
    """
    Theo dõi lần xem cuối của mỗi user cho mỗi ticket.
    Dùng để tính số event mới chưa xem.
    """
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='views')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ticket_views')
    last_viewed_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        unique_together = [['ticket', 'user']]
        indexes = [
            models.Index(fields=['ticket', 'user']),
            models.Index(fields=['user', '-last_viewed_at']),
        ]
    
    def __str__(self):
        return f"TicketView({self.ticket.ticket_number} by {self.user.username})"


class Feedback(models.Model):
    """
    Lưu reviews/feedbacks từ Shopee API.
    Sync trực tiếp từ Shopee API và lưu local để xử lý.
    """
    
    # IDs từ Shopee API
    comment_id = models.BigIntegerField(unique=True, db_index=True)  # Comment ID từ Shopee (duy nhất)
    connection_id = models.IntegerField(db_index=True)  # Shop connection ID
    
    # Legacy fields (giữ lại để tương thích với code cũ)
    feedback_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # Legacy: id từ Sapo MP (có thể null)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)  # Legacy: tenant_id từ Sapo MP
    cmt_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # Legacy: cmt_id (giữ lại để tương thích)
    item_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # Product item_id trên Shopee
    product_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # Product ID từ Shopee
    
    # Product info
    product_name = models.CharField(max_length=500, blank=True)
    product_image = models.URLField(max_length=500, blank=True)
    product_cover = models.CharField(max_length=200, blank=True)  # Product cover ID từ Shopee
    model_id = models.BigIntegerField(null=True, blank=True)  # Model ID từ Shopee
    model_name = models.CharField(max_length=500, blank=True)  # Model name từ Shopee
    
    # Order info
    channel_order_number = models.CharField(max_length=100, blank=True, db_index=True)  # order_sn từ Shopee
    order_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # Order ID từ Shopee
    
    # Customer info
    buyer_user_name = models.CharField(max_length=200, blank=True, db_index=True)  # user_name từ Shopee
    user_portrait = models.CharField(max_length=200, blank=True)  # user_portrait từ Shopee (avatar ID)
    user_id = models.BigIntegerField(null=True, blank=True)  # user_id từ Shopee
    
    # Rating & Comment
    rating = models.IntegerField(db_index=True)  # rating_star từ Shopee (1-5 sao)
    comment = models.TextField(blank=True)  # comment từ Shopee (nội dung đánh giá)
    images = models.JSONField(default=list, blank=True)  # images từ Shopee (list URLs hình ảnh/video)
    
    # Reply info
    status_reply = models.CharField(max_length=50, null=True, blank=True)  # Trạng thái phản hồi
    reply = models.TextField(null=True, blank=True)  # reply từ Shopee (nội dung phản hồi)
    reply_time = models.BigIntegerField(null=True, blank=True)  # Timestamp phản hồi
    user_reply = models.CharField(max_length=200, null=True, blank=True)  # User đã phản hồi
    reply_type = models.CharField(max_length=50, null=True, blank=True)
    
    # Additional fields from Shopee
    is_hidden = models.BooleanField(default=False)  # is_hidden từ Shopee
    status = models.IntegerField(null=True, blank=True)  # status từ Shopee
    can_follow_up = models.BooleanField(null=True, blank=True)  # can_follow_up từ Shopee
    follow_up = models.TextField(null=True, blank=True)  # follow_up từ Shopee
    submit_time = models.BigIntegerField(null=True, blank=True)  # submit_time từ Shopee
    low_rating_reasons = models.JSONField(default=list, blank=True)  # low_rating_reasons từ Shopee
    
    # Timestamps
    create_time = models.BigIntegerField(db_index=True)  # ctime từ Shopee (timestamp)
    ctime = models.BigIntegerField(null=True, blank=True, db_index=True)  # ctime từ Shopee
    mtime = models.BigIntegerField(null=True, blank=True)  # mtime từ Shopee
    created_at = models.DateTimeField(auto_now_add=True)  # Khi sync vào DB
    updated_at = models.DateTimeField(auto_now=True)  # Khi update từ Shopee
    
    # Linked data (sau khi xử lý)
    sapo_customer_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # Customer ID từ Sapo
    sapo_order_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # Order ID từ Sapo
    sapo_product_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # Product ID từ Sapo
    sapo_variant_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # Variant ID từ Sapo
    
    # Ticket link (nếu tạo ticket từ bad review)
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True, blank=True, related_name='cskh_feedbacks')
    
    # AI processing flags
    ai_processed_name = models.BooleanField(default=False)  # Đã xử lý tên bằng AI
    ai_processed_gender = models.BooleanField(default=False)  # Đã xử lý giới tính bằng AI
    ai_suggested_reply = models.TextField(blank=True)  # Gợi ý phản hồi từ AI
    ai_processed_at = models.DateTimeField(null=True, blank=True)  # Khi nào AI xử lý
    
    class Meta:
        ordering = ['-create_time']
        indexes = [
            models.Index(fields=['rating', '-create_time']),
            models.Index(fields=['connection_id', '-create_time']),
            models.Index(fields=['status_reply', '-create_time']),
            models.Index(fields=['buyer_user_name']),
            models.Index(fields=['channel_order_number']),
            models.Index(fields=['comment_id']),  # Unique index cho comment_id
        ]
    
    def __str__(self):
        comment_id_str = str(self.comment_id) if self.comment_id else "N/A"
        return f"Feedback {comment_id_str} - {self.buyer_user_name} - {self.rating}*"
    
    @property
    def is_replied(self) -> bool:
        """Kiểm tra đã phản hồi chưa"""
        return bool(self.reply and self.status_reply)
    
    @property
    def is_good_review(self) -> bool:
        """Đánh giá tốt (5 sao)"""
        return self.rating == 5
    
    @property
    def is_bad_review(self) -> bool:
        """Đánh giá xấu (1-4 sao)"""
        return 1 <= self.rating <= 4
    
    @property
    def shop_name(self) -> str:
        """Lấy tên shop từ connection_id"""
        from core.system_settings import get_shop_by_connection_id
        shop = get_shop_by_connection_id(self.connection_id)
        return shop.get('name', f'Shop {self.connection_id}') if shop else f'Shop {self.connection_id}'


class FeedbackLog(models.Model):
    """
    Lưu logs về việc xử lý feedbacks: ai đã phản hồi, khi nào, nội dung gì.
    Dùng để track KPI và lịch sử xử lý.
    """
    
    feedback = models.ForeignKey(Feedback, on_delete=models.CASCADE, related_name='logs')
    action_type = models.CharField(max_length=50, db_index=True)  # 'reply', 'create_ticket', 'ai_process', 'update_customer'
    action_data = models.JSONField(default=dict, blank=True)  # Dữ liệu chi tiết của action
    
    # User tracking
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    user_name = models.CharField(max_length=200, blank=True)  # Lưu tên user để backup
    
    # Rating tracking (để track KPI khi khách thay đổi đánh giá)
    rating_before = models.IntegerField(null=True, blank=True)  # Rating trước khi xử lý
    rating_after = models.IntegerField(null=True, blank=True)  # Rating sau khi xử lý (nếu có)
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    
    # Notes
    note = models.TextField(blank=True)  # Ghi chú thêm
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['feedback', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action_type', '-created_at']),
        ]
    
    def __str__(self):
        return f"FeedbackLog {self.action_type} for Feedback {self.feedback.feedback_id} by {self.user_name or 'System'}"
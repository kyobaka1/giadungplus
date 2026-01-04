from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from typing import Optional
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
        ('waiting_cskh', 'Chờ CSKH xử lý'),
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
    feedback_id = models.BigIntegerField(unique=True, db_index=True)  # Feedback ID = comment_id từ Shopee (key chính, duy nhất)
    connection_id = models.IntegerField(db_index=True)  # Shop connection ID
    
    # Legacy fields (giữ lại để tương thích với code cũ)
    comment_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # Comment ID từ Shopee (giữ lại để tương thích, không unique)
    tenant_id = models.IntegerField(null=True, blank=True, db_index=True)  # Legacy: tenant_id từ Sapo MP (không có từ Shopee API)
    item_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # Product item_id trên Shopee
    product_id = models.BigIntegerField(null=True, blank=True, db_index=True)  # Product ID từ Shopee
    
    # Product info
    product_name = models.CharField(max_length=1000, blank=True)  # Tăng từ 500 lên 1000
    product_image = models.URLField(max_length=500, blank=True)
    product_cover = models.CharField(max_length=200, blank=True)  # Product cover ID từ Shopee
    model_id = models.BigIntegerField(null=True, blank=True)  # Model ID từ Shopee
    model_name = models.TextField(blank=True)  # Model name từ Shopee - dùng TextField vì có thể rất dài
    
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
            models.Index(fields=['feedback_id']),  # Unique index cho feedback_id (key chính)
        ]
    
    def __str__(self):
        feedback_id_str = str(self.feedback_id) if self.feedback_id else "N/A"
        return f"Feedback {feedback_id_str} - {self.buyer_user_name} - {self.rating}*"
    
    @property
    def is_replied(self) -> bool:
        """Kiểm tra đã phản hồi chưa"""
        return bool(self.reply and self.status_reply)
    
    @property
    def reply_datetime(self):
        """Convert reply_time (timestamp) sang datetime object"""
        # Thử lấy từ reply_time field trước
        reply_time_value = self.reply_time
        
        # Nếu không có, thử extract từ reply field (cho dữ liệu cũ)
        if not reply_time_value and self.reply:
            reply_time_value = self._extract_reply_time_from_reply_field()
        
        if reply_time_value:
            try:
                from datetime import datetime
                return datetime.fromtimestamp(reply_time_value, tz=timezone.get_current_timezone())
            except (ValueError, OSError):
                return None
        return None
    
    def _extract_reply_time_from_reply_field(self):
        """Extract ctime từ reply field nếu reply_time chưa được lưu riêng"""
        if not self.reply:
            return None
        
        reply_value = self.reply
        
        # Nếu là string, thử parse JSON hoặc dict string
        if isinstance(reply_value, str):
            if reply_value.strip().startswith("{") or reply_value.strip().startswith("'"):
                try:
                    import json
                    parsed = json.loads(reply_value)
                    if isinstance(parsed, dict):
                        ctime = parsed.get("ctime")
                        if ctime:
                            try:
                                return int(ctime)
                            except (ValueError, TypeError):
                                return None
                except (json.JSONDecodeError, ValueError, TypeError):
                    try:
                        import ast
                        parsed = ast.literal_eval(reply_value)
                        if isinstance(parsed, dict):
                            ctime = parsed.get("ctime")
                            if ctime:
                                try:
                                    return int(ctime)
                                except (ValueError, TypeError):
                                    return None
                    except (ValueError, SyntaxError, TypeError):
                        pass
        
        # Nếu là dict (ít khi xảy ra)
        if isinstance(reply_value, dict):
            ctime = reply_value.get("ctime")
            if ctime:
                try:
                    return int(ctime)
                except (ValueError, TypeError):
                    return None
        
        return None
    
    @property
    def reply_duration(self):
        """
        Tính thời gian từ khi đánh giá (create_time) đến khi shop phản hồi (reply_time).
        Trả về string format: "X ngày Y giờ" hoặc "X ngày" hoặc "Y giờ"
        
        Sau khi migrate, reply_time đã được lưu riêng, không cần extract từ reply field nữa.
        Nhưng vẫn giữ logic extract để tương thích với dữ liệu cũ chưa migrate.
        """
        # Ưu tiên dùng reply_time field trước (dữ liệu mới)
        reply_time_value = self.reply_time
        
        # Nếu chưa có reply_time, thử extract từ reply field (dữ liệu cũ)
        if not reply_time_value and self.reply:
            reply_time_value = self._extract_reply_time_from_reply_field()
        
        if not reply_time_value or not self.create_time:
            return None
        
        try:
            from datetime import datetime, timedelta
            create_dt = datetime.fromtimestamp(self.create_time, tz=timezone.get_current_timezone())
            reply_dt = datetime.fromtimestamp(reply_time_value, tz=timezone.get_current_timezone())
            
            duration = reply_dt - create_dt
            
            if duration.total_seconds() < 0:
                return None  # Reply trước khi đánh giá (không hợp lý)
            
            days = duration.days
            hours = duration.seconds // 3600
            
            if days > 0:
                if hours > 0:
                    return f"{days} ngày {hours} giờ"
                else:
                    return f"{days} ngày"
            else:
                if hours > 0:
                    return f"{hours} giờ"
                else:
                    minutes = duration.seconds // 60
                    if minutes > 0:
                        return f"{minutes} phút"
                    else:
                        return "Vừa xong"
        except (ValueError, OSError, TypeError):
            return None
    
    @property
    def reply_comment(self):
        """
        Extract comment từ reply field.
        Sau khi migrate, reply field chỉ chứa text (comment), không còn JSON/dict nữa.
        Nhưng vẫn giữ logic extract để tương thích với dữ liệu cũ chưa migrate.
        """
        if not self.reply:
            return ""
        
        reply_value = self.reply
        
        # Nếu là string, kiểm tra xem có phải là JSON/dict string không
        if isinstance(reply_value, str):
            # Nếu không bắt đầu bằng { hoặc ', có thể đã là text thuần (dữ liệu mới)
            if not (reply_value.strip().startswith("{") or reply_value.strip().startswith("'") or reply_value.strip().startswith('"')):
                # Dữ liệu mới: reply đã là text thuần
                return reply_value
            
            # Dữ liệu cũ: thử parse JSON hoặc dict string
            try:
                import json
                parsed = json.loads(reply_value)
                if isinstance(parsed, dict):
                    return parsed.get("comment", "") or ""
            except (json.JSONDecodeError, ValueError, TypeError):
                # Thử parse dict string (Python representation)
                try:
                    import ast
                    parsed = ast.literal_eval(reply_value)
                    if isinstance(parsed, dict):
                        return parsed.get("comment", "") or ""
                except (ValueError, SyntaxError, TypeError):
                    pass
            # Nếu không parse được, trả về string gốc
            return reply_value
        
        # Nếu là dict (ít khi xảy ra vì TextField lưu string)
        if isinstance(reply_value, dict):
            return reply_value.get("comment", "") or ""
        
        return str(reply_value) if reply_value else ""
    
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
    
    @property
    def shop_logo(self) -> str:
        """Lấy đường dẫn logo shop từ connection_id"""
        shop_name = self.shop_name
        shop_lower = shop_name.lower()
        
        if 'lteng' in shop_lower:
            return '/static/logo-lteng.jpg'
        elif 'phaledo' in shop_lower:
            return '/static/logo-phaledo.jpg'
        else:
            return '/static/giaodiensang.png'


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


class FeedbackSyncJob(models.Model):
    """
    Lưu trạng thái và tiến trình của sync job.
    Dùng để track progress của full sync và incremental sync.
    """
    STATUS_CHOICES = [
        ('pending', 'Chờ xử lý'),
        ('running', 'Đang chạy'),
        ('completed', 'Hoàn thành'),
        ('failed', 'Thất bại'),
        ('paused', 'Tạm dừng'),
    ]
    
    SYNC_TYPE_CHOICES = [
        ('full', 'Full Sync - Sync toàn bộ'),
        ('incremental', 'Incremental Sync - Cập nhật mới'),
    ]
    
    # Basic info
    sync_type = models.CharField(max_length=20, choices=SYNC_TYPE_CHOICES, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    
    # Progress tracking
    total_shops = models.IntegerField(default=0)
    current_shop_index = models.IntegerField(default=0)
    current_shop_name = models.CharField(max_length=200, blank=True)
    
    total_feedbacks = models.IntegerField(default=0)  # Tổng số feedbacks cần sync
    processed_feedbacks = models.IntegerField(default=0)  # Đã xử lý
    synced_feedbacks = models.IntegerField(default=0)  # Đã sync thành công
    updated_feedbacks = models.IntegerField(default=0)  # Đã update
    error_count = models.IntegerField(default=0)
    
    # Shop progress (JSON): {shop_name: {processed, synced, updated, errors}}
    shop_progress = models.JSONField(default=dict, blank=True)
    
    # Current position để resume
    current_connection_id = models.IntegerField(null=True, blank=True)
    current_page = models.IntegerField(default=1)
    current_cursor = models.BigIntegerField(null=True, blank=True)
    last_processed_feedback_id = models.BigIntegerField(null=True, blank=True)
    
    # Time tracking
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_updated_at = models.DateTimeField(auto_now=True)
    
    # Error logs
    errors = models.JSONField(default=list, blank=True)  # List of error messages
    logs = models.JSONField(default=list, blank=True)  # List of log messages (last 1000)
    
    # Settings
    days = models.IntegerField(null=True, blank=True, default=None)  # Số ngày gần nhất (None = không giới hạn)
    page_size = models.IntegerField(default=50)
    max_feedbacks_per_shop = models.IntegerField(null=True, blank=True)  # None = không giới hạn
    
    # Incremental sync specific
    batch_size = models.IntegerField(default=50)  # Số feedbacks mỗi batch cho incremental
    
    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['status', '-started_at']),
            models.Index(fields=['sync_type', '-started_at']),
        ]
    
    def __str__(self):
        return f"FeedbackSyncJob {self.id} - {self.get_sync_type_display()} - {self.get_status_display()}"
    
    @property
    def progress_percentage(self) -> float:
        """Tính phần trăm hoàn thành"""
        if self.total_feedbacks == 0:
            return 0.0
        return (self.processed_feedbacks / self.total_feedbacks) * 100
    
    @property
    def duration(self) -> Optional[timedelta]:
        """Tính thời gian đã chạy"""
        if not self.started_at:
            return None
        end_time = self.completed_at or timezone.now()
        return end_time - self.started_at


class TrainingDocument(models.Model):
    """
    Tài liệu training nội bộ cho CSKH.
    Nội dung được lưu dưới dạng file Markdown trong thư mục settings/logs/train_cskh/,
    model này chỉ lưu metadata để quản lý.
    """

    title = models.CharField(max_length=255, help_text="Tên hiển thị của tài liệu")
    filename = models.CharField(
        max_length=255,
        unique=True,
        help_text="Tên file .md được lưu trong settings/logs/train_cskh/",
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="training_documents",
    )
    uploaded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title or self.filename
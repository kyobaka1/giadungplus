from django.db import models
from django.utils import timezone


class GiftRule(models.Model):
    """
    Quy tắc quà tặng/khuyến mãi.
    Scope:
    - 'order': Điều kiện theo tổng giá trị đơn hàng
    - 'line': Điều kiện theo sản phẩm cụ thể
    """
    SCOPE_CHOICES = [
        ('order', 'Theo đơn hàng'),
        ('line', 'Theo sản phẩm'),
    ]

    # Thông tin cơ bản
    name = models.CharField(max_length=255, verbose_name="Tên chương trình")
    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        verbose_name="Phạm vi áp dụng"
    )

    # Điều kiện theo shop
    shop_code = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Mã shop (optional)"
    )

    # Order-level conditions (áp dụng khi scope='order')
    min_order_total = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="Giá trị đơn tối thiểu (đồng)",
        help_text="Giá trị đơn hàng tối thiểu (VNĐ) khi scope='order'"
    )
    max_order_total = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="Giá trị đơn tối đa (đồng)",
        help_text="Giá trị đơn hàng tối đa (VNĐ) khi scope='order'"
    )

    # Line-level conditions (áp dụng khi scope='line')
    required_variant_ids = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Variant IDs sản phẩm yêu cầu",
        help_text="Danh sách IDs của variants (JSON array)"
    )
    required_min_qty = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Số lượng tối thiểu",
        help_text="Số lượng sản phẩm tối thiểu khi scope='line'"
    )
    required_max_qty = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Số lượng tối đa",
        help_text="Số lượng sản phẩm tối đa khi scope='line'"
    )

    # Quản lý trạng thái
    priority = models.IntegerField(
        default=0,
        verbose_name="Độ ưu tiên (số càng cao càng ưu tiên)"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Đang hoạt động"
    )
    start_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Thời gian bắt đầu"
    )
    end_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Thời gian kết thúc"
    )
    stop_further = models.BooleanField(
        default=False,
        verbose_name="Dừng xét rule khác sau khi áp dụng"
    )

    # Audit fields
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['is_active', '-priority']),
            models.Index(fields=['shop_code']),
        ]
        verbose_name = "Gift Rule"
        verbose_name_plural = "Gift Rules"

    def __str__(self):
        return f"{self.name} ({self.get_scope_display()})"

    def is_currently_active(self):
        """Check if rule is active and within time range"""
        if not self.is_active:
            return False
        
        now = timezone.now()
        if self.start_at and now < self.start_at:
            return False
        if self.end_at and now > self.end_at:
            return False
        
        return True


class GiftRuleGift(models.Model):
    """
    Quà tặng thuộc về một GiftRule.
    Một rule có thể có nhiều loại quà.
    """
    rule = models.ForeignKey(
        GiftRule,
        on_delete=models.CASCADE,
        related_name='gifts',
        verbose_name="Gift Rule"
    )
    gift_variant_id = models.BigIntegerField(
        verbose_name="Variant ID của quà tặng"
    )
    gift_qty = models.IntegerField(
        default=1,
        verbose_name="Số lượng quà tặng"
    )
    match_quantity = models.BooleanField(
        default=False,
        verbose_name="Tặng theo số lượng mua (1:1)",
        help_text="Nếu True, số lượng quà = số lượng sản phẩm mua. Nếu False, số lượng quà cố định."
    )

    class Meta:
        verbose_name = "Gift"
        verbose_name_plural = "Gifts"

    def __str__(self):
        qty_display = f"x{self.gift_qty}" if not self.match_quantity else "x1:1"
        return f"Gift: Variant {self.gift_variant_id} {qty_display} (Rule: {self.rule.name})"


class VariantTag(models.Model):
    """
    Quản lý tags cho variants (plan_tags).
    Mỗi tag có tên tiếng Việt và màu sắc để hiển thị.
    """
    tags_name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Tên tag (tiếng Việt)",
        help_text="Ví dụ: Đang đẩy mạnh, Duy trì ổn định, Xả kho gấp..."
    )
    
    color = models.CharField(
        max_length=50,
        default="blue",
        verbose_name="Màu sắc",
        help_text="Màu sắc để hiển thị tag (blue, green, red, yellow, orange, purple, gray, pink)"
    )
    
    # Audit fields
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['tags_name']
        verbose_name = "Variant Tag"
        verbose_name_plural = "Variant Tags"
    
    def __str__(self):
        return self.tags_name
    
    def get_color_classes(self):
        """Trả về các class Tailwind CSS tương ứng với màu"""
        color_map = {
            'blue': 'bg-blue-100 text-blue-800 border-blue-200',
            'green': 'bg-green-100 text-green-800 border-green-200',
            'red': 'bg-red-100 text-red-800 border-red-200',
            'yellow': 'bg-yellow-100 text-yellow-800 border-yellow-200',
            'orange': 'bg-orange-100 text-orange-800 border-orange-200',
            'purple': 'bg-purple-100 text-purple-800 border-purple-200',
            'gray': 'bg-gray-100 text-gray-800 border-gray-200',
            'pink': 'bg-pink-100 text-pink-800 border-pink-200',
        }
        return color_map.get(self.color, 'bg-blue-100 text-blue-800 border-blue-200')
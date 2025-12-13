# products/models.py
"""
Django models cho products app.
"""

from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal


class VariantSalesForecast(models.Model):
    """
    Lưu trữ dự báo bán hàng cho variant.
    Thay thế việc lưu trong Sapo product description (GDP_META).
    """
    variant_id = models.BigIntegerField(
        db_index=True,
        help_text="Variant ID từ Sapo"
    )
    period_days = models.IntegerField(
        default=7,
        help_text="Số ngày tính toán (ví dụ: 7, 14, 30)"
    )
    
    # Dữ liệu kỳ hiện tại
    total_sold = models.IntegerField(
        default=0,
        help_text="Tổng lượt bán kỳ hiện tại (x ngày gần nhất)"
    )
    
    # Dữ liệu kỳ trước (cùng kỳ)
    total_sold_previous_period = models.IntegerField(
        default=0,
        help_text="Tổng lượt bán kỳ trước (x ngày cùng kỳ)"
    )
    
    # Tính toán
    sales_rate = models.FloatField(
        default=0.0,
        help_text="Tốc độ bán (số lượng/ngày)"
    )
    growth_percentage = models.FloatField(
        null=True,
        blank=True,
        help_text="% tăng trưởng so với kỳ trước"
    )
    
    # ABC Analysis (chỉ tính cho period_days=30)
    ABC_CATEGORY_CHOICES = [
        ('A', 'Nhóm A (70-80% doanh thu)'),
        ('B', 'Nhóm B (15-25% doanh thu)'),
        ('C', 'Nhóm C (5-10% doanh thu)'),
    ]
    abc_category = models.CharField(
        max_length=1,
        choices=ABC_CATEGORY_CHOICES,
        null=True,
        blank=True,
        db_index=True,
        help_text="Phân loại ABC (chỉ có khi period_days=30)"
    )
    revenue = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        null=True,
        blank=True,
        help_text="Tổng doanh thu (line_amount) - chỉ tính cho period_days=30"
    )
    revenue_percentage = models.FloatField(
        null=True,
        blank=True,
        help_text="% doanh thu trên tổng doanh thu (chỉ có khi period_days=30)"
    )
    cumulative_percentage = models.FloatField(
        null=True,
        blank=True,
        help_text="% tích lũy cộng dồn (chỉ có khi period_days=30)"
    )
    abc_rank = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Thứ tự xếp hạng theo doanh thu (1 = cao nhất, chỉ có khi period_days=30)"
    )
    
    # Priority Score fields (chỉ tính cho period_days=30)
    priority_score = models.FloatField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Điểm ưu tiên (0-10) = 45% Velocity Stability + 30% ASP + 25% Revenue Contribution"
    )
    velocity_stability_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Velocity Stability Score (0-12) = VelocityScore + Stability Bonus"
    )
    velocity_score = models.IntegerField(
        null=True,
        blank=True,
        help_text="Velocity Score (2, 4, 6, 8, 10) dựa trên phân vị tốc độ bán"
    )
    stability_bonus = models.IntegerField(
        null=True,
        blank=True,
        help_text="Stability Bonus (0, 1, 2) dựa trên so sánh cùng kỳ 7 ngày"
    )
    asp_score = models.IntegerField(
        null=True,
        blank=True,
        help_text="ASP Score (2, 4, 6, 8, 10) dựa trên phân vị giá trị SKU"
    )
    revenue_contribution_score = models.IntegerField(
        null=True,
        blank=True,
        help_text="Revenue Contribution Score (4, 7, 10) từ nhóm ABC"
    )
    
    # Metadata
    calculated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Thời điểm tính toán"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Thời điểm tạo record"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Thời điểm cập nhật cuối"
    )
    
    class Meta:
        db_table = 'products_variant_sales_forecast'
        verbose_name = 'Variant Sales Forecast'
        verbose_name_plural = 'Variant Sales Forecasts'
        # Unique constraint: mỗi variant chỉ có 1 forecast cho mỗi period_days
        unique_together = [['variant_id', 'period_days']]
        indexes = [
            models.Index(fields=['variant_id', 'period_days']),
            models.Index(fields=['calculated_at']),
            models.Index(fields=['-updated_at']),  # Descending để query mới nhất trước
            models.Index(fields=['abc_category']),
            models.Index(fields=['abc_rank']),
            models.Index(fields=['priority_score']),
        ]
    
    def __str__(self):
        return f"Variant {self.variant_id} - {self.period_days} days - Sold: {self.total_sold}"
    
    def calculate_growth(self):
        """Tính % tăng trưởng"""
        if self.total_sold_previous_period > 0:
            self.growth_percentage = ((self.total_sold - self.total_sold_previous_period) / self.total_sold_previous_period) * 100
        elif self.total_sold > 0 and self.total_sold_previous_period == 0:
            self.growth_percentage = 100.0  # Tăng 100% (từ 0 lên có bán)
        else:
            self.growth_percentage = 0.0
        return self.growth_percentage


class ContainerTemplate(models.Model):
    """
    Template container (INIT CONTAINER) - Mẫu container để tái sử dụng.
    """
    # Thông tin cơ bản
    code = models.CharField(max_length=50, unique=True, db_index=True, help_text="Mã container (ví dụ: CONT-01)")
    name = models.CharField(max_length=200, blank=True, help_text="Tên container (tùy chọn)")
    
    # Kích thước container
    CONTAINER_TYPE_CHOICES = [
        ("40ft", "40 feet"),
        ("20ft", "20 feet"),
    ]
    container_type = models.CharField(
        max_length=20,
        choices=CONTAINER_TYPE_CHOICES,
        default="40ft",
        help_text="Loại container"
    )
    volume_cbm = models.FloatField(default=65.0, help_text="Mét khối (mặc định 65 CBM cho 40ft)")
    
    # Nhà sản xuất đóng container (mặc định)
    default_supplier_id = models.BigIntegerField(null=True, blank=True, help_text="Sapo supplier_id")
    default_supplier_code = models.CharField(max_length=100, blank=True, help_text="Mã NSX (ví dụ: ShuangQing)")
    default_supplier_name = models.CharField(max_length=200, blank=True, help_text="Tên NSX")
    
    # Thời gian vận chuyển (ngày)
    ship_time_avg_hn = models.IntegerField(default=0, help_text="TQ -> Hà Nội (ngày)")
    ship_time_avg_hcm = models.IntegerField(default=0, help_text="TQ -> Hồ Chí Minh (ngày)")
    
    # Cảng xuất
    departure_port = models.CharField(max_length=100, blank=True, help_text="Ningbo, Shanghai...")
    
    # Chu kỳ nhập hàng (tính toán tự động sau)
    avg_import_cycle_days = models.IntegerField(null=True, blank=True, help_text="Ngày/1 lần nhập (tính toán tự động)")
    
    # Giá trị đơn trung bình (dự kiến tài chính)
    avg_total_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0, 
        help_text="Giá trị dự kiến của container (để dự trù tài chính)"
    )
    
    # Metadata
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'products_container_template'
        verbose_name = 'Container Template'
        verbose_name_plural = 'Container Templates'
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name or 'N/A'}"


class ContainerTemplateSupplier(models.Model):
    """
    Quan hệ nhiều-nhiều: Container Template <-> Suppliers.
    Mỗi NSX có thể đóng hàng tại nhiều INIT CONTAINER.
    """
    container_template = models.ForeignKey(
        ContainerTemplate,
        on_delete=models.CASCADE,
        related_name='suppliers'
    )
    supplier_id = models.BigIntegerField(db_index=True, help_text="Sapo supplier_id")
    supplier_code = models.CharField(max_length=100)
    supplier_name = models.CharField(max_length=200)
    supplier_logo_path = models.CharField(max_length=500, blank=True, help_text="Logo URL")
    
    # Thứ tự ưu tiên (nếu cần)
    priority = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'products_container_template_supplier'
        unique_together = [['container_template', 'supplier_id']]
        indexes = [
            models.Index(fields=['container_template', 'supplier_id']),
            models.Index(fields=['supplier_id']),
        ]
    
    def __str__(self):
        return f"{self.container_template.code} - {self.supplier_name}"


class SumPurchaseOrder(models.Model):
    """
    Đợt nhập container - Gộp nhiều PO vào 1 container.
    """
    # Thông tin cơ bản
    code = models.CharField(max_length=50, unique=True, db_index=True, help_text="SPO-2025-001")
    name = models.CharField(max_length=200, blank=True, help_text="Tên đợt nhập (tùy chọn)")
    
    # Container template
    container_template = models.ForeignKey(
        ContainerTemplate,
        on_delete=models.PROTECT,
        related_name='sum_purchase_orders'
    )
    
    # Trạng thái
    STATUS_CHOICES = [
        ('draft', 'Nháp'),
        ('created', 'Tạo SPO'),
        ('sent_to_supplier', 'Gửi đơn NSX'),
        ('packed', 'Đóng container'),
        ('departed_cn', 'Tàu rời cảng'),
        ('arrived_vn', 'Tàu tới HCM/HN'),
        ('completed', 'Hoàn tất'),
        ('cancelled', 'Đã hủy'),
    ]
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='draft')
    
    # Cảng đến và ngày dự kiến
    DESTINATION_PORT_CHOICES = [
        ('hcm', 'Hồ Chí Minh'),
        ('haiphong', 'Hải Phòng'),
    ]
    destination_port = models.CharField(
        max_length=20, 
        choices=DESTINATION_PORT_CHOICES, 
        blank=True, 
        null=True,
        help_text="Cảng đến (Hồ Chí Minh hoặc Hải Phòng)"
    )
    expected_arrival_date = models.DateField(
        blank=True, 
        null=True,
        help_text="Dự kiến ngày hàng về (phải cách ngày lên đơn tối thiểu 12 ngày)"
    )
    created_date = models.DateField(
        blank=True,
        null=True,
        help_text="Ngày tạo SPO (có thể điền thủ công)"
    )
    
    # Tracking Timeline (JSON)
    # Format: [{"stage": "created", "planned_date": "2025-01-01", "actual_date": "2025-01-02", "note": "..."}, ...]
    timeline = models.JSONField(default=list, blank=True)
    
    # Chi phí chung (phân bổ theo CBM)
    shipping_cn_vn = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Vận chuyển TQ-VN")
    customs_processing_vn = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Xử lý Hải Quan VN")
    other_costs = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Phí phát sinh")
    port_to_warehouse = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Cảng -> kho")
    loading_unloading = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Bốc xếp")
    
    # Tổng CBM của container (để phân bổ chi phí)
    total_cbm = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Thông tin tàu và tracking
    ship_name = models.CharField(max_length=200, blank=True, help_text="Tên tàu")
    ship_tracking_link = models.URLField(max_length=500, blank=True, help_text="Link tracking vị trí tàu")
    
    # Metadata
    tags = models.JSONField(default=list, blank=True, help_text="Tags từ Sapo PO (ví dụ: ['TEMP_HCM'])")
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'products_sum_purchase_order'
        verbose_name = 'Sum Purchase Order'
        verbose_name_plural = 'Sum Purchase Orders'
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['status']),
            models.Index(fields=['container_template']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.get_status_display()}"
    
    def update_status(self, new_status: str, actual_date=None, note: str = ""):
        """Cập nhật trạng thái và log vào timeline"""
        if actual_date is None:
            actual_date = timezone.now()
        
        # Tìm stage trong timeline
        stage_found = False
        for stage in self.timeline:
            if stage.get('stage') == new_status:
                stage['actual_date'] = actual_date.isoformat()
                if note:
                    stage['note'] = note
                stage_found = True
                break
        
        # Nếu chưa có trong timeline, thêm mới
        if not stage_found:
            self.timeline.append({
                'stage': new_status,
                'planned_date': None,
                'actual_date': actual_date.isoformat(),
                'note': note
            })
        
        self.status = new_status
        self.save()


class PurchaseOrder(models.Model):
    """
    Purchase Order (PO) - Độc lập, không phụ thuộc vào SPO.
    Mỗi PO có thể được chuyển giữa các SPO mà vẫn giữ nguyên thông tin.
    """
    # Liên kết với Sapo
    sapo_order_supplier_id = models.BigIntegerField(
        unique=True,
        db_index=True,
        help_text="Sapo order_supplier.id (unique để đảm bảo mỗi PO chỉ có 1 record)"
    )
    
    # Thông tin cơ bản từ Sapo (snapshot)
    sapo_code = models.CharField(max_length=100, blank=True, help_text="Mã PO từ Sapo")
    supplier_id = models.BigIntegerField(db_index=True, help_text="Sapo supplier_id")
    supplier_name = models.CharField(max_length=200, blank=True)
    supplier_code = models.CharField(max_length=100, blank=True)
    
    # Trạng thái giao hàng
    DELIVERY_STATUS_CHOICES = [
        ('ordered', 'Lên đơn'),
        ('sent_label', 'Gửi đơn & Label'),
        ('production', 'Sản xuất'),
        ('delivered', 'Giao hàng'),
    ]
    delivery_status = models.CharField(
        max_length=50,
        choices=DELIVERY_STATUS_CHOICES,
        default='ordered',
        help_text="Trạng thái giao hàng của PO"
    )
    
    # Dự kiến giao hàng (để sắp xếp với lịch đóng container)
    expected_delivery_date = models.DateField(
        null=True,
        blank=True,
        help_text="Dự kiến giao hàng (để sắp xếp với lịch đóng container)"
    )
    
    # Timeline giao hàng (JSON)
    # Format: [{"status": "ordered", "date": "2025-01-01", "note": "..."}, ...]
    delivery_timeline = models.JSONField(default=list, blank=True)
    
    # Tiền hàng (CNY) - Match với giá mua trung quốc từ variants
    product_amount_cny = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Tiền hàng (CNY) - tính từ giá mua trung quốc của variants"
    )
    
    # Tổng cần thanh toán (CNY) = product_amount + costs
    total_amount_cny = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Tổng cần thanh toán (CNY) = tiền hàng + chi phí"
    )
    
    # Số tiền đã thanh toán (CNY) - tính từ các payment records
    paid_amount_cny = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Số tiền đã thanh toán (CNY) - tự động tính từ payments"
    )
    
    # Metadata
    note = models.TextField(blank=True, help_text="Ghi chú cho PO")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'products_purchase_order'
        verbose_name = 'Purchase Order'
        verbose_name_plural = 'Purchase Orders'
        indexes = [
            models.Index(fields=['sapo_order_supplier_id']),
            models.Index(fields=['supplier_id']),
            models.Index(fields=['delivery_status']),
            models.Index(fields=['expected_delivery_date']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"PO-{self.sapo_order_supplier_id} ({self.sapo_code or 'N/A'})"
    
    def update_delivery_status(self, new_status: str, date=None, note: str = ""):
        """Cập nhật trạng thái giao hàng và log vào timeline"""
        if date is None:
            date = timezone.now().date()
        
        # Thêm vào timeline
        self.delivery_timeline.append({
            'status': new_status,
            'date': date.isoformat(),
            'note': note
        })
        
        self.delivery_status = new_status
        if new_status == 'delivered' and not self.expected_delivery_date:
            self.expected_delivery_date = date
        self.save()
    
    def calculate_total_amount(self):
        """Tính tổng cần thanh toán = tiền hàng + tổng chi phí"""
        total_costs = sum(
            cost.amount_cny for cost in self.costs.all()
        )
        self.total_amount_cny = self.product_amount_cny + Decimal(str(total_costs))
        self.save()
        return self.total_amount_cny
    
    def calculate_paid_amount(self):
        """Tính tổng đã thanh toán từ các payment records"""
        total_paid = sum(
            payment.amount_cny for payment in self.payments.all()
        )
        self.paid_amount_cny = Decimal(str(total_paid))
        self.save()
        return self.paid_amount_cny


class SPOPurchaseOrder(models.Model):
    """
    Quan hệ many-to-many giữa SPO và PO.
    Cho phép chuyển PO giữa các SPO mà vẫn giữ nguyên thông tin PO.
    """
    # Liên kết với SPO
    sum_purchase_order = models.ForeignKey(
        SumPurchaseOrder,
        on_delete=models.CASCADE,
        related_name='spo_purchase_orders'
    )
    
    # Liên kết với PO (độc lập)
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='spo_relations'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'products_spo_purchase_order'
        verbose_name = 'SPO Purchase Order'
        verbose_name_plural = 'SPO Purchase Orders'
        unique_together = [['sum_purchase_order', 'purchase_order']]
        indexes = [
            models.Index(fields=['sum_purchase_order', 'purchase_order']),
            models.Index(fields=['purchase_order']),
        ]
    
    def __str__(self):
        return f"SPO-{self.sum_purchase_order_id} - PO-{self.purchase_order.sapo_order_supplier_id}"


class PurchaseOrderCost(models.Model):
    """
    Chi phí cho PO (nhân dân tệ).
    Các loại: Giao hàng nội địa TQ, phí đóng hàng, chi phí khác.
    Phân bổ theo mét khối (CBM).
    """
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='costs'
    )
    
    # Loại chi phí
    COST_TYPE_CHOICES = [
        ('domestic_shipping_cn', 'Giao hàng nội địa TQ'),
        ('packing_fee', 'Phí đóng hàng'),
        ('other', 'Chi phí khác'),
    ]
    cost_type = models.CharField(
        max_length=50,
        choices=COST_TYPE_CHOICES,
        default='other'
    )
    
    # Số tiền (CNY)
    amount_cny = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    
    # Phân bổ theo CBM (nếu có)
    cbm = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Mét khối (CBM) để phân bổ chi phí"
    )
    
    # Mô tả
    description = models.CharField(
        max_length=500,
        blank=True,
        help_text="Mô tả chi phí"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'products_purchase_order_cost'
        verbose_name = 'Purchase Order Cost'
        verbose_name_plural = 'Purchase Order Costs'
        indexes = [
            models.Index(fields=['purchase_order']),
            models.Index(fields=['cost_type']),
        ]
    
    def __str__(self):
        return f"{self.get_cost_type_display()} - {self.amount_cny} CNY (PO-{self.purchase_order.sapo_order_supplier_id})"


class PurchaseOrderPayment(models.Model):
    """
    Thanh toán cho PO (NSX).
    Lưu thông tin thanh toán: loại, số tiền (CNY), số tiền VNĐ, tỷ giá.
    Liên kết với BalanceTransaction để trừ từ số dư.
    """
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='payments'
    )
    
    # Liên kết với giao dịch số dư (tự động tạo khi thanh toán)
    balance_transaction = models.OneToOneField(
        'BalanceTransaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='po_payment_link',
        help_text="Giao dịch số dư tương ứng (tự động tạo khi thanh toán)"
    )
    
    # Loại thanh toán
    PAYMENT_TYPE_CHOICES = [
        ('deposit', 'Cọc sản xuất'),
        ('payment', 'Thanh toán đơn hàng'),
    ]
    payment_type = models.CharField(
        max_length=50,
        choices=PAYMENT_TYPE_CHOICES,
        default='payment'
    )
    
    # Số tiền (CNY)
    amount_cny = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    
    # Số tiền VNĐ đã bỏ
    amount_vnd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Số tiền VNĐ đã bỏ để thanh toán"
    )
    
    # Tỷ giá CNY/VNĐ (tự động tính nếu có amount_vnd)
    exchange_rate = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Tỷ giá CNY/VNĐ (tự động tính = amount_vnd / amount_cny)"
    )
    
    # Ngày thanh toán
    payment_date = models.DateField(
        default=timezone.now,
        help_text="Ngày thanh toán"
    )
    
    # Mô tả
    description = models.CharField(
        max_length=500,
        blank=True,
        help_text="Mô tả thanh toán"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'products_purchase_order_payment'
        verbose_name = 'Purchase Order Payment'
        verbose_name_plural = 'Purchase Order Payments'
        indexes = [
            models.Index(fields=['purchase_order']),
            models.Index(fields=['payment_type']),
            models.Index(fields=['payment_date']),
        ]
    
    def __str__(self):
        return f"{self.get_payment_type_display()} - {self.amount_cny} CNY (PO-{self.purchase_order.sapo_order_supplier_id})"
    
    def save(self, *args, **kwargs):
        """Tự động tính tỷ giá khi có amount_vnd và amount_cny (nếu chưa có exchange_rate)"""
        # Chỉ tính tỷ giá nếu chưa có exchange_rate và có đủ amount_vnd và amount_cny
        if not self.exchange_rate and self.amount_vnd and self.amount_cny and self.amount_cny > 0:
            self.exchange_rate = self.amount_vnd / self.amount_cny
        super().save(*args, **kwargs)
        
        # Cập nhật paid_amount của PO
        self.purchase_order.calculate_paid_amount()


class SPOCost(models.Model):
    """
    Chi phí cho Container (SPO) - Dynamic list.
    Thay thế dần cho các fixed fields trong SumPurchaseOrder.
    Liên kết với BalanceTransaction để trừ từ số dư (nếu thanh toán bằng CNY).
    """
    sum_purchase_order = models.ForeignKey(
        SumPurchaseOrder,
        on_delete=models.CASCADE,
        related_name='costs'
    )
    name = models.CharField(max_length=200, help_text="Tên chi phí (ví dụ: Vận chuyển, Hải quan...)")
    amount_vnd = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Số tiền (VNĐ)")
    
    # Số tiền CNY (nếu thanh toán từ số dư)
    amount_cny = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Số tiền (CNY) - nếu thanh toán từ số dư"
    )
    
    # Liên kết với giao dịch số dư (tự động tạo khi thanh toán)
    balance_transaction = models.OneToOneField(
        'BalanceTransaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='spo_cost_link',
        help_text="Giao dịch số dư tương ứng (tự động tạo khi thanh toán)"
    )
    
    note = models.TextField(blank=True, help_text="Ghi chú chi tiết")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'products_spo_cost'
        verbose_name = 'SPO Cost'
        verbose_name_plural = 'SPO Costs'
        indexes = [
            models.Index(fields=['sum_purchase_order']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.amount_vnd}"


class SPODocument(models.Model):
    """
    Tài liệu/Chứng từ cho SPO.
    """
    sum_purchase_order = models.ForeignKey(
        SumPurchaseOrder,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    file = models.FileField(upload_to='spo_documents/%Y/%m/', help_text="File chứng từ")
    
    def get_file_url(self):
        """Lấy URL file từ static directory"""
        if self.file:
            # Lấy đường dẫn từ file.name (có thể là spo_documents/2025/12/filename.xlsx)
            file_path = self.file.name
            # Nếu đã có spo_documents trong đường dẫn, giữ nguyên, nếu không thì thêm
            if file_path.startswith('spo_documents/'):
                return f'/static/{file_path}'
            else:
                # Lấy tên file
                filename = file_path.split('/')[-1]
                return f'/static/spo_documents/{filename}'
        return None
    
    def get_file_icon(self):
        """Lấy icon dựa trên extension của file"""
        if not self.file:
            return None
        filename = self.file.name.lower()
        if filename.endswith(('.xls', '.xlsx')):
            return '/static/excel-icon.png'
        elif filename.endswith('.pdf'):
            return '/static/pdf-icon.png'
        elif filename.endswith(('.doc', '.docx')):
            return '/static/word-icon.png'
        else:
            return None
    name = models.CharField(max_length=200, blank=True, help_text="Tên tài liệu (nếu để trống sẽ lấy tên file)")
    
    # Metadata
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'products_spo_document'
        verbose_name = 'SPO Document'
        verbose_name_plural = 'SPO Documents'
        indexes = [
            models.Index(fields=['sum_purchase_order']),
        ]
    
    def __str__(self):
        return self.name or self.file.name


class BalanceTransaction(models.Model):
    """
    Giao dịch nạp/rút số dư nhân dân tệ tại Trung Quốc.
    """
    TRANSACTION_TYPE_CHOICES = [
        ('deposit_bank', 'Nạp qua ngân hàng'),
        ('deposit_black_market', 'Mua chợ đen'),
        ('withdraw_po', 'Rút - Thanh toán PO'),
        ('withdraw_spo_cost', 'Rút - Chi phí SPO'),
    ]
    
    transaction_type = models.CharField(
        max_length=50,
        choices=TRANSACTION_TYPE_CHOICES,
        help_text="Loại giao dịch"
    )
    
    # Số tiền (CNY) - dương nếu nạp, âm nếu rút
    amount_cny = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Số tiền nhân dân tệ (dương = nạp, âm = rút)"
    )
    
    # Số tiền VNĐ (chỉ có khi nạp)
    amount_vnd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Số tiền VNĐ đã chi (chỉ có khi nạp)"
    )
    
    # Tỷ giá CNY/VNĐ (tự động tính nếu có amount_vnd và amount_cny)
    exchange_rate = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Tỷ giá CNY/VNĐ"
    )
    
    # Thông tin nạp qua ngân hàng
    bank_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Tên ngân hàng (nếu nạp qua ngân hàng)"
    )
    
    # Ngày giao dịch
    transaction_date = models.DateField(
        default=timezone.now,
        help_text="Ngày giao dịch"
    )
    
    # Liên kết với thanh toán (nếu là rút)
    purchase_order_payment = models.ForeignKey(
        'PurchaseOrderPayment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='balance_transactions',
        help_text="Liên kết với thanh toán PO (nếu là rút)"
    )
    
    spo_cost = models.ForeignKey(
        'SPOCost',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='balance_transactions',
        help_text="Liên kết với chi phí SPO (nếu là rút)"
    )
    
    # Mô tả
    description = models.TextField(
        blank=True,
        help_text="Mô tả giao dịch"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'products_balance_transaction'
        verbose_name = 'Balance Transaction'
        verbose_name_plural = 'Balance Transactions'
        indexes = [
            models.Index(fields=['transaction_type']),
            models.Index(fields=['transaction_date']),
            models.Index(fields=['-transaction_date']),
        ]
        ordering = ['-transaction_date', '-created_at']
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount_cny} CNY ({self.transaction_date})"
    
    def save(self, *args, **kwargs):
        """Tự động tính tỷ giá khi có amount_vnd và amount_cny (nếu chưa có exchange_rate)"""
        if not self.exchange_rate and self.amount_vnd and self.amount_cny and self.amount_cny > 0:
            self.exchange_rate = self.amount_vnd / self.amount_cny
        super().save(*args, **kwargs)
    
    @property
    def is_deposit(self):
        """Kiểm tra xem có phải giao dịch nạp không"""
        return self.transaction_type in ['deposit_bank', 'deposit_black_market']
    
    @property
    def is_withdraw(self):
        """Kiểm tra xem có phải giao dịch rút không"""
        return self.transaction_type in ['withdraw_po', 'withdraw_spo_cost']


class PaymentPeriod(models.Model):
    """
    Kỳ thanh toán - Quản lý tỷ giá và số dư theo kỳ.
    """
    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Mã kỳ thanh toán (ví dụ: KTT2025-001)"
    )
    
    name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Tên kỳ thanh toán (tùy chọn)"
    )
    
    # Ngày đầu và ngày cuối kỳ
    start_date = models.DateField(
        help_text="Ngày đầu kỳ"
    )
    end_date = models.DateField(
        help_text="Ngày cuối kỳ"
    )
    
    # Tỷ giá trung bình (tự động tính)
    avg_exchange_rate = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Tỷ giá trung bình trong kỳ (tự động tính)"
    )
    
    # Số dư đầu kỳ (chỉ dùng cho kỳ đầu tiên, các kỳ sau tính realtime từ kỳ trước)
    opening_balance_cny = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Số dư đầu kỳ (CNY) - chỉ dùng cho kỳ đầu tiên"
    )
    
    # Số dư cuối kỳ (DEPRECATED - không lưu nữa, tính realtime)
    # Giữ lại field để tương thích với migration, nhưng không dùng nữa
    closing_balance_cny = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="DEPRECATED - Số dư cuối kỳ tính realtime, không lưu"
    )
    
    # Metadata
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'products_payment_period'
        verbose_name = 'Payment Period'
        verbose_name_plural = 'Payment Periods'
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['-start_date']),
        ]
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.code} ({self.start_date} - {self.end_date})"
    
    def calculate_avg_exchange_rate(self):
        """
        DEPRECATED - Giữ lại để tương thích với code cũ.
        Tỷ giá trung bình giờ tính realtime qua property avg_exchange_rate_realtime
        """
        # Không làm gì, chỉ để tương thích
        return self.avg_exchange_rate_realtime
    
    @property
    def avg_exchange_rate_realtime(self):
        """
        Tỷ giá trung bình realtime của kỳ thanh toán.
        
        Logic theo MAKE.md:
        - Tỷ giá là realtime chứ không phải cố định
        - Tỷ giá của kỳ thanh toán được tính là: bình quân gia quyền của 
          đầu kỳ thanh toán & tỷ giá trước đó + các giao dịch và tỷ giá trong kỳ hiện tại
        - Xác định tỷ giá của số tiền đang có trong kỳ thanh toán đó, 
          chứ không phải là tỷ giá NẠP. Vì có thể còn tồn lại tiền của kỳ trước.
        
        Công thức:
        Tỷ giá TB = (Số dư đầu kỳ * Tỷ giá kỳ trước + Tổng (Số tiền nạp * Tỷ giá nạp)) 
                    / (Số dư đầu kỳ + Tổng số tiền nạp)
        """
        from django.db.models import Sum
        
        # Lấy số dư đầu kỳ
        opening_balance = self.opening_balance_cny_realtime
        
        # Lấy tỷ giá của kỳ trước (nếu có số dư đầu kỳ > 0)
        previous_period_rate = None
        if opening_balance > 0:
            previous_period = PaymentPeriod.objects.filter(
                created_at__lt=self.created_at
            ).order_by('-created_at').first()
            
            if previous_period:
                # Lấy tỷ giá realtime của kỳ trước (có thể là None nếu kỳ trước chưa có tỷ giá)
                previous_period_rate = previous_period.avg_exchange_rate_realtime
        
        # Lấy tất cả giao dịch nạp trong kỳ (theo logic total_deposits_cny_realtime)
        # Sử dụng cùng logic với total_deposits_cny_realtime để lấy đúng khoảng thời gian
        period_deposits = self.period_transactions.filter(
            balance_transaction__transaction_type__in=['deposit_bank', 'deposit_black_market']
        ).select_related('balance_transaction').order_by('balance_transaction__created_at')
        
        if not period_deposits.exists():
            # Nếu không có giao dịch nạp, trả về tỷ giá của kỳ trước (nếu có)
            return previous_period_rate
        
        # Lấy thời gian từ giao dịch đầu tiên và cuối cùng
        first_deposit = period_deposits.first().balance_transaction
        last_deposit = period_deposits.last().balance_transaction
        
        start_datetime = first_deposit.created_at
        end_datetime = last_deposit.created_at
        
        # Lấy TẤT CẢ giao dịch nạp trong khoảng thời gian này (tự động bao gồm giao dịch mới)
        all_deposits = BalanceTransaction.objects.filter(
            transaction_type__in=['deposit_bank', 'deposit_black_market'],
            created_at__gte=start_datetime,
            created_at__lte=end_datetime,
            exchange_rate__isnull=False
        )
        
        # Tính tổng số tiền nạp và tổng trọng số (số tiền * tỷ giá)
        total_deposit_cny = Decimal('0')
        weighted_deposit_rate = Decimal('0')
        
        for deposit in all_deposits:
            if deposit.exchange_rate and deposit.amount_cny > 0:
                total_deposit_cny += deposit.amount_cny
                weighted_deposit_rate += deposit.amount_cny * deposit.exchange_rate
        
        # Tính tổng số tiền (số dư đầu kỳ + tổng nạp)
        total_cny = opening_balance + total_deposit_cny
        
        if total_cny <= 0:
            # Nếu không có tiền, trả về tỷ giá của kỳ trước hoặc None
            return previous_period_rate
        
        # Tính tỷ giá trung bình có trọng số
        # Nếu có số dư đầu kỳ và tỷ giá kỳ trước
        if opening_balance > 0 and previous_period_rate:
            weighted_rate = (opening_balance * previous_period_rate) + weighted_deposit_rate
        else:
            # Nếu không có số dư đầu kỳ hoặc không có tỷ giá kỳ trước
            weighted_rate = weighted_deposit_rate
        
        return weighted_rate / total_cny
    
    @property
    def opening_balance_cny_realtime(self):
        """
        Số dư đầu kỳ realtime:
        - Kỳ đầu tiên: dùng opening_balance_cny (đã lưu)
        - Các kỳ sau: = số dư cuối kỳ của kỳ trước (realtime)
        """
        # Tìm kỳ trước (kỳ được tạo trước kỳ này)
        # Logic: tìm kỳ có created_at < self.created_at, sắp xếp theo created_at giảm dần để lấy kỳ gần nhất
        previous_period = PaymentPeriod.objects.filter(
            created_at__lt=self.created_at
        ).order_by('-created_at').first()
        
        if previous_period:
            # Kỳ sau: dùng số dư cuối kỳ của kỳ trước
            return previous_period.closing_balance_cny_realtime
        else:
            # Kỳ đầu tiên: dùng opening_balance_cny đã lưu
            return self.opening_balance_cny
    
    @property
    def closing_balance_cny_realtime(self):
        """
        Số dư cuối kỳ realtime = Số dư đầu kỳ + Tổng nạp - Tổng rút
        Tính toán realtime, không lưu vào DB
        Sử dụng total_deposits_cny_realtime và total_withdraws_cny_realtime (đã filter theo datetime)
        """
        opening = self.opening_balance_cny_realtime
        total_deposits = self.total_deposits_cny_realtime
        total_withdraws = self.total_withdraws_cny_realtime
        
        # Số dư cuối kỳ = số dư đầu kỳ + nạp - rút
        return opening + total_deposits - total_withdraws
    
    def calculate_closing_balance(self):
        """
        DEPRECATED - Giữ lại để tương thích với code cũ.
        Số dư cuối kỳ giờ tính realtime qua property closing_balance_cny_realtime
        """
        # Không làm gì, chỉ để tương thích
        return self.closing_balance_cny_realtime
    
    @classmethod
    def find_period_for_transaction_date(cls, transaction_date):
        """
        Tìm kỳ thanh toán cho một ngày giao dịch.
        DEPRECATED: Nên dùng find_period_for_transaction_datetime với datetime.
        
        Args:
            transaction_date: date object
            
        Returns:
            PaymentPeriod hoặc None nếu không tìm thấy
        """
        # Chuyển đổi date thành datetime (00:00:00) để so sánh
        from django.utils import timezone
        from datetime import datetime
        if isinstance(transaction_date, datetime):
            transaction_datetime = transaction_date
            if timezone.is_naive(transaction_datetime):
                transaction_datetime = timezone.make_aware(transaction_datetime)
        else:
            transaction_datetime = timezone.make_aware(
                datetime.combine(transaction_date, datetime.min.time())
            )
        return cls.find_period_for_transaction_datetime(transaction_datetime)
    
    @classmethod
    def find_period_for_transaction_datetime(cls, transaction_datetime):
        """
        Tìm kỳ thanh toán cho một datetime giao dịch (tính cả giờ).
        
        Logic theo MAKE.md:
        1. Nếu transaction_datetime nằm trong một kỳ (từ giao dịch nạp đầu tiên đến cuối cùng) -> dùng kỳ đó
        2. Nếu không nằm trong kỳ nào -> tìm kỳ có end_datetime gần nhất trước transaction_datetime (kỳ cũ hơn)
        3. Khoảng thời gian trống giữa 2 kỳ sẽ thuộc về kỳ cũ hơn (dùng tiền của kỳ cũ)
        
        Args:
            transaction_datetime: datetime object (có thể là naive hoặc aware)
            
        Returns:
            PaymentPeriod hoặc None nếu không tìm thấy
        """
        from django.utils import timezone
        from datetime import datetime
        
        # Đảm bảo transaction_datetime là timezone-aware
        if timezone.is_naive(transaction_datetime):
            transaction_datetime = timezone.make_aware(transaction_datetime)
        
        # Bước 1: Tìm kỳ có transaction_datetime nằm trong khoảng thời gian của kỳ
        # Khoảng thời gian của kỳ = từ giao dịch nạp đầu tiên đến giao dịch nạp cuối cùng
        periods = cls.objects.all().prefetch_related('period_transactions__balance_transaction')
        
        for period in periods:
            # Lấy giao dịch nạp đầu tiên và cuối cùng của kỳ
            period_deposits = period.period_transactions.filter(
                balance_transaction__transaction_type__in=['deposit_bank', 'deposit_black_market']
            ).select_related('balance_transaction').order_by('balance_transaction__created_at')
            
            if period_deposits.exists():
                first_deposit = period_deposits.first().balance_transaction
                last_deposit = period_deposits.last().balance_transaction
                
                start_datetime = first_deposit.created_at
                end_datetime = last_deposit.created_at
                
                # Nếu transaction_datetime nằm trong khoảng thời gian này
                if start_datetime <= transaction_datetime <= end_datetime:
                    return period
        
        # Bước 2: Nếu không có, tìm kỳ có end_datetime gần nhất trước transaction_datetime
        # (kỳ cũ hơn - khoảng trống thuộc về kỳ cũ, dùng tiền của kỳ cũ)
        best_period = None
        best_end_datetime = None
        
        for period in periods:
            period_deposits = period.period_transactions.filter(
                balance_transaction__transaction_type__in=['deposit_bank', 'deposit_black_market']
            ).select_related('balance_transaction').order_by('balance_transaction__created_at')
            
            if period_deposits.exists():
                last_deposit = period_deposits.last().balance_transaction
                end_datetime = last_deposit.created_at
                
                if end_datetime < transaction_datetime:
                    if best_end_datetime is None or end_datetime > best_end_datetime:
                        best_end_datetime = end_datetime
                        best_period = period
        
        return best_period
    
    @property
    def total_deposits_cny(self):
        """Tổng số tiền nạp trong kỳ (DEPRECATED - dùng total_deposits_cny_realtime)"""
        return self.total_deposits_cny_realtime
    
    @property
    def total_withdraws_cny(self):
        """Tổng số tiền rút trong kỳ (DEPRECATED - dùng total_withdraws_cny_realtime)"""
        return self.total_withdraws_cny_realtime
    
    @property
    def total_deposits_cny_realtime(self):
        """
        Tổng số tiền nạp trong kỳ (realtime).
        
        Logic theo MAKE.md:
        - Tổng toàn bộ số tiền nạp vào trong thời điểm start-end (từ giao dịch cũ nhất -> giao dịch mới nhất)
        - Lấy TẤT CẢ giao dịch nạp trong khoảng thời gian, không chỉ những giao dịch đã liên kết
        - Nếu phát sinh giao dịch mới trong thời điểm này thì tự động cho vào KTT đó
        """
        from django.utils import timezone
        from datetime import datetime
        
        # Lấy thời gian từ giao dịch đầu tiên và cuối cùng của kỳ (từ period_transactions)
        # Để xác định khoảng thời gian chính xác
        period_deposits = self.period_transactions.filter(
            balance_transaction__transaction_type__in=['deposit_bank', 'deposit_black_market']
        ).select_related('balance_transaction').order_by('balance_transaction__created_at')
        
        if not period_deposits.exists():
            return Decimal('0')
        
        # Lấy thời gian từ giao dịch đầu tiên và cuối cùng
        first_deposit = period_deposits.first().balance_transaction
        last_deposit = period_deposits.last().balance_transaction
        
        start_datetime = first_deposit.created_at
        end_datetime = last_deposit.created_at
        
        # Lấy TẤT CẢ giao dịch nạp trong khoảng thời gian này (tự động bao gồm giao dịch mới)
        all_deposits = BalanceTransaction.objects.filter(
            transaction_type__in=['deposit_bank', 'deposit_black_market'],
            created_at__gte=start_datetime,
            created_at__lte=end_datetime
        )
        
        return all_deposits.aggregate(
            total=Sum('amount_cny')
        )['total'] or Decimal('0')
    
    @property
    def total_withdraws_cny_realtime(self):
        """
        Tổng số tiền rút trong kỳ (realtime).
        
        Logic theo MAKE.md:
        - Rút là những khoản giao dịch đã dùng tiền của kỳ thanh toán này
        - Rút có thể phát sinh từ thời điểm start của KTT và có thể là sau cả enddate của kỳ thanh toán
        - Rút là việc xác định khoản thanh toán đó dùng số tiền của kỳ thanh toán nào
        - Lấy TẤT CẢ giao dịch rút dùng tiền của kỳ này (có thể sau end_date)
        """
        # Lấy thời gian bắt đầu của kỳ (từ giao dịch nạp đầu tiên)
        period_deposits = self.period_transactions.filter(
            balance_transaction__transaction_type__in=['deposit_bank', 'deposit_black_market']
        ).select_related('balance_transaction').order_by('balance_transaction__created_at')
        
        if not period_deposits.exists():
            return Decimal('0')
        
        # start_datetime = thời gian giao dịch nạp đầu tiên của kỳ
        start_datetime = period_deposits.first().balance_transaction.created_at
        # end_datetime = thời gian giao dịch nạp cuối cùng của kỳ
        end_datetime = period_deposits.last().balance_transaction.created_at
        
        # Lấy TẤT CẢ giao dịch rút từ start_datetime trở đi
        # Logic: Rút có thể phát sinh sau end_date, nhưng vẫn dùng tiền của kỳ này
        # Nếu giao dịch rút nằm trong khoảng thời gian của kỳ -> thuộc kỳ này
        # Nếu giao dịch rút nằm sau end_datetime nhưng trước kỳ tiếp theo -> thuộc kỳ này (khoảng trống)
        all_withdraws = BalanceTransaction.objects.filter(
            transaction_type__in=['withdraw_po', 'withdraw_spo_cost'],
            created_at__gte=start_datetime
        ).order_by('created_at')
        
        # Tìm kỳ tiếp theo (nếu có) để xác định ranh giới
        next_period = PaymentPeriod.objects.filter(
            created_at__gt=self.created_at
        ).order_by('created_at').first()
        
        next_period_start = None
        if next_period:
            next_period_deposits = next_period.period_transactions.filter(
                balance_transaction__transaction_type__in=['deposit_bank', 'deposit_black_market']
            ).select_related('balance_transaction').order_by('balance_transaction__created_at')
            if next_period_deposits.exists():
                next_period_start = next_period_deposits.first().balance_transaction.created_at
        
        # Lọc giao dịch rút thuộc về kỳ này
        # - Nằm trong khoảng thời gian của kỳ (start_datetime <= created_at <= end_datetime)
        # - Hoặc nằm sau end_datetime nhưng trước kỳ tiếp theo (khoảng trống)
        total = Decimal('0')
        for withdraw in all_withdraws:
            if withdraw.created_at <= end_datetime:
                # Nằm trong khoảng thời gian của kỳ
                total += abs(withdraw.amount_cny)
            elif next_period_start is None or withdraw.created_at < next_period_start:
                # Nằm trong khoảng trống (sau kỳ này, trước kỳ tiếp theo) -> dùng tiền của kỳ này
                total += abs(withdraw.amount_cny)
        
        return total


class PaymentPeriodTransaction(models.Model):
    """
    Liên kết giao dịch số dư với kỳ thanh toán.
    """
    payment_period = models.ForeignKey(
        PaymentPeriod,
        on_delete=models.CASCADE,
        related_name='period_transactions'
    )
    
    balance_transaction = models.ForeignKey(
        BalanceTransaction,
        on_delete=models.CASCADE,
        related_name='payment_periods'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'products_payment_period_transaction'
        verbose_name = 'Payment Period Transaction'
        verbose_name_plural = 'Payment Period Transactions'
        unique_together = [['payment_period', 'balance_transaction']]
        indexes = [
            models.Index(fields=['payment_period', 'balance_transaction']),
        ]
    
    def __str__(self):
        return f"{self.payment_period.code} - {self.balance_transaction}"


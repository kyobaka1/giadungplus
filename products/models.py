# products/models.py
"""
Django models cho products app.
"""

from django.db import models
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
    """
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='payments'
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
        """Tự động tính tỷ giá khi có amount_vnd và amount_cny"""
        if self.amount_vnd and self.amount_cny and self.amount_cny > 0:
            self.exchange_rate = self.amount_vnd / self.amount_cny
        super().save(*args, **kwargs)
        
        # Cập nhật paid_amount của PO
        self.purchase_order.calculate_paid_amount()


class SPOCost(models.Model):
    """
    Chi phí cho Container (SPO) - Dynamic list.
    Thay thế dần cho các fixed fields trong SumPurchaseOrder.
    """
    sum_purchase_order = models.ForeignKey(
        SumPurchaseOrder,
        on_delete=models.CASCADE,
        related_name='costs'
    )
    name = models.CharField(max_length=200, help_text="Tên chi phí (ví dụ: Vận chuyển, Hải quan...)")
    amount_vnd = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Số tiền (VNĐ)")
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


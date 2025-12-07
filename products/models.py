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
        ('created', 'Đã tạo SPO'),
        ('supplier_confirmed', 'NSX xác nhận PO'),
        ('producing', 'Đang sản xuất'),
        ('waiting_packing', 'Đợi đóng container'),
        ('packed', 'Đóng xong container'),
        ('departed_cn', 'Rời cảng Trung Quốc'),
        ('arrived_vn', 'Về cảng Việt Nam'),
        ('customs_cleared', 'Thông quan'),
        ('arrived_warehouse_hn', 'Về kho Hà Nội'),
        ('arrived_warehouse_hcm', 'Về kho Hồ Chí Minh'),
        ('completed', 'Hoàn thành'),
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


class SPOPurchaseOrder(models.Model):
    """
    Quan hệ giữa SPO và PO - Chỉ lưu thông tin cơ bản.
    PO được lưu trữ trên Sapo, chỉ lấy qua API khi cần.
    """
    # Liên kết với SPO
    sum_purchase_order = models.ForeignKey(
        SumPurchaseOrder,
        on_delete=models.CASCADE,
        related_name='spo_purchase_orders'
    )
    
    # Liên kết với Sapo (chỉ lưu ID, không lưu toàn bộ data)
    sapo_order_supplier_id = models.BigIntegerField(db_index=True, help_text="Sapo order_supplier.id")
    
    # Thông tin cơ bản của PO (chỉ lưu những gì cần thiết)
    domestic_shipping_cn = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0, 
        help_text="Vận chuyển nội địa TQ (ship nội địa của PO)"
    )
    
    # Thời gian dự kiến
    expected_production_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Thời gian dự kiến PO sản xuất xong"
    )
    expected_delivery_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Thời gian dự kiến ship đến nơi nhận"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'products_spo_purchase_order'
        verbose_name = 'SPO Purchase Order'
        verbose_name_plural = 'SPO Purchase Orders'
        unique_together = [['sum_purchase_order', 'sapo_order_supplier_id']]
        indexes = [
            models.Index(fields=['sum_purchase_order', 'sapo_order_supplier_id']),
            models.Index(fields=['sapo_order_supplier_id']),
        ]
    
    def __str__(self):
        return f"SPO-{self.sum_purchase_order_id} - PO-{self.sapo_order_supplier_id}"

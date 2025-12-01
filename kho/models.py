from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Ticket(models.Model):
    """
    Ticket khiếu nại từ CSKH gửi đến kho.
    """
    STATUS_CHOICES = [
        ('pending', 'Chờ xử lý'),
        ('processing', 'Đang xử lý'),
        ('resolved', 'Đã xử lý'),
        ('closed', 'Đã đóng'),
    ]
    
    ERROR_TYPE_CHOICES = [
        ('warehouse_error', 'Lỗi kho'),
        ('shipping_error', 'Lỗi vận chuyển'),
        ('supplier_error', 'Lỗi nhà cung cấp'),
        ('customer_error', 'Lỗi khách hàng'),
        ('other', 'Khác'),
    ]
    
    # Thông tin cơ bản
    order_code = models.CharField(max_length=50, db_index=True)  # Mã đơn hàng
    sapo_order_id = models.BigIntegerField(null=True, blank=True)  # Sapo order ID
    reference_number = models.CharField(max_length=100, blank=True)  # Mã đơn sàn TMĐT
    
    # Nội dung ticket
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    error_type = models.CharField(max_length=50, choices=ERROR_TYPE_CHOICES, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Người tạo và xử lý
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tickets_created')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_assigned')
    confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_confirmed')
    
    # Thời gian
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # Ghi chú và hình ảnh
    images = models.JSONField(default=list, blank=True)  # Danh sách URL hình ảnh
    warehouse_note = models.TextField(blank=True)  # Ghi chú từ kho
    cskh_note = models.TextField(blank=True)  # Ghi chú từ CSKH
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['order_code']),
        ]
    
    def __str__(self):
        return f"Ticket #{self.id} - {self.order_code}"


class TicketComment(models.Model):
    """
    Comments trong ticket.
    """
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"Comment #{self.id} on Ticket #{self.ticket.id}"

class Warehouse(models.Model):
    code = models.CharField(max_length=20, unique=True)  # 'gele', 'toky'
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    warehouses = models.ManyToManyField(Warehouse, blank=True)
    display_name = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.display_name or self.user.username


class WarehousePackingSetting(models.Model):
    """
    Cài đặt bật/tắt tính năng đóng gói hàng (packing_orders) cho từng kho.
    - KHO_HCM: Kho HCM (Geleximco / toky)
    - KHO_HN: Kho Hà Nội (Geleximco)
    """
    WAREHOUSE_CHOICES = [
        ('KHO_HCM', 'Kho HCM (Geleximco & Toky)'),
        ('KHO_HN', 'Kho Hà Nội (Geleximco)'),
    ]
    
    warehouse_code = models.CharField(
        max_length=20, 
        choices=WAREHOUSE_CHOICES, 
        unique=True,
        help_text="Mã kho: KHO_HCM hoặc KHO_HN"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Bật/tắt tính năng đóng gói hàng cho nhân viên thông thường (WarehousePacker)"
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='packing_settings_updated'
    )
    
    class Meta:
        verbose_name = "Cài đặt đóng gói hàng kho"
        verbose_name_plural = "Cài đặt đóng gói hàng kho"
        ordering = ['warehouse_code']
    
    def __str__(self):
        status = "Hoạt động" if self.is_active else "Tạm dừng"
        return f"{self.get_warehouse_code_display()} - {status}"
    
    @classmethod
    def get_setting_for_warehouse(cls, warehouse_code):
        """
        Lấy cài đặt cho kho. Nếu chưa có thì tạo mới với is_active=True (mặc định bật).
        warehouse_code: 'KHO_HCM' hoặc 'KHO_HN'
        """
        setting, created = cls.objects.get_or_create(
            warehouse_code=warehouse_code,
            defaults={'is_active': True}
        )
        return setting
    
    @classmethod
    def is_packing_enabled_for_user(cls, user):
        """
        Kiểm tra xem user có được phép sử dụng tính năng packing_orders không.
        - WarehouseManager: luôn được phép
        - WarehousePacker: phụ thuộc vào cài đặt của kho
        - Các user khác: không được phép
        
        Returns: (is_allowed, reason)
        """
        from django.contrib.auth.models import Group
        
        # WarehouseManager luôn được phép
        if user.is_superuser or user.groups.filter(name="Admin").exists():
            return True, "Quản lý"
        
        if user.groups.filter(name="WarehouseManager").exists():
            return True, "Quản lý kho"
        
        # WarehousePacker cần kiểm tra cài đặt
        if user.groups.filter(name="WarehousePacker").exists():
            # Xác định kho từ user.last_name
            last_name = (user.last_name or "").strip().upper()
            
            warehouse_code = None
            if last_name == "KHO_HCM":
                warehouse_code = "KHO_HCM"
            elif last_name == "KHO_HN":
                warehouse_code = "KHO_HN"
            
            if not warehouse_code:
                return False, "Không xác định được kho từ thông tin tài khoản"
            
            # Lấy cài đặt cho kho
            setting = cls.get_setting_for_warehouse(warehouse_code)
            if setting.is_active:
                return True, f"Kho {warehouse_code}"
            else:
                return False, f"Tính năng đóng gói hàng đã bị tắt cho {warehouse_code}"
        
        return False, "Không có quyền truy cập"
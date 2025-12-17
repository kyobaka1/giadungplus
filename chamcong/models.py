import os
import uuid

from django.conf import settings
from django.db import models

from .storage import attendance_photo_storage


class WorkLocation(models.Model):
    """
    Địa điểm chấm công hợp lệ (theo GPS).

    - Chỉ cấu hình các vị trí, không cần bộ phận.
    - Bộ phận nào chấm công ở các vị trí đã cấu hình đều được coi là hợp lệ.
    - Dùng bán kính (m) để kiểm tra hợp lệ.
    """

    name = models.CharField(max_length=255)
    latitude = models.FloatField(help_text="Vĩ độ (GPS)")
    longitude = models.FloatField(help_text="Kinh độ (GPS)")
    radius_m = models.PositiveIntegerField(
        default=150, help_text="Bán kính cho phép tính từ điểm chuẩn (mét)"
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Địa điểm chấm công"
        verbose_name_plural = "Địa điểm chấm công"

    def __str__(self) -> str:  # pragma: no cover - simple repr
        return f"{self.name}"


class WorkRule(models.Model):
    """
    Quy định giờ làm cho từng bộ phận + chức vụ (group) + ca làm việc.

    - Cho phép cấu hình giờ bắt đầu / kết thúc chuẩn theo ca (sáng/tối).
    - Dùng để tính tổng giờ làm & tăng ca.
    """

    DEPARTMENT_CHOICES = [
        ("CSKH", "CSKH"),
        ("KHO_HCM", "Kho hàng HCM"),
        ("KHO_HN", "Kho hàng HN"),
        ("MARKETING", "Marketing"),
        ("ADMIN", "Admin / Quản trị"),
    ]

    # Quy định ca làm việc: sáng / chiều / tối
    SHIFT_CHOICES = [
        ("morning", "Ca sáng"),
        ("afternoon", "Ca chiều"),
        ("evening", "Ca tối"),
    ]

    department = models.CharField(
        max_length=50,
        choices=DEPARTMENT_CHOICES,
        help_text="Bộ phận làm việc (last_name của user)",
    )
    group_name = models.CharField(
        max_length=100,
        help_text="Tên group quyền (VD: WarehouseManager, CSKHStaff, MarketingManager...)",
    )
    shift = models.CharField(
        max_length=20,
        choices=SHIFT_CHOICES,
        default="morning",
        help_text="Ca làm việc: sáng / chiều / tối",
    )
    start_time = models.TimeField(
        help_text="Giờ bắt đầu chuẩn (24h, VD: 08:30)"
    )
    end_time = models.TimeField(
        help_text="Giờ kết thúc chuẩn (24h, VD: 17:30)"
    )
    allow_overtime = models.BooleanField(default=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Quy định giờ làm"
        verbose_name_plural = "Quy định giờ làm"
        unique_together = ("department", "group_name", "shift", "is_active")

    def __str__(self) -> str:  # pragma: no cover - simple repr
        return f"{self.department} / {self.group_name} / {self.get_shift_display()}"


def attendance_photo_upload_to(instance, filename: str) -> str:
    """
    Sinh tên file ngẫu nhiên để tránh trùng (vd: 2025-02-01_uuid4.jpg).
    Thư mục gốc đã được cấu hình trong storage (assets/nhanvien/chamcong).
    """
    base, ext = os.path.splitext(filename)
    ext = ext.lower() or ".jpg"
    return f"{uuid.uuid4().hex}{ext}"


class AttendanceRecord(models.Model):
    """
    Bảng chấm công chi tiết.

    Lưu:
    - User, bộ phận (last_name), group chính (chức vụ)
    - Check-in / check-out + GPS + selfie
    - Tổng giờ làm, giờ tăng ca, trạng thái duyệt.
    """

    APPROVAL_STATUS_CHOICES = [
        ("pending", "Chờ duyệt"),
        ("approved", "Đã duyệt"),
        ("rejected", "Từ chối"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    # Cache lại để dễ filter/reporting
    department = models.CharField(
        max_length=50, help_text="Bộ phận làm việc tại thời điểm chấm công (last_name)"
    )
    group_name = models.CharField(
        max_length=100,
        help_text="Chức vụ / group tại thời điểm chấm công",
    )

    work_date = models.DateField(help_text="Ngày làm việc (theo GMT+7)")

    # Ca làm
    SHIFT_CHOICES = [
        ("morning", "Ca sáng"),
        ("afternoon", "Ca chiều"),
        ("evening", "Ca tối"),
    ]

    shift = models.CharField(
        max_length=20,
        choices=SHIFT_CHOICES,
        null=True,
        blank=True,
        help_text="Ca làm: sáng / chiều / tối",
    )

    # Check-in
    check_in_time = models.DateTimeField(null=True, blank=True)
    check_in_latitude = models.FloatField(null=True, blank=True)
    check_in_longitude = models.FloatField(null=True, blank=True)
    check_in_address = models.CharField(
        max_length=255, null=True, blank=True, help_text="Địa chỉ hiển thị (optional)"
    )
    check_in_location_valid = models.BooleanField(
        default=False, help_text="Vị trí check-in có hợp lệ hay không"
    )
    check_in_photo = models.ImageField(
        storage=attendance_photo_storage,
        upload_to=attendance_photo_upload_to,
        null=True,
        blank=True,
        help_text="Ảnh selfie khi check-in (assets/nhanvien/chamcong)",
    )

    # Check-out
    check_out_time = models.DateTimeField(null=True, blank=True)
    check_out_latitude = models.FloatField(null=True, blank=True)
    check_out_longitude = models.FloatField(null=True, blank=True)
    check_out_address = models.CharField(
        max_length=255, null=True, blank=True, help_text="Địa chỉ hiển thị (optional)"
    )
    check_out_location_valid = models.BooleanField(
        default=False, help_text="Vị trí check-out có hợp lệ hay không"
    )
    check_out_photo = models.ImageField(
        storage=attendance_photo_storage,
        upload_to=attendance_photo_upload_to,
        null=True,
        blank=True,
        help_text="Ảnh selfie khi check-out (nếu cần, assets/nhanvien/chamcong)",
    )

    # Tổng giờ làm (phút)
    total_minutes = models.PositiveIntegerField(default=0, help_text="Tổng giờ làm (phút)")
    overtime_minutes = models.PositiveIntegerField(
        default=0, help_text="Số phút tăng ca (nếu có)"
    )

    # Duyệt công
    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default="pending",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_attendances",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_note = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Chấm công"
        verbose_name_plural = "Chấm công"
        indexes = [
            models.Index(fields=["work_date", "department"]),
            models.Index(fields=["user", "work_date"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - simple repr
        return f"{self.user.username} - {self.work_date}"



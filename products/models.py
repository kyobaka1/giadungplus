# products/models.py
"""
Django models cho products app.
"""

from django.db import models
from django.utils import timezone


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

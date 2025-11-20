# core/models.py
from django.db import models
from django.utils import timezone

class SapoToken(models.Model):
    """
    Lưu token/headers để dùng lại, thay vì lưu txt.
    key:
      - 'loginss'  : headers cho MAIN_URL (orders.json)
      - 'tmdt'     : headers cho market-place.sapoapps.vn
    """
    key = models.CharField(max_length=50, unique=True)
    headers = models.JSONField(default=dict)   # toàn bộ headers cần dùng
    expires_at = models.DateTimeField()        # thời điểm hết hạn dự kiến

    def is_valid(self) -> bool:
        return self.expires_at > timezone.now()

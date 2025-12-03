# core/models.py
from django.conf import settings
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
    headers = models.JSONField(default=dict)  # toàn bộ headers cần dùng
    expires_at = models.DateTimeField()  # thời điểm hết hạn dự kiến

    def is_valid(self) -> bool:
        return self.expires_at > timezone.now()


class WebPushSubscription(models.Model):
    """
    Lưu thông tin subscription/token cho Web Push Notification.
    Dùng chung cho Android Web (Chrome) và iOS Web (Safari 16.4+).
    """

    DEVICE_ANDROID_WEB = "android_web"
    DEVICE_IOS_WEB = "ios_web"
    DEVICE_UNKNOWN = "unknown"

    DEVICE_CHOICES = (
        (DEVICE_ANDROID_WEB, "Android Web (Chrome)"),
        (DEVICE_IOS_WEB, "iOS Web (Safari)"),
        (DEVICE_UNKNOWN, "Unknown Web"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="webpush_subscriptions",
    )
    device_type = models.CharField(
        max_length=32,
        choices=DEVICE_CHOICES,
        default=DEVICE_UNKNOWN,
        help_text="Loại thiết bị: android_web, ios_web, unknown",
    )
    # Endpoint + keys cho Web Push (Safari iOS / browser khác)
    endpoint = models.TextField(blank=True, null=True)
    p256dh = models.TextField(blank=True, null=True)
    auth = models.TextField(blank=True, null=True)

    # FCM token cho Chrome Android (và có thể dùng cho browser khác nếu có)
    fcm_token = models.CharField(max_length=255, blank=True, null=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["endpoint"]),
            models.Index(fields=["fcm_token"]),
            models.Index(fields=["device_type"]),
        ]
        verbose_name = "Web Push Subscription"
        verbose_name_plural = "Web Push Subscriptions"

    def __str__(self) -> str:
        if self.fcm_token:
            return f"{self.device_type} / FCM: {self.fcm_token[:20]}..."
        if self.endpoint:
            return f"{self.device_type} / {self.endpoint[:40]}..."
        return f"{self.device_type} / (no token)"

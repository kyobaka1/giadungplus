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


class Notification(models.Model):
    """
    Lưu trữ thông báo tới người dùng.
    Hỗ trợ cả runtime và scheduled notifications.
    """

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = (
        (STATUS_PENDING, "Chờ gửi"),
        (STATUS_SENT, "Đã gửi"),
        (STATUS_FAILED, "Gửi thất bại"),
        (STATUS_CANCELLED, "Đã hủy"),
    )

    ACTION_SHOW_POPUP = "show_popup"
    ACTION_PLAY_SOUND = "play_sound"
    ACTION_BADGE_UPDATE = "badge_update"
    ACTION_BOSS_POPUP = "boss_popup"

    ACTION_CHOICES = (
        (ACTION_SHOW_POPUP, "Hiển thị popup"),
        (ACTION_PLAY_SOUND, "Phát âm thanh"),
        (ACTION_BADGE_UPDATE, "Cập nhật badge"),
        (ACTION_BOSS_POPUP, "Thông báo của sếp"),
    )

    # Thông tin cơ bản
    title = models.CharField(max_length=200, help_text="Tiêu đề thông báo")
    body = models.TextField(help_text="Nội dung thông báo")
    link = models.CharField(max_length=500, blank=True, null=True, help_text="URL khi click vào thông báo")

    # Action và metadata
    action = models.CharField(
        max_length=50,
        choices=ACTION_CHOICES,
        default=ACTION_SHOW_POPUP,
        help_text="Loại hành động: show_popup, play_sound, badge_update, boss_popup",
    )
    sound = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Link sound ở /static/ (nếu có)",
    )
    count = models.IntegerField(
        blank=True,
        null=True,
        help_text="Số lượng cho badge_update",
    )

    # Collapse/Tag để đè notify cũ
    collapse_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="ID/tag để đè notify cũ bằng notify mới",
    )
    tag = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="Tag phân loại thông báo",
    )

    # Hẹn giờ
    scheduled_time = models.DateTimeField(
        blank=True,
        null=True,
        db_index=True,
        help_text="Thời gian hẹn gửi (nếu có, null = gửi ngay)",
    )

    # Business layer info
    event_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="Loại event từ business layer (ví dụ: ticket_created, order_updated)",
    )
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Dữ liệu context từ business layer (JSON)",
    )

    # Trạng thái
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    # Thời gian
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["collapse_id"]),
            models.Index(fields=["tag"]),
            models.Index(fields=["event_type"]),
            models.Index(fields=["scheduled_time", "status"]),
        ]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self) -> str:
        return f"Notification #{self.id}: {self.title} ({self.status})"


class NotificationDelivery(models.Model):
    """
    Lưu trữ việc gửi thông báo tới từng user qua từng kênh.
    Một Notification có thể có nhiều NotificationDelivery (1 user = 1 delivery).
    """

    CHANNEL_WEB_PUSH = "web_push"
    CHANNEL_IN_APP = "in_app"
    CHANNEL_EMAIL = "email"  # Dự phòng cho tương lai

    CHANNEL_CHOICES = (
        (CHANNEL_WEB_PUSH, "Web Push"),
        (CHANNEL_IN_APP, "In-app"),
        (CHANNEL_EMAIL, "Email"),
    )

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = (
        (STATUS_PENDING, "Chờ gửi"),
        (STATUS_SENT, "Đã gửi"),
        (STATUS_FAILED, "Gửi thất bại"),
    )

    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="deliveries",
        help_text="Thông báo được gửi",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_deliveries",
        help_text="User nhận thông báo",
    )

    channel = models.CharField(
        max_length=50,
        choices=CHANNEL_CHOICES,
        default=CHANNEL_IN_APP,
        db_index=True,
        help_text="Kênh gửi: web_push, in_app, email",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    # Metadata
    sent_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    delivery_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Metadata về delivery (subscription_id, response, etc.)",
    )

    # Đánh dấu đã đọc (cho in-app)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["notification", "channel"]),
            models.Index(fields=["status"]),
        ]
        verbose_name = "Notification Delivery"
        verbose_name_plural = "Notification Deliveries"
        unique_together = [["notification", "user", "channel"]]

    def __str__(self) -> str:
        return f"Delivery #{self.id}: {self.notification.title} -> {self.user.username} ({self.channel})"
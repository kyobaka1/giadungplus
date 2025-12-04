from rest_framework import serializers

from .models import WebPushSubscription


class WebPushSubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer tối giản để validate/giao tiếp WebPushSubscription.
    Trên API đầu vào:
      - device_type: android_web | ios_web | unknown
      - endpoint, keys: cho Web Push
      - fcm_token: cho Android Chrome (hoặc nơi khác)
      - username (optional): cho phép client đẩy username để map sang user_id
    """

    # Cho phép client gửi "keys" dạng object {p256dh, auth}
    keys = serializers.DictField(required=False, allow_null=True)
    # Cho phép client gửi thêm username để backend map sang user (input)
    username = serializers.CharField(required=False, allow_blank=True, write_only=True)
    # Thông tin user ở dạng read-only để client dễ debug (output)
    user_id = serializers.IntegerField(source="user_id", read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True, allow_null=True)

    class Meta:
        model = WebPushSubscription
        fields = (
            "id",
            "device_type",
            "endpoint",
            "p256dh",
            "auth",
            "fcm_token",
            "is_active",
            "created_at",
            "updated_at",
            "keys",
            "username",   # input
            "user_id",    # output
            "user_name",  # output
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_device_type(self, value: str) -> str:
        allowed = {c[0] for c in WebPushSubscription.DEVICE_CHOICES}
        if value not in allowed:
            return WebPushSubscription.DEVICE_UNKNOWN
        return value

    def validate(self, attrs):
        """
        Map 'keys' từ payload vào p256dh/auth nếu có.
        """
        keys = attrs.pop("keys", None)
        if keys:
            attrs["p256dh"] = keys.get("p256dh") or attrs.get("p256dh")
            attrs["auth"] = keys.get("auth") or attrs.get("auth")
        # username giữ nguyên trong attrs để view có thể xử lý
        return attrs



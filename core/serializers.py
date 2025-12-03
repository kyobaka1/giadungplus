from rest_framework import serializers

from .models import WebPushSubscription


class WebPushSubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer tối giản để validate/giao tiếp WebPushSubscription.
    Trên API đầu vào:
      - device_type: android_web | ios_web | unknown
      - endpoint, keys: cho Web Push
      - fcm_token: cho Android Chrome (hoặc nơi khác)
    """

    # Cho phép client gửi "keys" dạng object {p256dh, auth}
    keys = serializers.DictField(required=False, allow_null=True)

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
        return attrs



"""
Dịch vụ gửi Web Push Notification qua Firebase Cloud Messaging (FCM).

Giả định:
- Sử dụng FCM HTTP legacy API với SERVER KEY lưu trong biến môi trường FCM_SERVER_KEY.
- Với Web (Chrome Android), ta gửi tới trường "to": <fcm_token>.
- Với các subscription Web Push thuần (endpoint/keys) chưa được tích hợp đầy đủ ở đây.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
import json
import time

import requests
from pywebpush import webpush, WebPushException
from django.conf import settings
from django.contrib.auth import get_user_model

from core.models import WebPushSubscription

logger = logging.getLogger(__name__)

FCM_LEGACY_ENDPOINT = "https://fcm.googleapis.com/fcm/send"


def _get_fcm_server_key() -> str:
    """
    Lấy FCM_SERVER_KEY theo thứ tự ưu tiên:
    1. Biến môi trường FCM_SERVER_KEY (nếu có).
    2. File settings/firebase/prive-key.txt (dòng đầu tiên).
    """
    # 1. Ưu tiên ENV nếu đã set (ví dụ trên server production)
    key = os.environ.get("FCM_SERVER_KEY")
    if key:
        return key.strip()

    # 2. Fallback: đọc từ file settings/firebase/prive-key.txt
    try:
        prive_key_path = settings.BASE_DIR / "settings" / "firebase" / "prive-key.txt"
        with open(prive_key_path, "r", encoding="utf-8") as f:
            file_key = f.readline().strip()
        if not file_key:
            raise RuntimeError("File prive-key.txt rỗng, không tìm thấy FCM server key.")
        return file_key
    except FileNotFoundError:
        raise RuntimeError(
            "Không tìm thấy FCM server key: "
            "chưa set ENV FCM_SERVER_KEY và thiếu file settings/firebase/prive-key.txt."
        )
    except OSError as exc:
        raise RuntimeError(f"Lỗi đọc file prive-key.txt: {exc}") from exc


def _get_vapid_keys() -> Dict[str, str]:
    """
    Đọc VAPID public/private key dùng cho Web Push (desktop browsers).
    Giả định:
    - Public key nằm trong settings/firebase/keypair.txt (1 dòng).
    - Private key nằm trong settings/firebase/prive-key.txt (1 dòng).
    """
    base = settings.BASE_DIR / "settings" / "firebase"
    public_path = base / "keypair.txt"
    private_path = base / "prive-key.txt"

    try:
        with open(public_path, "r", encoding="utf-8") as f:
            public_key = f.readline().strip()
        with open(private_path, "r", encoding="utf-8") as f:
            private_key = f.readline().strip()
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Thiếu VAPID keypair: cần settings/firebase/keypair.txt và prive-key.txt"
        ) from exc

    if not public_key or not private_key:
        raise RuntimeError("VAPID keypair rỗng hoặc không hợp lệ.")

    return {
        "publicKey": public_key,
        "privateKey": private_key,
    }


def send_webpush_to_subscription(
    subscription: WebPushSubscription,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    icon: Optional[str] = None,
    url: Optional[str] = None,
) -> bool:
    """
    Gửi 1 Web Push Notification tới 1 subscription cụ thể thông qua FCM.

    Hiện tại hỗ trợ chính cho các subscription có fcm_token (Chrome Android).
    Với subscription chỉ có endpoint/keys (Web Push thuần) cần tích hợp thêm webpush library.
    """

    if not subscription.is_active:
        logger.info("Bỏ qua subscription không active: %s", subscription)
        return False

    # Nhánh 1: dùng FCM legacy với fcm_token (Android Chrome, v.v.)
    if subscription.fcm_token:
        server_key = _get_fcm_server_key()

        notification: Dict[str, Any] = {
            "title": title,
            "body": body,
        }
        if icon:
            notification["icon"] = icon
        if url:
            # Trên Web, click_action sẽ được SW dùng để mở URL tương ứng
            notification["click_action"] = url

        payload: Dict[str, Any] = {
            "to": subscription.fcm_token,
            "notification": notification,
            "data": data or {},
        }

        headers = {
            "Authorization": f"key={server_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(
                FCM_LEGACY_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=2,  # giới hạn tối đa ~2 giây cho mỗi request tới FCM
            )
            if resp.status_code != 200:
                logger.error(
                    "Gửi FCM thất bại (%s): %s",
                    resp.status_code,
                    resp.text[:500],
                )
                return False

            logger.info("Đã gửi WebPush (FCM) tới subscription %s", subscription.id)
            return True
        except Exception as exc:
            logger.exception("Lỗi khi gửi FCM WebPush: %s", exc)
            return False

    # Nhánh 2: Web Push thuần (desktop/iOS) với endpoint + keys
    if subscription.endpoint and subscription.p256dh and subscription.auth:
        vapid = _get_vapid_keys()
        payload_data: Dict[str, Any] = {
            "title": title,
            "body": body,
            "icon": icon,
            "url": url,
        }
        # Gộp thêm data custom nếu có
        if data:
            payload_data.update(data)

        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=json.dumps(payload_data),
                vapid_private_key=vapid["privateKey"],
                vapid_claims={
                    # Email admin để identify sender trong VAPID (phải là dạng mailto:...)
                    "sub": "mailto:support@giadungplus.io.vn",
                },
            )
            logger.info("Đã gửi WebPush (endpoint) tới subscription %s", subscription.id)
            return True
        except WebPushException as exc:
            logger.error("Lỗi WebPush (endpoint) cho subscription %s: %s", subscription.id, exc)
            return False
        except Exception as exc:
            logger.exception("Lỗi không xác định khi gửi WebPush (endpoint): %s", exc)
            return False

    logger.warning(
        "Subscription %s không có fcm_token hoặc endpoint/keys đầy đủ, bỏ qua.",
        subscription.id,
    )
    return False


def send_webpush_to_user(
    user,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    icon: Optional[str] = None,
    url: Optional[str] = None,
) -> int:
    """
    Gửi notification tới tất cả subscription active của 1 user.

    Returns:
        Số subscription gửi thành công.
    """

    if not user:
        return 0

    qs = WebPushSubscription.objects.filter(user=user, is_active=True)
    success_count = 0
    start_time = time.monotonic()

    for sub in qs:
        # Nếu thời gian xử lý cho user này đã vượt quá 2 giây thì bỏ qua các subscription còn lại
        elapsed = time.monotonic() - start_time
        if elapsed > 2.0:
            logger.warning(
                "Dừng gửi WebPush cho user %s do vượt quá 2s (đã gửi thành công %s subscription)",
                getattr(user, "id", None),
                success_count,
            )
            break

        try:
            ok = send_webpush_to_subscription(sub, title, body, data=data, icon=icon, url=url)
            if ok:
                success_count += 1
        except Exception as exc:
            # Bắt mọi lỗi ở mức user để không làm hỏng toàn bộ luồng push-notification
            logger.exception(
                "Lỗi khi gửi WebPush cho user %s, subscription %s: %s",
                getattr(user, "id", None),
                sub.id,
                exc,
            )
            continue

    logger.info("Đã gửi WebPush tới %s subscription của user %s", success_count, user.id)
    return success_count


def send_webpush_to_user_id(
    user_id: int,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    icon: Optional[str] = None,
    url: Optional[str] = None,
) -> int:
    """
    Helper gửi WebPush theo user_id (dùng cho management command).
    """

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error("Không tìm thấy user id=%s để gửi WebPush", user_id)
        return 0

    return send_webpush_to_user(user, title, body, data=data, icon=icon, url=url)



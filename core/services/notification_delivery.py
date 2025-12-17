"""
Delivery Worker - Thực sự gửi notification qua các kênh.

Luồng:
1. Đọc NotificationDelivery có status=pending
2. Gửi qua channel tương ứng (web_push, in_app)
3. Cập nhật status và metadata
"""

from __future__ import annotations

import logging
from typing import List, Optional
from django.utils import timezone

from core.models import Notification, NotificationDelivery
from core.services.notifications import send_webpush_to_user

logger = logging.getLogger(__name__)


class NotificationDeliveryWorker:
    """
    Worker xử lý gửi notification thực sự.
    """

    @staticmethod
    def send_web_push_delivery(delivery: NotificationDelivery) -> bool:
        """
        Gửi web push notification cho 1 delivery.

        Returns:
            bool: True nếu gửi thành công
        """
        if delivery.channel != NotificationDelivery.CHANNEL_WEB_PUSH:
            logger.warning(f"Delivery #{delivery.id} không phải web_push channel")
            return False

        if delivery.status != NotificationDelivery.STATUS_PENDING:
            logger.warning(f"Delivery #{delivery.id} không ở trạng thái pending")
            return False

        notification = delivery.notification
        user = delivery.user

        # Chuẩn bị data cho web push
        data = {
            "notification_id": notification.id,
            "delivery_id": delivery.id,
            "action": notification.action,
            "tag": notification.tag or "",
        }

        if notification.link:
            data["url"] = notification.link

        if notification.count is not None:
            data["count"] = notification.count

        # Gửi web push
        try:
            success_count = send_webpush_to_user(
                user=user,
                title=notification.title,
                body=notification.body,
                data=data,
                icon=None,  # Có thể thêm icon sau
                url=notification.link,
            )

            if success_count > 0:
                delivery.status = NotificationDelivery.STATUS_SENT
                delivery.sent_at = timezone.now()
                delivery.delivery_metadata = {
                    "subscriptions_sent": success_count,
                    "method": "web_push",
                }
                delivery.save(update_fields=["status", "sent_at", "delivery_metadata"])
                logger.info(f"Sent web push delivery #{delivery.id} to user {user.username}")
                return True
            else:
                delivery.status = NotificationDelivery.STATUS_FAILED
                delivery.error_message = "Không có subscription active"
                delivery.save(update_fields=["status", "error_message"])
                logger.warning(f"No active subscriptions for user {user.username}")
                return False

        except Exception as exc:
            delivery.status = NotificationDelivery.STATUS_FAILED
            delivery.error_message = str(exc)
            delivery.save(update_fields=["status", "error_message"])
            logger.exception(f"Error sending web push delivery #{delivery.id}: {exc}")
            return False

    @staticmethod
    def send_in_app_delivery(delivery: NotificationDelivery) -> bool:
        """
        Đánh dấu in-app delivery là đã gửi (vì in-app chỉ cần lưu vào DB,
        frontend sẽ tự đọc từ API).

        Returns:
            bool: True (luôn thành công vì chỉ cần lưu DB)
        """
        if delivery.channel != NotificationDelivery.CHANNEL_IN_APP:
            logger.warning(f"Delivery #{delivery.id} không phải in_app channel")
            return False

        if delivery.status != NotificationDelivery.STATUS_PENDING:
            logger.warning(f"Delivery #{delivery.id} không ở trạng thái pending")
            return False

        # In-app chỉ cần đánh dấu là sent (frontend sẽ đọc từ API)
        delivery.status = NotificationDelivery.STATUS_SENT
        delivery.sent_at = timezone.now()
        delivery.delivery_metadata = {"method": "in_app"}
        delivery.save(update_fields=["status", "sent_at", "delivery_metadata"])
        logger.info(f"Marked in-app delivery #{delivery.id} as sent")
        return True

    @classmethod
    def process_delivery(cls, delivery: NotificationDelivery) -> bool:
        """
        Xử lý 1 delivery theo channel.

        Returns:
            bool: True nếu gửi thành công
        """
        if delivery.channel == NotificationDelivery.CHANNEL_WEB_PUSH:
            return cls.send_web_push_delivery(delivery)
        elif delivery.channel == NotificationDelivery.CHANNEL_IN_APP:
            return cls.send_in_app_delivery(delivery)
        else:
            logger.warning(f"Unknown channel: {delivery.channel}")
            return False

    @classmethod
    def process_pending_deliveries(
        cls,
        limit: Optional[int] = None,
        notification_id: Optional[int] = None,
        timeout_seconds: Optional[int] = 30,
    ) -> dict:
        """
        Xử lý tất cả deliveries có status=pending.

        Args:
            limit: Giới hạn số lượng xử lý (None = không giới hạn)
            notification_id: Chỉ xử lý deliveries của notification này (None = tất cả)
            timeout_seconds: Timeout tổng thể cho toàn bộ quá trình xử lý (None = không giới hạn)

        Returns:
            dict: {
                "processed": int,
                "success": int,
                "failed": int,
                "timeout": bool,  # True nếu bị timeout
            }
        """
        import time
        
        start_time = time.monotonic()
        qs = NotificationDelivery.objects.filter(status=NotificationDelivery.STATUS_PENDING)

        if notification_id:
            qs = qs.filter(notification_id=notification_id)

        if limit:
            qs = qs[:limit]

        deliveries = list(qs)
        total = len(deliveries)
        success = 0
        failed = 0
        timed_out = False

        for delivery in deliveries:
            # Kiểm tra timeout trước mỗi delivery
            if timeout_seconds is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout_seconds:
                    logger.warning(
                        f"Timeout sau {timeout_seconds}s khi xử lý deliveries "
                        f"(đã xử lý {success + failed}/{total})"
                    )
                    timed_out = True
                    break
            
            try:
                if cls.process_delivery(delivery):
                    success += 1
                else:
                    failed += 1
            except Exception as exc:
                # Bắt mọi exception để không làm gián đoạn toàn bộ quá trình
                logger.exception(f"Lỗi không mong đợi khi xử lý delivery #{delivery.id}: {exc}")
                failed += 1
                # Đánh dấu delivery là failed
                try:
                    delivery.status = NotificationDelivery.STATUS_FAILED
                    delivery.error_message = str(exc)[:500]  # Giới hạn độ dài error message
                    delivery.save(update_fields=["status", "error_message"])
                except Exception as save_exc:
                    logger.exception(f"Lỗi khi lưu delivery #{delivery.id} sau khi xử lý lỗi: {save_exc}")

        # Cập nhật status của notification nếu tất cả deliveries đã xử lý (và không bị timeout)
        if notification_id and not timed_out:
            try:
                notification = Notification.objects.get(id=notification_id)
                remaining = NotificationDelivery.objects.filter(
                    notification=notification,
                    status=NotificationDelivery.STATUS_PENDING,
                ).count()

                if remaining == 0:
                    # Kiểm tra xem có delivery nào failed không
                    has_failed = NotificationDelivery.objects.filter(
                        notification=notification,
                        status=NotificationDelivery.STATUS_FAILED,
                    ).exists()

                    if has_failed:
                        notification.status = Notification.STATUS_FAILED
                    else:
                        notification.status = Notification.STATUS_SENT
                        notification.sent_at = timezone.now()
                    notification.save(update_fields=["status", "sent_at"])
            except Exception as exc:
                logger.exception(f"Lỗi khi cập nhật status notification #{notification_id}: {exc}")

        result = {
            "processed": success + failed,
            "success": success,
            "failed": failed,
            "timeout": timed_out,
        }

        logger.info(
            f"Processed {success + failed}/{total} deliveries: {success} success, {failed} failed"
            + (f" (timeout after {timeout_seconds}s)" if timed_out else "")
        )

        return result


"""
Notification Engine - Xử lý routing và tạo bản ghi notification.

Luồng làm việc:
1. Business layer gọi emit_event(event_type, context)
2. Notification Engine:
   - Đọc rule & setting
   - Quyết định ai nhận, kênh nào
   - Tạo bản ghi Notification (lịch sử)
   - Tạo NotificationDelivery cho từng channel
3. Delivery worker gửi thực sự (FCM, email, v.v.)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from django.db import transaction

from core.models import Notification, NotificationDelivery

logger = logging.getLogger(__name__)

User = get_user_model()


class NotificationEngine:
    """
    Engine xử lý notification: routing và tạo bản ghi.
    """

    # Departments từ user.last_name
    DEPT_CSKH = "CSKH"
    DEPT_MARKETING = "Marketing"
    DEPT_QUAN_TRI = "QUẢN TRỊ VIÊN"
    DEPT_KHO_HN = "KHO_HN"
    DEPT_KHO_HCM = "KHO_HCM"

    # Shop groups
    SHOP_GIADUNGPLUS = "SHOP_GIADUNGPLUS"
    SHOP_LTENG = "SHOP_LTENG"
    SHOP_PHALEDO = "SHOP_PHALEDO"

    @staticmethod
    def get_users_by_criteria(
        groups: Optional[List[str]] = None,
        departments: Optional[List[str]] = None,
        shops: Optional[List[str]] = None,
        user_ids: Optional[List[int]] = None,
    ) -> List[User]:
        """
        Lấy danh sách users theo các tiêu chí.

        Args:
            groups: Danh sách tên group (ví dụ: ["Admin", "CSKHManager"])
            departments: Danh sách department từ user.last_name (ví dụ: ["CSKH", "KHO_HN"])
            shops: Danh sách shop group (ví dụ: ["SHOP_GIADUNGPLUS"])
            user_ids: Danh sách user ID cụ thể

        Returns:
            List[User]: Danh sách users thỏa mãn tiêu chí
        """
        users = User.objects.filter(is_active=True)

        # Filter theo groups
        if groups:
            if "ALL" not in groups:
                users = users.filter(groups__name__in=groups).distinct()

        # Filter theo departments (từ user.last_name)
        if departments:
            if "ALL" not in departments:
                users = users.filter(last_name__in=departments)

        # Filter theo shop groups
        if shops:
            if "ALL" not in shops:
                users = users.filter(groups__name__in=shops).distinct()

        # Filter theo user_ids cụ thể
        if user_ids:
            users = users.filter(id__in=user_ids)

        return list(users)

    @staticmethod
    def create_notification(
        title: str,
        body: str,
        link: Optional[str] = None,
        action: str = Notification.ACTION_SHOW_POPUP,
        sound: Optional[str] = None,
        count: Optional[int] = None,
        collapse_id: Optional[str] = None,
        tag: Optional[str] = None,
        scheduled_time: Optional[datetime] = None,
        event_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Notification:
        """
        Tạo bản ghi Notification.

        Nếu có collapse_id, tìm và đánh dấu các notification cũ cùng collapse_id là cancelled.
        """
        # Nếu có collapse_id, đánh dấu các notification cũ là cancelled
        if collapse_id:
            Notification.objects.filter(
                collapse_id=collapse_id,
                status=Notification.STATUS_PENDING,
            ).update(status=Notification.STATUS_CANCELLED)

        notification = Notification.objects.create(
            title=title,
            body=body,
            link=link or "",
            action=action,
            sound=sound or "",
            count=count,
            collapse_id=collapse_id,
            tag=tag,
            scheduled_time=scheduled_time,
            event_type=event_type,
            context=context or {},
            status=Notification.STATUS_PENDING if not scheduled_time else Notification.STATUS_PENDING,
        )

        logger.info(f"Created notification #{notification.id}: {title}")
        return notification

    @staticmethod
    def create_deliveries(
        notification: Notification,
        users: List[User],
        channels: Optional[List[str]] = None,
    ) -> List[NotificationDelivery]:
        """
        Tạo NotificationDelivery cho từng user và channel.

        Args:
            notification: Notification instance
            users: Danh sách users cần gửi
            channels: Danh sách channels (mặc định: [CHANNEL_IN_APP, CHANNEL_WEB_PUSH])

        Returns:
            List[NotificationDelivery]: Danh sách deliveries đã tạo
        """
        if not channels:
            channels = [NotificationDelivery.CHANNEL_IN_APP, NotificationDelivery.CHANNEL_WEB_PUSH]

        deliveries = []
        for user in users:
            for channel in channels:
                delivery, created = NotificationDelivery.objects.get_or_create(
                    notification=notification,
                    user=user,
                    channel=channel,
                    defaults={
                        "status": NotificationDelivery.STATUS_PENDING,
                    },
                )
                if created:
                    deliveries.append(delivery)

        logger.info(
            f"Created {len(deliveries)} deliveries for notification #{notification.id} "
            f"to {len(users)} users"
        )
        return deliveries

    @classmethod
    def emit_notification(
        cls,
        title: str,
        body: str,
        link: Optional[str] = None,
        action: str = Notification.ACTION_SHOW_POPUP,
        sound: Optional[str] = None,
        count: Optional[int] = None,
        collapse_id: Optional[str] = None,
        tag: Optional[str] = None,
        scheduled_time: Optional[datetime] = None,
        event_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        # Target criteria
        groups: Optional[List[str]] = None,
        departments: Optional[List[str]] = None,
        shops: Optional[List[str]] = None,
        user_ids: Optional[List[int]] = None,
        channels: Optional[List[str]] = None,
    ) -> Notification:
        """
        Tạo notification và deliveries cho các users thỏa mãn tiêu chí.

        Đây là hàm chính để gọi từ business layer.

        Returns:
            Notification: Notification instance đã tạo
        """
        with transaction.atomic():
            # 1. Tạo notification
            notification = cls.create_notification(
                title=title,
                body=body,
                link=link,
                action=action,
                sound=sound,
                count=count,
                collapse_id=collapse_id,
                tag=tag,
                scheduled_time=scheduled_time,
                event_type=event_type,
                context=context,
            )

            # 2. Lấy danh sách users
            users = cls.get_users_by_criteria(
                groups=groups,
                departments=departments,
                shops=shops,
                user_ids=user_ids,
            )

            if not users:
                logger.warning(f"No users found for notification #{notification.id}")
                return notification

            # 3. Tạo deliveries
            cls.create_deliveries(
                notification=notification,
                users=users,
                channels=channels,
            )

            return notification


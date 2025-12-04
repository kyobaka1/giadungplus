"""
Service tái sử dụng để gửi notification từ mọi app.

Cách sử dụng:
    from core.services.notify import notify

    # Gửi cho group
    notify.send(
        title="Ticket mới",
        body="Có ticket #123 cần xử lý",
        groups=["CSKHManager", "CSKHStaff"],
        link="/cskh/tickets/123",
    )

    # Gửi cho department
    notify.send(
        title="Đơn hàng mới",
        body="Có đơn hàng #456",
        departments=["KHO_HN"],
        link="/kho/orders/456",
    )

    # Gửi với action và sound
    notify.send(
        title="Thông báo quan trọng",
        body="Cần xử lý ngay",
        action="boss_popup",
        sound="/static/sounds/alert.mp3",
        groups=["ALL"],
    )

    # Badge update
    notify.send(
        title="Cập nhật badge",
        action="badge_update",
        count=5,
        collapse_id="ticket_count",
        groups=["CSKHStaff"],
    )

    # Hẹn giờ
    from datetime import datetime, timedelta
    notify.send(
        title="Nhắc nhở",
        body="Nhắc nhở sau 1 giờ",
        scheduled_time=datetime.now() + timedelta(hours=1),
        groups=["ALL"],
    )
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

from core.services.notification_engine import NotificationEngine
from core.models import Notification

logger = logging.getLogger(__name__)


class NotifyService:
    """
    Service tái sử dụng để gửi notification.
    """

    @staticmethod
    def send(
        title: str,
        body: str = "",
        link: Optional[str] = None,
        action: str = Notification.ACTION_SHOW_POPUP,
        sound: Optional[str] = None,
        count: Optional[int] = None,
        collapse_id: Optional[str] = None,
        tag: Optional[str] = None,
        scheduled_time: Optional[datetime] = None,
        event_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        # Target criteria - có thể dùng "ALL" để chọn tất cả
        groups: Optional[Union[List[str], str]] = None,
        departments: Optional[Union[List[str], str]] = None,
        shops: Optional[Union[List[str], str]] = None,
        user_ids: Optional[Union[List[int], int]] = None,
        channels: Optional[List[str]] = None,
    ) -> Notification:
        """
        Gửi notification tới users thỏa mãn tiêu chí.

        Args:
            title: Tiêu đề thông báo (bắt buộc)
            body: Nội dung thông báo
            link: URL khi click vào thông báo
            action: Loại hành động (show_popup, play_sound, badge_update, boss_popup)
            sound: Link sound ở /static/ (nếu có)
            count: Số lượng cho badge_update
            collapse_id: ID để đè notify cũ bằng notify mới
            tag: Tag phân loại thông báo
            scheduled_time: Thời gian hẹn gửi (None = gửi ngay)
            event_type: Loại event từ business layer
            context: Dữ liệu context từ business layer (JSON)
            groups: Danh sách tên group hoặc "ALL" (ví dụ: ["Admin", "CSKHManager"] hoặc "ALL")
            departments: Danh sách department hoặc "ALL" (ví dụ: ["CSKH", "KHO_HN"] hoặc "ALL")
            shops: Danh sách shop group hoặc "ALL" (ví dụ: ["SHOP_GIADUNGPLUS"] hoặc "ALL")
            user_ids: Danh sách user ID cụ thể hoặc 1 user ID
            channels: Danh sách channels (mặc định: [in_app, web_push])

        Returns:
            Notification: Notification instance đã tạo

        Examples:
            # Gửi cho tất cả users
            notify.send(
                title="Thông báo chung",
                body="Nội dung thông báo",
                groups="ALL",
            )

            # Gửi cho group cụ thể
            notify.send(
                title="Ticket mới",
                body="Có ticket cần xử lý",
                groups=["CSKHManager", "CSKHStaff"],
                link="/cskh/tickets/123",
            )

            # Gửi cho department
            notify.send(
                title="Đơn hàng mới",
                departments=["KHO_HN"],
                link="/kho/orders/456",
            )

            # Badge update với collapse_id
            notify.send(
                title="",
                action="badge_update",
                count=5,
                collapse_id="ticket_count",
                groups=["CSKHStaff"],
            )
        """
        # Normalize input: chuyển string thành list
        if groups == "ALL" or groups is None:
            groups_list = ["ALL"]
        elif isinstance(groups, str):
            groups_list = [groups]
        else:
            groups_list = groups

        if departments == "ALL" or departments is None:
            departments_list = ["ALL"]
        elif isinstance(departments, str):
            departments_list = [departments]
        else:
            departments_list = departments

        if shops == "ALL" or shops is None:
            shops_list = ["ALL"]
        elif isinstance(shops, str):
            shops_list = [shops]
        else:
            shops_list = shops

        if user_ids is None:
            user_ids_list = None
        elif isinstance(user_ids, int):
            user_ids_list = [user_ids]
        else:
            user_ids_list = user_ids

        # Gọi Notification Engine
        notification = NotificationEngine.emit_notification(
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
            groups=groups_list,
            departments=departments_list,
            shops=shops_list,
            user_ids=user_ids_list,
            channels=channels,
        )

        logger.info(
            f"Notification #{notification.id} created: {title} "
            f"(groups={groups_list}, departments={departments_list}, shops={shops_list})"
        )

        return notification


# Export singleton instance
notify = NotifyService()


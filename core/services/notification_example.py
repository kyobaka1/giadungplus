"""
Ví dụ sử dụng hệ thống notification.

Chạy trong Django shell:
    python manage.py shell
    >>> from core.services.notification_example import *
    >>> test_send_notification()
"""

from core.services.notify import notify
from datetime import datetime, timedelta


def test_send_notification():
    """
    Test gửi notification cho tất cả users.
    """
    notification = notify.send(
        title="Test Notification",
        body="Đây là thông báo test từ hệ thống",
        groups="ALL",
        link="/",
        event_type="test",
        context={"test": True},
    )
    print(f"✅ Đã tạo notification #{notification.id}")
    return notification


def test_send_to_group():
    """
    Test gửi notification cho group cụ thể.
    """
    notification = notify.send(
        title="Thông báo cho CSKH",
        body="Có ticket mới cần xử lý",
        groups=["CSKHManager", "CSKHStaff"],
        link="/cskh/",
        event_type="ticket_created",
    )
    print(f"✅ Đã tạo notification #{notification.id} cho CSKH")
    return notification


def test_badge_update():
    """
    Test cập nhật badge.
    """
    notification = notify.send(
        title="",
        body="",
        action="badge_update",
        count=5,
        collapse_id="test_badge",
        groups="ALL",
    )
    print(f"✅ Đã tạo badge update notification #{notification.id}")
    return notification


def test_scheduled_notification():
    """
    Test hẹn giờ gửi notification (sau 1 phút).
    """
    scheduled_time = datetime.now() + timedelta(minutes=1)
    notification = notify.send(
        title="Thông báo hẹn giờ",
        body="Thông báo này sẽ được gửi sau 1 phút",
        scheduled_time=scheduled_time,
        groups="ALL",
    )
    print(f"✅ Đã tạo scheduled notification #{notification.id} (sẽ gửi lúc {scheduled_time})")
    print("   Chạy: python manage.py process_notifications để xử lý")
    return notification


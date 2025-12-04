"""
Management command để xử lý notifications:
- Gửi các scheduled notifications đã đến giờ
- Xử lý pending deliveries

Chạy mỗi 10 phút bằng cron:
    */10 * * * * cd /path/to/project && python manage.py process_notifications
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime

from core.models import Notification
from core.services.notification_delivery import NotificationDeliveryWorker


class Command(BaseCommand):
    help = (
        "Xử lý notifications:\n"
        "- Gửi các scheduled notifications đã đến giờ\n"
        "- Xử lý pending deliveries"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Giới hạn số lượng deliveries xử lý (mặc định: không giới hạn)",
        )
        parser.add_argument(
            "--notification-id",
            type=int,
            default=None,
            help="Chỉ xử lý deliveries của notification này",
        )

    def handle(self, *args, **options):
        limit = options.get("limit")
        notification_id = options.get("notification_id")

        # 1. Xử lý scheduled notifications đã đến giờ
        now = timezone.now()
        scheduled_notifications = Notification.objects.filter(
            status=Notification.STATUS_PENDING,
            scheduled_time__lte=now,
            scheduled_time__isnull=False,
        )

        count_scheduled = scheduled_notifications.count()
        if count_scheduled > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Tìm thấy {count_scheduled} scheduled notifications đã đến giờ"
                )
            )

            for notification in scheduled_notifications:
                # Xử lý deliveries của notification này
                result = NotificationDeliveryWorker.process_pending_deliveries(
                    notification_id=notification.id,
                )
                self.stdout.write(
                    f"  Notification #{notification.id}: "
                    f"{result['success']} success, {result['failed']} failed"
                )

        # 2. Xử lý pending deliveries (không scheduled hoặc đã đến giờ)
        self.stdout.write("Xử lý pending deliveries...")
        result = NotificationDeliveryWorker.process_pending_deliveries(
            limit=limit,
            notification_id=notification_id,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Đã xử lý {result['processed']} deliveries: "
                f"{result['success']} success, {result['failed']} failed"
            )
        )


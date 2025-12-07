# orders/management/commands/auto_xpress_push.py
"""
Django management command để tự động xử lý đơn hoả tốc.
Chạy mỗi 5 phút bằng crontab:
    */5 * * * * cd /path/to/project && python manage.py auto_xpress_push
"""

from django.core.management.base import BaseCommand
from orders.services.auto_xpress_push import auto_process_express_orders
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Tự động xử lý đơn hoả tốc: tìm lại shipper cho đơn đã chuẩn bị, chuẩn bị hàng cho đơn chưa chuẩn bị (>50 phút)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Số đơn tối đa xử lý mỗi lần (default: 50)',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        
        self.stdout.write(self.style.SUCCESS(f"[AUTO_XPRESS] Bắt đầu xử lý đơn hoả tốc (limit={limit})..."))
        
        try:
            result = auto_process_express_orders(limit=limit)
            
            self.stdout.write(self.style.SUCCESS(f"[AUTO_XPRESS] Hoàn tất:"))
            self.stdout.write(f"  - Tổng đơn: {result['total']}")
            self.stdout.write(f"  - Đã chuẩn bị: {result['prepared']}")
            self.stdout.write(f"  - Chưa chuẩn bị: {result['unprepared']}")
            if result.get('skipped', 0) > 0:
                self.stdout.write(self.style.WARNING(f"  - Bị bỏ qua: {result['skipped']}"))
            self.stdout.write(f"  - Tìm lại shipper: ✅ {result['find_shipper_success']} | ❌ {result['find_shipper_failed']}")
            self.stdout.write(f"  - Chuẩn bị hàng: ✅ {result['prepare_success']} | ❌ {result['prepare_failed']}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[AUTO_XPRESS] Lỗi: {e}"))
            logger.exception("Lỗi khi chạy auto_xpress_push")
            raise

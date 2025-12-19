# orders/management/commands/auto_xpress_push.py
"""
Django management command để tự động xử lý đơn hoả tốc.
Chạy mỗi 5 phút bằng crontab:
    */5 * * * * cd /path/to/project && python manage.py auto_xpress_push

Thời gian chạy:
- Thứ 2 đến thứ 7: 8:00 - 20:00
- Chủ nhật: 10:00 - 18:00
"""

from django.core.management.base import BaseCommand
from orders.services.auto_xpress_push import auto_process_express_orders
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Tự động xử lý đơn hoả tốc: tìm lại shipper cho đơn đã chuẩn bị, chuẩn bị hàng cho đơn chưa chuẩn bị (>30 phút)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Số đơn tối đa xử lý mỗi lần (default: 50)',
        )

    def _is_within_working_hours(self) -> bool:
        """
        Kiểm tra xem thời gian hiện tại có nằm trong giờ làm việc không.
        
        Giờ làm việc:
        - Ngày thường (Thứ 2-7): 8:00 - 20:00 (bao gồm cả 20:00)
        - Chủ nhật: 10:00 - 18:00 (bao gồm cả 18:00)
        
        Returns:
            True nếu trong giờ làm việc, False nếu không
        """
        from zoneinfo import ZoneInfo
        
        # Sử dụng timezone VN để đảm bảo chính xác
        tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
        now = datetime.now(tz_vn)
        weekday = now.weekday()  # 0 = Monday, 6 = Sunday
        hour = now.hour
        minute = now.minute
        
        # Chủ nhật (weekday = 6): 10:00 - 18:00 (bao gồm cả 18:00)
        if weekday == 6:
            if hour < 10:
                return False
            if hour > 18:
                return False
            if hour == 18:
                return True  # 18:00 vẫn được tính
            return True  # 10 <= hour < 18
        
        # Thứ 2 đến thứ 7 (weekday 0-5): 8:00 - 20:00 (bao gồm cả 20:00)
        if hour < 8:
            return False
        if hour > 20:
            return False
        if hour == 20:
            return True  # 20:00 vẫn được tính
        return True  # 8 <= hour < 20

    def handle(self, *args, **options):
        from zoneinfo import ZoneInfo
        
        limit = options['limit']
        
        # Kiểm tra thời gian trước khi chạy
        if not self._is_within_working_hours():
            tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
            now = datetime.now(tz_vn)
            weekday_name = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật'][now.weekday()]
            self.stdout.write(
                self.style.WARNING(
                    f"[AUTO_XPRESS] Ngoài giờ làm việc. "
                    f"Hiện tại: {weekday_name} {now.strftime('%H:%M:%S')} (GMT+7). "
                    f"Chỉ chạy từ 8h-20h (Thứ 2-7) hoặc 10h-18h (Chủ nhật)."
                )
            )
            logger.warning(
                f"[AUTO_XPRESS] Ngoài giờ làm việc. "
                f"Hiện tại: {weekday_name} {now.strftime('%H:%M:%S')} (GMT+7). "
                f"Chỉ chạy từ 8h-20h (Thứ 2-7) hoặc 10h-18h (Chủ nhật)."
            )
            return
        
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

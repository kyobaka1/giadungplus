# orders/management/commands/auto_prepare_xpress_orders.py
from django.core.management.base import BaseCommand
from orders.services.order_xpress_auto import auto_prepare_express_orders

class Command(BaseCommand):
    help = "Tự động chuẩn bị hàng cho đơn hoả tốc"

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Số đơn tối đa xử lý mỗi lần.',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        self.stdout.write(f"Đang tự chuẩn bị hoả tốc (limit={limit})...")
        auto_prepare_express_orders(limit=limit)
        self.stdout.write("Xong.")

import json

from django.core.management.base import BaseCommand, CommandParser

from core.models import WebPushSubscription
from core.services.notifications import (
    send_webpush_to_subscription,
    send_webpush_to_user_id,
)


class Command(BaseCommand):
    help = (
        "Gửi test Web Push Notification.\n"
        "- Nếu truyền --user_id: gửi tới tất cả subscription active của user đó.\n"
        "- Nếu KHÔNG truyền --user_id: gửi tới TẤT CẢ subscription active trong hệ thống (kể cả user_id=None)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--user_id",
            type=int,
            required=False,
            default=None,
            help="ID của user cần gửi (bỏ trống để gửi tới tất cả subscription)",
        )
        parser.add_argument(
            "--title",
            type=str,
            default="Thông báo test",
            help="Tiêu đề notification",
        )
        parser.add_argument(
            "--body",
            type=str,
            default="Đây là thông báo test từ hệ thống GiaDungPlus.",
            help="Nội dung notification",
        )
        parser.add_argument(
            "--url",
            type=str,
            default="/",
            help="URL khi user click vào notification",
        )
        parser.add_argument(
            "--data",
            type=str,
            default="{}",
            help='Chuỗi JSON data bổ sung, ví dụ: \'{"type": "test"}\'',
        )

    def handle(self, *args, **options):
        user_id = options.get("user_id")
        title = options["title"]
        body = options["body"]
        url = options["url"]
        raw_data = options["data"]

        try:
            extra_data = json.loads(raw_data) if raw_data else {}
        except json.JSONDecodeError:
            self.stderr.write(self.style.ERROR("Chuỗi --data không phải JSON hợp lệ, dùng {}."))
            extra_data = {}

        # Thêm url vào data để service worker có thể dùng nếu cần
        extra_data.setdefault("url", url)

        if user_id is not None:
            # Gửi cho 1 user cụ thể (giữ hành vi cũ)
            self.stdout.write(
                f"Gửi test WebPush tới user_id={user_id} với title='{title}', body='{body}'..."
            )
            count = send_webpush_to_user_id(
                user_id,
                title,
                body,
                data=extra_data,
                url=url,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Đã gửi thành công tới {count} subscription.")
            )
        else:
            # Gửi tới toàn bộ subscription active (kể cả user_id=None)
            self.stdout.write(
                f"Gửi test WebPush tới TẤT CẢ subscription active với title='{title}', body='{body}'..."
            )
            qs = WebPushSubscription.objects.filter(is_active=True)
            total = qs.count()
            success = 0
            for sub in qs:
                if send_webpush_to_subscription(
                    sub,
                    title,
                    body,
                    data=extra_data,
                    url=url,
                ):
                    success += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Đã gửi thành công tới {success}/{total} subscription active."
                )
            )



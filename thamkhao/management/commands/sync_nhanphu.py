# thamkhao/management/commands/sync_nhanphu.py
"""
Management command để đồng bộ thông tin nhãn phụ từ customer note lên product description.
"""
from django.core.management.base import BaseCommand
from django.test import RequestFactory
from thamkhao.views import sync_nhanphu_from_customer_note
import json


class Command(BaseCommand):
    help = 'Đồng bộ thông tin nhãn phụ từ customer note (ID: 760093681) lên product description metagdp'

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write("Đang chạy sync_nhanphu_from_customer_note...")
        self.stdout.write("=" * 60)
        
        factory = RequestFactory()
        request = factory.get('/thamkhao/sync-nhanphu/')
        
        try:
            self.stdout.write("Đang gọi hàm...")
            response = sync_nhanphu_from_customer_note(request)
            content = json.loads(response.content)
            
            self.stdout.write("\nKết quả:")
            self.stdout.write(json.dumps(content, indent=2, ensure_ascii=False))
            
            if content.get('status') == 'ok':
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n✅ Thành công: {content.get('success')}/{content.get('processed')} products"
                    )
                )
                if content.get('errors') > 0:
                    self.stdout.write(
                        self.style.WARNING(f"⚠️  Lỗi: {content.get('errors')} products")
                    )
            else:
                self.stdout.write(
                    self.style.ERROR(f"\n❌ Lỗi: {content.get('message', 'Unknown error')}")
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Lỗi khi chạy: {e}"))
            import traceback
            traceback.print_exc()

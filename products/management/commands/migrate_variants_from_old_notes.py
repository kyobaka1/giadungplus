# products/management/commands/migrate_variants_from_old_notes.py
"""
Management command để migrate variant metadata từ customer notes (format cũ) 
sang product.description với GDP_META (format mới).

Usage:
    python manage.py migrate_variants_from_old_notes
    python manage.py migrate_variants_from_old_notes --test-mode
    python manage.py migrate_variants_from_old_notes --limit 100
"""

from django.core.management.base import BaseCommand
from products.services.variant_migration import init_variants_from_old_data


class Command(BaseCommand):
    help = 'Migrate variant metadata từ customer notes cũ sang product.description (GDP_META format)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-mode',
            action='store_true',
            help='Chế độ test: chỉ log, không thực sự update (default: False)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Giới hạn số lượng variants để migrate (default: None = tất cả)',
        )

    def handle(self, *args, **options):
        test_mode = options['test_mode']
        limit = options['limit']
        
        if test_mode:
            self.stdout.write(
                self.style.WARNING('⚠️  CHẾ ĐỘ TEST: Chỉ log, không thực sự update!')
            )
        else:
            self.stdout.write(
                self.style.WARNING('⚠️  CHẾ ĐỘ THẬT: Sẽ update product.description!')
            )
            confirm = input('Bạn có chắc chắn muốn tiếp tục? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.ERROR('Đã hủy.'))
                return
        
        self.stdout.write('')
        self.stdout.write('=' * 60)
        self.stdout.write('BẮT ĐẦU MIGRATE VARIANTS TỪ CUSTOMER NOTES')
        self.stdout.write('=' * 60)
        self.stdout.write('')
        
        if limit:
            self.stdout.write(f'Giới hạn: {limit} variants')
        else:
            self.stdout.write('Không giới hạn - sẽ migrate tất cả variants')
        
        self.stdout.write('')
        self.stdout.write('Đang tải dữ liệu từ customer notes...')
        
        # Gọi hàm migration
        result = init_variants_from_old_data(test_mode=test_mode, limit=limit)
        
        # Hiển thị kết quả
        self.stdout.write('')
        self.stdout.write('=' * 60)
        self.stdout.write('KẾT QUẢ MIGRATION')
        self.stdout.write('=' * 60)
        self.stdout.write('')
        
        self.stdout.write(f'Tổng số variants trong customer notes: {result["total_old_variants"]}')
        self.stdout.write(
            self.style.SUCCESS(f'✓ Đã migrate thành công: {result["migrated"]}')
        )
        self.stdout.write(
            self.style.WARNING(f'⚠ Đã bỏ qua: {result["skipped"]}')
        )
        self.stdout.write(
            self.style.ERROR(f'✗ Lỗi: {result["errors"]}')
        )
        
        # Hiển thị chi tiết nếu có
        if result.get("details"):
            self.stdout.write('')
            self.stdout.write('Chi tiết:')
            success_count = sum(1 for d in result["details"] if d.get("status") == "success")
            error_count = sum(1 for d in result["details"] if d.get("status") == "error")
            skipped_count = sum(1 for d in result["details"] if d.get("status") == "skipped")
            
            if success_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'  - Thành công: {success_count} variants')
                )
            if error_count > 0:
                self.stdout.write(
                    self.style.ERROR(f'  - Lỗi: {error_count} variants')
                )
                # Hiển thị một vài lỗi đầu tiên
                errors = [d for d in result["details"] if d.get("status") == "error"][:5]
                for err in errors:
                    self.stdout.write(
                        self.style.ERROR(f'    Variant {err.get("variant_id")}: {err.get("reason", "Unknown error")}')
                    )
            if skipped_count > 0:
                self.stdout.write(
                    self.style.WARNING(f'  - Bỏ qua: {skipped_count} variants')
                )
        
        self.stdout.write('')
        self.stdout.write('=' * 60)
        self.stdout.write(
            self.style.SUCCESS('✓ HOÀN THÀNH!')
        )
        self.stdout.write('=' * 60)


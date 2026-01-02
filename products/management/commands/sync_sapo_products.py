# products/management/commands/sync_sapo_products.py
"""
Management command để sync products và variants từ Sapo API vào database cache.

Usage:
    python manage.py sync_sapo_products
    python manage.py sync_sapo_products --status active
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
import logging

from products.services.product_sync_service import ProductSyncService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync products và variants từ Sapo API vào database cache'

    def add_arguments(self, parser):
        parser.add_argument(
            '--status',
            type=str,
            default='active',
            help='Status filter (default: active)'
        )

    def handle(self, *args, **options):
        status = options.get('status', 'active')
        
        self.stdout.write(self.style.SUCCESS(
            f'Starting sync products from Sapo API (status={status})...'
        ))
        
        start_time = timezone.now()
        
        try:
            service = ProductSyncService()
            stats = service.sync_all_products(status=status)
            
            elapsed_time = (timezone.now() - start_time).total_seconds()
            
            # Output results
            self.stdout.write(self.style.SUCCESS(
                f'\n=== Sync Completed ===\n'
                f'Total pages: {stats["total_pages"]}\n'
                f'Total products: {stats["total_products"]}\n'
                f'Total variants: {stats["total_variants"]}\n'
                f'Created products: {stats["created_products"]}\n'
                f'Updated products: {stats["updated_products"]}\n'
                f'Created variants: {stats["created_variants"]}\n'
                f'Updated variants: {stats["updated_variants"]}\n'
                f'Time elapsed: {elapsed_time:.2f}s\n'
            ))
            
            if stats["errors"]:
                self.stdout.write(self.style.WARNING(
                    f'\nErrors ({len(stats["errors"])}):'
                ))
                for error in stats["errors"][:10]:  # Show first 10 errors
                    self.stdout.write(self.style.ERROR(f'  - {error}'))
                if len(stats["errors"]) > 10:
                    self.stdout.write(self.style.WARNING(
                        f'  ... and {len(stats["errors"]) - 10} more errors'
                    ))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f'Error syncing products: {str(e)}'
            ))
            logger.error(f'Error in sync_sapo_products command: {e}', exc_info=True)
            raise

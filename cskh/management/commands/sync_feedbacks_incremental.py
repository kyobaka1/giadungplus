# cskh/management/commands/sync_feedbacks_incremental.py
"""
Django management command để incremental sync feedbacks mới từ Shopee API (chạy định kỳ).
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from core.sapo_client import get_sapo_client
from cskh.services.feedback_sync_service import FeedbackSyncService
from cskh.models import FeedbackSyncJob
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Incremental sync feedbacks mới từ Shopee API (chạy định kỳ)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Số feedbacks mỗi batch (default: 50)'
        )
    
    def handle(self, *args, **options):
        batch_size = options['batch_size']
        
        # Initialize services
        sapo_client = get_sapo_client()
        sync_service = FeedbackSyncService(sapo_client)
        
        # Tạo incremental job
        job = sync_service.create_incremental_sync_job(batch_size=batch_size)
        self.stdout.write(
            self.style.SUCCESS(f'Created incremental sync job {job.id}')
        )
        
        # Chạy sync
        self.stdout.write(f'Starting incremental sync (job {job.id})...')
        self.stdout.write(f'  Batch size: {batch_size}')
        
        try:
            result = sync_service.run_incremental_sync(job)
            
            if result['success']:
                stopped_msg = " (stopped at existing feedback)" if result.get('stopped_at_existing') else ""
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Incremental sync completed{stopped_msg}: '
                        f'{result["synced"]} synced, {result["updated"]} updated, '
                        f'{len(result["errors"])} errors'
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f'❌ Incremental sync failed: {", ".join(result["errors"][:5])}'
                    )
                )
        except KeyboardInterrupt:
            job.status = 'paused'
            job.save()
            self.stdout.write(
                self.style.WARNING(f'Sync paused (job {job.id})')
            )
        except Exception as e:
            logger.error(f"Error in incremental sync command: {e}", exc_info=True)
            job.status = 'failed'
            job.completed_at = timezone.now()
            job.save()
            self.stdout.write(
                self.style.ERROR(f'❌ Sync failed: {str(e)}')
            )


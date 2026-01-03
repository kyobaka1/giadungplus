# cskh/management/commands/sync_feedbacks_full.py
"""
Django management command để full sync feedbacks từ Shopee API (chạy nền).
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from core.sapo_client import get_sapo_client
from cskh.services.feedback_sync_service import FeedbackSyncService
from cskh.models import FeedbackSyncJob
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Full sync feedbacks từ Shopee API (chạy nền)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=365,
            help='Số ngày gần nhất cần sync (default: 365)'
        )
        parser.add_argument(
            '--page-size',
            type=int,
            default=50,
            help='Số items mỗi trang (default: 50)'
        )
        parser.add_argument(
            '--max-feedbacks-per-shop',
            type=int,
            default=None,
            help='Số feedbacks tối đa mỗi shop (None = không giới hạn)'
        )
        parser.add_argument(
            '--resume-job-id',
            type=int,
            help='Resume từ job đã có (job ID)'
        )
    
    def handle(self, *args, **options):
        days = options['days']
        page_size = options['page_size']
        max_feedbacks_per_shop = options.get('max_feedbacks_per_shop')
        resume_job_id = options.get('resume_job_id')
        
        # Initialize services
        sapo_client = get_sapo_client()
        sync_service = FeedbackSyncService(sapo_client)
        
        # Tạo hoặc resume job
        if resume_job_id:
            try:
                job = FeedbackSyncJob.objects.get(id=resume_job_id)
                if job.status not in ['pending', 'paused', 'failed', 'completed']:
                    self.stdout.write(
                        self.style.ERROR(f'Job {resume_job_id} không thể resume (status: {job.status})')
                    )
                    return
                # Cho phép resume từ completed nếu có page/cursor
                if job.status == 'completed' and (job.current_page and job.current_page > 1):
                    self.stdout.write(
                        self.style.WARNING(f'Job {resume_job_id} có status=completed, nhưng có page/cursor -> cho phép resume')
                    )
                job.status = 'pending'
                job.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Resuming job {resume_job_id} (previous status: {job.status})')
                )
            except FeedbackSyncJob.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Job {resume_job_id} không tồn tại')
                )
                return
        else:
            # Tạo job mới
            job = sync_service.create_full_sync_job(
                days=days,
                page_size=page_size,
                max_feedbacks_per_shop=max_feedbacks_per_shop
            )
            self.stdout.write(
                self.style.SUCCESS(f'Created full sync job {job.id}')
            )
        
        # Chạy sync
        self.stdout.write(f'Starting full sync (job {job.id})...')
        self.stdout.write(f'  Days: {days}')
        self.stdout.write(f'  Page size: {page_size}')
        self.stdout.write(f'  Max feedbacks per shop: {max_feedbacks_per_shop or "unlimited"}')
        
        try:
            result = sync_service.run_full_sync(job)
            
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Full sync completed: {result["synced"]} synced, '
                        f'{result["updated"]} updated, {len(result["errors"])} errors'
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f'❌ Full sync failed: {", ".join(result["errors"][:5])}'
                    )
                )
        except KeyboardInterrupt:
            job.status = 'paused'
            job.save()
            self.stdout.write(
                self.style.WARNING(f'Sync paused (job {job.id}). Resume with --resume-job-id {job.id}')
            )
        except Exception as e:
            logger.error(f"Error in full sync command: {e}", exc_info=True)
            job.status = 'failed'
            job.completed_at = timezone.now()
            job.save()
            self.stdout.write(
                self.style.ERROR(f'❌ Sync failed: {str(e)}')
            )


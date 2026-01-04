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
        parser.add_argument(
            '--auto-resume-from-db',
            action='store_true',
            help='Tự động tính page/cursor từ database để tiếp tục (không bắt đầu lại từ đầu)'
        )
    
    def handle(self, *args, **options):
        days = options['days']
        page_size = options['page_size']
        max_feedbacks_per_shop = options.get('max_feedbacks_per_shop')
        resume_job_id = options.get('resume_job_id')
        auto_resume_from_db = options.get('auto_resume_from_db', False)
        
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
            
            # Tự động tính page/cursor từ database nếu có flag
            if auto_resume_from_db:
                from cskh.models import Feedback
                from core.system_settings import load_shopee_shops_detail
                import math
                
                shops_detail = load_shopee_shops_detail()
                self.stdout.write('📊 Tính toán page/cursor từ database...')
                
                # Tìm shop có nhiều feedbacks nhất để làm mốc
                max_feedbacks = 0
                shop_with_max = None
                
                for shop_name, shop_info in shops_detail.items():
                    connection_id = shop_info.get("shop_connect")
                    if connection_id:
                        count = Feedback.objects.filter(connection_id=connection_id).count()
                        if count > max_feedbacks:
                            max_feedbacks = count
                            shop_with_max = (shop_name, connection_id)
                
                if shop_with_max and max_feedbacks > 0:
                    shop_name, connection_id = shop_with_max
                    latest_feedback = Feedback.objects.filter(
                        connection_id=connection_id
                    ).order_by('-create_time').first()
                    
                    if latest_feedback:
                        # Tính page từ số feedbacks
                        estimated_page = math.ceil(max_feedbacks / page_size) + 1
                        estimated_cursor = latest_feedback.feedback_id
                        
                        job.current_shop_name = shop_name
                        job.current_connection_id = connection_id
                        job.current_page = estimated_page
                        job.current_cursor = estimated_cursor
                        job.save()
                        
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'✅ Auto-resume từ DB: shop={shop_name}, '
                                f'page={estimated_page}, cursor={estimated_cursor} '
                                f'({max_feedbacks} feedbacks)'
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING('Không tìm thấy feedback trong DB, bắt đầu từ đầu')
                        )
                else:
                    self.stdout.write(
                        self.style.WARNING('Chưa có feedback nào trong DB, bắt đầu từ đầu')
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


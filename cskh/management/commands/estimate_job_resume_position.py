# cskh/management/commands/estimate_job_resume_position.py
"""
Django management command để estimate resume position từ số reviews đã có trong DB.
"""

from django.core.management.base import BaseCommand
from cskh.models import FeedbackSyncJob, Feedback
from core.system_settings import load_shopee_shops_detail
import math


class Command(BaseCommand):
    help = 'Estimate resume position (page/cursor) từ số reviews trong DB'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--job-id',
            type=int,
            required=True,
            help='Job ID cần estimate'
        )
        parser.add_argument(
            '--total-reviews',
            type=int,
            help='Tổng số reviews trong DB (nếu không có, sẽ đếm từ DB)'
        )
        parser.add_argument(
            '--page-size',
            type=int,
            default=50,
            help='Page size (default: 50)'
        )
    
    def handle(self, *args, **options):
        job_id = options['job_id']
        total_reviews = options.get('total_reviews')
        page_size = options.get('page_size', 50)
        
        try:
            job = FeedbackSyncJob.objects.get(id=job_id)
        except FeedbackSyncJob.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Job {job_id} không tồn tại')
            )
            return
        
        self.stdout.write(f'Job {job_id}: {job.sync_type}, status={job.status}')
        self.stdout.write(f'  Current shop: {job.current_shop_name} (index: {job.current_shop_index})')
        self.stdout.write(f'  Connection ID: {job.current_connection_id}')
        self.stdout.write(f'  Page size: {page_size}')
        
        if not job.current_connection_id:
            self.stdout.write(
                self.style.ERROR('Job chưa có current_connection_id')
            )
            return
        
        # Đếm số reviews trong DB cho shop này
        if not total_reviews:
            if job.current_connection_id:
                total_reviews = Feedback.objects.filter(
                    connection_id=job.current_connection_id
                ).count()
                self.stdout.write(f'  Tổng số reviews trong DB (connection_id={job.current_connection_id}): {total_reviews}')
            else:
                # Nếu không có connection_id, đếm tất cả
                total_reviews = Feedback.objects.count()
                self.stdout.write(f'  Tổng số reviews trong DB (tất cả shops): {total_reviews}')
        else:
            self.stdout.write(f'  Tổng số reviews (từ tham số): {total_reviews}')
        
        if total_reviews == 0:
            self.stdout.write(
                self.style.WARNING('Chưa có reviews nào trong DB. Bắt đầu từ page 1, cursor 0')
            )
            return
        
        # Estimate page từ số reviews
        estimated_page = math.ceil(total_reviews / page_size)
        self.stdout.write(f'\n  📊 Estimate:')
        self.stdout.write(f'    Số reviews đã có: {total_reviews}')
        self.stdout.write(f'    Page size: {page_size}')
        self.stdout.write(f'    Page đã xử lý: ~{estimated_page} pages')
        self.stdout.write(f'    Page tiếp theo (để resume): ~{estimated_page + 1}')
        
        # Tìm feedback cuối cùng trong DB
        # Thử tìm theo connection_id trước, nếu không có thì lấy tất cả
        latest_feedback = None
        if job.current_connection_id:
            latest_feedback = Feedback.objects.filter(
                connection_id=job.current_connection_id
            ).order_by('-create_time').first()
        
        if not latest_feedback:
            # Nếu không tìm thấy theo connection_id, lấy feedback cuối cùng của tất cả
            latest_feedback = Feedback.objects.order_by('-create_time').first()
            if latest_feedback:
                self.stdout.write(f'\n  ⚠️  Lưu ý: Không tìm thấy feedback với connection_id={job.current_connection_id}')
                self.stdout.write(f'       Lấy feedback cuối cùng của tất cả shops (connection_id={latest_feedback.connection_id})')
        
        if latest_feedback:
            self.stdout.write(f'\n  📝 Feedback cuối cùng trong DB:')
            self.stdout.write(f'    Feedback ID: {latest_feedback.feedback_id}')
            self.stdout.write(f'    Create time: {latest_feedback.create_time}')
            
            # Cursor là feedback_id của feedback cuối cùng
            # Khi resume, dùng cursor này để fetch page tiếp theo
            estimated_cursor = latest_feedback.feedback_id
            
            self.stdout.write(f'\n  ✅ Recommended resume position:')
            self.stdout.write(f'    Page: {estimated_page + 1}')
            self.stdout.write(f'    Cursor: {estimated_cursor}')
            
            # Hỏi có muốn update không
            self.stdout.write(f'\n  💡 Để update job với giá trị này:')
            self.stdout.write(
                f'    python manage.py update_job_resume_position '
                f'--job-id {job_id} --method manual '
                f'--page {estimated_page + 1} --cursor {estimated_cursor}'
            )
        else:
            self.stdout.write(
                self.style.WARNING('Không tìm thấy feedback cuối cùng trong DB')
            )
        
        # So sánh với giá trị hiện tại
        self.stdout.write(f'\n  🔍 So sánh với giá trị hiện tại:')
        self.stdout.write(f'    Current page: {job.current_page}')
        self.stdout.write(f'    Current cursor: {job.current_cursor}')
        self.stdout.write(f'    Processed feedbacks: {job.processed_feedbacks}')


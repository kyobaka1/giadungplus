# cskh/management/commands/reset_job_shop_index.py
"""
Django management command để reset shop index về 0 để xử lý tất cả shops từ đầu.
"""

from django.core.management.base import BaseCommand
from cskh.models import FeedbackSyncJob


class Command(BaseCommand):
    help = 'Reset shop index về 0 để xử lý tất cả shops từ đầu'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--job-id',
            type=int,
            required=True,
            help='Job ID cần reset'
        )
        parser.add_argument(
            '--keep-page-cursor',
            action='store_true',
            help='Giữ nguyên page/cursor (chỉ reset shop index)'
        )
    
    def handle(self, *args, **options):
        job_id = options['job_id']
        keep_page_cursor = options.get('keep_page_cursor', False)
        
        try:
            job = FeedbackSyncJob.objects.get(id=job_id)
        except FeedbackSyncJob.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Job {job_id} không tồn tại')
            )
            return
        
        self.stdout.write(f'Job {job_id}: {job.sync_type}, status={job.status}')
        self.stdout.write(f'  Current shop: {job.current_shop_name} (index: {job.current_shop_index})')
        self.stdout.write(f'  Current page: {job.current_page}, cursor: {job.current_cursor}')
        
        # Reset shop index về 0
        old_index = job.current_shop_index
        job.current_shop_index = 0
        job.current_shop_name = ''
        job.current_connection_id = None
        
        if not keep_page_cursor:
            # Reset page/cursor về đầu
            job.current_page = 1
            job.current_cursor = None
            self.stdout.write(f'  Reset shop index: {old_index} -> 0')
            self.stdout.write(f'  Reset page/cursor về đầu')
        else:
            self.stdout.write(f'  Reset shop index: {old_index} -> 0 (giữ nguyên page/cursor)')
        
        job.save()
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Đã reset job {job_id}: shop_index=0')
        )
        self.stdout.write(f'\n  💡 Để chạy lại từ đầu tất cả shops:')
        self.stdout.write(f'    python manage.py sync_feedbacks_full --resume-job-id {job_id}')


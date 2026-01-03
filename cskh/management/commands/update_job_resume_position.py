# cskh/management/commands/update_job_resume_position.py
"""
Django management command để update resume position (page/cursor) cho job.
Sử dụng khi job bị dừng đột ngột và chưa kịp lưu page/cursor.
"""

from django.core.management.base import BaseCommand
from cskh.models import FeedbackSyncJob, Feedback
from core.shopee_client import ShopeeClient
from core.system_settings import load_shopee_shops_detail
from datetime import timedelta
from zoneinfo import ZoneInfo
import re


class Command(BaseCommand):
    help = 'Update resume position (page/cursor) cho feedback sync job'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--job-id',
            type=int,
            required=True,
            help='Job ID cần update'
        )
        parser.add_argument(
            '--method',
            type=str,
            choices=['from_feedback_id', 'from_logs', 'manual', 'from_debug_log'],
            default='from_feedback_id',
            help='Method để tìm page/cursor: from_feedback_id, from_logs, manual, from_debug_log'
        )
        parser.add_argument(
            '--page',
            type=int,
            help='Page number (chỉ dùng với method=manual)'
        )
        parser.add_argument(
            '--cursor',
            type=int,
            help='Cursor (comment_id) (chỉ dùng với method=manual)'
        )
        parser.add_argument(
            '--feedback-id',
            type=int,
            help='Feedback ID cuối cùng đã xử lý (dùng với method=from_feedback_id)'
        )
        parser.add_argument(
            '--parse-debug-log',
            type=str,
            help='Parse từ debug log URL (ví dụ: page_number=69&cursor=79118132818)'
        )
    
    def handle(self, *args, **options):
        job_id = options['job_id']
        method = options['method']
        
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
        self.stdout.write(f'  Processed: {job.processed_feedbacks}/{job.total_feedbacks}')
        
        if method == 'manual':
            # Manual set page/cursor
            if not options.get('page') or not options.get('cursor'):
                self.stdout.write(
                    self.style.ERROR('Với method=manual, cần --page và --cursor')
                )
                return
            
            page = options['page']
            cursor = options['cursor']
            
            self.stdout.write(f'  Setting: page={page}, cursor={cursor}')
            job.current_page = page
            job.current_cursor = cursor
            job.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Đã update job {job_id}: page={page}, cursor={cursor}')
            )
        
        elif method == 'from_debug_log':
            # Parse trực tiếp từ debug log URL
            parse_log = options.get('parse_debug_log')
            if not parse_log:
                self.stdout.write(
                    self.style.ERROR('Với method=from_debug_log, cần --parse-debug-log')
                )
                return
            
            # Parse từ URL: page_number=69&cursor=79118132818
            page_match = re.search(r'page_number=(\d+)', parse_log)
            cursor_match = re.search(r'cursor=(\d+)', parse_log)
            
            if not page_match or not cursor_match:
                self.stdout.write(
                    self.style.ERROR('Không parse được page_number và cursor từ log. Format: page_number=69&cursor=79118132818')
                )
                return
            
            page = int(page_match.group(1))
            cursor = int(cursor_match.group(1))
            
            # Nếu log có page_number=69, nghĩa là đang fetch page 69
            # Để resume, tiếp tục từ page 70 với cursor từ page 69
            resume_page = page + 1
            resume_cursor = cursor
            
            self.stdout.write(f'  Parse từ debug log: page={page}, cursor={cursor}')
            self.stdout.write(f'  Resume từ: page={resume_page}, cursor={resume_cursor}')
            
            job.current_page = resume_page
            job.current_cursor = resume_cursor
            job.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Đã update job {job_id}: page={resume_page}, cursor={resume_cursor}')
            )
        
        elif method == 'from_feedback_id':
            # Tìm page/cursor từ feedback_id cuối cùng
            feedback_id = options.get('feedback_id')
            
            if not feedback_id:
                # Tìm feedback_id cuối cùng từ DB (theo shop)
                if not job.current_shop_name or not job.current_connection_id:
                    self.stdout.write(
                        self.style.ERROR('Job chưa có current_shop_name hoặc current_connection_id')
                    )
                    return
                
                # Tìm feedback mới nhất của shop này
                latest_feedback = Feedback.objects.filter(
                    connection_id=job.current_connection_id
                ).order_by('-create_time').first()
                
                if not latest_feedback:
                    self.stdout.write(
                        self.style.ERROR('Không tìm thấy feedback nào của shop này')
                    )
                    return
                
                feedback_id = latest_feedback.feedback_id
                self.stdout.write(f'  Tìm thấy feedback_id cuối cùng: {feedback_id}')
            
            # Tìm page/cursor từ feedback_id này
            page, cursor = self._find_page_cursor_from_feedback_id(
                job, feedback_id
            )
            
            if page and cursor:
                self.stdout.write(f'  Tìm thấy: page={page}, cursor={cursor}')
                job.current_page = page
                job.current_cursor = cursor
                job.save()
                
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Đã update job {job_id}: page={page}, cursor={cursor}')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('Không tìm thấy page/cursor từ feedback_id')
                )
        
        elif method == 'from_logs':
            # Parse từ logs
            page = None
            cursor = None
            
            # Method 1: Parse từ --parse-debug-log (URL string)
            parse_log = options.get('parse_debug_log')
            if parse_log:
                # Parse từ URL: page_number=69&cursor=79118132818
                page_match = re.search(r'page_number=(\d+)', parse_log)
                cursor_match = re.search(r'cursor=(\d+)', parse_log)
                if page_match and cursor_match:
                    page = int(page_match.group(1))
                    cursor = int(cursor_match.group(1))
                    self.stdout.write(f'  Parse từ debug log: page={page}, cursor={cursor}')
                    # Cursor từ page N là để fetch page N+1, nên giữ nguyên
                    # Nhưng nếu muốn resume page N, dùng cursor từ page N-1
                    # Hoặc nếu muốn tiếp tục từ page N+1, giữ nguyên cursor này
            
            # Method 2: Tìm trong job.logs (format: "Page X | Cursor Y")
            if not page or not cursor:
                if job.logs:
                    for log in reversed(job.logs):
                        # Tìm pattern: "Page {number} | Cursor {number}"
                        match = re.search(r'Page\s+(\d+)\s*\|\s*Cursor\s+(\d+)', log)
                        if match:
                            page = int(match.group(1))
                            cursor = int(match.group(2))
                            self.stdout.write(f'  Tìm thấy trong job.logs: "{log}"')
                            break
            
            if not page or not cursor:
                self.stdout.write(
                    self.style.WARNING(
                        'Không tìm thấy Page/Cursor.\n'
                        'Sử dụng: --parse-debug-log "page_number=69&cursor=79118132818"\n'
                        'Hoặc thử method=from_feedback_id'
                    )
                )
                return
            
            # Logic: Nếu đã fetch xong page N với cursor C, thì để resume page N+1 cần:
            # - page = N+1
            # - cursor = C (cursor từ page N)
            # Nhưng từ log, cursor trong URL là cursor để fetch page đó, không phải cursor sau khi fetch
            # Vậy nếu log có page_number=69&cursor=79118132818, nghĩa là đang fetch page 69 với cursor này
            # Để resume, nên dùng page=70 và cursor=79118132818 (giữ nguyên cursor)
            resume_page = page + 1  # Page tiếp theo
            resume_cursor = cursor   # Giữ nguyên cursor để tiếp tục
            
            self.stdout.write(f'  Update để resume: page={resume_page}, cursor={resume_cursor}')
            job.current_page = resume_page
            job.current_cursor = resume_cursor
            job.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Đã update job {job_id}: page={resume_page}, cursor={resume_cursor}')
            )
    
    def _find_page_cursor_from_feedback_id(self, job: FeedbackSyncJob, feedback_id: int):
        """
        Tìm page/cursor từ feedback_id bằng cách crawl lại API.
        """
        if not job.current_connection_id:
            return None, None
        
        try:
            # Tính time range từ job
            tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
            from datetime import datetime
            now_vn = datetime.now(tz_vn)
            time_end = int(now_vn.timestamp())
            time_start = int((now_vn - timedelta(days=job.days)).timestamp())
            
            # Tạo ShopeeClient
            shopee_client = ShopeeClient(shop_key=job.current_connection_id)
            
            # Crawl từ đầu để tìm feedback_id
            cursor = 0
            page = 1
            from_page = 1
            page_size = job.page_size or 50
            
            self.stdout.write(f'  Đang tìm feedback_id {feedback_id}...')
            
            for page_num in range(1, 1000):  # Giới hạn 1000 pages
                response = shopee_client.repo.get_shop_ratings_raw(
                    rating_star="5,4,3,2,1",
                    time_start=time_start,
                    time_end=time_end,
                    page_number=page,
                    page_size=page_size,
                    cursor=cursor,
                    from_page_number=from_page,
                    language="vi"
                )
                
                if response.get("code") != 0:
                    self.stdout.write(
                        self.style.ERROR(f'API error: {response.get("message")}')
                    )
                    return None, None
                
                page_data = response.get("data", {}).get("list", [])
                if not page_data:
                    break
                
                # Kiểm tra xem có feedback_id này không
                for feedback in page_data:
                    comment_id = feedback.get("comment_id")
                    if comment_id == feedback_id:
                        # Tìm thấy! Trả về page tiếp theo (vì đã xử lý xong page này)
                        self.stdout.write(f'  ✅ Tìm thấy ở page {page}, cursor {cursor}')
                        return page + 1, cursor
                
                # Update cursor và page cho lần tiếp theo
                if page_data:
                    cursor = page_data[-1].get("comment_id", cursor)
                page += 1
                from_page = page - 1
                
                # Log progress mỗi 50 pages
                if page_num % 50 == 0:
                    self.stdout.write(f'  Đã kiểm tra {page_num} pages...')
            
            self.stdout.write(
                self.style.WARNING('Không tìm thấy feedback_id trong 1000 pages đầu')
            )
            return None, None
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Lỗi khi tìm page/cursor: {e}')
            )
            return None, None


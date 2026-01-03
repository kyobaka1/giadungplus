# cskh/management/commands/migrate_feedback_reply.py
"""
Django management command để migrate dữ liệu feedback reply từ format JSON/dict sang format đúng.

Vấn đề:
- Trường reply hiện đang lưu toàn bộ JSON object: {'comment': '...', 'is_hidden': False, 'comment_id': 83320290945, 'ctime': 1767084203}
- Cần chuyển thành:
  - reply: chỉ lưu nội dung comment
  - reply_time: lưu giá trị ctime
  - status_reply: True nếu đã có reply, False nếu chưa có

Usage:
    python manage.py migrate_feedback_reply [--dry-run] [--limit N]
"""

import json
import ast
import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from cskh.models import Feedback

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Migrate feedback reply data from JSON/dict format to correct format'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chạy thử không lưu vào database',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Giới hạn số lượng feedbacks để migrate (để test)',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Số lượng feedbacks xử lý mỗi batch (default: 1000)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options.get('limit')
        batch_size = options.get('batch_size', 1000)

        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(self.style.SUCCESS('Bắt đầu migrate feedback reply data'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('⚠️  DRY RUN MODE - Không lưu vào database'))
        
        # Lấy tất cả feedbacks có reply không rỗng
        queryset = Feedback.objects.exclude(
            reply__isnull=True
        ).exclude(
            reply=''
        )
        
        total_count = queryset.count()
        self.stdout.write(f'Tổng số feedbacks cần kiểm tra: {total_count}')
        
        if limit:
            queryset = queryset[:limit]
            self.stdout.write(f'Giới hạn: {limit} feedbacks')
        
        # Thống kê
        stats = {
            'total': 0,
            'migrated': 0,
            'skipped': 0,
            'errors': 0,
            'already_correct': 0,
        }
        
        # Xử lý theo batch
        processed = 0
        batch = []
        
        for feedback in queryset.iterator(chunk_size=batch_size):
            stats['total'] += 1
            processed += 1
            
            try:
                result = self._migrate_feedback_reply(feedback, dry_run)
                
                if result == 'migrated':
                    stats['migrated'] += 1
                    if not dry_run:
                        batch.append(feedback)
                elif result == 'skipped':
                    stats['skipped'] += 1
                elif result == 'already_correct':
                    stats['already_correct'] += 1
                elif result == 'error':
                    stats['errors'] += 1
                
                # Lưu batch khi đủ số lượng
                if len(batch) >= batch_size:
                    if not dry_run:
                        self._save_batch(batch)
                    batch = []
                    self.stdout.write(f'Đã xử lý: {processed}/{total_count if not limit else limit} feedbacks')
                
            except Exception as e:
                stats['errors'] += 1
                logger.error(f'Error processing feedback {feedback.id}: {e}', exc_info=True)
                self.stdout.write(
                    self.style.ERROR(f'❌ Lỗi khi xử lý feedback {feedback.id}: {str(e)}')
                )
        
        # Lưu batch cuối cùng
        if batch and not dry_run:
            self._save_batch(batch)
        
        # In thống kê
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('KẾT QUẢ MIGRATE'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(f'Tổng số feedbacks đã kiểm tra: {stats["total"]}')
        self.stdout.write(self.style.SUCCESS(f'✅ Đã migrate: {stats["migrated"]}'))
        self.stdout.write(self.style.WARNING(f'⏭️  Đã bỏ qua (không phải JSON/dict): {stats["skipped"]}'))
        self.stdout.write(self.style.SUCCESS(f'✓ Đã đúng format: {stats["already_correct"]}'))
        self.stdout.write(self.style.ERROR(f'❌ Lỗi: {stats["errors"]}'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  DRY RUN - Không có thay đổi nào được lưu vào database'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Đã lưu {stats["migrated"]} feedbacks vào database'))

    def _migrate_feedback_reply(self, feedback: Feedback, dry_run: bool) -> str:
        """
        Migrate một feedback reply từ format JSON/dict sang format đúng.
        
        Returns:
            'migrated': Đã migrate thành công
            'skipped': Bỏ qua (không phải JSON/dict format)
            'already_correct': Đã đúng format rồi
            'error': Có lỗi
        """
        reply_value = feedback.reply
        
        if not reply_value:
            return 'skipped'
        
        # Kiểm tra xem reply_value có phải là dict object không (từ JSONField)
        parsed_dict = None
        if isinstance(reply_value, dict):
            parsed_dict = reply_value
        else:
            # Kiểm tra xem có phải là JSON/dict string không
            reply_str = str(reply_value).strip()
            
            # Nếu không bắt đầu bằng { hoặc ', có thể đã đúng format (chỉ là text)
            if not (reply_str.startswith('{') or reply_str.startswith("'") or reply_str.startswith('"')):
                # Kiểm tra xem đã đúng format chưa (reply là text, reply_time đã có)
                if feedback.reply_time and feedback.status_reply:
                    return 'already_correct'
                # Nếu reply là text nhưng chưa có reply_time, có thể cần migrate
                # Nhưng trong trường hợp này, không có thông tin ctime, nên bỏ qua
                return 'skipped'
            
            # Thử parse JSON
            if reply_str.startswith('{'):
                try:
                    parsed_dict = json.loads(reply_str)
                except json.JSONDecodeError:
                    pass
            
            # Nếu không parse được JSON, thử parse dict string (dùng ast.literal_eval)
            if not parsed_dict:
                try:
                    parsed_dict = ast.literal_eval(reply_str)
                except (ValueError, SyntaxError, TypeError):
                    pass
        
        # Nếu vẫn không parse được, bỏ qua
        if not parsed_dict or not isinstance(parsed_dict, dict):
            return 'skipped'
        
        # Extract comment và ctime từ dict
        comment = parsed_dict.get('comment', '')
        ctime = parsed_dict.get('ctime')
        
        # Nếu không có comment, bỏ qua
        if not comment:
            return 'skipped'
        
        # Kiểm tra xem có cần migrate không
        # Nếu reply hiện tại đã là comment và reply_time đã có, có thể đã đúng rồi
        if isinstance(feedback.reply, str) and feedback.reply == comment and feedback.reply_time:
            # Nhưng vẫn cần check status_reply
            if not feedback.status_reply:
                if not dry_run:
                    feedback.status_reply = "replied"
                    # Không save ở đây, để save trong batch
                return 'migrated'
            return 'already_correct'
        
        # Migrate: update reply, reply_time, status_reply
        if not dry_run:
            feedback.reply = comment
            if ctime:
                try:
                    feedback.reply_time = int(ctime)
                except (ValueError, TypeError):
                    feedback.reply_time = None
            else:
                feedback.reply_time = None
            
            # Set status_reply = "replied" nếu có reply
            if comment:
                feedback.status_reply = "replied"
            else:
                feedback.status_reply = None
            # Không save ở đây, để save trong batch
        
        return 'migrated'

    @transaction.atomic
    def _save_batch(self, batch):
        """Lưu một batch feedbacks"""
        Feedback.objects.bulk_update(
            batch,
            ['reply', 'reply_time', 'status_reply'],
            batch_size=500
        )


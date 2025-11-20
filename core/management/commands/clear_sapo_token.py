# core/management/commands/clear_sapo_token.py
"""
Management command để xóa Sapo token trong DB.
Sử dụng khi cần force re-login hoặc clear token cũ không có x-sapo-client.
"""

from django.core.management.base import BaseCommand
from core.models import SapoToken


class Command(BaseCommand):
    help = 'Clear Sapo tokens from database (force re-login on next API call)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--key',
            type=str,
            default='all',
            help='Token key to clear: loginss, tmdt, or all (default: all)',
        )

    def handle(self, *args, **options):
        key = options['key']
        
        if key == 'all':
            count = SapoToken.objects.all().count()
            SapoToken.objects.all().delete()
            self.stdout.write(
                self.style.SUCCESS(f'✓ Cleared {count} Sapo token(s) from database')
            )
            self.stdout.write('Next API call will trigger browser login to get fresh tokens.')
        else:
            try:
                token = SapoToken.objects.get(key=key)
                token.delete()
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Cleared Sapo token: {key}')
                )
                self.stdout.write(f'Next API call will refresh {key} token.')
            except SapoToken.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f'Token "{key}" not found in database')
                )

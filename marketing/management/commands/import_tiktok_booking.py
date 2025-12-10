"""
Management command để import data từ CSV/Excel files.
Usage: python manage.py import_tiktok_booking --path ./data_import --format auto --create-missing --dry-run
"""

import os
import csv
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from datetime import datetime
import pandas as pd
from marketing.models import (
    Brand, Product,
    Creator, CreatorChannel, CreatorContact, CreatorTag, CreatorTagMap,
    Campaign, CampaignProduct, CampaignCreator,
    Booking, BookingDeliverable,
    Video, VideoMetricSnapshot,
    TrackingAsset, TrackingConversion,
    Payment,
)


class Command(BaseCommand):
    help = 'Import data từ CSV/Excel files với idempotent logic'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            type=str,
            required=True,
            help='Đường dẫn tới folder chứa files import',
        )
        parser.add_argument(
            '--format',
            type=str,
            default='auto',
            choices=['auto', 'csv', 'xlsx'],
            help='Format file: auto (detect), csv, xlsx',
        )
        parser.add_argument(
            '--create-missing',
            action='store_true',
            help='Tạo records thiếu khi FK reference không tồn tại',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chạy thử không lưu vào database',
        )

    def handle(self, *args, **options):
        path = Path(options['path'])
        file_format = options['format']
        create_missing = options['create_missing']
        dry_run = options['dry_run']

        if not path.exists():
            self.stdout.write(self.style.ERROR(f'Path không tồn tại: {path}'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('=== DRY RUN MODE - Không lưu vào database ==='))

        summary = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': [],
        }

        # Mapping file names to import functions
        importers = {
            'brands.csv': self.import_brands,
            'products.csv': self.import_products,
            'creators.csv': self.import_creators,
            'creator_channels.csv': self.import_creator_channels,
            'creator_contacts.csv': self.import_creator_contacts,
            'campaigns.csv': self.import_campaigns,
            'campaign_products.csv': self.import_campaign_products,
            'campaign_creators.csv': self.import_campaign_creators,
            'bookings.csv': self.import_bookings,
            'booking_deliverables.csv': self.import_booking_deliverables,
            'videos.csv': self.import_videos,
            'video_snapshots.csv': self.import_video_snapshots,
            'tracking_assets.csv': self.import_tracking_assets,
            'conversions.csv': self.import_conversions,
            'payments.csv': self.import_payments,
        }

        # Also support .xlsx versions
        for csv_name, func in list(importers.items()):
            xlsx_name = csv_name.replace('.csv', '.xlsx')
            importers[xlsx_name] = func

        # Process each file
        for filename, importer_func in importers.items():
            filepath = path / filename
            if not filepath.exists():
                continue

            self.stdout.write(f'\nĐang xử lý: {filename}...')
            try:
                with transaction.atomic():
                    file_summary = importer_func(filepath, create_missing, dry_run)
                    summary['created'] += file_summary['created']
                    summary['updated'] += file_summary['updated']
                    summary['skipped'] += file_summary['skipped']
                    summary['errors'].extend(file_summary['errors'])

                    if dry_run:
                        transaction.set_rollback(True)
                    else:
                        self.stdout.write(self.style.SUCCESS(
                            f'  ✓ Created: {file_summary["created"]}, Updated: {file_summary["updated"]}, Skipped: {file_summary["skipped"]}'
                        ))
            except Exception as e:
                error_msg = f'Lỗi khi xử lý {filename}: {str(e)}'
                self.stdout.write(self.style.ERROR(f'  ✗ {error_msg}'))
                summary['errors'].append(error_msg)
                if not dry_run:
                    transaction.rollback()

        # Print summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write('SUMMARY:')
        self.stdout.write(f'  Created: {summary["created"]}')
        self.stdout.write(f'  Updated: {summary["updated"]}')
        self.stdout.write(f'  Skipped: {summary["skipped"]}')
        if summary['errors']:
            self.stdout.write(self.style.ERROR(f'  Errors: {len(summary["errors"])}'))
            for error in summary['errors']:
                self.stdout.write(self.style.ERROR(f'    - {error}'))
        else:
            self.stdout.write(self.style.SUCCESS('  ✓ Không có lỗi'))

    def read_file(self, filepath):
        """Đọc file CSV hoặc Excel."""
        if filepath.suffix == '.csv':
            return pd.read_csv(filepath, encoding='utf-8-sig')
        elif filepath.suffix in ['.xlsx', '.xls']:
            return pd.read_excel(filepath)
        else:
            raise ValueError(f'Format không hỗ trợ: {filepath.suffix}')

    def parse_date(self, value):
        """Parse date từ string."""
        if pd.isna(value) or value == '':
            return None
        if isinstance(value, datetime):
            return value.date()
        try:
            return pd.to_datetime(value).date()
        except:
            return None

    def parse_datetime(self, value):
        """Parse datetime từ string."""
        if pd.isna(value) or value == '':
            return None
        if isinstance(value, datetime):
            return value
        try:
            return pd.to_datetime(value)
        except:
            return None

    def parse_decimal(self, value):
        """Parse decimal từ string."""
        if pd.isna(value) or value == '':
            return Decimal('0.00')
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return Decimal('0.00')

    def parse_int(self, value, default=0):
        """Parse integer."""
        if pd.isna(value) or value == '':
            return default
        try:
            return int(value)
        except:
            return default

    def get_user(self, username):
        """Lấy user theo username."""
        if pd.isna(username) or username == '':
            return None
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            return None

    # ========================================================================
    # IMPORT FUNCTIONS
    # ========================================================================

    def import_brands(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                code = str(row['code']).strip()
                name = str(row['name']).strip()
                description = str(row.get('description', '')).strip() if not pd.isna(row.get('description')) else ''

                brand, created = Brand.objects.get_or_create(
                    code=code,
                    defaults={'name': name, 'description': description}
                )
                if not created:
                    brand.name = name
                    brand.description = description
                    brand.save()
                    summary['updated'] += 1
                else:
                    summary['created'] += 1
            except Exception as e:
                summary['errors'].append(f'Brand row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary

    def import_products(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                brand_code = str(row['brand_code']).strip()
                try:
                    brand = Brand.objects.get(code=brand_code)
                except Brand.DoesNotExist:
                    if create_missing:
                        brand = Brand.objects.create(
                            code=brand_code,
                            name=f'AUTO-CREATED: {brand_code}',
                            description='AUTO-CREATED BY IMPORT'
                        )
                    else:
                        summary['errors'].append(f'Product row {_}: Brand {brand_code} không tồn tại')
                        summary['skipped'] += 1
                        continue

                code = str(row['code']).strip()
                name = str(row['name']).strip()
                category = str(row.get('category', '')).strip() if not pd.isna(row.get('category')) else None
                sapo_id = self.parse_int(row.get('sapo_id'), None) if not pd.isna(row.get('sapo_id')) else None
                shopee_id = str(row.get('shopee_id', '')).strip() if not pd.isna(row.get('shopee_id')) else None

                product, created = Product.objects.get_or_create(
                    brand=brand,
                    code=code,
                    defaults={
                        'name': name,
                        'category': category,
                        'sapo_product_id': sapo_id,
                        'shopee_id': shopee_id,
                        'is_active': True,
                    }
                )
                if not created:
                    product.name = name
                    product.category = category
                    product.sapo_product_id = sapo_id
                    product.shopee_id = shopee_id
                    product.save()
                    summary['updated'] += 1
                else:
                    summary['created'] += 1
            except Exception as e:
                summary['errors'].append(f'Product row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary

    def import_creators(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                creator_key = str(row.get('creator_key', '')).strip()
                name = str(row['name']).strip()
                
                # Use creator_key if provided, otherwise use name
                lookup_field = 'name'
                lookup_value = name
                if creator_key and creator_key != '':
                    # Try to find by a custom field or use name
                    lookup_value = name  # Fallback to name

                creator, created = Creator.objects.get_or_create(
                    name=name,
                    defaults={
                        'alias': str(row.get('alias', '')).strip() if not pd.isna(row.get('alias')) else None,
                        'gender': str(row.get('gender', '')).strip() if not pd.isna(row.get('gender')) else None,
                        'dob': self.parse_date(row.get('dob')),
                        'location': str(row.get('location', '')).strip() if not pd.isna(row.get('location')) else None,
                        'niche': str(row.get('niche', '')).strip() if not pd.isna(row.get('niche')) else None,
                        'status': str(row.get('status', 'active')).strip(),
                        'priority_score': self.parse_int(row.get('priority_score'), 5),
                        'note_internal': str(row.get('note_internal', '')).strip() if not pd.isna(row.get('note_internal')) else None,
                    }
                )
                if not created:
                    # Update fields
                    if not pd.isna(row.get('alias')):
                        creator.alias = str(row['alias']).strip()
                    if not pd.isna(row.get('status')):
                        creator.status = str(row['status']).strip()
                    if not pd.isna(row.get('priority_score')):
                        creator.priority_score = self.parse_int(row.get('priority_score'), 5)
                    creator.save()
                    summary['updated'] += 1
                else:
                    summary['created'] += 1
            except Exception as e:
                summary['errors'].append(f'Creator row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary

    def import_creator_channels(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                creator_key = str(row['creator_key']).strip()
                # Find creator by name (assuming creator_key matches name or we use name)
                try:
                    creator = Creator.objects.get(name=creator_key)
                except Creator.DoesNotExist:
                    if create_missing:
                        creator = Creator.objects.create(
                            name=creator_key,
                            note_internal='AUTO-CREATED BY IMPORT'
                        )
                    else:
                        summary['errors'].append(f'CreatorChannel row {_}: Creator {creator_key} không tồn tại')
                        summary['skipped'] += 1
                        continue

                platform = str(row['platform']).strip()
                handle = str(row['handle']).strip()

                channel, created = CreatorChannel.objects.get_or_create(
                    creator=creator,
                    platform=platform,
                    handle=handle,
                    defaults={
                        'profile_url': str(row.get('profile_url', '')).strip() if not pd.isna(row.get('profile_url')) else None,
                        'external_id': str(row.get('external_id', '')).strip() if not pd.isna(row.get('external_id')) else None,
                        'follower_count': self.parse_int(row.get('follower_count'), 0),
                        'avg_view_10': self.parse_int(row.get('avg_view_10'), 0),
                        'avg_engagement_rate': self.parse_decimal(row.get('avg_engagement_rate')),
                    }
                )
                if not created:
                    channel.follower_count = self.parse_int(row.get('follower_count'), 0)
                    channel.avg_view_10 = self.parse_int(row.get('avg_view_10'), 0)
                    channel.avg_engagement_rate = self.parse_decimal(row.get('avg_engagement_rate'))
                    channel.save()
                    summary['updated'] += 1
                else:
                    summary['created'] += 1
            except Exception as e:
                summary['errors'].append(f'CreatorChannel row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary

    def import_creator_contacts(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                creator_key = str(row['creator_key']).strip()
                try:
                    creator = Creator.objects.get(name=creator_key)
                except Creator.DoesNotExist:
                    if create_missing:
                        creator = Creator.objects.create(name=creator_key, note_internal='AUTO-CREATED BY IMPORT')
                    else:
                        summary['skipped'] += 1
                        continue

                contact_type = str(row.get('contact_type', 'owner')).strip()
                name = str(row['name']).strip()

                # Use composite key: creator + contact_type + name
                contact, created = CreatorContact.objects.get_or_create(
                    creator=creator,
                    contact_type=contact_type,
                    name=name,
                    defaults={
                        'phone': str(row.get('phone', '')).strip() if not pd.isna(row.get('phone')) else None,
                        'zalo': str(row.get('zalo', '')).strip() if not pd.isna(row.get('zalo')) else None,
                        'email': str(row.get('email', '')).strip() if not pd.isna(row.get('email')) else None,
                        'wechat': str(row.get('wechat', '')).strip() if not pd.isna(row.get('wechat')) else None,
                        'is_primary': bool(row.get('is_primary', False)) if not pd.isna(row.get('is_primary')) else False,
                        'note': str(row.get('note', '')).strip() if not pd.isna(row.get('note')) else None,
                    }
                )
                if created:
                    summary['created'] += 1
                else:
                    summary['updated'] += 1
            except Exception as e:
                summary['errors'].append(f'CreatorContact row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary

    def import_campaigns(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                code = str(row['code']).strip()
                brand_code = str(row['brand_code']).strip()
                try:
                    brand = Brand.objects.get(code=brand_code)
                except Brand.DoesNotExist:
                    if create_missing:
                        brand = Brand.objects.create(code=brand_code, name=f'AUTO-CREATED: {brand_code}')
                    else:
                        summary['skipped'] += 1
                        continue

                owner_username = str(row.get('owner_username', '')).strip() if not pd.isna(row.get('owner_username')) else None
                owner = self.get_user(owner_username) if owner_username else None

                campaign, created = Campaign.objects.get_or_create(
                    code=code,
                    defaults={
                        'name': str(row['name']).strip(),
                        'brand': brand,
                        'channel': str(row.get('channel', 'tiktok')).strip(),
                        'objective': str(row.get('objective', 'sale')).strip(),
                        'description': str(row.get('description', '')).strip() if not pd.isna(row.get('description')) else None,
                        'start_date': self.parse_date(row.get('start_date')),
                        'end_date': self.parse_date(row.get('end_date')),
                        'budget_planned': self.parse_decimal(row.get('budget_planned')),
                        'kpi_view': self.parse_int(row.get('kpi_view'), 0),
                        'kpi_order': self.parse_int(row.get('kpi_order'), 0),
                        'kpi_revenue': self.parse_decimal(row.get('kpi_revenue')),
                        'status': str(row.get('status', 'draft')).strip(),
                        'owner': owner,
                    }
                )
                if created:
                    summary['created'] += 1
                else:
                    summary['updated'] += 1
            except Exception as e:
                summary['errors'].append(f'Campaign row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary

    def import_campaign_products(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                campaign_code = str(row['campaign_code']).strip()
                product_code = str(row['product_code']).strip()
                brand_code = str(row['brand_code']).strip()

                try:
                    campaign = Campaign.objects.get(code=campaign_code)
                    product = Product.objects.get(brand__code=brand_code, code=product_code)
                except (Campaign.DoesNotExist, Product.DoesNotExist) as e:
                    summary['skipped'] += 1
                    continue

                cp, created = CampaignProduct.objects.get_or_create(
                    campaign=campaign,
                    product=product,
                    defaults={
                        'priority': self.parse_int(row.get('priority'), 1),
                        'note': str(row.get('note', '')).strip() if not pd.isna(row.get('note')) else None,
                    }
                )
                if created:
                    summary['created'] += 1
                else:
                    summary['updated'] += 1
            except Exception as e:
                summary['errors'].append(f'CampaignProduct row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary

    def import_campaign_creators(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                campaign_code = str(row['campaign_code']).strip()
                creator_key = str(row['creator_key']).strip()

                try:
                    campaign = Campaign.objects.get(code=campaign_code)
                    creator = Creator.objects.get(name=creator_key)
                except (Campaign.DoesNotExist, Creator.DoesNotExist) as e:
                    summary['skipped'] += 1
                    continue

                cc, created = CampaignCreator.objects.get_or_create(
                    campaign=campaign,
                    creator=creator,
                    defaults={
                        'role': str(row.get('role', 'main')).strip(),
                        'note': str(row.get('note', '')).strip() if not pd.isna(row.get('note')) else None,
                    }
                )
                if created:
                    summary['created'] += 1
                else:
                    summary['updated'] += 1
            except Exception as e:
                summary['errors'].append(f'CampaignCreator row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary

    def import_bookings(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                code = str(row['code']).strip()
                campaign_code = str(row['campaign_code']).strip()
                creator_key = str(row['creator_key']).strip()
                brand_code = str(row['brand_code']).strip()

                try:
                    campaign = Campaign.objects.get(code=campaign_code)
                    creator = Creator.objects.get(name=creator_key)
                    brand = Brand.objects.get(code=brand_code)
                except (Campaign.DoesNotExist, Creator.DoesNotExist, Brand.DoesNotExist) as e:
                    summary['skipped'] += 1
                    continue

                # Get channel if provided
                channel = None
                if not pd.isna(row.get('platform')) and not pd.isna(row.get('handle')):
                    platform = str(row['platform']).strip()
                    handle = str(row['handle']).strip()
                    try:
                        channel = CreatorChannel.objects.get(creator=creator, platform=platform, handle=handle)
                    except CreatorChannel.DoesNotExist:
                        pass

                # Get product if provided
                product = None
                if not pd.isna(row.get('product_code')):
                    product_code = str(row['product_code']).strip()
                    try:
                        product = Product.objects.get(brand=brand, code=product_code)
                    except Product.DoesNotExist:
                        pass

                booking, created = Booking.objects.get_or_create(
                    code=code,
                    defaults={
                        'campaign': campaign,
                        'creator': creator,
                        'channel': channel,
                        'brand': brand,
                        'product_focus': product,
                        'booking_type': str(row.get('booking_type', 'video_only')).strip(),
                        'brief_summary': str(row.get('brief_summary', '')).strip() if not pd.isna(row.get('brief_summary')) else None,
                        'start_date': self.parse_date(row.get('start_date')),
                        'end_date': self.parse_date(row.get('end_date')),
                        'total_fee_agreed': self.parse_decimal(row.get('total_fee_agreed')),
                        'currency': str(row.get('currency', 'VND')).strip(),
                        'deliverables_count_planned': self.parse_int(row.get('deliverables_count_planned'), 0),
                        'status': str(row.get('status', 'negotiating')).strip(),
                        'internal_note': str(row.get('internal_note', '')).strip() if not pd.isna(row.get('internal_note')) else None,
                    }
                )
                if created:
                    summary['created'] += 1
                else:
                    summary['updated'] += 1
            except Exception as e:
                summary['errors'].append(f'Booking row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary

    def import_booking_deliverables(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                booking_code = str(row['booking_code']).strip()
                try:
                    booking = Booking.objects.get(code=booking_code)
                except Booking.DoesNotExist:
                    summary['skipped'] += 1
                    continue

                deliverable_type = str(row['deliverable_type']).strip()
                title = str(row['title']).strip()
                deadline_post = self.parse_datetime(row.get('deadline_post'))

                # Use composite key: booking + type + title + deadline
                deliverable, created = BookingDeliverable.objects.get_or_create(
                    booking=booking,
                    deliverable_type=deliverable_type,
                    title=title,
                    defaults={
                        'script_link': str(row.get('script_link', '')).strip() if not pd.isna(row.get('script_link')) else None,
                        'requirements': str(row.get('requirements', '')).strip() if not pd.isna(row.get('requirements')) else None,
                        'deadline_shoot': self.parse_datetime(row.get('deadline_shoot')),
                        'deadline_post': deadline_post,
                        'quantity': self.parse_int(row.get('quantity'), 1),
                        'fee': self.parse_decimal(row.get('fee')) if not pd.isna(row.get('fee')) else None,
                        'status': str(row.get('status', 'planned')).strip(),
                    }
                )
                if created:
                    summary['created'] += 1
                else:
                    summary['updated'] += 1
            except Exception as e:
                summary['errors'].append(f'BookingDeliverable row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary

    def import_videos(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                booking_code = str(row.get('booking_code', '')).strip() if not pd.isna(row.get('booking_code')) else None
                booking = None
                if booking_code:
                    try:
                        booking = Booking.objects.get(code=booking_code)
                    except Booking.DoesNotExist:
                        pass

                campaign_code = str(row.get('campaign_code', '')).strip() if not pd.isna(row.get('campaign_code')) else None
                if not campaign_code and booking:
                    campaign_code = booking.campaign.code
                if not campaign_code:
                    summary['skipped'] += 1
                    continue

                try:
                    campaign = Campaign.objects.get(code=campaign_code)
                except Campaign.DoesNotExist:
                    summary['skipped'] += 1
                    continue

                creator_key = str(row.get('creator_key', '')).strip() if not pd.isna(row.get('creator_key')) else None
                if not creator_key and booking:
                    creator_key = booking.creator.name
                if not creator_key:
                    summary['skipped'] += 1
                    continue

                try:
                    creator = Creator.objects.get(name=creator_key)
                except Creator.DoesNotExist:
                    summary['skipped'] += 1
                    continue

                channel = str(row.get('channel', 'tiktok')).strip()
                platform_video_id = str(row.get('platform_video_id', '')).strip() if not pd.isna(row.get('platform_video_id')) else None

                # Use unique key: channel + platform_video_id, or url
                if platform_video_id:
                    video, created = Video.objects.get_or_create(
                        channel=channel,
                        platform_video_id=platform_video_id,
                        defaults={
                            'booking': booking,
                            'campaign': campaign,
                            'creator': creator,
                            'url': str(row.get('url', '')).strip() if not pd.isna(row.get('url')) else None,
                            'title': str(row.get('title', '')).strip() if not pd.isna(row.get('title')) else None,
                            'post_date': self.parse_datetime(row.get('post_date')),
                            'thumbnail_url': str(row.get('thumbnail_url', '')).strip() if not pd.isna(row.get('thumbnail_url')) else None,
                            'status': str(row.get('status', 'posted')).strip(),
                        }
                    )
                else:
                    url = str(row.get('url', '')).strip()
                    if not url:
                        summary['skipped'] += 1
                        continue
                    video, created = Video.objects.get_or_create(
                        channel=channel,
                        url=url,
                        defaults={
                            'booking': booking,
                            'campaign': campaign,
                            'creator': creator,
                            'platform_video_id': platform_video_id,
                            'title': str(row.get('title', '')).strip() if not pd.isna(row.get('title')) else None,
                            'post_date': self.parse_datetime(row.get('post_date')),
                            'thumbnail_url': str(row.get('thumbnail_url', '')).strip() if not pd.isna(row.get('thumbnail_url')) else None,
                            'status': str(row.get('status', 'posted')).strip(),
                        }
                    )

                if created:
                    summary['created'] += 1
                else:
                    summary['updated'] += 1
            except Exception as e:
                summary['errors'].append(f'Video row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary

    def import_video_snapshots(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                channel = str(row['channel']).strip()
                platform_video_id = str(row['platform_video_id']).strip()

                try:
                    video = Video.objects.get(channel=channel, platform_video_id=platform_video_id)
                except Video.DoesNotExist:
                    summary['skipped'] += 1
                    continue

                snapshot_time = self.parse_datetime(row.get('snapshot_time'))
                if not snapshot_time:
                    snapshot_time = timezone.now()

                snapshot, created = VideoMetricSnapshot.objects.get_or_create(
                    video=video,
                    snapshot_time=snapshot_time,
                    defaults={
                        'view_count': self.parse_int(row.get('view_count'), 0),
                        'like_count': self.parse_int(row.get('like_count'), 0),
                        'comment_count': self.parse_int(row.get('comment_count'), 0),
                        'share_count': self.parse_int(row.get('share_count'), 0),
                        'save_count': self.parse_int(row.get('save_count'), 0),
                        'engagement_rate': self.parse_decimal(row.get('engagement_rate')) if not pd.isna(row.get('engagement_rate')) else None,
                    }
                )
                if created:
                    summary['created'] += 1
                else:
                    summary['updated'] += 1
            except Exception as e:
                summary['errors'].append(f'VideoSnapshot row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary

    def import_tracking_assets(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                campaign_code = str(row['campaign_code']).strip()
                try:
                    campaign = Campaign.objects.get(code=campaign_code)
                except Campaign.DoesNotExist:
                    summary['skipped'] += 1
                    continue

                booking_code = str(row.get('booking_code', '')).strip() if not pd.isna(row.get('booking_code')) else None
                booking = None
                if booking_code:
                    try:
                        booking = Booking.objects.get(code=booking_code)
                    except Booking.DoesNotExist:
                        pass

                creator_key = str(row.get('creator_key', '')).strip() if not pd.isna(row.get('creator_key')) else None
                creator = None
                if creator_key:
                    try:
                        creator = Creator.objects.get(name=creator_key)
                    except Creator.DoesNotExist:
                        pass

                platform = str(row['platform']).strip()
                code_type = str(row['code_type']).strip()
                code_value = str(row['code_value']).strip()

                asset, created = TrackingAsset.objects.get_or_create(
                    platform=platform,
                    code_type=code_type,
                    code_value=code_value,
                    defaults={
                        'campaign': campaign,
                        'booking': booking,
                        'creator': creator,
                        'target_url': str(row.get('target_url', '')).strip() if not pd.isna(row.get('target_url')) else None,
                        'note': str(row.get('note', '')).strip() if not pd.isna(row.get('note')) else None,
                        'is_active': bool(row.get('is_active', True)) if not pd.isna(row.get('is_active')) else True,
                    }
                )
                if created:
                    summary['created'] += 1
                else:
                    summary['updated'] += 1
            except Exception as e:
                summary['errors'].append(f'TrackingAsset row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary

    def import_conversions(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                platform = str(row['platform']).strip()
                code_type = str(row['code_type']).strip()
                code_value = str(row['code_value']).strip()

                try:
                    tracking_asset = TrackingAsset.objects.get(
                        platform=platform,
                        code_type=code_type,
                        code_value=code_value
                    )
                except TrackingAsset.DoesNotExist:
                    summary['skipped'] += 1
                    continue

                order_code = str(row['order_code']).strip()

                product = None
                if not pd.isna(row.get('product_code')) and not pd.isna(row.get('brand_code')):
                    brand_code = str(row['brand_code']).strip()
                    product_code = str(row['product_code']).strip()
                    try:
                        product = Product.objects.get(brand__code=brand_code, code=product_code)
                    except Product.DoesNotExist:
                        pass

                conversion, created = TrackingConversion.objects.get_or_create(
                    tracking_asset=tracking_asset,
                    order_code=order_code,
                    defaults={
                        'order_id_external': str(row.get('order_id_external', '')).strip() if not pd.isna(row.get('order_id_external')) else None,
                        'order_date': self.parse_datetime(row.get('order_date')) or timezone.now(),
                        'revenue': self.parse_decimal(row.get('revenue')),
                        'currency': str(row.get('currency', 'VND')).strip(),
                        'source_platform': str(row.get('source_platform', '')).strip() if not pd.isna(row.get('source_platform')) else None,
                        'product': product,
                        'quantity': self.parse_int(row.get('quantity'), None) if not pd.isna(row.get('quantity')) else None,
                    }
                )
                if created:
                    summary['created'] += 1
                else:
                    summary['updated'] += 1
            except Exception as e:
                summary['errors'].append(f'Conversion row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary

    def import_payments(self, filepath, create_missing, dry_run):
        df = self.read_file(filepath)
        summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

        for _, row in df.iterrows():
            try:
                booking_code = str(row['booking_code']).strip()
                try:
                    booking = Booking.objects.get(code=booking_code)
                except Booking.DoesNotExist:
                    summary['skipped'] += 1
                    continue

                creator_key = str(row.get('creator_key', '')).strip() if not pd.isna(row.get('creator_key')) else None
                if not creator_key:
                    creator_key = booking.creator.name
                try:
                    creator = Creator.objects.get(name=creator_key)
                except Creator.DoesNotExist:
                    summary['skipped'] += 1
                    continue

                campaign_code = str(row.get('campaign_code', '')).strip() if not pd.isna(row.get('campaign_code')) else None
                if not campaign_code:
                    campaign_code = booking.campaign.code
                try:
                    campaign = Campaign.objects.get(code=campaign_code)
                except Campaign.DoesNotExist:
                    summary['skipped'] += 1
                    continue

                payment_date = self.parse_date(row.get('payment_date'))
                amount = self.parse_decimal(row.get('amount'))
                status = str(row.get('status', 'planned')).strip()

                # Use composite key: booking + payment_date + amount + status (or payment_ref if provided)
                payment_ref = str(row.get('payment_ref', '')).strip() if not pd.isna(row.get('payment_ref')) else None
                
                if payment_ref:
                    payment, created = Payment.objects.get_or_create(
                        booking=booking,
                        invoice_number=payment_ref,
                        defaults={
                            'creator': creator,
                            'campaign': campaign,
                            'amount': amount,
                            'currency': str(row.get('currency', 'VND')).strip(),
                            'exchange_rate': self.parse_decimal(row.get('exchange_rate')) if not pd.isna(row.get('exchange_rate')) else None,
                            'amount_vnd': self.parse_decimal(row.get('amount_vnd')) if not pd.isna(row.get('amount_vnd')) else None,
                            'payment_date': payment_date,
                            'payment_method': str(row.get('payment_method', 'bank_transfer')).strip(),
                            'status': status,
                            'invoice_number': str(row.get('invoice_number', '')).strip() if not pd.isna(row.get('invoice_number')) else None,
                            'note': str(row.get('note', '')).strip() if not pd.isna(row.get('note')) else None,
                            'created_by': self.get_user(str(row.get('created_by_username', '')).strip()) if not pd.isna(row.get('created_by_username')) else None,
                        }
                    )
                else:
                    # Fallback to composite key
                    payment, created = Payment.objects.get_or_create(
                        booking=booking,
                        payment_date=payment_date,
                        amount=amount,
                        status=status,
                        defaults={
                            'creator': creator,
                            'campaign': campaign,
                            'currency': str(row.get('currency', 'VND')).strip(),
                            'exchange_rate': self.parse_decimal(row.get('exchange_rate')) if not pd.isna(row.get('exchange_rate')) else None,
                            'amount_vnd': self.parse_decimal(row.get('amount_vnd')) if not pd.isna(row.get('amount_vnd')) else None,
                            'payment_method': str(row.get('payment_method', 'bank_transfer')).strip(),
                            'invoice_number': str(row.get('invoice_number', '')).strip() if not pd.isna(row.get('invoice_number')) else None,
                            'note': str(row.get('note', '')).strip() if not pd.isna(row.get('note')) else None,
                            'created_by': self.get_user(str(row.get('created_by_username', '')).strip()) if not pd.isna(row.get('created_by_username')) else None,
                        }
                    )

                if created:
                    summary['created'] += 1
                else:
                    summary['updated'] += 1
            except Exception as e:
                summary['errors'].append(f'Payment row {_}: {str(e)}')
                summary['skipped'] += 1

        return summary


"""
Tests cho TikTok Booking Center import system.
"""

import os
import tempfile
import shutil
from pathlib import Path
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta
from marketing.models import (
    Brand, Product,
    Creator, CreatorChannel, CreatorContact,
    Campaign, CampaignProduct, CampaignCreator,
    Booking, BookingDeliverable,
    Video, VideoMetricSnapshot,
    Payment,
)


class ImportIdempotencyTest(TestCase):
    """
    Test import idempotency: chạy import 2 lần không tạo duplicate rows.
    """

    def setUp(self):
        """Tạo temp folder và sample CSV files."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Tạo admin user
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='admin',
            is_staff=True,
            is_superuser=True
        )

        # Tạo sample CSV files
        self.create_sample_files()

    def tearDown(self):
        """Xóa temp folder."""
        shutil.rmtree(self.temp_dir)

    def create_sample_files(self):
        """Tạo sample CSV files."""
        # brands.csv
        with open(self.temp_path / 'brands.csv', 'w', encoding='utf-8-sig') as f:
            f.write('code,name,description\n')
            f.write('BRAND1,Thương hiệu A,Mô tả A\n')

        # products.csv
        with open(self.temp_path / 'products.csv', 'w', encoding='utf-8-sig') as f:
            f.write('brand_code,code,name,category,sapo_id,shopee_id\n')
            f.write('BRAND1,P001,Sản phẩm 1,Danh mục,1001,SP001\n')

        # creators.csv
        with open(self.temp_path / 'creators.csv', 'w', encoding='utf-8-sig') as f:
            f.write('creator_key,name,alias,gender,dob,location,niche,status,priority_score,note_internal\n')
            f.write('creator_a,Nguyễn Văn A,alias_a,male,1995-05-15,Hà Nội,beauty,active,9,Ghi chú\n')

        # creator_channels.csv
        with open(self.temp_path / 'creator_channels.csv', 'w', encoding='utf-8-sig') as f:
            f.write('creator_key,platform,handle,profile_url,external_id,follower_count,avg_view_10,avg_engagement_rate\n')
            f.write('creator_a,tiktok,handle_a,https://tiktok.com/@a,tiktok_123,500000,50000,5.50\n')

        # campaigns.csv
        with open(self.temp_path / 'campaigns.csv', 'w', encoding='utf-8-sig') as f:
            f.write('code,name,brand_code,channel,objective,description,start_date,end_date,budget_planned,kpi_view,kpi_order,kpi_revenue,status,owner_username\n')
            f.write('CAMP001,Campaign 1,BRAND1,tiktok,sale,Mô tả,2024-01-01,2024-03-31,50000000,1000000,500,200000000,running,admin\n')

        # bookings.csv
        with open(self.temp_path / 'bookings.csv', 'w', encoding='utf-8-sig') as f:
            f.write('code,campaign_code,brand_code,creator_key,platform,handle,product_code,booking_type,brief_summary,start_date,end_date,total_fee_agreed,currency,deliverables_count_planned,status,internal_note\n')
            f.write('BOOK001,CAMP001,BRAND1,creator_a,tiktok,handle_a,P001,combo,Tóm tắt,2024-01-15,2024-02-15,15000000,VND,3,in_progress,Ghi chú\n')

    def test_brands_idempotency(self):
        """Test import brands 2 lần không tạo duplicate."""
        # Import lần 1
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=True)
        count1 = Brand.objects.filter(code='BRAND1').count()
        self.assertEqual(count1, 1)

        # Import lần 2
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=True)
        count2 = Brand.objects.filter(code='BRAND1').count()
        self.assertEqual(count2, 1, "Không được tạo duplicate brand")

    def test_products_idempotency(self):
        """Test import products 2 lần không tạo duplicate."""
        # Import lần 1
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=True)
        count1 = Product.objects.filter(brand__code='BRAND1', code='P001').count()
        self.assertEqual(count1, 1)

        # Import lần 2
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=True)
        count2 = Product.objects.filter(brand__code='BRAND1', code='P001').count()
        self.assertEqual(count2, 1, "Không được tạo duplicate product")

    def test_creators_idempotency(self):
        """Test import creators 2 lần không tạo duplicate."""
        # Import lần 1
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=True)
        count1 = Creator.objects.filter(name='Nguyễn Văn A').count()
        self.assertEqual(count1, 1)

        # Import lần 2
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=True)
        count2 = Creator.objects.filter(name='Nguyễn Văn A').count()
        self.assertEqual(count2, 1, "Không được tạo duplicate creator")

    def test_campaigns_idempotency(self):
        """Test import campaigns 2 lần không tạo duplicate."""
        # Import lần 1
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=True)
        count1 = Campaign.objects.filter(code='CAMP001').count()
        self.assertEqual(count1, 1)

        # Import lần 2
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=True)
        count2 = Campaign.objects.filter(code='CAMP001').count()
        self.assertEqual(count2, 1, "Không được tạo duplicate campaign")

    def test_bookings_idempotency(self):
        """Test import bookings 2 lần không tạo duplicate."""
        # Import lần 1
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=True)
        count1 = Booking.objects.filter(code='BOOK001').count()
        self.assertEqual(count1, 1)

        # Import lần 2
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=True)
        count2 = Booking.objects.filter(code='BOOK001').count()
        self.assertEqual(count2, 1, "Không được tạo duplicate booking")


class FKMappingTest(TestCase):
    """
    Test FK mapping sử dụng creator_key và campaign_code.
    """

    def setUp(self):
        """Tạo temp folder và sample CSV files."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Tạo admin user
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='admin',
            is_staff=True,
            is_superuser=True
        )

    def tearDown(self):
        """Xóa temp folder."""
        shutil.rmtree(self.temp_dir)

    def test_creator_key_mapping(self):
        """Test mapping creator_key trong creator_channels."""
        # Tạo brand và creator trước
        brand = Brand.objects.create(code='BRAND1', name='Brand 1')
        creator = Creator.objects.create(name='Nguyễn Văn A', status='active')

        # Tạo CSV với creator_key
        with open(self.temp_path / 'creator_channels.csv', 'w', encoding='utf-8-sig') as f:
            f.write('creator_key,platform,handle,profile_url,external_id,follower_count,avg_view_10,avg_engagement_rate\n')
            f.write('Nguyễn Văn A,tiktok,handle_a,https://tiktok.com/@a,tiktok_123,500000,50000,5.50\n')

        # Import
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=False)

        # Verify
        channel = CreatorChannel.objects.get(creator=creator, platform='tiktok', handle='handle_a')
        self.assertIsNotNone(channel)
        self.assertEqual(channel.creator, creator)

    def test_campaign_code_mapping(self):
        """Test mapping campaign_code trong campaign_products."""
        # Tạo brand, product, campaign trước
        brand = Brand.objects.create(code='BRAND1', name='Brand 1')
        product = Product.objects.create(brand=brand, code='P001', name='Product 1')
        campaign = Campaign.objects.create(
            code='CAMP001',
            name='Campaign 1',
            brand=brand,
            channel='tiktok',
            objective='sale',
            status='running'
        )

        # Tạo CSV với campaign_code
        with open(self.temp_path / 'campaign_products.csv', 'w', encoding='utf-8-sig') as f:
            f.write('campaign_code,brand_code,product_code,priority,note\n')
            f.write('CAMP001,BRAND1,P001,1,Ghi chú\n')

        # Import
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=False)

        # Verify
        cp = CampaignProduct.objects.get(campaign=campaign, product=product)
        self.assertIsNotNone(cp)
        self.assertEqual(cp.campaign, campaign)
        self.assertEqual(cp.product, product)

    def test_create_missing_option(self):
        """Test --create-missing tạo records thiếu."""
        # Tạo CSV với brand_code không tồn tại
        with open(self.temp_path / 'products.csv', 'w', encoding='utf-8-sig') as f:
            f.write('brand_code,code,name,category,sapo_id,shopee_id\n')
            f.write('BRAND_NEW,P001,Product 1,Category,1001,SP001\n')

        # Import với --create-missing
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=True)

        # Verify brand được tạo tự động
        brand = Brand.objects.get(code='BRAND_NEW')
        self.assertIsNotNone(brand)
        self.assertIn('AUTO-CREATED', brand.name)

        # Verify product được tạo
        product = Product.objects.get(brand=brand, code='P001')
        self.assertIsNotNone(product)


class DryRunTest(TestCase):
    """
    Test --dry-run không persist data.
    """

    def setUp(self):
        """Tạo temp folder và sample CSV files."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Tạo admin user
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='admin',
            is_staff=True,
            is_superuser=True
        )

        # Tạo sample CSV
        with open(self.temp_path / 'brands.csv', 'w', encoding='utf-8-sig') as f:
            f.write('code,name,description\n')
            f.write('BRAND1,Thương hiệu A,Mô tả A\n')

    def tearDown(self):
        """Xóa temp folder."""
        shutil.rmtree(self.temp_dir)

    def test_dry_run_no_persist(self):
        """Test --dry-run không lưu vào database."""
        # Verify không có brand trước
        count_before = Brand.objects.count()
        self.assertEqual(count_before, 0)

        # Import với --dry-run
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=True, dry_run=True)

        # Verify vẫn không có brand sau
        count_after = Brand.objects.count()
        self.assertEqual(count_after, 0, "Dry-run không được persist data")

    def test_dry_run_vs_normal(self):
        """Test so sánh dry-run và normal import."""
        # Dry-run
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=True, dry_run=True)
        count_dry = Brand.objects.count()
        self.assertEqual(count_dry, 0)

        # Normal import
        call_command('import_tiktok_booking', path=str(self.temp_path), format='csv', create_missing=True, dry_run=False)
        count_normal = Brand.objects.count()
        self.assertEqual(count_normal, 1, "Normal import phải persist data")


class ModelRelationshipsTest(TestCase):
    """
    Test relationships giữa các models.
    """

    def setUp(self):
        """Tạo sample data."""
        self.brand = Brand.objects.create(code='BRAND1', name='Brand 1')
        self.product = Product.objects.create(brand=self.brand, code='P001', name='Product 1')
        self.creator = Creator.objects.create(name='Creator 1', status='active')
        self.channel = CreatorChannel.objects.create(
            creator=self.creator,
            platform='tiktok',
            handle='handle1',
            follower_count=100000
        )
        self.campaign = Campaign.objects.create(
            code='CAMP001',
            name='Campaign 1',
            brand=self.brand,
            channel='tiktok',
            objective='sale',
            status='running'
        )
        self.booking = Booking.objects.create(
            code='BOOK001',
            campaign=self.campaign,
            creator=self.creator,
            channel=self.channel,
            brand=self.brand,
            product_focus=self.product,
            booking_type='video_only',
            total_fee_agreed=Decimal('10000000'),
            currency='VND',
            status='confirmed'
        )

    def test_campaign_products_relationship(self):
        """Test relationship Campaign -> Products."""
        cp = CampaignProduct.objects.create(
            campaign=self.campaign,
            product=self.product,
            priority=1
        )
        self.assertEqual(cp.campaign, self.campaign)
        self.assertEqual(cp.product, self.product)
        self.assertIn(cp, self.campaign.campaign_products.all())

    def test_booking_deliverables_relationship(self):
        """Test relationship Booking -> Deliverables."""
        deliverable = BookingDeliverable.objects.create(
            booking=self.booking,
            deliverable_type='video_feed',
            title='Video 1',
            status='planned'
        )
        self.assertEqual(deliverable.booking, self.booking)
        self.assertIn(deliverable, self.booking.deliverables.all())

    def test_video_snapshots_relationship(self):
        """Test relationship Video -> Snapshots."""
        video = Video.objects.create(
            booking=self.booking,
            campaign=self.campaign,
            creator=self.creator,
            channel='tiktok',
            platform_video_id='video_001',
            status='posted'
        )
        snapshot = VideoMetricSnapshot.objects.create(
            video=video,
            snapshot_time=timezone.now(),
            view_count=10000,
            like_count=1000
        )
        self.assertEqual(snapshot.video, video)
        self.assertIn(snapshot, video.snapshots.all())

    def test_payment_relationships(self):
        """Test relationship Payment -> Booking, Creator, Campaign."""
        payment = Payment.objects.create(
            booking=self.booking,
            creator=self.creator,
            campaign=self.campaign,
            amount=Decimal('5000000'),
            currency='VND',
            status='paid'
        )
        self.assertEqual(payment.booking, self.booking)
        self.assertEqual(payment.creator, self.creator)
        self.assertEqual(payment.campaign, self.campaign)
        self.assertIn(payment, self.booking.payments.all())
        self.assertIn(payment, self.creator.payments.all())
        self.assertIn(payment, self.campaign.payments.all())

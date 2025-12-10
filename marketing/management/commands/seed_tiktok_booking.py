"""
Management command để tạo sample data cho TikTok Booking Center.
Usage: python manage.py seed_tiktok_booking
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta
from marketing.models import (
    Brand, Product,
    Creator, CreatorChannel, CreatorContact, CreatorTag, CreatorTagMap,
    Campaign, CampaignProduct, CampaignCreator,
    Booking, BookingDeliverable,
    Video, VideoMetricSnapshot,
    Payment,
    Template, Rule,
)


class Command(BaseCommand):
    help = 'Tạo sample data cho TikTok Booking Center (brands, products, creators, campaigns, bookings, videos, payments)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Bắt đầu tạo seed data...'))

        # Get or create admin user
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@example.com', 'is_staff': True, 'is_superuser': True}
        )
        if not admin_user.check_password('admin'):
            admin_user.set_password('admin')
            admin_user.save()

        # ========================================================================
        # 1. BRANDS & PRODUCTS
        # ========================================================================
        self.stdout.write('Tạo brands và products...')
        
        brand1, _ = Brand.objects.get_or_create(
            code='BRAND1',
            defaults={'name': 'Thương hiệu A', 'description': 'Thương hiệu chuyên về đồ gia dụng'}
        )
        brand2, _ = Brand.objects.get_or_create(
            code='BRAND2',
            defaults={'name': 'Thương hiệu B', 'description': 'Thương hiệu thời trang'}
        )

        products_data = [
            (brand1, 'P001', 'Nồi cơm điện cao cấp', 'Đồ gia dụng', 1001, 'SP001'),
            (brand1, 'P002', 'Máy xay sinh tố', 'Đồ gia dụng', 1002, 'SP002'),
            (brand1, 'P003', 'Bếp từ đôi', 'Đồ gia dụng', 1003, 'SP003'),
            (brand2, 'P004', 'Áo thun nam', 'Thời trang', 2001, 'SP004'),
            (brand2, 'P005', 'Quần jean nữ', 'Thời trang', 2002, 'SP005'),
            (brand2, 'P006', 'Giày thể thao', 'Thời trang', 2003, 'SP006'),
        ]

        products = []
        for brand, code, name, category, sapo_id, shopee_id in products_data:
            product, _ = Product.objects.get_or_create(
                brand=brand,
                code=code,
                defaults={
                    'name': name,
                    'category': category,
                    'sapo_product_id': sapo_id,
                    'shopee_id': shopee_id,
                    'is_active': True
                }
            )
            products.append(product)

        # ========================================================================
        # 2. CREATORS
        # ========================================================================
        self.stdout.write('Tạo creators...')

        creators_data = [
            ('Nguyễn Văn A', 'creator_a', 'male', date(1995, 5, 15), 'Hà Nội', 'beauty', 'active', 9),
            ('Trần Thị B', 'creator_b', 'female', date(1998, 8, 20), 'TP.HCM', 'fashion', 'active', 8),
            ('Lê Văn C', 'creator_c', 'male', date(1992, 3, 10), 'Đà Nẵng', 'tech', 'active', 7),
            ('Phạm Thị D', 'creator_d', 'female', date(1996, 11, 5), 'Hà Nội', 'lifestyle', 'watchlist', 6),
            ('Hoàng Văn E', 'creator_e', 'male', date(1994, 7, 25), 'TP.HCM', 'food', 'active', 5),
            ('Vũ Thị F', 'creator_f', 'female', date(1999, 2, 14), 'Hà Nội', 'beauty', 'active', 8),
        ]

        creators = []
        for name, alias, gender, dob, location, niche, status, priority in creators_data:
            creator, _ = Creator.objects.get_or_create(
                name=name,
                defaults={
                    'alias': alias,
                    'gender': gender,
                    'dob': dob,
                    'location': location,
                    'niche': niche,
                    'status': status,
                    'priority_score': priority,
                }
            )
            creators.append(creator)

        # Creator channels
        channels_data = [
            (creators[0], 'tiktok', 'creator_a_tiktok', 'https://tiktok.com/@creator_a', 'tiktok_123', 500000, 50000, Decimal('5.50')),
            (creators[1], 'tiktok', 'creator_b_tiktok', 'https://tiktok.com/@creator_b', 'tiktok_456', 800000, 80000, Decimal('6.20')),
            (creators[2], 'tiktok', 'creator_c_tiktok', 'https://tiktok.com/@creator_c', 'tiktok_789', 300000, 30000, Decimal('4.80')),
            (creators[3], 'tiktok', 'creator_d_tiktok', 'https://tiktok.com/@creator_d', 'tiktok_101', 200000, 20000, Decimal('3.50')),
            (creators[4], 'tiktok', 'creator_e_tiktok', 'https://tiktok.com/@creator_e', 'tiktok_202', 400000, 40000, Decimal('5.00')),
            (creators[5], 'tiktok', 'creator_f_tiktok', 'https://tiktok.com/@creator_f', 'tiktok_303', 600000, 60000, Decimal('5.80')),
        ]

        channels = []
        for creator, platform, handle, profile_url, external_id, followers, avg_view, engagement in channels_data:
            channel, _ = CreatorChannel.objects.get_or_create(
                creator=creator,
                platform=platform,
                handle=handle,
                defaults={
                    'profile_url': profile_url,
                    'external_id': external_id,
                    'follower_count': followers,
                    'avg_view_10': avg_view,
                    'avg_engagement_rate': engagement,
                }
            )
            channels.append(channel)

        # Creator contacts
        for i, creator in enumerate(creators):
            CreatorContact.objects.get_or_create(
                creator=creator,
                contact_type='owner',
                defaults={
                    'name': creator.name,
                    'phone': f'090000000{i+1}',
                    'zalo': f'zalo_{i+1}',
                    'email': f'{creator.alias}@example.com',
                    'is_primary': True,
                }
            )

        # Creator tags
        tag1, _ = CreatorTag.objects.get_or_create(name='Top Creator', defaults={'description': 'Creator hàng đầu'})
        tag2, _ = CreatorTag.objects.get_or_create(name='Beauty Expert', defaults={'description': 'Chuyên về làm đẹp'})
        tag3, _ = CreatorTag.objects.get_or_create(name='Fashion Influencer', defaults={'description': 'Influencer thời trang'})

        CreatorTagMap.objects.get_or_create(creator=creators[0], tag=tag1)
        CreatorTagMap.objects.get_or_create(creator=creators[0], tag=tag2)
        CreatorTagMap.objects.get_or_create(creator=creators[1], tag=tag3)

        # ========================================================================
        # 3. CAMPAIGNS
        # ========================================================================
        self.stdout.write('Tạo campaigns...')

        campaign1, _ = Campaign.objects.get_or_create(
            code='CAMP001',
            defaults={
                'name': 'Chiến dịch Q1 2024 - Brand A',
                'brand': brand1,
                'channel': 'tiktok',
                'objective': 'sale',
                'description': 'Chiến dịch bán hàng Q1 cho thương hiệu A',
                'start_date': date.today() - timedelta(days=30),
                'end_date': date.today() + timedelta(days=30),
                'budget_planned': Decimal('50000000'),
                'kpi_view': 1000000,
                'kpi_order': 500,
                'kpi_revenue': Decimal('200000000'),
                'status': 'running',
                'owner': admin_user,
            }
        )

        campaign2, _ = Campaign.objects.get_or_create(
            code='CAMP002',
            defaults={
                'name': 'Chiến dịch Launch - Brand B',
                'brand': brand2,
                'channel': 'tiktok',
                'objective': 'launch',
                'description': 'Chiến dịch ra mắt sản phẩm mới',
                'start_date': date.today(),
                'end_date': date.today() + timedelta(days=60),
                'budget_planned': Decimal('30000000'),
                'kpi_view': 500000,
                'kpi_order': 200,
                'kpi_revenue': Decimal('100000000'),
                'status': 'planned',
                'owner': admin_user,
            }
        )

        # Campaign products
        CampaignProduct.objects.get_or_create(campaign=campaign1, product=products[0], defaults={'priority': 1})
        CampaignProduct.objects.get_or_create(campaign=campaign1, product=products[1], defaults={'priority': 2})
        CampaignProduct.objects.get_or_create(campaign=campaign2, product=products[3], defaults={'priority': 1})
        CampaignProduct.objects.get_or_create(campaign=campaign2, product=products[4], defaults={'priority': 2})

        # Campaign creators
        CampaignCreator.objects.get_or_create(campaign=campaign1, creator=creators[0], defaults={'role': 'main'})
        CampaignCreator.objects.get_or_create(campaign=campaign1, creator=creators[1], defaults={'role': 'supporting'})
        CampaignCreator.objects.get_or_create(campaign=campaign2, creator=creators[2], defaults={'role': 'main'})
        CampaignCreator.objects.get_or_create(campaign=campaign2, creator=creators[3], defaults={'role': 'trial'})

        # ========================================================================
        # 4. BOOKINGS
        # ========================================================================
        self.stdout.write('Tạo bookings...')

        booking1, _ = Booking.objects.get_or_create(
            code='BOOK001',
            defaults={
                'campaign': campaign1,
                'creator': creators[0],
                'channel': channels[0],
                'brand': brand1,
                'product_focus': products[0],
                'booking_type': 'combo',
                'brief_summary': 'Tạo 3 video về nồi cơm điện',
                'start_date': date.today() - timedelta(days=10),
                'end_date': date.today() + timedelta(days=20),
                'total_fee_agreed': Decimal('15000000'),
                'currency': 'VND',
                'deliverables_count_planned': 3,
                'status': 'in_progress',
            }
        )

        booking2, _ = Booking.objects.get_or_create(
            code='BOOK002',
            defaults={
                'campaign': campaign1,
                'creator': creators[1],
                'channel': channels[1],
                'brand': brand1,
                'product_focus': products[1],
                'booking_type': 'video_only',
                'brief_summary': '1 video về máy xay sinh tố',
                'start_date': date.today() - timedelta(days=5),
                'end_date': date.today() + timedelta(days=15),
                'total_fee_agreed': Decimal('8000000'),
                'currency': 'VND',
                'deliverables_count_planned': 1,
                'status': 'confirmed',
            }
        )

        # Booking deliverables
        deliverable1, _ = BookingDeliverable.objects.get_or_create(
            booking=booking1,
            deliverable_type='video_feed',
            title='Video 1 - Giới thiệu sản phẩm',
            defaults={
                'deadline_post': timezone.now() + timedelta(days=5),
                'quantity': 1,
                'fee': Decimal('5000000'),
                'status': 'shooting',
            }
        )

        deliverable2, _ = BookingDeliverable.objects.get_or_create(
            booking=booking1,
            deliverable_type='video_feed',
            title='Video 2 - Hướng dẫn sử dụng',
            defaults={
                'deadline_post': timezone.now() + timedelta(days=10),
                'quantity': 1,
                'fee': Decimal('5000000'),
                'status': 'planned',
            }
        )

        deliverable3, _ = BookingDeliverable.objects.get_or_create(
            booking=booking2,
            deliverable_type='video_feed',
            title='Video review máy xay',
            defaults={
                'deadline_post': timezone.now() + timedelta(days=7),
                'quantity': 1,
                'fee': Decimal('8000000'),
                'status': 'waiting_approve',
            }
        )

        # ========================================================================
        # 5. VIDEOS
        # ========================================================================
        self.stdout.write('Tạo videos...')

        video1, _ = Video.objects.get_or_create(
            channel='tiktok',
            platform_video_id='tiktok_video_001',
            defaults={
                'booking_deliverable': deliverable1,
                'booking': booking1,
                'campaign': campaign1,
                'creator': creators[0],
                'url': 'https://tiktok.com/@creator_a/video/001',
                'title': 'Nồi cơm điện cao cấp - Review chi tiết',
                'post_date': timezone.now() - timedelta(days=2),
                'thumbnail_url': 'https://example.com/thumb1.jpg',
                'status': 'posted',
            }
        )

        # Video snapshots
        VideoMetricSnapshot.objects.get_or_create(
            video=video1,
            snapshot_time=timezone.now() - timedelta(days=1),
            defaults={
                'view_count': 50000,
                'like_count': 5000,
                'comment_count': 500,
                'share_count': 200,
                'save_count': 1000,
                'engagement_rate': Decimal('14.00'),
            }
        )

        VideoMetricSnapshot.objects.get_or_create(
            video=video1,
            snapshot_time=timezone.now(),
            defaults={
                'view_count': 120000,
                'like_count': 12000,
                'comment_count': 1200,
                'share_count': 500,
                'save_count': 2500,
                'engagement_rate': Decimal('12.50'),
            }
        )

        # ========================================================================
        # 6. PAYMENTS
        # ========================================================================
        self.stdout.write('Tạo payments...')

        Payment.objects.get_or_create(
            booking=booking1,
            payment_date=date.today() - timedelta(days=5),
            amount=Decimal('5000000'),
            defaults={
                'creator': creators[0],
                'campaign': campaign1,
                'currency': 'VND',
                'amount_vnd': Decimal('5000000'),
                'payment_method': 'bank_transfer',
                'status': 'paid',
                'created_by': admin_user,
            }
        )

        Payment.objects.get_or_create(
            booking=booking1,
            payment_date=date.today() + timedelta(days=10),
            amount=Decimal('10000000'),
            defaults={
                'creator': creators[0],
                'campaign': campaign1,
                'currency': 'VND',
                'amount_vnd': Decimal('10000000'),
                'payment_method': 'bank_transfer',
                'status': 'planned',
                'created_by': admin_user,
            }
        )

        # ========================================================================
        # 7. TEMPLATES & RULES
        # ========================================================================
        self.stdout.write('Tạo templates và rules...')

        Template.objects.get_or_create(
            name='Brief Template - TikTok Video',
            defaults={
                'template_type': 'brief',
                'channel': 'tiktok',
                'content': '''# Brief cho Video TikTok

## Sản phẩm: {{product_name}}
## Creator: {{creator_name}}

### Yêu cầu:
- Thời lượng: 30-60 giây
- Format: Vertical (9:16)
- Nội dung: {{content_requirements}}

### Deadline: {{deadline}}
''',
                'variables': {'product_name': 'string', 'creator_name': 'string', 'content_requirements': 'string', 'deadline': 'date'},
                'is_active': True,
            }
        )

        Rule.objects.get_or_create(
            name='Auto-update campaign budget',
            defaults={
                'scope': 'campaign',
                'description': 'Tự động cập nhật budget_actual từ payments',
                'condition_json': {'type': 'payment_status_changed', 'status': 'paid'},
                'action_json': {'type': 'update_campaign_budget'},
                'is_active': True,
            }
        )

        self.stdout.write(self.style.SUCCESS('✓ Hoàn thành tạo seed data!'))
        self.stdout.write(f'  - Brands: {Brand.objects.count()}')
        self.stdout.write(f'  - Products: {Product.objects.count()}')
        self.stdout.write(f'  - Creators: {Creator.objects.count()}')
        self.stdout.write(f'  - Campaigns: {Campaign.objects.count()}')
        self.stdout.write(f'  - Bookings: {Booking.objects.count()}')
        self.stdout.write(f'  - Videos: {Video.objects.count()}')
        self.stdout.write(f'  - Payments: {Payment.objects.count()}')


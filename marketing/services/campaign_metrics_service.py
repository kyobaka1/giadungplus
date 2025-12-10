"""
Campaign Metrics Service - Tính toán metrics và health flags cho campaigns.
"""
from decimal import Decimal
from typing import Dict, List, Optional
from django.db.models import Sum, Count, Q
from django.utils import timezone
from marketing.models import Campaign, CampaignProduct, CampaignCreator, Booking, Payment, Video, BookingDeliverable


class CampaignMetricsService:
    """
    Service để tính toán metrics và health flags cho campaigns.
    Gracefully degrade nếu các module khác chưa tồn tại.
    """
    
    @staticmethod
    def get_campaign_metrics(campaign: Campaign) -> Dict:
        """
        Tính toán tất cả metrics cho một campaign.
        
        Returns:
            Dict với các metrics:
            - budget_actual_paid: Tổng đã thanh toán
            - budget_committed: Tổng đã cam kết (từ bookings)
            - creators_count: Số creators
            - products_count: Số products
            - bookings_count_by_status: Dict số bookings theo status
            - deliverables_total/posted/overdue: Số deliverables
            - videos_posted: Số videos đã post
            - views_latest_total: Tổng views mới nhất
            - orders_attributed: Số đơn hàng
            - revenue_attributed: Doanh thu
            - ROAS, CPO, CPV: Các chỉ số hiệu quả
            - progress_percent: % hoàn thành
        """
        metrics = {
            'budget_actual_paid': Decimal('0.00'),
            'budget_committed': Decimal('0.00'),
            'creators_count': 0,
            'products_count': 0,
            'bookings_count_by_status': {},
            'deliverables_total': 0,
            'deliverables_posted': 0,
            'deliverables_overdue': 0,
            'videos_posted': 0,
            'views_latest_total': 0,
            'orders_attributed': 0,
            'revenue_attributed': Decimal('0.00'),
            'roas': None,
            'cpo': None,
            'cpv': None,
            'progress_percent': 0,
        }
        
        # Creators và Products count (luôn có)
        metrics['creators_count'] = campaign.campaign_creators.filter(is_active=True).count()
        metrics['products_count'] = campaign.campaign_products.filter(is_active=True).count()
        
        # Budget committed (từ bookings) - gracefully degrade nếu Booking chưa tồn tại
        try:
            bookings = Booking.objects.filter(campaign=campaign, is_active=True)
            metrics['budget_committed'] = bookings.aggregate(
                total=Sum('total_fee_agreed')
            )['total'] or Decimal('0.00')
            
            # Bookings count by status
            for status, _ in Booking.STATUS_CHOICES:
                count = bookings.filter(status=status).count()
                if count > 0:
                    metrics['bookings_count_by_status'][status] = count
        except Exception:
            pass  # Booking model chưa tồn tại hoặc lỗi
        
        # Budget actual paid (từ payments) - gracefully degrade
        try:
            payments = Payment.objects.filter(
                campaign=campaign,
                is_active=True,
                status='paid'
            )
            metrics['budget_actual_paid'] = payments.aggregate(
                total=Sum('amount_vnd')
            )['total'] or Decimal('0.00')
        except Exception:
            pass  # Payment model chưa tồn tại hoặc lỗi
        
        # Deliverables - gracefully degrade
        try:
            deliverables = BookingDeliverable.objects.filter(
                booking__campaign=campaign,
                booking__is_active=True,
                is_active=True
            )
            metrics['deliverables_total'] = deliverables.count()
            metrics['deliverables_posted'] = deliverables.filter(status='posted').count()
            
            # Overdue: deadline_post đã qua nhưng chưa posted
            now = timezone.now()
            metrics['deliverables_overdue'] = deliverables.filter(
                deadline_post__lt=now,
                status__in=['planned', 'shooting', 'waiting_approve', 'scheduled']
            ).count()
        except Exception:
            pass
        
        # Videos posted - gracefully degrade
        try:
            videos = Video.objects.filter(
                campaign=campaign,
                is_active=True,
                status='posted'
            )
            metrics['videos_posted'] = videos.count()
            
            # Views latest total: lấy snapshot mới nhất của mỗi video
            from marketing.models import VideoMetricSnapshot
            latest_snapshots = VideoMetricSnapshot.objects.filter(
                video__campaign=campaign,
                video__is_active=True
            ).order_by('video', '-snapshot_time').distinct('video')
            metrics['views_latest_total'] = sum(
                s.view_count for s in latest_snapshots
            )
        except Exception:
            pass
        
        # Orders và Revenue attributed - gracefully degrade
        try:
            from marketing.models import TrackingConversion
            conversions = TrackingConversion.objects.filter(
                tracking_asset__campaign=campaign,
                is_active=True
            )
            metrics['orders_attributed'] = conversions.count()
            metrics['revenue_attributed'] = conversions.aggregate(
                total=Sum('revenue')
            )['total'] or Decimal('0.00')
        except Exception:
            pass
        
        # Tính ROAS, CPO, CPV
        if metrics['revenue_attributed'] > 0 and metrics['budget_actual_paid'] > 0:
            metrics['roas'] = float(metrics['revenue_attributed'] / metrics['budget_actual_paid'])
        
        if metrics['orders_attributed'] > 0 and metrics['budget_actual_paid'] > 0:
            metrics['cpo'] = float(metrics['budget_actual_paid'] / metrics['orders_attributed'])
        
        if metrics['views_latest_total'] > 0 and metrics['budget_actual_paid'] > 0:
            metrics['cpv'] = float(metrics['budget_actual_paid'] / metrics['views_latest_total'])
        
        # Progress percent
        # Phase 1: Planning progress (có dates, creators, products, budget)
        has_dates = bool(campaign.start_date and campaign.end_date)
        has_creators = metrics['creators_count'] > 0
        has_products = metrics['products_count'] > 0
        has_budget = campaign.budget_planned > 0
        
        planning_progress = sum([has_dates, has_creators, has_products, has_budget]) / 4 * 100
        
        # Phase 2: Execution progress (nếu có deliverables)
        if metrics['deliverables_total'] > 0:
            execution_progress = (metrics['deliverables_posted'] / metrics['deliverables_total']) * 100
            # Weighted: 30% planning + 70% execution
            metrics['progress_percent'] = int(planning_progress * 0.3 + execution_progress * 0.7)
        else:
            metrics['progress_percent'] = int(planning_progress)
        
        return metrics
    
    @staticmethod
    def get_health_flags(campaign: Campaign) -> List[Dict]:
        """
        Tính toán health flags cho campaign.
        
        Returns:
            List[Dict] với format: [{'code': 'MISSING_CREATOR', 'severity': 'warning', 'message': '...'}, ...]
        """
        flags = []
        
        # MISSING_CREATOR
        if campaign.status in ['planned', 'running']:
            creators_count = campaign.campaign_creators.filter(is_active=True).count()
            if creators_count == 0:
                flags.append({
                    'code': 'MISSING_CREATOR',
                    'severity': 'error',
                    'message': 'Campaign đang thiếu creators'
                })
        
        # MISSING_PRODUCT (optional warning)
        if campaign.status in ['planned', 'running']:
            products_count = campaign.campaign_products.filter(is_active=True).count()
            if products_count == 0:
                flags.append({
                    'code': 'MISSING_PRODUCT',
                    'severity': 'warning',
                    'message': 'Campaign chưa có sản phẩm nào'
                })
        
        # DATE_INVALID
        if campaign.start_date and campaign.end_date:
            if campaign.end_date < campaign.start_date:
                flags.append({
                    'code': 'DATE_INVALID',
                    'severity': 'error',
                    'message': 'Ngày kết thúc phải sau ngày bắt đầu'
                })
        
        # KPI_MISSING (nếu objective là sale/traffic)
        if campaign.objective in ['sale', 'traffic']:
            if campaign.kpi_view == 0 and campaign.kpi_order == 0 and campaign.kpi_revenue == 0:
                flags.append({
                    'code': 'KPI_MISSING',
                    'severity': 'warning',
                    'message': 'Chưa đặt KPI cho campaign'
                })
        
        # OVER_BUDGET
        try:
            metrics = CampaignMetricsService.get_campaign_metrics(campaign)
            if metrics['budget_actual_paid'] > campaign.budget_planned > 0:
                flags.append({
                    'code': 'OVER_BUDGET',
                    'severity': 'error',
                    'message': f'Đã vượt ngân sách: {metrics["budget_actual_paid"]:,.0f} / {campaign.budget_planned:,.0f}'
                })
        except Exception:
            pass
        
        # AT_RISK_DEADLINE (nếu có deliverables overdue)
        try:
            metrics = CampaignMetricsService.get_campaign_metrics(campaign)
            if metrics['deliverables_overdue'] > 0:
                flags.append({
                    'code': 'AT_RISK_DEADLINE',
                    'severity': 'warning',
                    'message': f'Có {metrics["deliverables_overdue"]} deliverables quá hạn'
                })
        except Exception:
            pass
        
        # CREATOR_RISK (nếu creator có status watchlist/blacklist)
        if campaign.status in ['planned', 'running']:
            risky_creators = campaign.campaign_creators.filter(
                is_active=True,
                creator__status__in=['watchlist', 'blacklist']
            )
            for cc in risky_creators:
                flags.append({
                    'code': 'CREATOR_RISK',
                    'severity': 'warning' if cc.creator.status == 'watchlist' else 'error',
                    'message': f'Creator {cc.creator.name} đang ở trạng thái {cc.creator.get_status_display()}'
                })
        
        return flags


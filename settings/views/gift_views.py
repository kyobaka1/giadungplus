# settings/views/gift_views.py
"""
Views for Gift/Promotion management (Read-only from Sapo)
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from kho.utils import admin_only
from core.sapo_client import get_sapo_client
from orders.services.promotion_service import PromotionService
import logging

logger = logging.getLogger(__name__)


@admin_only
def gift_list(request):
    """
    Danh sách promotions từ Sapo (read-only).
    Data được load từ cache hoặc fetch từ Sapo API.
    """
    sapo = get_sapo_client()
    promotion_service = PromotionService(sapo)
    
    promotions = []
    cache_time = None
    error = None
    
    try:
        promotions = promotion_service.load_from_cache()
        
        # Get cache timestamp if available
        import json
        from pathlib import Path
        cache_file = Path(promotion_service.CACHE_FILE)
        if cache_file.exists():
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                cache_time = cache_data.get('cached_at')
    except Exception as e:
        logger.error(f"[GiftViews] Failed to load promotions: {e}")
        error = str(e)
        messages.error(request, f"Không thể tải danh sách khuyến mãi: {e}")
    
    # Calculate counts before filtering
    total_count = len(promotions)
    active_count = len([p for p in promotions if p.status == 'active'])
    inactive_count = total_count - active_count
    
    # Filter by status if requested
    status_filter = request.GET.get('status', 'all')
    if status_filter == 'active':
        promotions = [p for p in promotions if p.status == 'active']
    elif status_filter == 'inactive':
        promotions = [p for p in promotions if p.status != 'active']
    
    context = {
        'promotions': promotions,
        'total_count': total_count,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'cache_time': cache_time,
        'status_filter': status_filter,
        'error': error,
        'is_readonly': True,
    }
    
    return render(request, 'settings/gift_list.html', context)


@admin_only
def gift_detail(request, promotion_id):
    """
    Xem chi tiết promotion từ Sapo (read-only).
    """
    sapo = get_sapo_client()
    promotion_service = PromotionService(sapo)
    
    try:
        promotions = promotion_service.load_from_cache()
        promotion = next((p for p in promotions if p.id == int(promotion_id)), None)
        
        if not promotion:
            messages.error(request, f"Không tìm thấy promotion ID {promotion_id}")
            return redirect('gift_list')
        
        context = {
            'promotion': promotion,
            'is_readonly': True,
        }
        
        return render(request, 'settings/gift_detail.html', context)
        
    except Exception as e:
        logger.error(f"[GiftViews] Failed to load promotion {promotion_id}: {e}")
        messages.error(request, f"Lỗi khi tải promotion: {e}")
        return redirect('gift_list')


@admin_only
@require_http_methods(["POST"])
def gift_sync(request):
    """
    Sync promotions từ Sapo API và refresh cache.
    """
    sapo = get_sapo_client()
    promotion_service = PromotionService(sapo)
    
    try:
        promotions = promotion_service.fetch_and_cache_promotions()
        messages.success(
            request, 
            f"✓ Đã sync {len(promotions)} chương trình khuyến mãi từ Sapo!"
        )
    except Exception as e:
        logger.error(f"[GiftViews] Failed to sync promotions: {e}")
        messages.error(request, f"Lỗi khi sync từ Sapo: {e}")
    
    return redirect('gift_list')

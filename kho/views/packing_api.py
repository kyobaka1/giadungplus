# kho/views/packing_api.py
"""
Packing Orders API Endpoints
Mobile-first packing workflow for warehouse staff
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from kho.utils import group_required

from core.sapo_client import SapoClient
from orders.services.sapo_service import SapoCoreOrderService, mo_rong_gon
from orders.services.order_builder import OrderDTOFactory

logger = logging.getLogger(__name__)

DEBUG_PRINT_ENABLED = True

def debug_print(*args, **kwargs):
    if DEBUG_PRINT_ENABLED:
        print("[DEBUG]", *args, **kwargs)


@group_required("WarehousePacker")
@require_http_methods(["GET"])
def get_order(request):
    """
    GET /kho/orders/packing/get_order/?tracking_code=<code>
    
    Lấy thông tin đơn hàng từ tracking code (QR).
    Returns OrderDTO with real_items, gifts, images, và dvvc.
    """
    tracking_code = request.GET.get('tracking_code', '').strip()
    
    if not tracking_code:
        return JsonResponse({
            'success': False,
            'error': 'Vui lòng nhập mã vận đơn'
        })
    
    debug_print(f"[PackingAPI] Getting order with tracking_code: {tracking_code}")
    
    try:
        sapo = SapoClient()
        order_service = SapoCoreOrderService()
        
        # Search order by tracking code
        # Tracking code is in fulfillment.shipment.tracking_code
        orders_raw = sapo.core.list_orders_raw(
            limit=50,
            query=tracking_code  # Search in multiple fields including tracking_code
        )
        
        debug_print(f"[PackingAPI] orders_raw type: {type(orders_raw)}")
        debug_print(f"[PackingAPI] orders_raw: {orders_raw}")
        
        if not orders_raw:
            debug_print(f"[PackingAPI] No orders found for tracking_code: {tracking_code}")
            return JsonResponse({
                'success': False,
                'error': f'Không tìm thấy đơn hàng với mã vận đơn: {tracking_code}'
            })
        
        # Handle if orders_raw is a dict with 'orders' key
        if isinstance(orders_raw, dict) and 'orders' in orders_raw:
            orders_raw = orders_raw['orders']
            debug_print(f"[PackingAPI] Extracted orders array, count: {len(orders_raw)}")
        
        # Find order with matching tracking code
        target_order_raw = None
        target_fulfillment = None
        
        for order_raw in orders_raw:
            fulfillments = order_raw.get('fulfillments', [])
            for fulfillment in fulfillments:
                shipment = fulfillment.get('shipment')
                if shipment and shipment.get('tracking_code') == tracking_code:
                    target_order_raw = order_raw
                    target_fulfillment = fulfillment
                    break
            if target_order_raw:
                break
        
        if not target_order_raw:
            debug_print(f"[PackingAPI] No order found with exact tracking_code match")
            return JsonResponse({
                'success': False,
                'error': f'Không tìm thấy đơn hàng với mã vận đơn: {tracking_code}'
            })
        
        # Validate order status
        order_status = target_order_raw.get('status')
        if order_status not in ['finalized', 'open', 'received']:
            debug_print(f"[PackingAPI] Order status invalid: {order_status}")
            return JsonResponse({
                'success': False,
                'error': f'Đơn hàng không hợp lệ để đóng gói (status: {order_status})'
            })
        
        # Build OrderDTO
        factory = OrderDTOFactory()
        order_dto = factory.from_sapo_json(target_order_raw, sapo)
        
        # Extract dvvc from shipment note
        dvvc = 'Chưa xác định'
        if target_fulfillment:
            shipment = target_fulfillment.get('shipment')
            if shipment and shipment.get('note'):
                try:
                    note_data = mo_rong_gon(shipment['note'])
                    dvvc = note_data.get('dvvc', 'Chưa xác định')
                except:
                    pass
        
        # Helper function to get variant image from Sapo
        def get_variant_image(variant_id):
            """Fetch variant image from Sapo API"""
            try:
                variant_url = f"variants/{variant_id}.json"
                variant_response = sapo.core.get(variant_url)
                
                if variant_response and 'variant' in variant_response:
                    variant_data = variant_response['variant']
                    images = variant_data.get('images', [])
                    if images and len(images) > 0:
                        # Return the full_path of the first (default) image
                        return images[0].get('full_path')
            except Exception as e:
                debug_print(f"[PackingAPI] Error fetching variant image for {variant_id}: {e}")
            
            return None
        
        # Prepare real_items data for JSON response
        real_items_data = []
        for item in order_dto.real_items:
            # Get image from Sapo API
            image_url = get_variant_image(item.variant_id) if item.variant_id else None
            
            real_items_data.append({
                'variant_id': item.variant_id,
                'sku': item.sku,
                'barcode': item.barcode,
                'product_name': item.product_name,
                'variant_options': item.variant_options,
                'quantity': item.quantity,
                'unit': item.unit,
                'image_url': image_url
            })
        
        # Prepare gifts data
        gifts_data = []
        for gift in order_dto.gifts:
            # Get image from Sapo API for gifts too
            gift_image_url = get_variant_image(gift.variant_id) if gift.variant_id else None
            
            gifts_data.append({
                'variant_id': gift.variant_id,
                'variant_name': gift.variant_name,
                'sku': gift.sku,
                'quantity': gift.quantity,
                'promotion_name': gift.promotion_name,
                'unit': gift.unit,
                'opt1': gift.opt1,
                'image_url': gift_image_url
            })
        
        debug_print(f"[PackingAPI] Order found: {order_dto.code}, {len(real_items_data)} items, {len(gifts_data)} gifts")
        
        return JsonResponse({
            'success': True,
            'order': {
                'id': order_dto.id,
                'code': order_dto.code,
                'customer_name': order_dto.customer_name,
                'customer_phone': order_dto.customer_phone,
                'shipping_address': order_dto.shipping_address_line,
                'real_items': real_items_data,
                'gifts': gifts_data,
                'notes': order_dto.note or '',
                'total_items': len(real_items_data) + len(gifts_data)
            },
            'dvvc': dvvc,
            'fulfillment_id': target_fulfillment.get('id') if target_fulfillment else None,
            'error': ''
        })
        
    except Exception as e:
        logger.error(f"[PackingAPI] Error getting order: {e}", exc_info=True)
        debug_print(f"[PackingAPI] Error: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Lỗi hệ thống: {str(e)}'
        })


@group_required("WarehousePacker")
@require_http_methods(["POST"])
def complete(request):
    """
    POST /kho/orders/packing/complete/
    Body: {"order_id": int, "fulfillment_id": int}
    
    Hoàn tất đóng gói - cập nhật packing_status=3, lưu người gói, thời gian.
    """
    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
        fulfillment_id = data.get('fulfillment_id')
        
        if not order_id or not fulfillment_id:
            return JsonResponse({
                'success': False,
                'message': 'Thiếu thông tin order_id hoặc fulfillment_id'
            })
        
        debug_print(f"[PackingAPI] Completing packing for order {order_id}, fulfillment {fulfillment_id}")
        
        # Get current user
        packer_username = request.user.username
        
        # Update packing status to Sapo
        sapo = SapoClient()
        order_service = SapoCoreOrderService()
        
        success = order_service.update_fulfillment_packing_status(
            order_id=order_id,
            fulfillment_id=fulfillment_id,
            packing_status=3,  # Đã đóng gói
            # Additional fields will be set automatically by the service
        )
        
        if success:
            debug_print(f"[PackingAPI] ✓ Packing completed successfully by {packer_username}")
            return JsonResponse({
                'success': True,
                'message': f'Đã hoàn tất đóng gói đơn hàng'
            })
        else:
            debug_print(f"[PackingAPI] ✗ Failed to update packing status")
            return JsonResponse({
                'success': False,
                'message': 'Không thể cập nhật trạng thái đóng gói. Vui lòng thử lại.'
            })
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Dữ liệu không hợp lệ'
        })
    except Exception as e:
        logger.error(f"[PackingAPI] Error completing packing: {e}", exc_info=True)
        debug_print(f"[PackingAPI] Error: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Lỗi hệ thống: {str(e)}'
        })

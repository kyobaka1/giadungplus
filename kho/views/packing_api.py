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

# Tắt debug print mặc định để tránh spam log trong kho
DEBUG_PRINT_ENABLED = False

def debug_print(*args, **kwargs):
    if DEBUG_PRINT_ENABLED:
        print("[DEBUG]", *args, **kwargs)


@group_required("WarehousePacker", "WarehouseManager")
@require_http_methods(["GET"])
def get_order(request):
    """
    GET /kho/orders/packing/get_order/?tracking_code=<code>
    
    Lấy thông tin đơn hàng từ tracking code (QR).
    Returns OrderDTO with real_items, gifts, images, và dvvc.
    """
    from kho.models import WarehousePackingSetting
    
    # Kiểm tra quyền truy cập tính năng packing
    is_allowed, reason = WarehousePackingSetting.is_packing_enabled_for_user(request.user)
    
    if not is_allowed:
        return JsonResponse({
            'success': False,
            'error': f'Bạn không thể sử dụng tính năng này. {reason}'
        }, status=403)
    
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
        
        # Validate order status - Đơn hàng đã huỷ
        order_status = target_order_raw.get('status')
        if order_status == 'cancelled':
            debug_print(f"[PackingAPI] Order is cancelled: {order_status}")
            return JsonResponse({
                'success': False,
                'error': 'Đơn hàng đã bị huỷ. Không thể đóng gói.'
            })
        
        # Validate order status - Chỉ cho phép finalized, open, received
        if order_status not in ['finalized', 'open', 'received']:
            debug_print(f"[PackingAPI] Order status invalid: {order_status}")
            return JsonResponse({
                'success': False,
                'error': f'Đơn hàng không hợp lệ để đóng gói (status: {order_status})'
            })
        
        # Validate fulfillment status và packing status
        if target_fulfillment:
            # Kiểm tra composite_fulfillment_status - chỉ cho phép "fulfilled" hoặc "packed"
            composite_status = target_fulfillment.get('composite_fulfillment_status')
            allowed_statuses = ['packed']
            
            if composite_status:
                if composite_status not in allowed_statuses:
                    status_messages = {
                        'retry_delivery': 'Đơn hàng đang chờ giao lại. Đã được gửi đi rồi. Không thể đóng gói.',
                        'fulfilled': 'Đơn hàng đã được giao đi rồi. Bên vận chuyển đã lấy hàng.',
                        'received': 'Đơn hàng đã được giao hàng. Không thể đóng gói.',
                        'packed_cancelled': 'Vận đơn đã bị huỷ. Đơn hàng có thể đã có mã vận chuyển khác. Không thể đóng gói.',
                        'fulfilled_cancelling': 'Vận đơn đang được huỷ. Không thể đóng gói.',
                        'fulfilled_cancelled': 'Vận đơn đã bị huỷ. Đơn hàng có thể đã có mã vận chuyển khác. Không thể đóng gói.',
                    }
                    
                    error_message = status_messages.get(composite_status)
                    if error_message:
                        debug_print(f"[PackingAPI] Composite fulfillment status not allowed: {composite_status}")
                        return JsonResponse({
                            'success': False,
                            'error': error_message
                        })
                    else:
                        # Trạng thái không xác định
                        debug_print(f"[PackingAPI] Composite fulfillment status unknown: {composite_status}")
                        return JsonResponse({
                            'success': False,
                            'error': f'Trạng thái đơn hàng không hợp lệ để đóng gói ({composite_status}). Chỉ có thể gói khi trạng thái là "fulfilled" hoặc "packed".'
                        })
            else:
                # Nếu không có composite_fulfillment_status, kiểm tra các trường khác
                # Kiểm tra fulfillment đã bị huỷ
                if target_fulfillment.get('cancel_date'):
                    debug_print(f"[PackingAPI] Fulfillment is cancelled (cancel_date exists)")
                    return JsonResponse({
                        'success': False,
                        'error': 'Vận đơn đã bị huỷ. Đơn hàng có thể đã có mã vận chuyển khác. Không thể đóng gói.'
                    })
        
        # Build OrderDTO để lấy packing_status
        factory = OrderDTOFactory()
        order_dto = factory.from_sapo_json(target_order_raw, sapo)
        
        # Kiểm tra packing_status = 4 (Đã gói)
        if order_dto.packing_status == 4:
            debug_print(f"[PackingAPI] Order already packed: packing_status=4")
            return JsonResponse({
                'success': False,
                'error': 'Đơn hàng đã được đóng gói rồi. Không thể đóng gói lại.'
            })
        
        # Apply gifts từ promotions (như print_now)
        try:
            from orders.services.promotion_service import PromotionService
            promotion_service = PromotionService(sapo)
            order_dto = promotion_service.apply_gifts_to_order(order_dto)
            debug_print(f"[PackingAPI] Applied {len(order_dto.gifts)} gift(s) from promotions")
        except Exception as e:
            logger.warning(f"[PackingAPI] Failed to apply gifts from promotions: {e}")
            debug_print(f"[PackingAPI] Warning: Could not apply gifts: {e}")
            # Continue without gifts if promotion service fails
        
        # Extract shop name from tags
        shop_name = 'Gia Dụng Plus'
        tags = order_dto.tags or []
        MARKETPLACE = {"Shopee", "Lazada", "Tiki", "TikTok", "TikTok Shop", "Sendo"}
        
        # Lấy shop từ tags[1] hoặc tìm tag không phải marketplace
        if len(tags) >= 2 and isinstance(tags[1], str) and tags[1].strip():
            shop_name = tags[1].strip()
        else:
            # Fallback: loại bỏ các tag marketplace, lấy tag còn lại
            for t in tags:
                if isinstance(t, str) and t.strip():
                    tag_clean = t.strip()
                    if 'Gia Dụng Plus' in tag_clean:
                        tag_clean = "Gia Dụng Plus Official"
                    if tag_clean not in MARKETPLACE:
                        shop_name = tag_clean
                        break
        
        # Extract dvvc from shipment.service_name (như sos_shopee)
        dvvc = 'Chưa xác định'
        shipment_weight = None
        if target_fulfillment:
            shipment = target_fulfillment.get('shipment')
            if shipment:
                # Lấy từ service_name (như sos_shopee)
                if shipment.get('service_name'):
                    dvvc = shipment.get('service_name')
                
                # Lấy weight từ shipment
                if shipment.get('weight'):
                    shipment_weight = float(shipment.get('weight', 0)) / 1000.0  # Chuyển từ gram sang kg
        
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
        total_quantity = 0  # Tổng sản phẩm sau quy đổi về đơn chiếc
        for item in order_dto.real_items:
            # Get image from Sapo API
            image_url = get_variant_image(item.variant_id) if item.variant_id else None
            
            # Tính tổng quantity (đã quy đổi về đơn chiếc)
            total_quantity += float(item.quantity) if item.quantity else 0
            
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
        
        debug_print(f"[PackingAPI] Order found: {order_dto.code}, {len(real_items_data)} items, {len(gifts_data)} gifts, total_quantity: {total_quantity}")
        
        return JsonResponse({
            'success': True,
            'order': {
                'id': order_dto.id,
                'code': order_dto.code,
                'customer_name': order_dto.customer_name,
                'customer_phone': order_dto.customer_phone,
                'shipping_address': order_dto.shipping_address_line,
                'shop_name': shop_name,
                'real_items': real_items_data,
                'gifts': gifts_data,
                'notes': order_dto.note or '',
                'total_quantity': total_quantity,  # Tổng sau quy đổi về đơn chiếc
                'total_items': len(real_items_data)  # Số loại sản phẩm (không đếm gifts)
            },
            'dvvc': dvvc,
            'estimated_weight': round(shipment_weight, 2) if shipment_weight else None,
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


@group_required("WarehousePacker", "WarehouseManager")
@require_http_methods(["POST"])
def complete(request):
    """
    POST /kho/orders/packing/complete/
    Body: {"order_id": int, "fulfillment_id": int}
    
    Hoàn tất đóng gói - cập nhật packing_status=4, lưu người gói, thời gian, dvvc.
    """
    from kho.models import WarehousePackingSetting
    
    # Kiểm tra quyền truy cập tính năng packing
    is_allowed, reason = WarehousePackingSetting.is_packing_enabled_for_user(request.user)
    
    if not is_allowed:
        return JsonResponse({
            'success': False,
            'message': f'Bạn không thể sử dụng tính năng này. {reason}'
        }, status=403)
    
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
        
        # Get current user - format: last_name: first_name
        user = request.user
        first_name = user.first_name or ""  # First_name
        last_name = user.last_name or ""  # Last_name
        
        # Format: last_name: first_name (ví dụ: KHO_HN: Đoàn Anh)
        if first_name and first_name.strip() and last_name and last_name.strip():
            nguoi_goi = f"{last_name}: {first_name}".strip()
        elif first_name and first_name.strip():
            # Chỉ có first_name
            nguoi_goi = first_name.strip()
        elif last_name and last_name.strip():
            # Chỉ có last_name
            nguoi_goi = last_name.strip()
        else:
            # Fallback về username
            nguoi_goi = user.username
        
        # Format thời gian gói theo format "%H:%M %d-%m-%Y"
        time_goi = datetime.now().strftime("%H:%M %d-%m-%Y")
        
        # Update packing status to Sapo
        sapo = SapoClient()
        order_service = SapoCoreOrderService()
        
        # Update sẽ tự động lấy dvvc từ shipment nếu chưa có trong note
        success = order_service.update_fulfillment_packing_status(
            order_id=order_id,
            fulfillment_id=fulfillment_id,
            packing_status=4,  # Đã đóng gói
            nguoi_goi=nguoi_goi,
            time_packing=time_goi,
            # dvvc sẽ được lấy tự động từ shipment.service_name nếu chưa có
        )
        
        if success:
            debug_print(f"[PackingAPI] ✓ Packing completed successfully by {nguoi_goi}")
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

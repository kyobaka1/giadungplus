# orders/services/auto_xpress_push.py
"""
Service tự động xử lý đơn hoả tốc:
- Tìm lại shipper cho đơn đã chuẩn bị hàng
- Tự động chuẩn bị hàng cho đơn chưa chuẩn bị (hơn 50 phút)
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Optional

from core.sapo_client import BaseFilter
from core import shopee_client
from core.system_settings import get_connection_ids, HOME_PARAM, KHO_GELEXIMCO, KHO_TOKY
from orders.services.sapo_service import SapoMarketplaceService, SapoCoreOrderService
from orders.services.dto import MarketplaceConfirmOrderDTO

logger = logging.getLogger(__name__)

# Shipping carrier IDs cho đơn hoả tốc
EXPRESS_CARRIER_IDS = "134097,1285481,108346,17426,60176,1283785,1285470,1292451,35696,47741,14895,1272209,176002"

# Connection IDs
connection_ids = get_connection_ids()


def is_express_order(order: Dict[str, Any]) -> bool:
    """
    Kiểm tra xem đơn có phải hoả tốc không.
    
    Args:
        order: Order dict từ Marketplace API
        
    Returns:
        True nếu là đơn hoả tốc
    """
    shipping_carrier = (order.get("shipping_carrier_name") or "").lower()
    return (
        "trong ngày" in shipping_carrier
        or "giao trong ngày" in shipping_carrier
        or "hoả tốc" in shipping_carrier
        or "hoa toc" in shipping_carrier
        or "grab" in shipping_carrier
        or "bedelivery" in shipping_carrier
        or "be delivery" in shipping_carrier
        or "ahamove" in shipping_carrier
        or "instant" in shipping_carrier
    )


def has_tracking_code(order_dto) -> bool:
    """
    Kiểm tra xem đơn đã có tracking code (đã chuẩn bị hàng) chưa.
    
    Args:
        order_dto: OrderDTO instance
        
    Returns:
        True nếu đã có tracking code
    """
    if not order_dto.fulfillments:
        return False
    
    # Lấy fulfillment cuối cùng
    last_fulfillment = order_dto.fulfillments[-1]
    if not last_fulfillment.shipment:
        return False
    
    tracking_code = last_fulfillment.shipment.tracking_code
    return bool(tracking_code and tracking_code.strip())


def find_shipper_for_prepared_order(
    order: Dict[str, Any],
    order_dto,
    shopee_client_instance: shopee_client.ShopeeClient
) -> Dict[str, Any]:
    """
    Tìm lại shipper cho đơn đã chuẩn bị hàng bằng Shopee API.
    
    Args:
        order: Order dict từ Marketplace API
        order_dto: OrderDTO instance
        shopee_client_instance: ShopeeClient instance
        
    Returns:
        Dict với kết quả: {"success": bool, "message": str}
    """
    try:
        channel_order_number = order.get("channel_order_number")
        if not channel_order_number:
            return {"success": False, "message": "Không có channel_order_number"}
        
        # Lấy Shopee order_id từ mã đơn
        try:
            order_info = shopee_client_instance.get_shopee_order_id(channel_order_number)
            shopee_order_id = order_info.get("order_id")
            if not shopee_order_id:
                return {"success": False, "message": "Không tìm thấy Shopee order_id"}
        except Exception as e:
            return {"success": False, "message": f"Không thể lấy Shopee order_id: {str(e)}"}
        
        # Lấy package info
        package_info = shopee_client_instance.get_package_info(shopee_order_id)
        package_list = package_info.get("package_list", [])
        
        if not package_list:
            return {"success": False, "message": "Không có package"}
        
        package_number = package_list[0].get("package_number")
        if not package_number:
            return {"success": False, "message": "Không có package_number"}
        
        # Arrange shipment (tìm lại shipper)
        result = shopee_client_instance.arrange_shipment(
            order_id=shopee_order_id,
            package_number=package_number
        )
        
        return {"success": True, "message": "Đã tìm lại shipper thành công", "result": result}
        
    except Exception as e:
        logger.error(f"Lỗi khi tìm lại shipper cho đơn {order.get('channel_order_number')}: {e}", exc_info=True)
        return {"success": False, "message": f"Lỗi: {str(e)}"}


def prepare_order_via_marketplace(
    order: Dict[str, Any],
    mp_service: SapoMarketplaceService
) -> Dict[str, Any]:
    """
    Chuẩn bị hàng cho đơn chưa chuẩn bị bằng Sapo Marketplace API.
    
    Args:
        order: Order dict từ Marketplace API
        mp_service: SapoMarketplaceService instance
        
    Returns:
        Dict với kết quả: {"success": bool, "message": str}
    """
    try:
        mp_order_id = order.get("id")
        if not mp_order_id:
            return {"success": False, "message": "Không có marketplace order ID"}
        
        # Init confirm để lấy pickup time slots
        init_result = mp_service.init_confirm([mp_order_id])
        
        # Parse init_result để lấy thông tin cần thiết
        data_root = init_result.get("data", {}) if isinstance(init_result, dict) else {}
        init_success_shopee = data_root.get("init_success", {}).get("shopee") or []
        
        if not init_success_shopee:
            return {"success": False, "message": "Không thể init confirm (đơn có thể đã được xử lý)"}
        
        # Lấy thông tin từ init_success
        shop_block = init_success_shopee[0]
        connection_id = shop_block["connection_id"]
        
        logistic = shop_block.get("logistic") or {}
        address_list = logistic.get("address_list") or []
        address_id = 0
        if address_list:
            addr_obj = address_list[0]
            address_id = int(addr_obj.get("address_id", 0) or 0)
        
        # Tìm order trong init_confirms
        init_confirms = shop_block.get("init_confirms", [])
        if not init_confirms:
            return {"success": False, "message": "Không tìm thấy order trong init_confirms"}
        
        item = init_confirms[0]
        pickup_time_id = None
        models = item.get("pick_up_shopee_models") or []
        if models and models[0].get("time_slot_list"):
            pickup_time_id = models[0]["time_slot_list"][0]["pickup_time_id"]
        
        if not pickup_time_id:
            return {"success": False, "message": "Không có pickup_time_id"}
        
        # Build confirm payload
        confirm_item = MarketplaceConfirmOrderDTO(
            connection_id=connection_id,
            order_id=mp_order_id,
            pickup_time_id=pickup_time_id,
            pick_up_type=1,  # Hoả tốc luôn dùng pickup
            address_id=address_id or 0,
        )
        
        # Confirm order
        confirm_result = mp_service.confirm_orders([confirm_item])
        
        # Kiểm tra kết quả
        if isinstance(confirm_result, dict):
            data = confirm_result.get("data", {})
            list_error = data.get("list_error", [])
            if list_error:
                error_msg = list_error[0].get("order_list", [{}])[0].get("error", "Unknown error")
                return {"success": False, "message": f"Confirm thất bại: {error_msg}"}
        
        return {"success": True, "message": "Đã chuẩn bị hàng thành công", "result": confirm_result}
        
    except Exception as e:
        logger.error(f"Lỗi khi chuẩn bị hàng cho đơn {order.get('channel_order_number')}: {e}", exc_info=True)
        return {"success": False, "message": f"Lỗi: {str(e)}"}


def auto_process_express_orders(limit: int = 250) -> Dict[str, Any]:
    """
    Tự động xử lý đơn hoả tốc:
    - Tìm lại shipper cho đơn đã chuẩn bị hàng
    - Chuẩn bị hàng cho đơn chưa chuẩn bị (hơn 50 phút)
    
    Args:
        limit: Số đơn tối đa xử lý mỗi lần
        
    Returns:
        Dict với kết quả tổng hợp
    """
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    now_vn = datetime.now(tz_vn)
    
    # Xử lý cho cả 2 location (HN và HCM) - bỏ qua filter location_id
    location_id = None  # None = xử lý tất cả location
    
    logger.info(f"[AUTO_XPRESS] Bắt đầu xử lý đơn hoả tốc (limit={limit})...")
    
    # Service layer
    mp_service = SapoMarketplaceService()
    core_service = SapoCoreOrderService()
    
    # Lấy danh sách đơn hoả tốc từ Marketplace
    mp_filter = BaseFilter(params={
        "connectionIds": connection_ids,
        "page": 1,
        "limit": limit,
        "channelOrderStatus": "PROCESSED,READY_TO_SHIP,RETRY_SHIP",
        "shippingCarrierIds": EXPRESS_CARRIER_IDS,
        "sortBy": "ISSUED_AT",
        "orderBy": "desc",
    })
    
    mp_resp = mp_service.list_orders(mp_filter)
    mp_orders = mp_resp.get("orders", [])
    
    if not mp_orders:
        summary = {
            "total": 0,
            "prepared": 0,
            "unprepared": 0,
            "skipped": 0,
            "find_shipper_success": 0,
            "find_shipper_failed": 0,
            "prepare_success": 0,
            "prepare_failed": 0,
        }
        logger.info(f"[AUTO_XPRESS] Hoàn tất:\n  - Tổng đơn: {summary['total']}\n  - Đã chuẩn bị: {summary['prepared']}\n  - Chưa chuẩn bị: {summary['unprepared']}\n  - Bị bỏ qua: {summary['skipped']}\n  - Tìm lại shipper: ✅ {summary['find_shipper_success']} | ❌ {summary['find_shipper_failed']}\n  - Chuẩn bị hàng: ✅ {summary['prepare_success']} | ❌ {summary['prepare_failed']}")
        return summary
    
    # Phân loại đơn
    prepared_orders = []  # Đã chuẩn bị hàng (có tracking code)
    unprepared_orders = []  # Chưa chuẩn bị hàng
    skipped_orders = []  # Đơn bị bỏ qua (lỗi, filter, etc.)
    
    for order in mp_orders:
        channel_order_number = order.get("channel_order_number", "N/A")
        
        # Lọc theo location_id nếu có
        sapo_order_id = order.get("sapo_order_id")
        if not sapo_order_id:
            skipped_orders.append((order, "Không có sapo_order_id"))
            continue
        
        try:
            order_dto = core_service.get_order_dto(sapo_order_id)
            
            # Bỏ qua filter location_id - xử lý cho cả 2 location (HN và HCM)
            
            # Kiểm tra đã chuẩn bị hàng chưa
            if has_tracking_code(order_dto):
                prepared_orders.append((order, order_dto))
            else:
                # Đơn chưa có tracking code - cần kiểm tra thời gian để chuẩn bị
                should_prepare = False
                skip_reason = None
                
                if order_dto.created_on:
                    try:
                        created_dt = datetime.fromisoformat(
                            order_dto.created_on.replace('Z', '+00:00')
                        )
                        if created_dt.tzinfo is None:
                            created_dt = created_dt.replace(tzinfo=tz_vn)
                        if created_dt.tzinfo != tz_vn:
                            created_dt = created_dt.astimezone(tz_vn)
                        
                        # Tính thời gian chênh lệch
                        time_diff = now_vn - created_dt
                        minutes_diff = time_diff.total_seconds() / 60
                        
                        # Nếu hơn 50 phút thì thêm vào danh sách chuẩn bị
                        if time_diff.total_seconds() > 50 * 60:  # 50 phút
                            should_prepare = True
                        else:
                            skip_reason = f"Chưa đủ 50 phút ({minutes_diff:.1f} phút)"
                            
                    except (ValueError, AttributeError) as e:
                        # Nếu không parse được thời gian, vẫn thêm vào danh sách chuẩn bị để xử lý
                        # Vì đơn chưa có tracking code nên cần chuẩn bị
                        should_prepare = True
                else:
                    # Không có created_on, nhưng đơn chưa có tracking code nên vẫn cần chuẩn bị
                    should_prepare = True
                
                if should_prepare:
                    unprepared_orders.append((order, order_dto))
                elif skip_reason:
                    skipped_orders.append((order, skip_reason))
                        
        except Exception as e:
            error_msg = f"Lỗi khi xử lý: {str(e)}"
            skipped_orders.append((order, error_msg))
            logger.error(f"[AUTO_XPRESS] Lỗi khi xử lý đơn {channel_order_number}: {e}", exc_info=True)
            continue
    
    # Xử lý đơn đã chuẩn bị: Tìm lại shipper
    find_shipper_success = 0
    find_shipper_failed = 0
    
    for order, order_dto in prepared_orders:
        try:
            connection_id = order.get("connection_id")
            if not connection_id:
                continue
            
            # Tạo ShopeeClient với connection_id
            client = shopee_client.ShopeeClient(connection_id)
            
            result = find_shipper_for_prepared_order(order, order_dto, client)
            
            if result["success"]:
                find_shipper_success += 1
            else:
                find_shipper_failed += 1
                logger.error(f"[AUTO_XPRESS] Tìm lại shipper thất bại cho đơn {order.get('channel_order_number')}: {result['message']}")
            
            # Delay giữa các request
            import time
            time.sleep(2)
            
        except Exception as e:
            find_shipper_failed += 1
            logger.error(f"[AUTO_XPRESS] Lỗi khi tìm lại shipper cho đơn {order.get('channel_order_number', 'N/A')}: {e}", exc_info=True)
    
    # Xử lý đơn chưa chuẩn bị: Chuẩn bị hàng
    prepare_success = 0
    prepare_failed = 0
    
    for order, order_dto in unprepared_orders:
        try:
            result = prepare_order_via_marketplace(order, mp_service)
            
            if result["success"]:
                prepare_success += 1
            else:
                prepare_failed += 1
                logger.error(f"[AUTO_XPRESS] Chuẩn bị hàng thất bại cho đơn {order.get('channel_order_number')}: {result['message']}")
            
            # Delay giữa các request
            import time
            time.sleep(2)
            
        except Exception as e:
            prepare_failed += 1
            logger.error(f"[AUTO_XPRESS] Lỗi khi chuẩn bị hàng cho đơn {order.get('channel_order_number', 'N/A')}: {e}", exc_info=True)
    
    summary = {
        "total": len(mp_orders),
        "prepared": len(prepared_orders),
        "unprepared": len(unprepared_orders),
        "skipped": len(skipped_orders),
        "find_shipper_success": find_shipper_success,
        "find_shipper_failed": find_shipper_failed,
        "prepare_success": prepare_success,
        "prepare_failed": prepare_failed,
    }
    
    logger.info(f"[AUTO_XPRESS] Hoàn tất:\n  - Tổng đơn: {summary['total']}\n  - Đã chuẩn bị: {summary['prepared']}\n  - Chưa chuẩn bị: {summary['unprepared']}\n  - Bị bỏ qua: {summary['skipped']}\n  - Tìm lại shipper: ✅ {summary['find_shipper_success']} | ❌ {summary['find_shipper_failed']}\n  - Chuẩn bị hàng: ✅ {summary['prepare_success']} | ❌ {summary['prepare_failed']}")
    return summary

"""
Service để xử lý Ticket - tìm order, tạo ticket, etc.
"""
import logging
from typing import Optional, Dict, Any, List

from orders.services.sapo_service import SapoCoreOrderService
from orders.services.dto import OrderDTO
from core.sapo_client import BaseFilter, get_sapo_client
from core.sapo_client.client import debug_print

logger = logging.getLogger(__name__)


class TicketService:
    """
    Service để xử lý ticket operations
    """
    
    def __init__(self):
        self.order_service = SapoCoreOrderService()
    
    def find_order(self, search_key: str) -> Optional[OrderDTO]:
        """
        Tìm order theo SON code hoặc reference_number (mã Shopee)
        
        Args:
            search_key: SON code (vd: SON613795) hoặc reference_number (vd: 251126R6362H4R)
            
        Returns:
            OrderDTO hoặc None nếu không tìm thấy
        """
        logger.info(f"[TicketService] find_order() start, search_key='{search_key}'")
        debug_print("[TicketService.find_order] start", {"search_key": search_key})
        
        # Thử tìm theo reference_number trước (mã Shopee)
        try:
            order = self.order_service.get_order_dto_from_shopee_sn(search_key)
            if order:
                logger.info(
                    "[TicketService] find_order() matched by reference_number: "
                    f"search_key='{search_key}', order_id={order.id}, code='{order.code}'"
                )
                debug_print(
                    "[TicketService.find_order] matched by reference_number",
                    {"search_key": search_key, "order_id": order.id, "code": order.code},
                )
                return order
            else:
                logger.debug(
                    "[TicketService] find_order() no result from get_order_dto_from_shopee_sn "
                    f"for key='{search_key}'"
                )
        except Exception as e:
            logger.debug(f"[TicketService] find_order() not found by reference: {e}")
            debug_print("[TicketService.find_order] not found by reference", {"error": str(e)})
        
        # Thử tìm theo SON code (query trong list_orders)
        try:
            flt = BaseFilter(params={'query': search_key, 'limit': 1, 'page': 1})
            logger.debug(
                "[TicketService] find_order() calling list_orders with params="
                f"{flt.to_params()}"
            )
            debug_print(
                "[TicketService.find_order] calling list_orders",
                {"params": flt.to_params()},
            )
            result = self.order_service.list_orders(flt)
            orders_data = result.get('orders', []) or []
            logger.debug(
                "[TicketService] find_order() list_orders returned "
                f"{len(orders_data)} orders for key='{search_key}'"
            )
            debug_print(
                "[TicketService.find_order] list_orders returned",
                {"count": len(orders_data), "search_key": search_key},
            )
            if orders_data:
                # Build OrderDTO từ raw data - payload format: {'order': {...}}
                from orders.services.order_builder import build_order_from_sapo
                sapo_client = get_sapo_client()
                order = build_order_from_sapo({'order': orders_data[0]}, sapo_client=sapo_client)
                logger.info(
                    "[TicketService] find_order() matched by SON/query: "
                    f"search_key='{search_key}', order_id={order.id}, code='{order.code}'"
                )
                debug_print(
                    "[TicketService.find_order] matched by SON/query",
                    {"search_key": search_key, "order_id": order.id, "code": order.code},
                )
                return order
        except Exception as e:
            logger.debug(f"[TicketService] find_order() not found by code/query: {e}")
            debug_print("[TicketService.find_order] not found by code/query", {"error": str(e)})
        
        logger.warning(f"[TicketService] find_order() order not found for key='{search_key}'")
        debug_print("[TicketService.find_order] order NOT FOUND", {"search_key": search_key})
        return None

    def search_orders_for_ticket(self, search_key: str, limit: int = 10) -> List[OrderDTO]:
        """
        Tìm danh sách orders phục vụ cho màn tạo ticket:
        - Tìm theo reference_number (mã Shopee) nếu khớp chính xác
        - Sau đó tìm theo SON / query trong list_orders (giới hạn số lượng)
        """
        from orders.services.order_builder import build_order_from_sapo

        logger.info(f"[TicketService] search_orders_for_ticket() start, search_key='{search_key}', limit={limit}")
        debug_print(
            "[TicketService.search_orders_for_ticket] start",
            {"search_key": search_key, "limit": limit},
        )
        results: List[OrderDTO] = []
        seen_ids = set()

        # 1. Thử tìm theo reference_number (mã Shopee) – thường chỉ ra 1 đơn
        try:
            order = self.order_service.get_order_dto_from_shopee_sn(search_key)
            if order and order.id not in seen_ids:
                results.append(order)
                seen_ids.add(order.id)
                logger.info(
                    "[TicketService] search_orders_for_ticket() matched by reference_number: "
                    f"search_key='{search_key}', order_id={order.id}, code='{order.code}'"
                )
                debug_print(
                    "[TicketService.search_orders_for_ticket] matched by reference_number",
                    {"search_key": search_key, "order_id": order.id, "code": order.code},
                )
        except Exception as e:
            logger.debug(f"[TicketService] search_orders_for_ticket() not found by reference: {e}")
            debug_print(
                "[TicketService.search_orders_for_ticket] not found by reference",
                {"error": str(e)},
            )

        # 2. Tìm theo SON / query trong list_orders
        try:
            flt = BaseFilter(params={'query': search_key, 'limit': limit, 'page': 1})
            logger.debug(
                "[TicketService] search_orders_for_ticket() calling list_orders with params="
                f"{flt.to_params()}"
            )
            debug_print(
                "[TicketService.search_orders_for_ticket] calling list_orders",
                {"params": flt.to_params()},
            )
            raw = self.order_service.list_orders(flt)
            orders_data = raw.get('orders', []) or []
            logger.debug(
                "[TicketService] search_orders_for_ticket() list_orders returned "
                f"{len(orders_data)} orders for key='{search_key}'"
            )
            debug_print(
                "[TicketService.search_orders_for_ticket] list_orders returned",
                {"count": len(orders_data), "search_key": search_key},
            )

            if orders_data:
                sapo_client = get_sapo_client()
                for od in orders_data:
                    try:
                        dto = build_order_from_sapo({'order': od}, sapo_client=sapo_client)
                        if dto.id not in seen_ids:
                            results.append(dto)
                            seen_ids.add(dto.id)
                            logger.info(
                                "[TicketService] search_orders_for_ticket() matched by SON/query: "
                                f"search_key='{search_key}', order_id={dto.id}, code='{dto.code}'"
                            )
                            debug_print(
                                "[TicketService.search_orders_for_ticket] matched by SON/query",
                                {"search_key": search_key, "order_id": dto.id, "code": dto.code},
                            )
                    except Exception as e:
                        logger.debug(
                            "[TicketService] search_orders_for_ticket() error building DTO "
                            f"for key='{search_key}': {e}"
                        )
                        debug_print(
                            "[TicketService.search_orders_for_ticket] error building DTO",
                            {"error": str(e)},
                        )
        except Exception as e:
            logger.debug(f"[TicketService] search_orders_for_ticket() error in list_orders: {e}")
            debug_print(
                "[TicketService.search_orders_for_ticket] error in list_orders",
                {"error": str(e)},
            )

        return results
    
    def extract_order_info(self, order: OrderDTO) -> Dict[str, Any]:
        """
        Extract thông tin từ OrderDTO để lưu vào Ticket
        
        Returns:
            Dict với các fields cần thiết cho Ticket
        """
        # Xác định kho hàng từ location_id
        warehouse = ''
        if order.location_id == 241737:
            warehouse = 'Kho GELE (HN)'
        elif order.location_id == 548744:
            warehouse = 'Kho TOKY (HCM)'
        else:
            warehouse = f'Kho {order.location_id}'
        
        # Lấy địa chỉ khách hàng
        customer_address = ''
        if order.shipping_address:
            addr = order.shipping_address
            parts = []
            if addr.ward:
                parts.append(addr.ward)
            if addr.district:
                parts.append(addr.district)
            if addr.city:
                parts.append(addr.city)
            if addr.address1:
                parts.append(addr.address1)
            customer_address = ', '.join(parts)

        # Lấy username & email khách hàng (push từ kho)
        customer_username = None
        customer_email = None
        if order.customer:
            # Username Shopee được map trong CustomerDTO.username (website field)
            customer_username = getattr(order.customer, "username", None)
            customer_email = order.customer.email or None
        # Nếu không có email ở customer thì fallback về email trên order/shipping address
        if not customer_email:
            if order.email:
                customer_email = order.email
            elif order.shipping_address and order.shipping_address.email:
                customer_email = order.shipping_address.email
        
        # Format trạng thái đơn hàng
        order_status = order.status or 'unknown'
        order_status_label = {
            'finalized': 'Đã xác nhận',
            'completed': 'Hoàn thành',
            'cancelled': 'Đã hủy',
            'draft': 'Nháp',
        }.get(order_status, order_status)
        
        # Format trạng thái giao hàng
        fulfillment_status = order.fulfillment_status or 'unshipped'
        fulfillment_status_label = {
            'shipped': 'Đã giao hàng',
            'unshipped': 'Chưa giao hàng',
            'partial': 'Giao một phần',
        }.get(fulfillment_status, fulfillment_status)
        
        packed_status = order.packed_status or 'unpacked'
        packed_status_label = {
            'packed': 'Đã đóng gói',
            'unpacked': 'Chưa đóng gói',
            'partial': 'Đóng gói một phần',
        }.get(packed_status, packed_status)
        
        # Lấy phí ship (freight_amount) từ shipment trong fulfillments (nếu có)
        freight_amount = 0.0
        try:
            if order.fulfillments:
                for f in order.fulfillments:
                    if getattr(f, "shipment", None) and getattr(f.shipment, "freight_amount", None):
                        freight_amount = float(f.shipment.freight_amount or 0)
                        break
        except Exception:
            freight_amount = 0.0

        # Nguồn đơn hàng: ưu tiên tên nguồn từ source_id (OrderDTO.source_name)
        channel_display = ""
        try:
            channel_display = (order.source_name or "").strip()
        except Exception:
            channel_display = ""
        if not channel_display:
            channel_display = order.channel or ""

        return {
            'order_id': order.id,
            'order_code': order.code,
            'reference_number': order.reference_number or '',
            'customer_id': order.customer_id,
            'customer_name': order.customer.name if order.customer else '',
            'customer_phone': order.phone_number or '',
            'customer_username': customer_username or '',
            'customer_email': customer_email or '',
            'customer_address': customer_address,
            'location_id': order.location_id,
            'warehouse': warehouse,
            'shop': order.shop_name or order.channel or '',  # Ưu tiên shop_name từ tags, fallback về channel
            # "Nguồn" hiển thị trên UI – lấy từ source_id (source_name) nếu có, fallback về channel gốc
            'channel': channel_display,
            'order_status': order_status,
            'order_status_label': order_status_label,
            'fulfillment_status': fulfillment_status,
            'fulfillment_status_label': fulfillment_status_label,
            'packed_status': packed_status,
            'packed_status_label': packed_status_label,
            'freight_amount': freight_amount,
        }


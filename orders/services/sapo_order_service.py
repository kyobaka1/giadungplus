# orders/services/sapo_order_service.py
"""
Sapo Order Service - Business logic layer cho orders từ Sapo.
Convert raw JSON responses sang OrderDTO.
"""

from typing import List, Dict, Any, Optional
import logging

from core.sapo_client.client import SapoClient
from .dto import OrderDTO
from .order_builder import OrderDTOFactory

logger = logging.getLogger(__name__)


class SapoOrderService:
    """
    Service layer để làm việc với Sapo orders.
    
    Chức năng:
    - Lấy orders từ Sapo Core/Marketplace API
    - Convert raw JSON → OrderDTO
    - Business logic xử lý orders
    
    Usage:
        sapo = SapoClient()
        service = SapoOrderService(sapo)
        
        # Get orders
        orders = service.list_orders(location_id=241737, limit=50)
        
        # Get single order
        order = service.get_order(order_id=123456)
        
        # Each order is OrderDTO with Pydantic validation
        for order in orders:
            print(order.code, order.customer_name)
            # Convert back to JSON if needed
            json_data = order.to_dict()
    """
    
    def __init__(self, sapo_client: SapoClient):
        """
        Args:
            sapo_client: SapoClient instance
        """
        self.sapo = sapo_client
        self.factory = OrderDTOFactory()
    
    def get_order(self, order_id: int) -> OrderDTO:
        """
        Lấy 1 order theo ID từ Sapo Core API.
        
        Args:
            order_id: Sapo order ID
            
        Returns:
            OrderDTO instance
        """
        logger.debug(f"[SapoOrderService] Getting order: {order_id}")
        
        raw = self.sapo.core.get_order_raw(order_id)
        order_data = raw.get("order", {})
        
        return self.factory.from_sapo_json(order_data)
    
    def get_order_by_reference(self, reference_number: str) -> Optional[OrderDTO]:
        """
        Tìm order theo reference_number (mã đơn sàn TMĐT).
        
        Args:
            reference_number: Mã đơn từ sàn (vd: 25112099T2CASS)
            
        Returns:
            OrderDTO hoặc None nếu không tìm thấy
        """
        logger.debug(f"[SapoOrderService] Finding order by reference: {reference_number}")
        
        raw_order = self.sapo.core.get_order_by_reference_number(reference_number)
        
        if not raw_order:
            logger.warning(f"[SapoOrderService] Order not found: {reference_number}")
            return None
        
        return self.factory.from_sapo_json(raw_order)
    
    def list_orders(self, **filters) -> List[OrderDTO]:
        """
        Lấy danh sách orders từ Sapo Core API.
        
        Args:
            **filters:
                - page: int
                - limit: int
                - location_id: int
                - status: str
                - created_on_min, created_on_max: str (ISO datetime)
                - etc.
                
        Returns:
            List of OrderDTO
        """
        logger.debug(f"[SapoOrderService] Listing orders with filters: {filters}")
        
        raw = self.sapo.core.list_orders_raw(**filters)
        orders_data = raw.get("orders", [])
        
        orders = [self.factory.from_sapo_json(o) for o in orders_data]
        
        logger.info(f"[SapoOrderService] Retrieved {len(orders)} orders")
        return orders
    
    def list_marketplace_orders(
        self,
        connection_ids: str,
        account_id: int,
        **filters
    ) -> List[Dict[str, Any]]:
        """
        Lấy danh sách orders từ Sapo Marketplace API.
        
        Note: Marketplace orders có structure khác một chút so với Core orders.
        Trả về raw dict thay vì OrderDTO vì cần thêm mapping logic.
        
        Args:
            connection_ids: Comma-separated connection IDs
            account_id: Sapo account ID
            **filters: page, limit, statuses, etc.
            
        Returns:
            List of raw marketplace order dicts
        """
        logger.debug(f"[SapoOrderService] Listing marketplace orders: {connection_ids}")
        
        raw = self.sapo.marketplace.list_orders_raw(
            connection_ids=connection_ids,
            account_id=account_id,
            **filters
        )
        
        orders = raw.get("data", [])
        logger.info(f"[SapoOrderService] Retrieved {len(orders)} marketplace orders")
        
        return orders
    
    def confirm_marketplace_orders(
        self,
        order_ids: List[int],
        account_id: int
    ) -> Dict[str, Any]:
        """
        Confirm orders trên Marketplace (tìm ship/chuẩn bị hàng).
        
        Workflow:
        1. Init confirm → get pickup time slots
        2. Build confirm payload
        3. Confirm orders
        
        Args:
            order_ids: List của marketplace order IDs
            account_id: Sapo account ID
            
        Returns:
            Confirm response
        """
        logger.info(f"[SapoOrderService] Confirming {len(order_ids)} marketplace orders")
        
        # Step 1: Init confirm
        init_result = self.sapo.marketplace.init_confirm_raw(
            order_ids=order_ids,
            account_id=account_id
        )
        
        # Step 2: Build payload từ init result
        # TODO: Implement payload building logic
        # Hiện tại return init result để caller xử lý
        
        return init_result

    def update_customer_info(self, customer_id: int, name: str, address: str = None) -> bool:
        """
        Update thông tin khách hàng trên Sapo.
        
        Args:
            customer_id: Sapo customer ID
            name: Tên khách hàng mới
            address: Địa chỉ mới (optional)
            
        Returns:
            True nếu thành công, False nếu thất bại
        """
        try:
            data = {"name": name}
            # Note: Address update logic can be complex due to Sapo structure (addresses array)
            # For now, we focus on name as per requirement. 
            # If address update is needed, we need to find the correct address ID or add new.
            
            self.sapo.core.update_customer(customer_id, data)
            logger.info(f"[SapoOrderService] Updated customer {customer_id} name to {name}")
            return True
        except Exception as e:
            logger.error(f"[SapoOrderService] Failed to update customer {customer_id}: {e}")
            return False

    def update_packing_status(self, order_id: int, packing_info: Dict[str, Any]) -> bool:
        """
        Update trạng thái đóng gói vào shipment note.
        
        Args:
            order_id: Sapo order ID
            packing_info: Dict chứa thông tin đóng gói (pks, human, tgoi, etc.)
            
        Returns:
            True nếu thành công
        """
        try:
            # 1. Find fulfillment (shipment) for this order
            fulfillments_raw = self.sapo.core.list_fulfillments_raw(
                query=str(order_id),
                delivery_types="courier",
                limit=1
            )
            
            fulfillments = fulfillments_raw.get("fulfillments", [])
            if not fulfillments:
                logger.warning(f"[SapoOrderService] No fulfillment found for order {order_id}")
                return False
                
            fulfillment = fulfillments[0]
            shipment = fulfillment.get("shipment")
            
            if not shipment:
                logger.warning(f"[SapoOrderService] No shipment in fulfillment {fulfillment['id']}")
                return False
            
            # 2. Merge with existing note if any
            import json
            current_note = shipment.get("note")
            note_data = {}
            
            if current_note and "{" in current_note:
                try:
                    note_data = json.loads(current_note)
                except json.JSONDecodeError:
                    pass
            
            # 3. Update data
            note_data.update(packing_info)
            
            # 4. Save back
            new_note = json.dumps(note_data)
            self.sapo.core.update_shipment(shipment["id"], new_note)
            
            logger.info(f"[SapoOrderService] Updated packing status for order {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"[SapoOrderService] Failed to update packing status for order {order_id}: {e}")
            return False

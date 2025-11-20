# core/sapo_client/repositories/marketplace_repository.py
"""
Repository cho Sapo Marketplace API (https://market-place.sapoapps.vn/v2).
Handles orders từ các sàn TMĐT, confirm orders (tìm ship/chuẩn bị hàng).
"""

from typing import Dict, Any, List
import logging

from core.base.repository import BaseRepository

logger = logging.getLogger(__name__)


class SapoMarketplaceRepository(BaseRepository):
    """
    Repository cho Sapo Marketplace API.
    Base URL: https://market-place.sapoapps.vn
    
    Endpoints:
    - /v2/orders - List orders from marketplace
    - /v2/orders/confirm/init - Init confirm (get pickup time slots)
    - /v2/orders/confirm - Confirm orders (arrange shipment)
    """
    
    def list_orders_raw(
        self, 
        connection_ids: str,
        account_id: int,
        **filters
    ) -> Dict[str, Any]:
        """
        Lấy danh sách orders từ Marketplace.
        
        Args:
            connection_ids: Comma-separated connection IDs (vd: "10925,155174")
            account_id: Sapo account ID (vd: 319911)
            **filters:
                - page: int
                - limit: int
                - statuses: str (comma-separated)
                - created_on_min, created_on_max
                - etc.
                
        Returns:
            {
                "data": [...],
                "metadata": {...}
            }
        """
        params = {
            "connectionIds": connection_ids,
            "accountId": account_id,
            **filters
        }
        
        logger.debug(f"[SapoMarketplaceRepo] list_orders with params: {params}")
        return self.get("v2/orders", params=params)
    
    def init_confirm_raw(
        self,
        order_ids: List[int],
        account_id: int
    ) -> Dict[str, Any]:
        """
        Init confirm - lấy pickup time slots trước khi confirm.
        
        GET /v2/orders/confirm/init?accountId=...&ids=1,2,3
        
        Args:
            order_ids: List marketplace order IDs
            account_id: Sapo account ID
            
        Returns:
            {
                "data": [
                    {
                        "order_id": 123,
                        "time_slot_list": [...],
                        "address_options": [...],
                        ...
                    },
                    ...
                ]
            }
        """
        ids_str = ",".join(str(i) for i in order_ids)
        params = {
            "accountId": account_id,
            "ids": ids_str
        }
        
        logger.info(f"[SapoMarketplaceRepo] init_confirm: {len(order_ids)} orders")
        logger.debug(f"Order IDs: {ids_str}")
        
        return self.get("v2/orders/confirm/init", params=params)
    
    def confirm_orders_raw(
        self,
        confirm_payload: List[Dict[str, Any]],
        account_id: int
    ) -> Dict[str, Any]:
        """
        Confirm orders - tìm ship / chuẩn bị hàng.
        
        PUT /v2/orders/confirm?accountId=...
        
        Payload format:
        [
          {
            "connection_id": 134366,
            "order_models": [
              {"order_id": 803738354, "pickup_time_id": "1763456400"}
            ],
            "shopee_logistic": {
              "pick_up_type": 1,
              "address_id": 200033410
            }
          },
          ...
        ]
        
        Args:
            confirm_payload: List của confirm requests (1 item per shop)
            account_id: Sapo account ID
            
        Returns:
            {
                "data": {...},
                "message": "..."
            }
        """
        params = {"accountId": account_id}
        payload = {"confirm_order_request_model": confirm_payload}
        
        logger.info(f"[SapoMarketplaceRepo] confirm_orders: {len(confirm_payload)} shops")
        logger.debug(f"Payload: {payload}")
        
        return self.put("v2/orders/confirm", params=params, json=payload)

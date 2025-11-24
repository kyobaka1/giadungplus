# core/shopee_client/repository.py
"""
Shopee KNB API Repository.
"""

from typing import Dict, Any
import logging

from core.base.repository import BaseRepository

logger = logging.getLogger(__name__)


class ShopeeRepository(BaseRepository):
    """
    Repository cho Shopee KNB API.
    Base URL: https://banhang.shopee.vn/api/v3
    
    Endpoints:
    - /order/get_order_list_search_bar_hint - Tìm order_id từ mã đơn
    - /order/get_package - Lấy package/shipment info
    - /shipment/get_pickup - Lấy pickup address
    - /shipment/get_pickup_time_slots - Lấy pickup time slots
    - /shipment/update_shipment_group_info - Arrange shipment (tìm ship)
    """
    
    def search_order_raw(self, order_sn: str) -> Dict[str, Any]:
        """
        Tìm Shopee order_id từ mã đơn (order_sn).
        
        Args:
            order_sn: Mã đơn Shopee (vd: 25112099T2CASS)
            
        Returns:
            {
                "data": {
                    "order_sn_result": {
                        "list": [
                            {"order_id": 123, "order_sn": "..."},
                            ...
                        ]
                    }
                }
            }
        """
        logger.debug(f"[ShopeeRepo] Searching order: {order_sn}")
        
        return self.get("order/get_order_list_search_bar_hint", params={
            "keyword": order_sn,
            "category": 1,
            "order_list_tab": 100
        })
    
    def get_package_raw(self, order_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin package/shipment của đơn.
        
        Args:
            order_id: Shopee order ID
            
        Returns:
            {
                "data": {
                    "order_info": {
                        "order_id": 123,
                        "package_list": [...],
                        ...
                    }
                }
            }
        """
        logger.debug(f"[ShopeeRepo] Getting package for order: {order_id}")
        
        return self.get("order/get_package", params={
            "order_id": order_id
        })
    
    def get_pickup_raw(self, order_id: int, package_number: str) -> Dict[str, Any]:
        """
        Lấy thông tin pickup address.
        
        Args:
            order_id: Shopee order ID
            package_number: Package number
            
        Returns:
            {
                "data": {
                    "pickup_address_id": 123,
                    "channel_id": 456,
                    ...
                }
            }
        """
        logger.debug(f"[ShopeeRepo] Getting pickup for order {order_id}, package {package_number}")
        
        return self.get("shipment/get_pickup", params={
            "SPC_CDS": "c9accf1d-0cc4-42c0-86d6-20b726cadd4a",
            "SPC_CDS_VER": "2",
            "order_id": order_id,
            "package_number": package_number
        })
    
    def get_pickup_time_slots_raw(
        self,
        order_ids: str,
        address_id: int,
        channel_id: int
    ) -> Dict[str, Any]:
        """
        Lấy các khung giờ pickup khả dụng.
        
        Args:
            order_ids: Comma-separated order IDs
            address_id: Pickup address ID
            channel_id: Channel ID
            
        Returns:
            {
                "data": {
                    "time_slots": [
                        {"id": 1, "value": "...", "title": "..."},
                        ...
                    ]
                }
            }
        """
        logger.debug(f"[ShopeeRepo] Getting pickup time slots for orders: {order_ids}")
        
        return self.get("shipment/get_pickup_time_slots", params={
            "SPC_CDS": "c9accf1d-0cc4-42c0-86d6-20b726cadd4a",
            "SPC_CDS_VER": "2",
            "order_ids": order_ids,
            "address_id": address_id,
            "channel_id": channel_id
        })
    
    def arrange_shipment_raw(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Arrange shipment - tìm ship / chuẩn bị hàng.
        
        Payload format:
        {
            "remark": "",
            "pickup_time": "...",
            "pickup_address_id": 123,
            "seller_real_name": "",
            "shipping_mode": "pickup",
            "group_info": {
                "group_shipment_id": 0,
                "primary_package_number": "...",
                "package_list": [
                    {"order_id": 123, "package_number": "..."},
                    ...
                ]
            }
        }
        
        Args:
            payload: Dict theo format trên
            
        Returns:
            Response from Shopee
        """
        logger.info(f"[ShopeeRepo] Arranging shipment for {len(payload.get('group_info', {}).get('package_list', []))} packages")
        
        return self.post("shipment/update_shipment_group_info", params={
            "SPC_CDS": "06614307-0c48-4f4f-829f-98b6da1345c2",
            "SPC_CDS_VER": "2"
        }, json=payload)
    
    def get_order_receipt_settings_batch_raw(self, order_ids: list[int]) -> Dict[str, Any]:
        """
        Lấy email và thông tin hóa đơn của khách hàng từ Shopee KNB.
        
        Args:
            order_ids: List of Shopee order IDs
            
        Returns:
            {
                "data": {
                    "order_receipt_settings": [
                        {
                            "order_id": 123,
                            "receipt_settings": {
                                "personal": {
                                    "email": "customer@example.com",
                                    "name": "******",
                                    "address": {"address": "******"}
                                }
                            }
                        }
                    ]
                },
                "code": 0
            }
            
        Note:
            Endpoint: POST /api/v4/invoice/seller/get_order_receipt_settings_batch
            Base URL khác với v3, cần override trong method này.
        """
        logger.debug(f"[ShopeeRepo] Getting receipt settings for orders: {order_ids}")
        
        # API v4 có base URL khác
        url = "https://banhang.shopee.vn/api/v4/invoice/seller/get_order_receipt_settings_batch"
        
        # Build queries payload
        queries = [{"order_id": order_id} for order_id in order_ids]
        payload = {"queries": queries}
        
        # Make request với params SPC_CDS
        response = self.session.post(
            url,
            params={
                "SPC_CDS": "a4ef0c3a-4b1a-4920-a8bf-4fccf56c8808",
                "SPC_CDS_VER": "2"
            },
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        try:
            return response.json()
        except ValueError:
            logger.warning(f"Response is not JSON: {response.text[:200]}")
            return {}
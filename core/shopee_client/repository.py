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
        
        # Timeout ngắn hơn (15s) và chỉ retry 1 lần để tăng tốc xử lý
        return self.get("order/get_order_list_search_bar_hint", params={
            "keyword": order_sn,
            "category": 1,
            "order_list_tab": 100
        }, timeout=15, retry=1)
    
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
        
        # Timeout ngắn hơn (15s) và chỉ retry 1 lần để tăng tốc xử lý
        return self.get("order/get_package", params={
            "order_id": order_id
        }, timeout=15, retry=1)
    
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
        # Timeout ngắn hơn (15s) để tăng tốc xử lý
        response = self.session.post(
            url,
            params={
                "SPC_CDS": "a4ef0c3a-4b1a-4920-a8bf-4fccf56c8808",
                "SPC_CDS_VER": "2"
            },
            json=payload,
            timeout=15
        )
        response.raise_for_status()
        
        try:
            return response.json()
        except ValueError:
            logger.warning(f"Response is not JSON: {response.text[:200]}")
            return {}
    
    def get_shop_ratings_raw(
        self,
        rating_star: str = "5,4,3,2,1",
        time_start: int = None,
        time_end: int = None,
        page_number: int = 1,
        page_size: int = 50,
        cursor: int = 0,
        from_page_number: int = 1,
        language: str = "vi"
    ) -> Dict[str, Any]:
        """
        Lấy danh sách đánh giá từ Shopee KNB API.
        
        Args:
            rating_star: Comma-separated ratings (vd: "5,4,3,2,1")
            time_start: Timestamp bắt đầu (Unix timestamp)
            time_end: Timestamp kết thúc (Unix timestamp)
            page_number: Số trang
            page_size: Số items mỗi trang
            cursor: Cursor cho pagination
            from_page_number: From page number
            language: Ngôn ngữ (default: "vi")
            
        Returns:
            {
                "code": 0,
                "message": "success",
                "data": {
                    "page_info": {
                        "total": 128233,
                        "page_number": null,
                        "page_size": null
                    },
                    "list": [
                        {
                            "comment_id": 80386957542,
                            "rating_star": 5,
                            "comment": "",
                            "images": [],
                            "ctime": 1764654168,
                            "user_id": 1041304483,
                            "user_name": "thanhnguynphng915",
                            "user_portrait": "vn-11134233-7qukw-ljp38pnhuxmc97",
                            "order_id": 218167800298720,
                            "order_sn": "2511304V8TTQ70",
                            "product_id": 17185925586,
                            ...
                        },
                        ...
                    ]
                }
            }
        """
        logger.debug(f"[ShopeeRepo] Getting shop ratings: rating_star={rating_star}, page={page_number}")
        
        # Build URL với SPC_CDS
        url = "settings/search_shop_rating_comments_new/"
        
        params = {
            "SPC_CDS": "15c18032-c3ae-45ea-9393-85c234ac4a32",
            "SPC_CDS_VER": "2",
            "rating_star": rating_star,
            "language": language,
            "page_number": page_number,
            "page_size": page_size,
            "cursor": cursor,
            "from_page_number": from_page_number,
        }
        
        if time_start:
            params["time_start"] = time_start
        if time_end:
            params["time_end"] = time_end
        
        # Timeout dài hơn (30s) vì API này có thể chậm
        return self.get(url, params=params, timeout=30, retry=2)
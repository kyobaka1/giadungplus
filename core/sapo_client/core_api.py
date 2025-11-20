# core/sapo_client/core_api.py
from typing import Dict, Any

from .base_api import BaseAPIClient
from .filters import BaseFilter


class SapoCoreAPI(BaseAPIClient):
    """
    API cho SAPO CORE (MAIN_URL).
    """

    def list_orders(self, flt: BaseFilter) -> Dict[str, Any]:
        """
        Lấy danh sách đơn từ /orders.json
        Ví dụ filter.params = {"page":1,"limit":50,"location_ids[]":241737}
        """
        res = self.get("orders.json", params=flt.to_params(), timeout=20)
        res.raise_for_status()
        return res.json()

    def get_order(self, order_id: int) -> Dict[str, Any]:
        res = self.get(f"orders/{order_id}.json", timeout=20)
        res.raise_for_status()
        return res.json()

    def get_order_from_shopee_sn(self, shopee_sn: str) -> Dict[str, Any]:
        res = self.get(f"orders.json?query={shopee_sn}&litmit=1&page=1", timeout=20)
        res.raise_for_status()
        return res.json()['orders'][0]

    def change_customer_info(self, customer_id: int, data: dict):
        """
        Update name / phone / address của khách vào SAPO
        """
        endpoint = f"/customers/{customer_id}.json"
        payload = {"customer": data}
        return self.put(endpoint, payload)
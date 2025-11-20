# core/sapo_client/marketplace_api.py
from typing import Any, Dict, Iterable, List

from core.sapo_client.base_api import BaseAPIClient  # hoặc import đúng đường dẫn BaseAPIClient
from core.sapo_client.filters import BaseFilter  # nếu đang dùng thế này

class SapoMarketplaceAPI(BaseAPIClient):
    """
    API cho Marketplace (https://market-place.sapoapps.vn)
    """


    def list_orders(self, flt: BaseFilter) -> Dict[str, Any]:
        res = self.get("v2/orders", params=flt.to_params(), timeout=20)
        res.raise_for_status()
        return res.json()

    # ---------------------- NEW: INIT CONFIRM ---------------------- #
    def init_confirm(self, order_ids: Iterable[int], account_id: int) -> Dict[str, Any]:
        """
        GET /v2/orders/confirm/init?accountId=...&ids=1,2,3

        - order_ids: danh sách ID đơn trên Marketplace (tmdt_order['id'])
        - account_id: 319911 (hoặc đọc từ settings)

        Trả về JSON y chang Sapo.
        """
        ids_str = ",".join(str(i) for i in order_ids)

        params = {
            "accountId": account_id,
            "ids": ids_str,
        }

        res = self.get("v2/orders/confirm/init", params=params, timeout=20)
        res.raise_for_status()
        return res.json()

    # ---------------------- NEW: CONFIRM ORDERS ---------------------- #
    def confirm_orders(
        self,
        confirm_order_request_model: List[Dict[str, Any]],
        account_id: int,
    ) -> Dict[str, Any]:
        """
        PUT /v2/orders/confirm?accountId=...

        confirm_order_request_model format:

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
        """
        params = {"accountId": account_id}
        payload = {"confirm_order_request_model": confirm_order_request_model}

        res = self.put("v2/orders/confirm", params=params, json=payload, timeout=20)
        res.raise_for_status()
        return res.json()


# orders/services/sapo_service.py
from typing import Dict, Any, List, Optional

from core.sapo_client import get_sapo_client, BaseFilter
from orders.services.dto import OrderDTO, MarketplaceConfirmOrderDTO
from orders.services.order_builder import build_order_from_sapo
import datetime

SAPO_ACCOUNT_ID = 319911
class SapoCoreOrderService:
    """
    Service cho Sapo CORE (MAIN_URL) – /orders.json, /orders/{id}.json
    """
    def __init__(self):
        sapo = get_sapo_client()
        self._core_api = sapo.core_api

    def _parse_sapo_time(self, s: str) -> datetime.datetime:
        # "2025-11-18T09:16:23Z" -> datetime UTC
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


    def get_order_dto(self, order_id: int) -> OrderDTO:
        payload = self._core_api.get_order(order_id)  # JSON /orders/{id}.json
        return build_order_from_sapo(payload)

    def get_order_dto_from_shopee_sn(self, shopee_sn: str) -> OrderDTO:
        payload = self._core_api.get_order_from_shopee_sn(shopee_sn)  # JSON /orders/{id}.json
        return build_order_from_sapo(payload)

    def list_orders(self, flt: BaseFilter) -> Dict[str, Any]:
        return self._core_api.list_orders(flt)


class SapoMarketplaceOrderService:
    """
    Service cho Marketplace (market-place.sapoapps.vn/v2/orders)
    """
    def __init__(self):
        sapo = get_sapo_client()
        self._mp_api = sapo.marketplace_api

    def list_orders(self, flt: BaseFilter) -> Dict[str, Any]:
        return self._mp_api.list_orders(flt)

    # ---------- NEW: dùng API init_confirm trong SapoMarketplaceAPI ---------- #
    def init_confirm(self, order_ids: List[int]) -> Dict[str, Any]:
        return self._mp_api.init_confirm(order_ids, account_id=SAPO_ACCOUNT_ID)

    def confirm_orders(self, items: List[MarketplaceConfirmOrderDTO]) -> Dict[str, Any]:
        """
        Group DTO thành payload confirm_order_request_model rồi gọi Marketplace API.
        """
        grouped: Dict[tuple, List[Dict[str, Any]]] = {}

        for dto in items:
            key = (dto.connection_id, dto.pick_up_type, dto.address_id)

            order_model: Dict[str, Any] = {
                "order_id": dto.order_id,
            }
            # CHỈ gửi pickup_time_id khi có time slot hợp lệ
            if dto.pickup_time_id not in (None, "", 0, "0"):
                order_model["pickup_time_id"] = str(dto.pickup_time_id)

            grouped.setdefault(key, []).append(order_model)

        confirm_order_request_model: List[Dict[str, Any]] = []

        for (connection_id, pick_up_type, address_id), order_models in grouped.items():
            confirm_order_request_model.append(
                {
                    "connection_id": connection_id,
                    "order_models": order_models,
                    "shopee_logistic": {
                        "pick_up_type": pick_up_type,
                        "address_id": address_id,
                    },
                }
            )

        return self._mp_api.confirm_orders(
            confirm_order_request_model=confirm_order_request_model,
            account_id=SAPO_ACCOUNT_ID,
        )
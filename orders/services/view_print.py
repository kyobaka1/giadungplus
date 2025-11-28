# orders/services/view_print.py
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from core.sapo_client import BaseFilter
from .sapo_service import SapoMarketplaceService, SapoCoreOrderService
from .order_builder import build_express_order
from .dto import Order

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")

# Mapping kho -> location_id
LOCATION_BY_KHO = {
    "geleximco": 241737,   # HN
    "toky": 548744,        # HCM
}

# Kết nối Shopee đang dùng (anh chỉnh đúng chuỗi của anh)
CONNECTION_IDS = "155938,155687,155174,134366,10925"


class ExpressOrderService:
    def __init__(self):
        self._mp = SapoMarketplaceService()
        self._core = SapoCoreOrderService()

    def list_express_orders(
        self,
        current_kho: str,
        limit: int = 50,
        connection_ids: str = CONNECTION_IDS,
    ) -> List[Order]:

        now_vn = datetime.now(TZ_VN)
        allowed_location_id: Optional[int] = LOCATION_BY_KHO.get(current_kho)

        flt = BaseFilter(params={
            "connectionIds": connection_ids,
            "page": 1,
            "limit": limit,
            "channelOrderStatus": "READY_TO_SHIP,RETRY_SHIP,PROCESSED",
            "shippingCarrierIds": (
                "134097,1285481,108346,17426,60176,1283785,1285470,1292451,"
                "35696,47741,14895,1272209,176002"
            ),
            "sortBy": "ISSUED_AT",
            "orderBy": "desc",
        })

        mp_resp = self._mp.list_orders(flt)
        mp_orders = mp_resp.get("orders", [])

        results: List[Order] = []

        for mp_o in mp_orders:
            sapo_order_id = mp_o.get("sapo_order_id")
            if not sapo_order_id:
                continue

            core_resp = self._core.get_order(sapo_order_id)
            sapo_order = core_resp.get("order")
            if not sapo_order:
                continue

            location_id = sapo_order.get("location_id")
            if allowed_location_id and location_id != allowed_location_id:
                # khác kho -> bỏ
                continue

            order_dto = build_express_order(mp_o, sapo_order, now_vn)
            results.append(order_dto)

        return results

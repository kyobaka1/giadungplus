# orders/services/order_xpress_auto.py

from django.utils import timezone
from django.db import transaction
import datetime
from zoneinfo import ZoneInfo
from core.sapo_client import BaseFilter
from core import shopee_client
from orders.services.sapo_service import (
    SapoMarketplaceService,
    SapoCoreOrderService,
)
from core.system_settings import get_connection_ids
import time

connection_ids = get_connection_ids()

def auto_prepare_single_order(order):
    """
    Hàm xử lý chuẩn bị hàng cho 1 đơn hoả tốc.
    Ở đây anh map sang logic thật của anh:
    - Gọi Sapo/Shopee để tạo phiếu chuẩn bị, đổi trạng thái, v.v.
    - Hoặc reuse từ print_now / service khác.
    """
    # TODO: thay bằng logic thật của anh
    # Ví dụ (giả định):
    # prepare_order_on_sapo(order)

    # Em để tạm print để anh test log cho dễ:
    print(f"[AUTO XPRESS] Preparing order #{order.id} - {order.channel_order_number}")


def auto_prepare_express_orders(limit=50):
    """
    Quét các đơn hoả tốc cần chuẩn bị hàng và xử lý.
    - Chỉ lấy một số lượng giới hạn (limit) để không nặng máy.
    - Chỉ chọn những đơn 'pending' để không bị làm lại.
    """
    # Giờ VN
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")

    # Service layer
    mp_service = SapoMarketplaceService()
    core_service = SapoCoreOrderService()

    # Filter cho Marketplace orders
    mp_filter = BaseFilter(params={ "connectionIds": connection_ids, "page": 1, "limit": 50, "channelOrderStatus": "READY_TO_SHIP,RETRY_SHIP,PROCESSED", "shippingCarrierIds": "134097,1285481,108346,17426,60176,1283785,1285470,35696,47741,14895,1272209,176002", "sortBy": "ISSUED_AT", "orderBy": "desc", })
    mp_resp = mp_service.list_orders(mp_filter)
    mp_orders = mp_resp.get("orders", [])

    if len(mp_orders) == 0:
        print("[AUTO XPRESS] Không có đơn hoả tốc nào cần xử lý.")
        return
    print(f"[AUTO XPRESS] Bắt đầu xử lý {len(mp_orders)} đơn hoả tốc!")
    for order in mp_orders:
        try:
            client = shopee_client.ShopeeClient(order['connection_id'])
            client._get_shopee_order_id(order['channel_order_number'])
            client._restart_express_shipping()
            time.sleep(10)
        except Exception as e:
            print(f"[AUTO XPRESS] Lỗi khi xử lý đơn #{order["channel_order_number"]}: {e}")

    print("[AUTO XPRESS] Hoàn tất 1 lượt quét.")



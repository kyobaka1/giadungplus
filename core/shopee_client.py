# shopee_client.py
import json
from pathlib import Path
import requests
import os
from pathlib import Path
from io import BytesIO
from typing import Optional, Dict, Any

import requests
from PyPDF2 import PdfReader, PdfWriter
from typing import Any, Dict, List
from core.system_settings import (
    get_shop_by_connection_id,
    resolve_pickup_address_id,
    load_shopee_shops_detail,
)
from core.sapo_client.core_api import SapoCoreAPI
from core.system_settings import SAPO_BASIC

# ===========================
# CONSTANTS
# ===========================

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BASE_DIR / "logs"
COOKIE_DIR = LOGS_DIR / "raw_cookie"
COVER_DIR = LOGS_DIR / "print-cover"
BILL_DIR = LOGS_DIR / "bill"

SHOPEE_API_BASE = "https://banhang.shopee.vn/api/v3"

CONFIG_PATH = Path("logs/shopee_shops.json")
DEBUG = True   # <<<<<< BẬT / TẮT DEBUG Ở ĐÂY

def debug_print(*args):
    if DEBUG:
        print("[ShopeeClient]", *args)



def parse_raw_headers(raw: str) -> dict:
    if not raw:
        debug_print("parse_raw_headers: raw EMPTY")
        return {}

    lines = [l.strip("\r") for l in raw.splitlines() if l.strip() != ""]
    headers = {}

    it = iter(lines)
    count = 0
    for key in it:
        try:
            value = next(it)
        except StopIteration:
            debug_print(f"parse_raw_headers: missing value for key '{key}'")
            break

        headers[key] = value
        count += 1

    debug_print(f"parse_raw_headers: loaded {count} headers")
    return headers

def load_headers_from_file(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        return parse_raw_headers(raw)
    except Exception as e:
        debug_print(f"Cannot load header file {path}: {e}")
        return {}


def load_shops(config_path: Path = CONFIG_PATH) -> dict:
    debug_print(f"Loading shops from: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    shops_map = {}
    for shop in data.get("shops", []):
        name = shop["name"]
        shop_connect = shop.get("shop_connect")
        headers_file = shop.get("headers_file")

        headers = load_headers_from_file(headers_file) if headers_file else {}

        shops_map[name] = {
            "name": name,
            "shop_connect": shop_connect,
            "headers": headers,
        }

    debug_print(f"Loaded {len(shops_map)} shop(s)")
    return shops_map

# ===========================
# ShopeeClient
# ===========================
SHOPS = load_shops()
CURRENT_CLIENT  = None

class ShopeeClient:
    """
    Shopee Client:
    - Tự detect shop theo connection_id
    - Load headers từ cookie file
    - Gọi API Shopee
    - Build PDF bill
    """

    def __init__(self, shop_key: int | str):
        """
        shop_key: có thể là connection_id (số) hoặc shop_name (chuỗi).
        """
        self.session = requests.Session()
        self.shopee_order_id = None
        self.channel_id = None
        self.first_pack = None
        self.shop_cfg = None
        self.package_list = None
        self.shop_name = None
        self.headers_file = None
        self.seller_shop_id = 0

        # đây chính là "doi_shop" khi khởi tạo
        self.switch_shop(shop_key)

    def _load_headers(self):
        if not self.headers_file:
            raise ValueError(f"Shop {self.shop_name} không có headers_file")

        file_path = Path(self.headers_file)
        if not file_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy cookie file: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            raw = f.read()

        headers = parse_raw_headers(raw)
        self.session.headers.clear()
        self.session.headers.update(headers)

    def switch_shop(self, shop_key: int | str):
        """
        Đổi sang shop khác:
        - Tìm config shop theo connection_id hoặc name.
        - Load headers từ cookie file vào self.session.headers.
        """
        self.shop_cfg = self._resolve_shop_cfg(shop_key)
        if not self.shop_cfg:
            raise ValueError(f"Không tìm thấy shop cho key={shop_key}")

        self.shop_name = self.shop_cfg["name"]
        # tuỳ cấu trúc shop_cfg của mày
        self.headers_file = self.shop_cfg.get("headers_file")
        self.seller_shop_id = int(self.shop_cfg.get("seller_shop_id") or 0)

        # load headers (cookie) vào session
        self._load_headers()

    def _resolve_shop_cfg(self, shop_key: int | str) -> dict:
        """
        Tìm config shop theo:
        - Nếu là số: dùng get_shop_by_connection_id.
        - Nếu là chuỗi: tìm theo name trong load_shopee_shops_detail() hoặc load_shops().
        """
        key_str = str(shop_key)

        # 1) Thử coi nó là connection_id
        cfg = None
        if key_str.isdigit():
            try:
                cfg = get_shop_by_connection_id(int(key_str))
            except Exception:
                cfg = None

        # 2) Nếu chưa thấy thì coi là tên shop
        if not cfg:
            # Tuỳ mày, nhưng em giả sử load_shopee_shops_detail()
            # trả về list/dict config có field "name"
            shops_detail = load_shopee_shops_detail()
            # nếu là dict {name: cfg}
            if isinstance(shops_detail, dict):
                cfg = shops_detail.get(key_str)
            else:
                # nếu là list các dict
                for s in shops_detail:
                    if str(s.get("name")) == key_str:
                        cfg = s
                        break

        if not cfg:
            raise ValueError(f"Không tìm thấy cấu hình shop cho '{shop_key}'")

        return cfg

    # ------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------

    def _get(self, url, **kw):
        return self.session.get(url, **kw)

    def _post(self, url, **kw):
        return self.session.post(url, **kw)

    # ------------------------------------------------------
    # Shopee API
    # ------------------------------------------------------
    def _get_shopee_order_id(self, order_sn: str) -> int:
        debug_print("→ get_shopee_order_id:")
        SHOPEE_ID = 0
        hint_url = (
            "https://banhang.shopee.vn/api/v3/order/get_order_list_search_bar_hint"
            f"?keyword={order_sn}"
            "&category=1&order_list_tab=100"
        )
        debug_print("→ Calling hint URL:", hint_url)

        hint_resp = self._get(hint_url)
        debug_print("→ Hint status:", hint_resp.status_code)

        try:
            hint_resp.raise_for_status()
        except Exception:
            debug_print("Hint raw:", hint_resp.text[:500])
            raise RuntimeError("Cookie Shopee lỗi – 403 hoặc expired!")

        data = hint_resp.json()
        try:
            SHOPEE_ID = data["data"]["order_sn_result"]["list"][0]["order_id"]
        except Exception:
            raise RuntimeError(f"Không tìm được order_id cho mã {order_sn}")

        debug_print("→ SHOPEE_ID:", SHOPEE_ID)
        self.shopee_order_id = SHOPEE_ID
        return SHOPEE_ID

    def _get_packed_list(self) -> int:
        pkg_url = (
            "https://banhang.shopee.vn/api/v3/order/get_package"
            f"?order_id={self.shopee_order_id}"
        )
        debug_print("→ pkg_url:", pkg_url)

        pkg_resp = self._get(pkg_url)
        pkg_resp.raise_for_status()

        pkg_data = pkg_resp.json()
        order_info: Dict[str, Any] = pkg_data["data"]["order_info"]
        package_list: List[Dict[str, Any]] = order_info.get("package_list") or []

        debug_print("→ package_list count:", len(package_list))

        if not package_list:
            raise RuntimeError("Không có package_list để in vận đơn.")

        first_pack = package_list[0]

        # channel_id ưu tiên: fulfillment_channel_id -> shipping_method -> checkout_channel_id
        channel_id = (
                first_pack.get("fulfillment_channel_id")
                or first_pack.get("shipping_method")
                or first_pack.get("checkout_channel_id")
        )
        debug_print("→ channel_id from package:", channel_id)

        self.channel_id = channel_id
        self.package_list = package_list
        self.first_pack = first_pack

        return channel_id

    def _restart_express_shipping(self):
        # TÌM TÀI XẾ LẠI.
        debug_print("Find tài xế: ", self.shopee_order_id, " trên shop: ", self.shop_name)

        if not self.package_list:
            self._get_packed_list()

        packed_number = self.package_list[0].get("package_number")

        RS = self._get(f"https://banhang.shopee.vn/api/v3/shipment/get_pickup?SPC_CDS=c9accf1d-0cc4-42c0-86d6-20b726cadd4a&SPC_CDS_VER=2&order_id={self.shopee_order_id}&package_number={packed_number}").json()
        address_id = RS['data']['pickup_address_id']
        RS = self._get(f"https://banhang.shopee.vn/api/v3/shipment/get_pickup_time_slots?SPC_CDS=c9accf1d-0cc4-42c0-86d6-20b726cadd4a&SPC_CDS_VER=2&order_ids={self.shopee_order_id}&address_id={address_id}&channel_id={RS['data']['channel_id']}").json()
        URL = "https://banhang.shopee.vn/api/v3/shipment/update_shipment_group_info?SPC_CDS=06614307-0c48-4f4f-829f-98b6da1345c2&SPC_CDS_VER=2"
        payload = {"remark": "", "pickup_time": RS['data']['time_slots'][0]['value'], "pickup_address_id": address_id,
                   "seller_real_name": "", "shipping_mode": "pickup",
                   "group_info": {"group_shipment_id": 0, "primary_package_number": packed_number,
                                  "package_list": [{"order_id": self.shopee_order_id, "package_number": packed_number}]}}

        RS = self._post(URL, json=payload)
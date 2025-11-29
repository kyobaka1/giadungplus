# core/system_settings.py
"""
Cấu hình hệ thống nội bộ cho Gia Dụng Plus:
- Thông tin kết nối Sapo
- Xpath field login
- Tham số HOME_PARAM, flag HN/HCM
- Các URL đặc biệt (market-place, scopes, v.v.)
"""

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Đọc biến môi trường với default (anh có thể set trong .env, Docker, v.v.)
# Ưu tiên đọc từ file settings/logs/sapo_config.env

SAPO_CONFIG_FILE = Path("settings/logs/sapo_config.env")
_file_config = {}

def load_config_file():
    global _file_config
    if SAPO_CONFIG_FILE.exists():
        try:
            with open(SAPO_CONFIG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    _file_config[key.strip()] = value.strip()
        except Exception as e:
            print(f"Error loading config file: {e}")

load_config_file()

def env(key: str, default: str = "") -> str:
    return _file_config.get(key) or os.environ.get(key, default)


# ================== CẤU HÌNH SAPO CƠ BẢN ==================

@dataclass
class SapoBasicConfig:
    MAIN_URL: str
    USERNAME: str
    PASSWORD: str

    LOGIN_USERNAME_FIELD: str
    LOGIN_PASSWORD_FIELD: str
    LOGIN_BUTTON: str


SAPO_BASIC = SapoBasicConfig(
    MAIN_URL=env("SAPO_MAIN_URL", "https://sisapsan.mysapogo.com/admin"),
    USERNAME=env("SAPO_USERNAME", "0988700162"),
    PASSWORD=env("SAPO_PASSWORD", "giadungPlus2@@4"),

    # Các selector dùng login – default theo giao diện mới của Sapo SSO
    # Trang: https://accounts.sapo.vn/login?serviceType=omni
    # - Username: ô "Email/Số điện thoại của bạn"
    # - Password: ô "Mật khẩu đăng nhập cửa hàng"
    # - Button: nút "Đăng nhập"
    #
    # Dùng XPATH đơn giản theo placeholder/text cho ổn định:
    LOGIN_USERNAME_FIELD=env(
        "SAPO_LOGIN_USERNAME_FIELD",
        "//input[@placeholder='Email/Số điện thoại của bạn']",
    ),
    LOGIN_PASSWORD_FIELD=env(
        "SAPO_LOGIN_PASSWORD_FIELD",
        "//input[@type='password' and @placeholder='Mật khẩu đăng nhập cửa hàng']",
    ),
    LOGIN_BUTTON=env(
        "SAPO_LOGIN_BUTTON",
        "//button[normalize-space()='Đăng nhập']",
    ),
)


# ================== CẤU HÌNH MARKET-PLACE / TMDT ==================

@dataclass
class SapoTmdtConfig:
    STAFF_ID: str
    SCOPES_URL: str

SAPO_TMDT = SapoTmdtConfig(
    STAFF_ID=env("SAPO_TMDT_STAFF_ID", "319911"),
    SCOPES_URL=f"https://market-place.sapoapps.vn/",
)


# ================== THAM SỐ VẬN HÀNH ==================

# HOME_PARAM quyết định “chế độ chạy” của worker:
#   - "HN"  : chỉ chạy cho HN
#   - "HCM" : chỉ chạy cho HCM
#   - "CSKH": chế độ CSKH
HOME_PARAM: str = env("GDPLUS_HOME_PARAM", "HN")

# Flag bật/tắt thông báo hoả tốc từng kho
HOATOC_HN_ON: bool = env("GDPLUS_HOATOC_HN_ON", "1") == "1"
HOATOC_HCM_ON: bool = env("GDPLUS_HOATOC_HCM_ON", "1") == "1"


# ================== SHOPEE CONFIG ==================

SHOPEE_SHOPS_CONFIG = Path("settings/logs/shopee_shops.json")

# Location ID theo Sapo
KHO_GELEXIMCO = 241737  # Hà Nội
KHO_TOKY = 548744       # HCM


def load_shopee_shops() -> Dict[str, int]:
    """
    Đọc file settings/logs/shopee_shops.json và trả về map:
    {
        "giadungplus_official": 10925,
        "lteng_vn": 155174,
        ...
    }

    Hàm này DÙNG CHUNG cho các chỗ cũ -> không sửa behaviour.
    Các field khác trong JSON (address_geleximco, address_toky, headers_file...)
    sẽ bị bỏ qua ở đây.
    """
    if not SHOPEE_SHOPS_CONFIG.is_file():
        return {}

    with SHOPEE_SHOPS_CONFIG.open("r", encoding="utf-8") as f:
        data = json.load(f)

    shops_map: Dict[str, int] = {}
    for shop in data.get("shops", []):
        name = shop.get("name")
        connect_id = shop.get("shop_connect")
        if name and connect_id:
            shops_map[name] = int(connect_id)

    return shops_map


def get_connection_ids(shop_names: Optional[List[str]] = None) -> str:
    """
    Trả về chuỗi connectionIds để truyền vào Marketplace:
    - Nếu shop_names = None -> lấy TẤT CẢ shop trong file.
    - Nếu shop_names = ['giadungplus_official', 'lteng_vn'] -> chỉ lấy 2 shop này.
    Kết quả: "10925,155174,..."
    """
    shops_map = load_shopee_shops()

    if not shop_names:
        ids = [str(v) for v in shops_map.values()]
    else:
        ids = [str(shops_map[name]) for name in shop_names if name in shops_map]

    return ",".join(ids)


# ================== PHẦN MỚI: cấu hình chi tiết & address_id ================== #

def load_shopee_shops_detail() -> Dict[str, Dict[str, Any]]:
    """
    Đọc file settings/logs/shopee_shops.json và trả về map chi tiết:
    {
        "giadungplus_official": {
            "name": "giadungplus_official",
            "shop_connect": 10925,
            "headers_file": "...",
            "address_geleximco": 29719283,
            "address_toky": 200025624,
            ...
        },
        ...
    }
    """
    if not SHOPEE_SHOPS_CONFIG.is_file():
        return {}

    with SHOPEE_SHOPS_CONFIG.open("r", encoding="utf-8") as f:
        data = json.load(f)

    shops_detail: Dict[str, Dict[str, Any]] = {}
    for shop in data.get("shops", []):
        name = shop.get("name")
        if not name:
            continue
        shops_detail[name] = shop

    return shops_detail


def get_shop_config(shop_name: str) -> Optional[Dict[str, Any]]:
    """
    Lấy full config của 1 shop theo name.
    Dùng được chung cho nhiều mục đích (headers_file, address_id, v.v.)
    """
    shops_detail = load_shopee_shops_detail()
    return shops_detail.get(shop_name)


def resolve_pickup_address_id(shop_name: str, location_id: int) -> int:
    """
    Định tuyến address_id để 'tìm ship / chuẩn bị hàng' theo:
    - shop_name (ví dụ: giadungplus_official, phaledo, lteng_vn, lteng_hcm...)
    - location_id (KHO_GELEXIMCO / KHO_TOKY)

    Lấy từ settings/logs/shopee_shops.json:
    - address_geleximco cho kho Hà Nội
    - address_toky cho kho HCM

    Nếu không tìm thấy -> trả về 0 để bên ngoài tự quyết định bỏ qua / raise.
    """
    shop_cfg = get_shop_config(shop_name)

    if not shop_cfg:
        print(f"[!] Không tìm thấy cấu hình shop trong shopee_shops.json: {shop_name}")
        return 0

    if location_id == KHO_GELEXIMCO:
        key = "address_geleximco"
        kho_label = "Kho HN - GELEXIMCO"
    elif location_id == KHO_TOKY:
        key = "address_toky"
        kho_label = "Kho HCM - TOKY"
    else:
        print(f"[!] location_id chưa hỗ trợ: {location_id} (shop: {shop_name})")
        return 0

    addr_value = shop_cfg.get(key)
    try:
        address_id = int(addr_value) if addr_value is not None else 0
    except (TypeError, ValueError):
        print(
            f"[!] address_id không hợp lệ ({addr_value}) cho shop={shop_name}, key={key}"
        )
        return 0

    if not address_id:
        print(
            f"[!] address_id = 0 cho shop={shop_name}, key={key}. "
            f"Kiểm tra lại settings/logs/shopee_shops.json"
        )
        return 0

    print(f"[+] Get packed {shop_name}: {kho_label}! (address_id={address_id})")
    return address_id

def resolve_location_by_address(address_id: int) -> Optional[int]:
    """
    Dựa vào address_id (Shopee pickup address) để suy ra location_id Sapo:

    - Nếu address_id trùng với address_geleximco trong settings/logs/shopee_shops.json
      -> trả về KHO_GELEXIMCO
    - Nếu address_id trùng với address_toky
      -> trả về KHO_TOKY
    - Không tìm thấy -> None

    => Mọi logic cần phân biệt HN / HCM từ address_id đều nên dùng hàm này.
    """
    if not SHOPEE_SHOPS_CONFIG.is_file():
        return None

    with SHOPEE_SHOPS_CONFIG.open("r", encoding="utf-8") as f:
        data = json.load(f)

    for shop in data.get("shops", []):
        addr_hn = shop.get("address_geleximco")
        addr_hcm = shop.get("address_toky")

        try:
            if addr_hn is not None and int(addr_hn) == address_id:
                return KHO_GELEXIMCO
            if addr_hcm is not None and int(addr_hcm) == address_id:
                return KHO_TOKY
        except (TypeError, ValueError):
            # Nếu config sai kiểu thì bỏ qua shop này
            continue

    return None


def is_geleximco_address(address_id: int) -> bool:
    """
    Helper nhanh: address_id này có phải kho GELEXIMCO (HN) không?
    """
    return resolve_location_by_address(address_id) == KHO_GELEXIMCO

def get_shop_by_connection_id(connection_id: int) -> Optional[Dict[str, Any]]:
    """
    Tìm shop config theo connection_id (shop_connect).
    Dùng khi chỉ có connection_id từ Marketplace.
    """
    if not SHOPEE_SHOPS_CONFIG.is_file():
        return None

    with SHOPEE_SHOPS_CONFIG.open("r", encoding="utf-8") as f:
        data = json.load(f)

    for shop in data.get("shops", []):
        if int(shop.get("shop_connect", 0) or 0) == int(connection_id):
            return shop

    return None
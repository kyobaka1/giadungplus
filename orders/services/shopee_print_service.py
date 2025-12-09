# File: orders/services/shopee_print_service.py

import json
import time
import logging
from io import BytesIO
from typing import Any, Dict, List, Optional
from pathlib import Path
import os
from django.conf import settings

import PyPDF2
import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from core.system_settings import get_shop_by_connection_id
from core.shopee_client import ShopeeClient
from core.sapo_client import get_sapo_client
from orders.services.sapo_service import (
    SapoMarketplaceService,
    SapoCoreOrderService,
)
from orders.services.dto import OrderDTO, RealItemDTO

# Logger
logger = logging.getLogger(__name__)

# =========================
# DEBUG CONFIG
# =========================
# DEBUG flag - có thể được set từ bên ngoài
DEBUG = False

def set_debug_mode(enabled: bool):
    """Set debug mode từ bên ngoài (ví dụ từ request parameter)"""
    global DEBUG
    DEBUG = enabled

def debug(*args):
    if DEBUG:
        msg = " ".join(str(arg) for arg in args)
        print("[SHOPEE_PRINT]", msg, flush=True)  # flush=True để đảm bảo in ngay
        logger.info(f"[SHOPEE_PRINT] {msg}")  # Cũng log vào logger để chắc chắn

# =========================
# CONFIG FILE KÊNH DVVC
# =========================

CHANNELS_FILE = Path("settings") / "logs/dvvc_shopee.json"


def _load_shipping_channels() -> Dict[int, Dict[str, Any]]:
    """
    Đọc file JSON chứa list kênh vận chuyển của Shopee:
    {
        "code": 0,
        "data": [
            {"channel_id": 50021, "name": "SPX Express", ...},
            ...
        ]
    }
    Trả về map: channel_id -> dict(channel_info)
    """
    if not CHANNELS_FILE.is_file():
        debug("→ Không tìm thấy file kênh DVVC:", CHANNELS_FILE)
        return {}

    try:
        with CHANNELS_FILE.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        debug("→ Lỗi đọc file kênh DVVC:", e)
        return {}

    channels_map: Dict[int, Dict[str, Any]] = {}
    for item in raw.get("data", []):
        cid = item.get("channel_id")
        if cid is not None:
            try:
                channels_map[int(cid)] = item
            except Exception:
                pass

    debug("→ Loaded shipping channels:", len(channels_map))
    return channels_map


# ===================================================================
# BUILD MVD PAGE
# ===================================================================
def detect_carrier_type(shipping_carrier_name: str) -> str:
    """
    Chuẩn hóa tên hãng vận chuyển thành 1 trong các loại:
    'spx', 'jnt', 'ninja', 'ghn', 'hoatoc', 'khac'
    """

    name = (shipping_carrier_name or "").lower()
    
    # Kiểm tra hoả tốc trước (ưu tiên cao nhất)
    # Bao gồm: Grab, beDelivery, Ahamove, Instant, Hoả Tốc - Trong ngày, SPX Express - Trong ngày, Ahamove - Giao trong ngày
    if (
        "grab" in name
        or "bedelivery" in name
        or "be delivery" in name
        or "ahamove" in name
        or "instant" in name
        or "hoả tốc" in name
        or "hoa toc" in name
        or "trong ngày" in name
        or "giao trong ngày" in name
    ):
        return "hoatoc"
        
    if "spx" in name or "shopee xpress" in name or "spx express" in name:
        return "spx"
    if "j&t" in name or "jnt" in name:
        return "jnt"
    if "ninja" in name:
        return "ninja"
    if "giao hàng nhanh" in name or "ghn" in name:
        return "ghn"
    
    return "khac"

def _build_mvd_overlay_page(
    channel_order_number: str, 
    shipping_carrier_name: str,
    order_dto: OrderDTO | None = None,  # NEW: Accept OrderDTO from caller
    current_package: Dict[str, Any] | None = None,  # NEW: Current package info
    total_packages: int = 1,  # NEW: Total number of packages
    client: ShopeeClient | None = None,  # NEW: ShopeeClient for API calls
    shopee_order_id: int | None = None,  # NEW: Shopee order ID
    seller_shop_id: int | None = None,  # NEW: Seller shop ID
    connection_id: int | None = None,  # NEW: Connection ID for MP order
):
    """
    Tạo trang MVD overlay – in mã đơn + shop lên trên label.
    
    Args:
        order_dto: OrderDTO with gifts already applied (optional, will fetch if not provided)
        current_package: Current package dict with package_number
        total_packages: Total number of packages (DON_TACH_FLAG)
    """
    # DEBUG: Xác nhận hàm được gọi
    debug("=" * 60)
    debug("DEBUG: _build_mvd_overlay_page được gọi")
    debug(f"  channel_order_number: {channel_order_number}")
    debug(f"  total_packages: {total_packages}")
    debug(f"  client: {client is not None}")
    debug(f"  shopee_order_id: {shopee_order_id}")
    debug(f"  seller_shop_id: {seller_shop_id}")
    debug(f"  connection_id: {connection_id}")
    debug("=" * 60)
    
    # Use provided DTO or fetch new one
    if order_dto is None:
        core_service = SapoCoreOrderService()
        try:
            order_dto: OrderDTO = core_service.get_order_dto_from_shopee_sn(channel_order_number)
        except Exception as e:
            debug(f"[MVD] Lỗi get_order_dto_from_shopee_sn({channel_order_number}): {e}")
            raise

    debug("→ Build MVD overlay:", channel_order_number)

    # Đăng ký font (lý tưởng là làm 1 lần global, nhưng tạm giữ như mày)
    font_dir = os.path.join(settings.BASE_DIR, 'assets', 'font')
    
    pdfmetrics.registerFont(TTFont('UTM Avo', os.path.join(font_dir, 'UTM_Avo.ttf')))
    pdfmetrics.registerFont(TTFont('UTM Avo Bold', os.path.join(font_dir, 'UTM_AvoBold.ttf')))
    pdfmetrics.registerFont(TTFont('Arial', os.path.join(font_dir, 'arial.ttf')))
    pdfmetrics.registerFont(TTFont('ArialI', os.path.join(font_dir, 'ariali.ttf')))

    # Chỉ cần 1 buffer
    buf = BytesIO()
    c = canvas.Canvas(buf)

    c.setPageSize((4.1 * inch, 5.8 * inch))
    c.translate(inch, inch)

    _render_mvd_overlay(
        c,
        channel_order_number=channel_order_number,
        shipping_carrier_name=shipping_carrier_name,
        order=order_dto,
        current_package=current_package,
        total_packages=total_packages,
        client=client,
        shopee_order_id=shopee_order_id,
        seller_shop_id=seller_shop_id,
        connection_id=connection_id,
    )

    # Kết thúc vẽ
    c.showPage()
    c.save()

    # LÙI VỀ ĐẦU buffer NÀY, không phải buffer khác
    buf.seek(0)

    # Đọc lại bằng PyPDF2
    reader = PyPDF2.PdfReader(buf)

    if not reader.pages:
        # Chặn case lạ cho dễ debug nếu sau này có lỗi khác
        raise ValueError("[MVD] Overlay PDF không có trang nào")

    return reader.pages[0]


def extract_customer_info(pdf_bytes: bytes) -> Dict[str, str]:
    """
    Trích xuất thông tin khách hàng từ file PDF phiếu gửi hàng.
    Logic dựa trên code cũ: Dòng thứ 3 thường là tên khách hàng.
    
    Args:
        pdf_bytes: Nội dung file PDF
        
    Returns:
        Dict chứa "name" và có thể các thông tin khác
    """
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                return {}
                
            page = pdf.pages[0]
            text = page.extract_text()
            if not text:
                return {}
                
            lines = text.split("\n")
            if len(lines) < 4:
                return {}
                
            # Logic cũ: Dòng 3 là tên khách hàng, cần replace các prefix của shop
            raw_name = lines[3]
            
            # List các prefix cần xóa (từ code cũ)
            prefixes = [
                "Gia Dụng Plus +", "Gia Dụng Plus Store ", "Gia Dụng Plus Official ",
                "Phaledo Official ", "Gia Dụng Plus HCM ", "Gia Dụng Plus HN ",
                "Gia Dụng Plus ", "Phaledo Offcial ", "lteng_vn ",
                "LTENG VIETNAM ", "PHALEDO ® ", "LTENG ", "LTENG HCM "
            ]
            
            clean_name = raw_name
            for p in prefixes:
                clean_name = clean_name.replace(p, "")
                
            clean_name = clean_name.strip()
            
            # logger.info(f"[ShopeePrintService] Extracted customer name: {clean_name}")
            return {"name": clean_name}
            
    except Exception as e:
        # logger.error(f"[ShopeePrintService] Failed to extract customer info: {e}")
        return {}


# ===================================================================
# Build MVD
# ===================================================================

def _render_mvd_overlay(
    c,
    *,
    channel_order_number: str,
    shipping_carrier_name: str,
    order: OrderDTO,
    current_package: Dict[str, Any] | None = None,
    total_packages: int = 1,
    client: ShopeeClient | None = None,
    shopee_order_id: int | None = None,
    seller_shop_id: int | None = None,
    connection_id: int | None = None,
):
    # DEBUG: Xác nhận hàm được gọi
    debug("=" * 60)
    debug("DEBUG: _render_mvd_overlay được gọi")
    debug(f"  channel_order_number: {channel_order_number}")
    debug(f"  total_packages: {total_packages}")
    debug("=" * 60)

    sc = detect_carrier_type(shipping_carrier_name)
    """
    In mã vận đơn. 
    """

    if sc not in ["hoatoc", "khac"]:
        # Xoay để in mã đơn ngang trên đầu giống code cũ
        c.rotate(90)
        c.setFont('UTM Avo Bold', 33)
        c.drawString(-45, 42, str(channel_order_number))
        c.rotate(270)

    """
    In sản phẩm trong đơn hàng.
    """

    config = {
        "spx": {
            "y_start_1": 168, "kho_11":-35,"kho_12":255,"kho_21":-35,"kho_22":245,"kho_31":-35,"kho_32":213,
            "deadline1": 87, "deadline2": 212, "total_11":-25, "total_12": 23, "total_21": 0, "total_22": 23
        },
        "jnt": {
            "y_start_1": 182,
            "deadline1": -15, "deadline2": 80, "total_11":-25, "total_12": 15, "total_21": 0, "total_22": 15
        },
        "ninja": {
            "y_start_1": 172,
            "deadline1": -5, "deadline2": 50, "total_11":-25, "total_12": 15, "total_21": 0, "total_22": 15
        },
        "ghn": {
            "y_start_1": 185, "kho_11":-35,"kho_12":265,"kho_21":-35,"kho_22":255,"kho_31":-35,"kho_32":231,
            "deadline1": 87, "deadline2": 230,"total_11":-25, "total_12": 15, "total_21": 0, "total_22": 15
        },
        "hoatoc": {
            "y_start_1": 170,"total_11":-25, "total_12": 23, "total_21": 0, "total_22": 23
        },
        "khac": {
            "y_start_1": 170, "total_11":-25, "total_12": 23, "total_21": 0, "total_22": 23
        }
    }
    y_value = config[sc]["y_start_1"]

    # Lấy các real_items thuộc package hiện tại (nếu là đơn tách)
    items_to_print = order.real_items  # Default: in toàn bộ real_items
    total_quantity = 0
    
    if total_packages > 1 and current_package and client and shopee_order_id and seller_shop_id and connection_id:
        debug("→ ĐI VÀO NHÁNH ĐƠN TÁCH")
        # Đơn tách: chỉ in các sản phẩm trong package hiện tại
        package_number = current_package.get("package_number")
        if package_number:
            debug(f"→ Processing split order, package: {package_number}")
            
            # Kiểm tra xem current_package đã có items chưa
            package_items = current_package.get("items", [])
            if not package_items:
                # Nếu chưa có, mới gọi API
                debug("→ current_package không có items, gọi API để lấy")
                package_items = _get_package_items_from_shopee(
                    client, shopee_order_id, seller_shop_id, package_number
                )
            else:
                debug(f"→ Dùng items từ current_package: {len(package_items)} items")
            
            # Lấy Sapo MP order để map item_id
            mp_order = _get_sapo_mp_order(connection_id, order.reference_number or channel_order_number)
            
            # Map và lọc real_items
            items_to_print = _map_item_ids_to_real_items(order, package_items, mp_order)
    
    # Tính total_quantity từ items_to_print
    for item in items_to_print:
        total_quantity += int(item.quantity) if item.quantity else 0
    
    # Tính line_spacing dựa trên số lượng items
    count_line = len(items_to_print) + len(order.gifts)
    line_spacing = 12 if count_line > 6 else int(60 / max(1, count_line))
    if line_spacing < 11:
        line_spacing = 10
    if line_spacing > 30:
        line_spacing = 20

    # In các real_items (đã được quy đổi từ combo, packed ra đơn chiếc)
    count = 0
    for x in items_to_print:
        if count < 10:
            unit_str = x.unit or "cái"
            line_order = f"** {int(x.quantity)} {unit_str} - {x.sku} - {x.variant_options or ''}"
            line_order = line_order[:53]
            c.setFont('Arial', 8)
            c.drawString(-32, y_value, line_order)

            # In tên của sản phẩm
            if count_line <= 5 and x.product_name:
                y_value -= 10
                c.setFont('ArialI', 7)
                c.drawString(-32, y_value, x.product_name.split("/")[0])

            y_value -= line_spacing

        count += 1

    """
    In quà tặng có trong đơn hàng.
    Logic: Chỉ in quà tặng nếu package hiện tại có chứa sản phẩm trigger quà tặng.
    """
    # Kiểm tra xem package hiện tại có sản phẩm trigger quà tặng không
    should_print_gifts = True
    if total_packages > 1 and items_to_print:
        # Lấy danh sách variant_ids trong package hiện tại
        package_variant_ids = {item.variant_id for item in items_to_print}
        package_variant_ids.update({item.old_id for item in items_to_print if item.old_id})
        
        # Kiểm tra xem có quà tặng nào được trigger bởi sản phẩm trong package này không
        has_triggering_product = False
        for gift in order.gifts:
            # Kiểm tra xem có variant_id nào trong trigger_variant_ids match với package không
            if gift.trigger_variant_ids:
                if any(trigger_id in package_variant_ids for trigger_id in gift.trigger_variant_ids):
                    has_triggering_product = True
                    break
            else:
                # Nếu không có trigger_variant_ids (quà tặng cũ), mặc định in ở package đầu tiên
                parcel_no = current_package.get("parcel_no", 1) if current_package else 1
                if parcel_no == 1:
                    has_triggering_product = True
                    break
        
        should_print_gifts = has_triggering_product
    elif total_packages == 1:
        # Đơn không tách: luôn in quà tặng
        should_print_gifts = True
    
    if should_print_gifts and len(order.gifts) > 0:
        line_order = f"---  QUÀ TẶNG KÈM TRONG ĐƠN  ---"
        c.setFont('Arial', 8)
        c.drawString(-32, y_value, line_order)
        y_value -= line_spacing

        for x in order.gifts:
            # Sử dụng thông tin từ GiftItemDTO (sku, unit, opt1 đã được fetch từ variant)
            unit_str = x.unit or "cái"  # Fallback về "cái" nếu không có unit
            sku_str = x.sku or ""  # SKU từ variant
            opt1_str = x.opt1 or ""  # Option 1 từ variant
            
            # Format: ** QUÀ TẶNG: {quantity} {unit} - {sku} - {opt1}
            line_order = f"** {int(x.quantity)} {unit_str}"
            if sku_str:
                line_order += f" - {sku_str}"
            if opt1_str:
                line_order += f" - {opt1_str}"
            
            line_order = line_order[:53]
            c.setFont('Arial', 8)
            c.drawString(-32, y_value, line_order)
            y_value -= line_spacing
        
    if count > 10:
        c.setFont('UTM Avo Bold', 8)
        c.drawString(-32, y_value, "** ĐƠN DÀI - QUÉT SAPO để xem thêm.")
        y_value -= 10
    if sc in ["spx","ghn"]:
        c.setFont('Arial', 8)
        if order.location_id == 241737:
            c.drawString(config[sc]["kho_11"], config[sc]["kho_12"], f"C21-02 KĐ Geleximco")
            c.drawString(config[sc]["kho_21"], config[sc]["kho_22"], f"Hà Đông, Hà Nội")
            c.setFont('UTM Avo Bold', 10)
            c.drawString(config[sc]["kho_31"], config[sc]["kho_32"], f"KHO HÀ NỘI: GELE")
        else:
            c.drawString(config[sc]["kho_11"], config[sc]["kho_12"], f"B76a Tô Ký, Q.12")
            c.drawString(config[sc]["kho_21"], config[sc]["kho_22"], f"Thành phố Hồ Chí Minh")
            c.setFont('UTM Avo Bold', 10)
            c.drawString(config[sc]["kho_31"], config[sc]["kho_32"], f"KHO SÀI GÒN: TOKY")

    if sc not in ["hoatoc","khac"]:
        SHIP_CONTENT = f"KPI: {order.ship_deadline_fast_str}"
        c.setFillColorRGB(1, 1, 1)
        c.setFont('UTM Avo Bold', 9)
        c.drawString(config[sc]["deadline1"], config[sc]["deadline2"], SHIP_CONTENT)

    # total_quantity đã được tính ở trên từ items_to_print

    c.setFillColorRGB(0, 0, 0)
    c.setFont('UTM Avo Bold', 15)
    if total_packages > 1:
        parcel_no = current_package.get("parcel_no", "1")
        c.drawString(config[sc]["total_11"], config[sc]["total_12"], f"- Tách đơn: {parcel_no}/{total_packages} -")
    else:
        c.drawString(config[sc]["total_21"], config[sc]["total_22"], f"- Tổng: {int(total_quantity)} -")

    if len(order.note) > 5:
        draw_label_with_bg(
            c,
            int(config[sc]["total_11"]-5),
            int(config[sc]["total_12"]+20),
            max_width=165,
            text="Ghi chú: " + order.note
        )

    return c


# ===================================================================
# HELPER FUNCTIONS FOR SPLIT ORDERS
# ===================================================================

def _get_package_items_from_shopee(
    client: ShopeeClient,
    shopee_order_id: int,
    seller_shop_id: int,
    package_number: str
) -> List[Dict[str, Any]]:
    """
    Lấy danh sách items trong package từ Shopee API.
    
    Args:
        client: ShopeeClient instance
        shopee_order_id: Shopee order ID
        seller_shop_id: Seller shop ID
        package_number: Package number
        
    Returns:
        List of items với model_id (item_id của Shopee)
    """
    try:
        url = "https://banhang.shopee.vn/api/v3/order/batch_get_packages_multi_shop"
        params = {
            "SPC_CDS": "f8cfde35-a66a-4a25-8b35-c7ea97c759aa",
            "SPC_CDS_VER": "2"
        }
        payload = {
            "orders": [{
                "order_id": shopee_order_id,
                "shop_id": seller_shop_id,
                "region_id": "VN"
            }]
        }
        
        debug("→ Getting package items from Shopee API")
        resp = client.session.post(url, params=params, json=payload)
        resp.raise_for_status()
        
        data = resp.json()
        package_list = data.get("data", {}).get("list", [])
        if not package_list:
            debug("→ No packages found in response")
            return []
        
        # Tìm package có package_number trùng
        for pkg in package_list[0].get("package_list", []):
            if pkg.get("package_number") == package_number:
                items = pkg.get("items", [])
                debug(f"→ Found {len(items)} items in package {package_number}")
                return items
        
        debug(f"→ Package {package_number} not found")
        return []
        
    except Exception as e:
        debug(f"→ Error getting package items: {e}")
        return []


def _get_sapo_mp_order(
    connection_id: int,
    reference_number: str
) -> Optional[Dict[str, Any]]:
    """
    Lấy Sapo MP order để map item_id với sapo_variant_id.
    
    Args:
        connection_id: Connection ID của shop
        reference_number: Mã đơn Shopee (reference_number)
        
    Returns:
        MP order dict với products list, hoặc None nếu không tìm thấy
    """
    try:
        sapo = get_sapo_client()
        mp_service = SapoMarketplaceService()
        
        debug(f"→ Getting Sapo MP order: {reference_number}")
        result = mp_service._mp_api.list_orders_raw(
            connection_ids=str(connection_id),
            account_id=319911,
            query=reference_number,
            page=1,
            limit=1
        )
        
        orders = result.get("orders", [])
        if orders:
            debug(f"→ Found MP order with {len(orders[0].get('products', []))} products")
            return orders[0]
        
        debug("→ MP order not found")
        return None
        
    except Exception as e:
        debug(f"→ Error getting MP order: {e}")
        return None


def _map_item_ids_to_real_items(
    order: OrderDTO,
    package_items: List[Dict[str, Any]],
    mp_order: Optional[Dict[str, Any]]
) -> List[RealItemDTO]:
    """
    Map item_id từ package với real_items thông qua Sapo MP order.
    
    Logic:
    1. MP order có products với variation_id (Shopee item_id) và sapo_variant_id
    2. Package items có model_id (Shopee item_id)
    3. Map: model_id -> variation_id -> sapo_variant_id -> real_items.variant_id
    
    Args:
        order: OrderDTO với real_items
        package_items: List items từ package (có model_id)
        mp_order: Sapo MP order (có products với variation_id và sapo_variant_id)
        
    Returns:
        List real_items thuộc package hiện tại
    """
    debug("=" * 60)
    debug("DEBUG: _map_item_ids_to_real_items được gọi")
    debug(f"  package_items count: {len(package_items) if package_items else 0}")
    debug(f"  mp_order: {mp_order is not None}")
    debug(f"  order.real_items count: {len(order.real_items)}")
    debug("=" * 60)
    
    if not package_items:
        # Nếu không có package items, trả về toàn bộ real_items (fallback)
        debug("→ No package items, returning all real_items")
        return order.real_items
    
    if not mp_order:
        # Nếu không có MP order, không thể map -> trả về toàn bộ real_items (fallback)
        debug("→ No MP order, returning all real_items")
        return order.real_items
    
    # DEBUG: In ra các item_id trong package
    debug("=" * 60)
    debug("DEBUG: Package Items (item_id từ Shopee)")
    debug("=" * 60)
    for idx, item in enumerate(package_items, 1):
        model_id = str(item.get("model_id", ""))
        quantity = item.get("quantity", 0)
        debug(f"  [{idx}] item_id (model_id): {model_id}, quantity: {quantity}")
    debug("=" * 60)
    
    # Tạo map: variation_id -> sapo_variant_id
    variation_to_sapo_variant = {}
    debug("=" * 60)
    debug("DEBUG: Sapo MP Order Products (variation_id -> sapo_variant_id)")
    debug("=" * 60)
    for idx, product in enumerate(mp_order.get("products", []), 1):
        variation_id = str(product.get("variation_id", ""))
        sapo_variant_id = product.get("sapo_variant_id")
        item_name = product.get("item_name", "")
        sku = product.get("sku", "")
        if variation_id and sapo_variant_id:
            variation_to_sapo_variant[variation_id] = sapo_variant_id
            debug(f"  [{idx}] variation_id: {variation_id} -> sapo_variant_id: {sapo_variant_id}, SKU: {sku}")
        else:
            debug(f"  [{idx}] SKIP: variation_id={variation_id}, sapo_variant_id={sapo_variant_id} (missing data)")
    debug("=" * 60)
    
    # Tạo map: model_id -> quantity trong package
    package_items_map = {}
    for item in package_items:
        model_id = str(item.get("model_id", ""))
        quantity = item.get("quantity", 0)
        if model_id:
            package_items_map[model_id] = package_items_map.get(model_id, 0) + quantity
    
    # DEBUG: Kiểm tra match giữa package items và MP order
    debug("=" * 60)
    debug("DEBUG: Matching Package Items với Sapo Variants")
    debug("=" * 60)
    unmatched_item_ids = []
    for model_id, pkg_quantity in package_items_map.items():
        if model_id in variation_to_sapo_variant:
            sapo_variant_id = variation_to_sapo_variant[model_id]
            debug(f"  ✓ MATCH: item_id={model_id} -> sapo_variant_id={sapo_variant_id}, qty={pkg_quantity}")
        else:
            unmatched_item_ids.append(model_id)
            debug(f"  ✗ NO MATCH: item_id={model_id} (không tìm thấy trong MP order products), qty={pkg_quantity}")
    
    if unmatched_item_ids:
        debug("=" * 60)
        debug("❌ ERROR: Có item_id trong package không match với MP order:")
        for item_id in unmatched_item_ids:
            debug(f"  - item_id: {item_id}, quantity: {package_items_map.get(item_id, 0)}")
        debug("=" * 60)
    else:
        debug("  ✓ Tất cả item_id đều match!")
    debug("=" * 60)
    
    # DEBUG: In ra real_items để so sánh
    debug("=" * 60)
    debug("DEBUG: Real Items từ OrderDTO")
    debug("=" * 60)
    for idx, real_item in enumerate(order.real_items, 1):
        debug(f"  [{idx}] variant_id={real_item.variant_id}, old_id={real_item.old_id}, sku={real_item.sku}, qty={real_item.quantity}")
    debug("=" * 60)
    
    # Tìm các real_items có variant_id hoặc old_id match với sapo_variant_id
    matched_items = []
    debug("=" * 60)
    debug("DEBUG: Mapping Real Items với Package Items")
    debug("=" * 60)
    for real_item in order.real_items:
        matched = False
        matched_quantity = 0
        
        # Kiểm tra variant_id
        if real_item.variant_id in variation_to_sapo_variant.values():
            # Tìm variation_id tương ứng
            for variation_id, sapo_variant_id in variation_to_sapo_variant.items():
                if sapo_variant_id == real_item.variant_id and variation_id in package_items_map:
                    matched_quantity = package_items_map[variation_id]
                    # Tạo copy của real_item với quantity từ package
                    matched_item = RealItemDTO(
                        variant_id=real_item.variant_id,
                        old_id=real_item.old_id,
                        product_id=real_item.product_id,
                        sku=real_item.sku,
                        barcode=real_item.barcode,
                        variant_options=real_item.variant_options,
                        quantity=matched_quantity,  # Quantity từ package
                        unit=real_item.unit,
                        product_name=real_item.product_name,
                    )
                    matched_items.append(matched_item)
                    debug(f"  ✓ MATCHED: variant_id={real_item.variant_id}, sku={real_item.sku}, qty={matched_quantity} (from package)")
                    matched = True
                    break
        
        # Kiểm tra old_id (cho combo items) - chỉ nếu chưa match
        if not matched and real_item.old_id and real_item.old_id in variation_to_sapo_variant.values():
            for variation_id, sapo_variant_id in variation_to_sapo_variant.items():
                if sapo_variant_id == real_item.old_id and variation_id in package_items_map:
                    matched_quantity = package_items_map[variation_id]
                    matched_item = RealItemDTO(
                        variant_id=real_item.variant_id,
                        old_id=real_item.old_id,
                        product_id=real_item.product_id,
                        sku=real_item.sku,
                        barcode=real_item.barcode,
                        variant_options=real_item.variant_options,
                        quantity=matched_quantity,  # Quantity từ package
                        unit=real_item.unit,
                        product_name=real_item.product_name,
                    )
                    matched_items.append(matched_item)
                    debug(f"  ✓ MATCHED (via old_id): old_id={real_item.old_id}, variant_id={real_item.variant_id}, sku={real_item.sku}, qty={matched_quantity} (from package)")
                    matched = True
                    break
        
        if not matched:
            debug(f"  ✗ NO MATCH: variant_id={real_item.variant_id}, old_id={real_item.old_id}, sku={real_item.sku} (không có trong package)")
    
    debug("=" * 60)
    
    if not matched_items:
        # Nếu không match được, trả về toàn bộ real_items (fallback)
        debug("→ No matched items, returning all real_items")
        return order.real_items
    
    debug(f"→ Mapped {len(matched_items)} real_items to package")
    return matched_items


# ===================================================================
# RESOLVE COVER PATH
# ===================================================================

def _resolve_cover_path(shop_name: str, shipping_carrier: str) -> Path:
    """
    Chọn file cover theo DVVC, theo cấu trúc:
    logs/print-cover/<tên shop>/dvvc/<ten-file>.pdf

    Đang map theo tên DVVC (string):
    - chứa "spx" / "shopee xpress"     -> shopee-express-cover.pdf
    - chứa "j&t"                       -> jat-express-cover.pdf
    - chứa "ninja"                     -> ninja-cover.pdf
    - chứa "ghn" / "giao hàng nhanh"  -> ghn-cover.pdf
    - chứa "grab" / "instant" / "ahamove" / "bedelivery" -> hoatoc.pdf
    - còn lại                          -> khac.pdf
    """
    debug("→ Resolve cover path:", shop_name, shipping_carrier)

    base_dir = Path("settings") / "logs/print-cover" / shop_name
    sc = (shipping_carrier or "").lower()

    # Kiểm tra hoả tốc trước (ưu tiên cao nhất)
    # Bao gồm: Grab, beDelivery, Ahamove, Instant, Hoả Tốc - Trong ngày, SPX Express - Trong ngày, Ahamove - Giao trong ngày
    if any(x in sc for x in ["grab", "instant", "ahamove", "bedelivery", "hoả tốc", "hoa toc", "trong ngày", "giao trong ngày"]):
        fname = "hoatoc.pdf"
    elif ("spx" in sc or "shopee xpress" in sc) and "Instant" not in sc and "trong ngày" not in sc:
        fname = "shopee-express-cover.pdf"
    elif "j&t" in sc or "j & t" in sc:
        fname = "jat-express-cover.pdf"
    elif "ninja" in sc:
        fname = "ninja-cover.pdf"
    elif "ghn" in sc or "giao hàng nhanh" in sc:
        fname = "ghn-cover.pdf"
    
    else:
        fname = "khac.pdf"

    path = base_dir / fname
    debug("→ Cover file:", path)
    return path


# ===================================================================
# MAIN SERVICE: GENERATE LABEL PDF
# ===================================================================

def generate_label_pdf_for_channel_order(
    connection_id: int,
    channel_order_number: str,
    shipping_carrier: str | None = None,
    order_dto: OrderDTO | None = None,  # NEW: OrderDTO với gifts đã apply
) -> bytes:
    """
    Lấy bill Shopee (Nguồn A) rồi xử lý lại:
    - Dò order_id từ channel_order_number qua /get_order_list_search_bar_hint
    - Gọi /get_package để lấy danh sách package + fulfillment_channel_id
    - Map fulfillment_channel_id -> tên DVVC từ file kênh
    - Gọi /logistics/create_sd_jobs + /download_sd_job để lấy file PDF vận đơn
    - Đắp cover + MVD custom (overlay) lên
    - Trả về bytes PDF cuối cùng
    
    Args:
        order_dto: OrderDTO with gifts already applied (optional, will fetch if not provided)
    """
    # DEBUG: Xác nhận hàm được gọi
    debug("=" * 60)
    debug("DEBUG: generate_label_pdf_for_channel_order được gọi")
    debug(f"  connection_id: {connection_id}")
    debug(f"  channel_order_number: {channel_order_number}")
    debug(f"  DEBUG flag: {DEBUG}")
    debug("=" * 60)

    debug("===============================")
    debug("=== GENERATE SHOPEE LABEL ===")
    debug("connection_id:", connection_id)
    debug("order:", channel_order_number)
    debug("shipping_carrier (input):", shipping_carrier)
    debug("===============================")

    # ----------------------------------------------------------
    # 1. SHOP CONFIG
    # ----------------------------------------------------------
    shop_cfg = get_shop_by_connection_id(int(connection_id))
    if not shop_cfg:
        raise RuntimeError(f"Không tìm thấy shop với connection_id={connection_id}")

    # ----------------------------------------------------------
    shop_name = shop_cfg["name"]
    seller_shop_id = int(shop_cfg["seller_shop_id"])
    debug("→ Shop name:", shop_name)
    debug("→ seller_shop_id:", seller_shop_id)
    
    # ----------------------------------------------------------
    # 2. SHOPEE CLIENT & ORDER ID
    # ----------------------------------------------------------
    client = ShopeeClient(shop_name)
    
    # Get Shopee order info (returns Dict with order_id, buyer_name, etc.)
    shopee_order_info = client.get_shopee_order_id(channel_order_number)
    SHOPEE_ID = shopee_order_info["order_id"]  # Extract order_id from Dict
    
    debug("→ Order ID:", SHOPEE_ID)
    logger.info(f"[ShopeePrintService] Order ID: {SHOPEE_ID}")
    
    #  ----------------------------------------------------------
    # 3. GET PACKAGE INFO
    # ----------------------------------------------------------
    package_info = client.get_package_info(SHOPEE_ID)
    package_list = package_info.get("package_list", [])
    
    if not package_list:
        raise RuntimeError(f"No packages found for order {SHOPEE_ID}")
    
    first_pack = package_list[0]
    channel_id = first_pack.get("fulfillment_channel_id") or first_pack.get("checkout_channel_id")
    
    # ----------------------------------------------------------
    channels_map = _load_shipping_channels()
    resolved_carrier = shipping_carrier  # nếu có truyền từ ngoài thì ưu tiên

    if not resolved_carrier:
        carrier_name_from_file = None
        if channels_map and channel_id:
            ch = channels_map.get(int(channel_id))  # type: ignore[arg-type]
            if ch:
                carrier_name_from_file = ch.get("display_name") or ch.get("name")

        if carrier_name_from_file:
            resolved_carrier = carrier_name_from_file
            debug("→ Resolved DVVC từ file kênh:", resolved_carrier)
        else:
            # fallback: lấy text ngay trong package
            resolved_carrier = (
                first_pack.get("fulfillment_carrier_name")
                or first_pack.get("checkout_carrier_name")
            )
            debug("→ Fallback DVVC từ package:", resolved_carrier)

    debug("→ shipping_carrier (final):", resolved_carrier)

    # ----------------------------------------------------------
    # COVER + MVD
    # ----------------------------------------------------------
    cover_path = _resolve_cover_path(shop_name, resolved_carrier or "")
    cover_page = None

    if cover_path.exists():
        try:
            cover_reader = PyPDF2.PdfReader(str(cover_path))
            cover_page = cover_reader.pages[0]
            debug("→ Cover loaded OK.")
        except Exception as e:
            debug("→ Cover load error:", e)
    else:
        debug("→ NO COVER FOUND.")

    # ----------------------------------------------------------
    # 5. LOOP PACKAGE → GET LABEL → MERGE
    # ----------------------------------------------------------
    final_writer = PyPDF2.PdfWriter()
    DON_TACH_FLAG = len(package_list)  # Số kiện hàng của đơn hàng

    for pack in package_list:
        package_number = pack["package_number"]
        debug("----- PACKAGE:", package_number, "-----")

        create_job_url = "https://banhang.shopee.vn/api/v3/logistics/create_sd_jobs"

        json_body: Dict[str, Any] = {
            "group_list": [
                {
                    "primary_package_number": package_number,
                    "group_shipment_id": 0,
                    "package_list": [
                        {"order_id": SHOPEE_ID, "package_number": package_number}
                    ],
                }
            ],
            "region_id": "VN",
            "shop_id": seller_shop_id,
            # cái này là "schema in" trên Shopee cho thermal PDF
            "channel_id": 50021,
            "record_generate_schema": False,
            "generate_file_details": [
                {
                    "file_type": "THERMAL_PDF",
                    "file_name": "Phiếu gửi hàng",
                    "file_contents": [3],
                }
            ],
        }

        debug("→ POST create_sd_jobs")
        resp = client.session.post(create_job_url, json=json_body)
        debug("→ Status create_sd_jobs:", resp.status_code)
        resp.raise_for_status()

        job_data = resp.json()
        try:
            # Kiểm tra cấu trúc response
            if "data" not in job_data:
                debug("create_sd_jobs response không có 'data':", job_data)
                raise RuntimeError(f"Response không có 'data': {job_data}")
            
            data = job_data["data"]
            if "list" not in data or not data["list"]:
                debug("create_sd_jobs 'data.list' rỗng hoặc không tồn tại:", job_data)
                raise RuntimeError(f"Response 'data.list' rỗng: {job_data}")
            
            job_id = data["list"][0]["job_id"]
            if not job_id:
                debug("create_sd_jobs job_id rỗng:", job_data)
                raise RuntimeError(f"job_id rỗng trong response: {job_data}")
        except (KeyError, IndexError, TypeError) as e:
            debug("create_sd_jobs raw:", job_data)
            debug("create_sd_jobs error:", str(e))
            raise RuntimeError(f"Không lấy được job_id từ response: {e}. Response: {job_data}")

        debug("→ job_id:", job_id)

        # Download job
        dl_url = (
            "https://banhang.shopee.vn/api/v3/logistics/download_sd_job"
            f"?job_id={job_id}&is_first_time=1"
        )
        debug("→ download:", dl_url)

        pdf_bytes = None
        for i in range(10):
            dl_resp = client.session.get(dl_url)
            debug("→ dl status:", dl_resp.status_code, "len:", len(dl_resp.content))
            if dl_resp.status_code == 200 and len(dl_resp.content) > 1000:
                pdf_bytes = dl_resp.content
                break
            debug("→ retry download...", i + 1)
            time.sleep(2)

        if not pdf_bytes:
            raise RuntimeError("Download SD job thất bại.")

        debug("→ label size:", len(pdf_bytes))

        # Build MVD overlay cho package hiện tại (mỗi package có overlay riêng với parcel_no)
        mvd_page = _build_mvd_overlay_page(
            channel_order_number, 
            resolved_carrier,
            order_dto=order_dto,  # Pass OrderDTO với gifts
            current_package=pack,  # Pass package hiện tại
            total_packages=DON_TACH_FLAG,  # Pass tổng số package
            client=client,  # Pass ShopeeClient
            shopee_order_id=SHOPEE_ID,  # Pass Shopee order ID
            seller_shop_id=seller_shop_id,  # Pass seller shop ID
            connection_id=connection_id,  # Pass connection ID
        )
        debug(f"→ MVD overlay built for package {pack.get('package_number', '')}", channel_order_number, resolved_carrier)

        # Merge cover + MVD
        base_reader = PyPDF2.PdfReader(BytesIO(pdf_bytes), strict=False)
        for page in base_reader.pages:
            merged = page

            if cover_page:
                merged.merge_page(cover_page)

            merged.merge_page(mvd_page)

            final_writer.add_page(merged)

    # ----------------------------------------------------------
    # 6. Xuất bytes PDF cuối
    # ----------------------------------------------------------
    debug("→ Writing final PDF")

    output = BytesIO()
    final_writer.write(output)
    output.seek(0)

    debug("=== DONE generate_label_pdf_for_channel_order ===")

    return output.getvalue()


def wrap_text(text, font_name, font_size, max_width):
    words = text.split(" ")
    lines = []
    current_line = ""

    for word in words:
        test_line = word if current_line == "" else current_line + " " + word
        if pdfmetrics.stringWidth(test_line, font_name, font_size) <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines


def draw_label_with_bg(c, x, y, text,
                       font_name="Arial",
                       font_size=9,
                       padding_x=4,
                       padding_y=2,
                       max_width=200):   # max_width theo PTS (tự chỉnh)
    
    c.setFont(font_name, font_size)

    # 1. Tách dòng theo max-width
    lines = wrap_text(text, font_name, font_size, max_width)

    # 2. Tính thông số
    text_height = font_size
    padding_bottom = padding_y + 2  # Padding-bottom tăng thêm 2 để tránh overflow
    total_height = len(lines) * text_height + padding_y + padding_bottom
    max_line_width = max(pdfmetrics.stringWidth(line, font_name, font_size) for line in lines)

    bg_x = x - padding_x
    bg_y = y - padding_y
    bg_w = max_line_width + padding_x * 2
    bg_h = total_height

    # 3. Vẽ nền đen
    c.setFillColorRGB(0, 0, 0)
    c.roundRect(bg_x, bg_y, bg_w, bg_h, radius=3, fill=1, stroke=0)

    # 4. Vẽ chữ từng dòng (trắng)
    c.setFillColorRGB(1, 1, 1)
    draw_y = y + (len(lines)-1) * text_height  # Vẽ từ trên xuống

    for line in lines:
        c.drawString(x, draw_y, line)
        draw_y -= text_height
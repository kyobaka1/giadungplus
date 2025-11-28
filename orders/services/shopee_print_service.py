# File: orders/services/shopee_print_service.py

import json
import time
import logging
from io import BytesIO
from typing import Any, Dict, List
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
from orders.services.sapo_service import (
    SapoMarketplaceService,
    SapoCoreOrderService,
)
from orders.services.dto import OrderDTO

# Logger
logger = logging.getLogger(__name__)

# =========================
# DEBUG CONFIG
# =========================
DEBUG = True
def debug(*args):
    if DEBUG:
        print("[SHOPEE_PRINT]", *args)


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
    order_dto: OrderDTO | None = None  # NEW: Accept OrderDTO from caller
):
    """
    Tạo trang MVD overlay – in mã đơn + shop lên trên label.
    
    Args:
        order_dto: OrderDTO with gifts already applied (optional, will fetch if not provided)
    """
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
):

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
            "deadline1": 87, "deadline2": 212
        },
        "jnt": {
            "y_start_1": 182,
            "deadline1": -15, "deadline2": 80
        },
        "ninja": {
            "y_start_1": 172,
            "deadline1": -5, "deadline2": 50
        },
        "ghn": {
            "y_start_1": 185, "kho_11":-35,"kho_12":265,"kho_21":-35,"kho_22":255,"kho_31":-35,"kho_32":231,
            "deadline1": 87, "deadline2": 230        },
        "hoatoc": {
            "y_start_1": 170
        },
        "khac": {
            "y_start_1": 170
        }
    }
    y_value = config[sc]["y_start_1"]

    count_line = len(order.order_line_items) + len(order.gifts)
    line_spacing = 12 if count_line > 6 else int(60 / max(1, count_line))
    if line_spacing < 11:
        line_spacing = 10
    if line_spacing > 30:
        line_spacing = 20

    count = 0
    for x in order.order_line_items:
        if count < 10:
            line_order = f"** {int(x.quantity)} cái - {x.sku} - {x.variant_options}"
            line_order = line_order[:53]
            c.setFont('Arial', 8)
            c.drawString(-32, y_value, line_order)

            # In tên của sản phẩm
            if count_line <= 5:
                y_value -= 10
                c.setFont('ArialI', 7)
                c.drawString(-32, y_value, x.product_name.split("/")[0])

            y_value -= line_spacing

        count += 1

    """
    In quà tặng có trong đơn hàng.
    """
    if len(order.gifts) > 0:
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

    return c


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

    mvd_page = _build_mvd_overlay_page(
        channel_order_number, 
        resolved_carrier,
        order_dto=order_dto  # Pass OrderDTO với gifts
    )
    debug(f"→ MVD overlay built.", channel_order_number, resolved_carrier)

    # ----------------------------------------------------------
    # 5. LOOP PACKAGE → GET LABEL → MERGE
    # ----------------------------------------------------------
    final_writer = PyPDF2.PdfWriter()

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

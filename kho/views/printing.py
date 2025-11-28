# kho/views/printing.py
from django.shortcuts import render
from django.http import HttpResponse, HttpRequest
from django.contrib.auth.decorators import login_required
from typing import Dict, Any
import logging
import re

from core.sapo_client import get_sapo_client
from products.services.sapo_product_service import SapoProductService
from products.brand_settings import (
    is_brand_enabled,
    reload_settings,
    sync_brands_from_api
)

logger = logging.getLogger(__name__)


@login_required
def sorry_letter(request):
    """
    Thư xin lỗi:
    - Form nhập thông tin khách hàng, sản phẩm thiếu, cách xử lý
    - Preview thư xin lỗi theo mẫu
    - In thư để gửi kèm đơn hàng
    """
    # Get form data from GET parameters
    save = {
        'username': request.GET.get('username', ''),
        'shop_name': request.GET.get('shop_name', 'Gia Dụng Plus Official'),
        'sanphamthieu': request.GET.get('sanphamthieu', ''),
        'phuonganxuly': request.GET.get('phuonganxuly', ''),
    }
    
    context = {
        "title": "In Thư Xin Lỗi - GIA DỤNG PLUS",
        "current_kho": request.session.get("current_kho", "geleximco"),
        "save": save,
    }
    return render(request, "kho/printing/sorry_letter.html", context)


@login_required
def sorry_letter_print(request):
    """
    Trang in thư xin lỗi - chỉ có nội dung in, không có base template
    """
    # Get form data from GET parameters
    save = {
        'username': request.GET.get('username', ''),
        'shop_name': request.GET.get('shop_name', 'Gia Dụng Plus Official'),
        'sanphamthieu': request.GET.get('sanphamthieu', ''),
        'phuonganxuly': request.GET.get('phuonganxuly', ''),
    }
    
    context = {
        "save": save,
    }
    return render(request, "kho/printing/sorry_letter_print.html", context)


@login_required
def product_barcode(request):
    """
    In barcode sản phẩm:
    - Lựa chọn SKU / scan SKU
    - In mã vạch theo template
    """
    if request.method == "POST":
        sku = request.POST.get("sku")
        quantity = int(request.POST.get("quantity", 1))
        
        # TODO: generate PDF/barcode image using python-barcode
        # import barcode
        # from barcode.writer import ImageWriter
        # ...
        
        return HttpResponse(f"Generate {quantity} barcodes for {sku}")

    context = {
        "title": "In Barcode Sản Phẩm - GIA DỤNG PLUS",
        "current_kho": request.session.get("current_kho", "geleximco"),
    }
    return render(request, "kho/printing/product_barcode.html", context)


def _parse_sku_for_sorting(sku: str) -> tuple:
    """
    Parse SKU để tạo sort key.
    
    Ví dụ: ER-0746-4XM -> (prefix='ER', number=746, suffix_num=4, suffix_letters='XM')
    
    Args:
        sku: SKU string (ví dụ: "ER-0746-4XM")
        
    Returns:
        Tuple (prefix, number, suffix_num, suffix_letters) để dùng cho sorting
    """
    if not sku:
        return ('', 0, 0, '')
    
    # Pattern: PREFIX-NUMBER-SUFFIX
    # Ví dụ: ER-0746-4XM, TG-0201-DEN
    parts = sku.split('-')
    
    if len(parts) < 2:
        # Không match pattern, trả về SKU gốc để sort alphabetically
        return (sku, 0, 0, '')
    
    prefix = parts[0]
    
    # Lấy phần số (có thể có leading zeros)
    try:
        number = int(parts[1])
    except (ValueError, IndexError):
        number = 0
    
    # Lấy suffix (phần cuối)
    if len(parts) >= 3:
        suffix = parts[2]
        # Parse suffix: 4XM -> (4, 'XM')
        suffix_match = re.match(r'^(\d+)([A-Za-z]*)$', suffix)
        if suffix_match:
            suffix_num = int(suffix_match.group(1))
            suffix_letters = suffix_match.group(2) or ''
        else:
            # Không match pattern số+chữ, dùng toàn bộ suffix
            suffix_num = 0
            suffix_letters = suffix
    else:
        suffix_num = 0
        suffix_letters = ''
    
    return (prefix, number, suffix_num, suffix_letters)


@login_required
def product(request: HttpRequest):
    """
    Danh sách sản phẩm (variants):
    - Hiển thị variants theo brand_id (mặc định = 833608)
    - Filter server-side để giảm tải
    - Có thể tìm kiếm theo SKU, barcode, tên
    - Sắp xếp theo SKU: nhóm theo mã số, sắp xếp suffix
    """
    # Brand ID mặc định
    DEFAULT_BRAND_ID = 833608
    
    # Lấy brand_id từ query param
    brand_id = request.GET.get('brand_id', str(DEFAULT_BRAND_ID))
    try:
        brand_id = int(brand_id)
    except (ValueError, TypeError):
        brand_id = DEFAULT_BRAND_ID
    
    context = {
        "title": "Danh sách sản phẩm",
        "variants": [],
        "total": 0,
        "selected_brand_id": brand_id,
        "brands": [],
        "current_kho": request.session.get("current_kho", "geleximco"),
    }

    try:
        # Reload settings trước để đảm bảo có dữ liệu mới nhất
        reload_settings()
        
        sapo_client = get_sapo_client()
        core_repo = sapo_client.core
        product_service = SapoProductService(sapo_client)
        
        # Lấy danh sách brands từ API search (đầy đủ hơn)
        brands_response = core_repo.list_brands_search_raw(page=1, limit=220)
        all_brands = brands_response.get("brands", [])
        
        # Đồng bộ brands mới từ API vào settings
        sync_brands_from_api(all_brands)
        
        # Lọc chỉ lấy brands được bật (enabled)
        enabled_brands = [
            brand for brand in all_brands 
            if is_brand_enabled(brand.get("name", ""))
        ]
        context["brands"] = sorted(enabled_brands, key=lambda x: x.get("name", ""))
        
        # Lấy variants theo brand_id từ Sapo API (server-side filter)
        all_variants = []
        page = 1
        limit = 250  # Sapo API limit tối đa là 250
        expected_total = None  # Sẽ được set từ metadata của page đầu tiên
        
        logger.info(f"[kho:product] Starting to fetch variants for brand_id={brand_id}")
        
        while True:
            variants_response = core_repo.list_variants_raw(
                page=page,
                limit=limit,
                brand_ids=brand_id,
                # Không filter status để lấy cả active và inactive
                composite=False,
                packsize=False
            )
            
            variants_data = variants_response.get("variants", [])
            
            # Lấy metadata từ page đầu tiên để biết tổng số
            metadata = variants_response.get("metadata", {})
            if page == 1:
                expected_total = metadata.get("total", 0)
                logger.info(f"[kho:product] Total variants expected: {expected_total}")
            
            # Nếu không còn variants nào, dừng
            if not variants_data:
                logger.info(f"[kho:product] No more variants at page {page}")
                break
            
            all_variants.extend(variants_data)
            logger.info(f"[kho:product] Fetched page {page}: {len(variants_data)} variants (total so far: {len(all_variants)}/{expected_total or 'unknown'})")
            
            # Kiểm tra nếu đã lấy đủ số lượng
            if expected_total and expected_total > 0:
                if len(all_variants) >= expected_total:
                    logger.info(f"[kho:product] Fetched all {expected_total} variants")
                    break
            else:
                # Nếu không có total trong metadata, tính total_pages
                total_pages = metadata.get("total_pages")
                if total_pages:
                    if page >= total_pages:
                        logger.info(f"[kho:product] Reached last page ({total_pages}), total variants: {len(all_variants)}")
                        break
                else:
                    # Tính total_pages từ total và limit
                    if expected_total and expected_total > 0:
                        calculated_pages = (expected_total + limit - 1) // limit  # Ceiling division
                        if page >= calculated_pages:
                            logger.info(f"[kho:product] Reached calculated last page ({calculated_pages}), total variants: {len(all_variants)}")
                            break
            
            # Nếu số variants trả về ít hơn limit, có nghĩa là đã hết
            if len(variants_data) < limit:
                logger.info(f"[kho:product] Received fewer variants than limit ({len(variants_data)} < {limit}), assuming last page")
                break
            
            page += 1
            
            # Safety limit để tránh vòng lặp vô hạn
            if page > 100:
                logger.warning(f"[kho:product] Reached safety limit of 100 pages, stopping")
                break
        
        # Lấy product metadata cho từng variant để có GDP metadata
        # Tạo map product_id -> product để tránh gọi API nhiều lần
        product_map = {}
        product_ids = set(v.get("product_id") for v in all_variants if v.get("product_id"))
        
        # Lấy products theo batch (mỗi lần 50 để tránh quá tải)
        product_ids_list = list(product_ids)
        batch_size = 50
        for i in range(0, len(product_ids_list), batch_size):
            batch_ids = product_ids_list[i:i+batch_size]
            for product_id in batch_ids:
                try:
                    product = product_service.get_product(product_id)
                    if product:
                        product_map[product_id] = product
                except Exception as e:
                    logger.warning(f"Failed to get product {product_id}: {e}")
                    continue
        
        # Parse variants và lấy metadata
        variants_data = []
        brands_set = set()
        statuses_set = set()
        
        for variant_raw in all_variants:
            variant_id = variant_raw.get("id")
            product_id = variant_raw.get("product_id")
            
            # Lấy product để có brand và metadata
            product = product_map.get(product_id)
            if not product:
                # Nếu không lấy được product, dùng dữ liệu từ variant_raw
                brand = variant_raw.get("brand") or ""
            else:
                brand = product.brand or ""
            
            # Chỉ thêm variants nếu nhãn hiệu được bật
            if brand and not is_brand_enabled(brand):
                continue
            
            if brand:
                brands_set.add(brand)
            
            variant_status = variant_raw.get("status", "")
            if variant_status:
                statuses_set.add(variant_status)
            
            # Lấy metadata từ product nếu có
            variant_meta = None
            nhanphu_info = None
            if product:
                # Lấy nhanphu_info từ product level
                if product.gdp_metadata:
                    nhanphu_info = product.gdp_metadata.nhanphu_info
                
                # Tìm variant trong product để lấy metadata
                for v in product.variants:
                    if v.id == variant_id:
                        variant_meta = v.gdp_metadata
                        break
            
            # Tính tổng inventory từ inventories
            inventories = variant_raw.get("inventories", [])
            total_inventory = sum(inv.get("on_hand", 0) for inv in inventories)
            total_available = sum(inv.get("available", 0) for inv in inventories)
            
            variants_data.append({
                "id": variant_id,
                "product_id": product_id,
                "product_name": product.name if product else variant_raw.get("name", "").split(" - ")[0] if variant_raw.get("name") else "",
                "brand": brand,
                "sku": variant_raw.get("sku", ""),
                "barcode": variant_raw.get("barcode") or "",
                "name": variant_raw.get("name", ""),
                "opt1": variant_raw.get("option1") or "",
                "opt2": variant_raw.get("option2") or "",
                "opt3": variant_raw.get("option3") or "",
                "status": variant_status,
                "variant_retail_price": variant_raw.get("retail_price", 0) or 0,
                "variant_whole_price": variant_raw.get("wholesale_price", 0) or 0,
                "total_inventory": total_inventory,
                "total_available": total_available,
                "weight_value": variant_raw.get("weight_value", 0) or 0,
                "weight_unit": variant_raw.get("weight_unit", "g"),
                "gdp_metadata": variant_meta,
                # Extract metadata fields
                "price_tq": variant_meta.price_tq if variant_meta else None,
                "sku_tq": variant_meta.sku_tq if variant_meta else None,
                "name_tq": variant_meta.name_tq if variant_meta else None,
                "sku_model_xnk": variant_meta.sku_model_xnk if variant_meta else None,
                "box_info": variant_meta.box_info if variant_meta else None,
                "packed_info": variant_meta.packed_info if variant_meta else None,
                "nhanphu_info": nhanphu_info,
            })
        
        # Sắp xếp variants theo SKU: nhóm theo mã số, sắp xếp suffix
        # Ví dụ: ER-0746-4XM, ER-0746-5XM, ER-0746-6XM, ER-0746-4XR, ER-0746-5XR
        variants_data.sort(key=lambda v: _parse_sku_for_sorting(v.get("sku", "")))
        
        logger.info(f"[kho:product] Sorted {len(variants_data)} variants by SKU pattern")
        
        # Luôn hiển thị tất cả variants
        context["variants"] = variants_data
        context["total"] = len(variants_data)
        context["total_variants"] = len(variants_data)
        context["statuses"] = sorted(list(statuses_set))

    except Exception as e:
        logger.error(f"Error in kho:product: {e}", exc_info=True)
        context["error"] = str(e)

    return render(request, "kho/products/product_list.html", context)


@login_required
def print_product_label(request: HttpRequest):
    """
    In nhãn phụ sản phẩm - kích thước A7 (74mm x 105mm)
    """
    try:
        variant_id = request.GET.get('variant_id')
        quantity = int(request.GET.get('quantity', 1))
        
        if not variant_id:
            return HttpResponse("Thiếu variant_id", status=400)
        
        sapo_client = get_sapo_client()
        core_repo = sapo_client.core
        product_service = SapoProductService(sapo_client)
        
        # Lấy variant
        variant_response = core_repo.get_variant_raw(int(variant_id))
        variant_raw = variant_response.get("variant", {})
        
        if not variant_raw:
            return HttpResponse(f"Variant {variant_id} không tồn tại", status=404)
        
        product_id = variant_raw.get("product_id")
        product = product_service.get_product(product_id)
        
        if not product:
            return HttpResponse(f"Product {product_id} không tồn tại", status=404)
        
        # Lấy brand info
        brand_name = product.brand or ""
        brand_id = variant_raw.get("brand_id")
        
        # Lấy supplier info (NSX) - tạm thời để trống, có thể bổ sung sau
        nsx_name = ""
        nsx_diachi = ""
        
        # Lấy nhanphu_info từ product metadata
        nhanphu_info = None
        if product.gdp_metadata and product.gdp_metadata.nhanphu_info:
            nhanphu_info = product.gdp_metadata.nhanphu_info
        
        # Tìm variant metadata
        variant_meta = None
        for v in product.variants:
            if v.id == int(variant_id):
                variant_meta = v.gdp_metadata
                break
        
        # Chuẩn bị dữ liệu variant
        sku = variant_raw.get("sku", "")
        skugon = sku[3:] if len(sku) > 3 else sku
        barcode = variant_raw.get("barcode") or ""
        opt1 = variant_raw.get("option1") or ""
        opt2 = variant_raw.get("option2") or ""
        opt3 = variant_raw.get("option3") or ""
        
        vari_list = []
        for i in range(quantity):
            vari_data = {
                "id": int(variant_id),
                "sku": sku,
                "skugon": skugon,
                "barcode": barcode,
                "opt1": opt1,
                "opt2": opt2,
                "opt3": opt3,
                "brand": brand_name.lower(),
                "vi_name": nhanphu_info.vi_name if nhanphu_info and nhanphu_info.vi_name else "",
                "en_name": nhanphu_info.en_name if nhanphu_info and nhanphu_info.en_name else "",
                "descreption": nhanphu_info.description if nhanphu_info and nhanphu_info.description else "",
                "material": nhanphu_info.material if nhanphu_info and nhanphu_info.material else "",
                "nsx_name": nsx_name,
                "nsx_diachi": nsx_diachi,
            }
            vari_list.append(vari_data)
        
        context = {
            "vari_list": vari_list,
            "size": "a7"
        }
        
        return render(request, "kho/products/print_label.html", context)
        
    except Exception as e:
        logger.error(f"Error in print_product_label: {e}", exc_info=True)
        return HttpResponse(f"Lỗi: {str(e)}", status=500)


@login_required
def print_product_barcode(request: HttpRequest):
    """
    In barcode sản phẩm - kích thước 5x7cm (50mm x 70mm)
    """
    try:
        variant_id = request.GET.get('variant_id')
        quantity = int(request.GET.get('quantity', 1))
        
        if not variant_id:
            return HttpResponse("Thiếu variant_id", status=400)
        
        sapo_client = get_sapo_client()
        core_repo = sapo_client.core
        product_service = SapoProductService(sapo_client)
        
        # Lấy variant
        variant_response = core_repo.get_variant_raw(int(variant_id))
        variant_raw = variant_response.get("variant", {})
        
        if not variant_raw:
            return HttpResponse(f"Variant {variant_id} không tồn tại", status=404)
        
        # Lấy product để có đầy đủ thông tin variant (bao gồm opt1, opt2, opt3)
        product_id = variant_raw.get("product_id")
        product = None
        variant_from_product = None
        
        if product_id:
            try:
                product = product_service.get_product(product_id)
                if product:
                    # Tìm variant trong product để lấy đầy đủ thông tin
                    for v in product.variants:
                        if v.id == int(variant_id):
                            variant_from_product = v
                            break
            except Exception as e:
                logger.warning(f"Không thể lấy product {product_id}: {e}")
        
        # Chuẩn bị dữ liệu variant - ưu tiên lấy từ product variant, fallback về variant_raw
        sku = variant_raw.get("sku", "")
        barcode = variant_raw.get("barcode") or ""
        
        # Lấy option1, option2, option3 - ưu tiên từ product variant
        if variant_from_product:
            opt1 = variant_from_product.opt1 or ""
            opt2 = variant_from_product.opt2 or ""
            opt3 = variant_from_product.opt3 or ""
        else:
            opt1 = variant_raw.get("option1") or ""
            opt2 = variant_raw.get("option2") or ""
            opt3 = variant_raw.get("option3") or ""
        
        # Xử lý SKU: bỏ 2 tiền tố và dấu "-" đầu tiên
        # Ví dụ: "CB-0630-DEN" -> "0630-DEN"
        sku_short = sku
        if "-" in sku:
            parts = sku.split("-", 1)  # Chỉ split 1 lần ở dấu "-" đầu tiên
            if len(parts) > 1:
                sku_short = parts[1]  # Lấy phần sau dấu "-" đầu tiên
        elif len(sku) > 2:
            sku_short = sku[2:]  # Bỏ 2 ký tự đầu nếu không có dấu "-"
        
        vari_list = []
        for i in range(quantity):
            vari_data = {
                "id": int(variant_id),
                "sku": sku,
                "sku_short": sku_short,
                "barcode": barcode,
                "opt1": opt1,
                "opt2": opt2,
                "opt3": opt3,
            }
            vari_list.append(vari_data)
        
        context = {
            "vari_list": vari_list
        }
        
        return render(request, "kho/products/print_barcode.html", context)
        
    except Exception as e:
        logger.error(f"Error in print_product_barcode: {e}", exc_info=True)
        return HttpResponse(f"Lỗi: {str(e)}", status=500)


# Mapping trans_type sang tên hiển thị
TRANS_TYPE_LABELS = {
    '104': 'Nhập hàng từ nhà sản xuất',
    '200': 'Nhập kho',
    '201': 'Nhập kho khác',
    '301': 'Xuất kho',
    '302': 'Xuất kho giao hàng cho khách/shipper',
    '303': 'Xuất kho khác',
    '400': 'Điều chuyển kho',
    '401': 'Nhận hàng kho khác',
    '500': 'Điều chỉnh tồn kho',
    '501': 'Kiểm kê kho',
}

def get_trans_type_label(trans_type):
    """Lấy label cho trans_type"""
    trans_type_str = str(trans_type)
    return TRANS_TYPE_LABELS.get(trans_type_str, f'Loại {trans_type}')


@login_required
def get_variant_inventory_history(request: HttpRequest):
    """
    API endpoint để lấy lịch sử xuất nhập kho của variant từ Sapo.
    Lấy TOÀN BỘ lịch sử (fetch tất cả pages).
    
    Query params:
        - variant_id: int (required) - ID của variant
        - trans_type: str (optional) - Lọc theo loại giao dịch (104, 200, 301, ...)
        - source: str (optional) - Lọc theo lý do (source field) - tìm kiếm theo text
    """
    from django.http import JsonResponse
    
    try:
        variant_id = request.GET.get('variant_id')
        if not variant_id:
            return JsonResponse({'error': 'Thiếu variant_id'}, status=400)
        
        try:
            variant_id = int(variant_id)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'variant_id không hợp lệ'}, status=400)
        
        # Lấy location_id từ session (kho hiện tại)
        current_kho = request.session.get("current_kho", "geleximco")
        location_id = 241737 if current_kho == "geleximco" else 548744
        
        # Lấy filter params
        action_type_filter = request.GET.get('action_type')  # 'in' (nhập) hoặc 'out' (xuất)
        source_filter = request.GET.get('source')  # Lọc theo lý do
        
        # Gọi Sapo API để lấy lịch sử kho - LẤY TẤT CẢ PAGES
        sapo_client = get_sapo_client()
        core_repo = sapo_client.core
        
        all_inventories = []
        page = 1
        limit = 250  # Sapo API limit tối đa
        
        while True:
            params = {
                'page': page,
                'limit': limit,
                'location_ids': location_id
            }
            
            # Gọi API: /admin/reports/inventories/variants/{variant_id}.json
            url = f"reports/inventories/variants/{variant_id}.json"
            response = core_repo.get(url, params=params)
            
            # Parse response
            variant_inventories = response.get('variant_inventories', [])
            metadata = response.get('metadata', {})
            
            if not variant_inventories:
                break
            
            all_inventories.extend(variant_inventories)
            
            # Kiểm tra xem còn trang nào không
            total = metadata.get('total', 0)
            if len(all_inventories) >= total:
                break
            
            # Kiểm tra nếu số items trả về ít hơn limit thì đã hết
            if len(variant_inventories) < limit:
                break
            
            page += 1
            
            # Safety limit để tránh vòng lặp vô hạn
            if page > 100:
                logger.warning(f"Reached safety limit of 100 pages for variant {variant_id}")
                break
        
        # Áp dụng filters nếu có
        filtered_inventories = []
        for inv in all_inventories:
            # Filter theo action_type (nhập/xuất) dựa vào onhand_adj
            if action_type_filter:
                onhand_adj = float(inv.get('onhand_adj', 0) or 0)
                if action_type_filter == 'in' and onhand_adj <= 0:
                    continue
                if action_type_filter == 'out' and onhand_adj >= 0:
                    continue
            
            # Filter theo source (lý do) - tìm kiếm theo text
            if source_filter:
                source = inv.get('source', '')
                if source_filter.lower() not in source.lower():
                    continue
            
            filtered_inventories.append(inv)
        
        # Lấy location_label từ item đầu tiên (nếu có)
        location_label = ''
        if all_inventories:
            location_label = all_inventories[0].get('location_label', '')
        
        # Format dữ liệu để trả về
        result = {
            'status': 'success',
            'variant_id': variant_id,
            'location_id': location_id,
            'location_label': location_label,
            'data': filtered_inventories,
            'metadata': {
                'total': len(filtered_inventories),  # Total sau khi filter
                'original_total': len(all_inventories),  # Total từ API (tất cả pages)
            }
        }
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error in get_variant_inventory_history: {e}", exc_info=True)
        return JsonResponse({'error': f'Lỗi: {str(e)}'}, status=500)
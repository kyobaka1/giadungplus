from django.shortcuts import render, redirect, get_object_or_404
from kho.utils import admin_only
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from typing import List, Dict, Any
import logging
import io
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

from core.sapo_client import get_sapo_client
from products.services.sapo_product_service import SapoProductService
from products.services.dto import ProductDTO, ProductVariantDTO
from products.brand_settings import (
    get_disabled_brands,
    is_brand_enabled,
    get_enabled_brands,
    set_brand_enabled,
    reload_settings,
    sync_brands_from_api
)
from products.views_excel import export_variants_excel, import_variants_excel
from products.services.xnk_model_service import XNKModelService
import re

logger = logging.getLogger(__name__)

# Import loginss từ thamkhao để giữ nguyên cách lưu Model XNK
try:
    from thamkhao.apps import loginss
except ImportError:
    # Nếu không import được, sẽ dùng SapoClient.core_session
    loginss = None


@admin_only
def product_list(request: HttpRequest):
    """
    Danh sách sản phẩm:
    - Hiển thị danh sách TẤT CẢ sản phẩm từ Sapo (không phân trang)
    - Có thể tìm kiếm, lọc theo brand, category, status
    - Có thể sửa, xoá sản phẩm
    """
    context = {
        "title": "Danh sách sản phẩm",
        "products": [],
        "total": 0,
    }

    try:
        sapo_client = get_sapo_client()
        product_service = SapoProductService(sapo_client)

        # Lấy TẤT CẢ products (loop qua nhiều pages) - KHÔNG CÓ FILTER GÌ HẾT
        all_products = []
        page = 1
        limit = 250  # Lấy nhiều nhất có thể mỗi page
        
        while True:
            # Chỉ lấy dữ liệu, không có filter gì
            filters = {
                "page": page,
                "limit": limit,
            }
            
            products = product_service.list_products(**filters)
            
            if not products:
                break
            
            all_products.extend(products)
            
            # Nếu số lượng products < limit thì đã hết
            if len(products) < limit:
                break
            
            page += 1
            
            # Giới hạn tối đa 1000 pages để tránh vòng lặp vô hạn
            if page > 1000:
                logger.warning("Reached max pages limit (1000) in product_list")
                break

        # Reload settings để đảm bảo có dữ liệu mới nhất
        reload_settings()
        
        # Convert to dict for template và collect brands
        products_data = []
        brands_set = set()
        statuses_set = set()
        
        for product in all_products:
            brand = product.brand or ""
            product_status = product.status or ""
            
            # Chỉ thêm sản phẩm nếu nhãn hiệu được bật
            if brand and not is_brand_enabled(brand):
                continue  # Bỏ qua sản phẩm có nhãn hiệu bị tắt
            
            if brand:
                brands_set.add(brand)
            if product_status:
                statuses_set.add(product_status)
            
            products_data.append({
                "id": product.id,
                "name": product.name,
                "brand": brand,
                "category": product.category or "",
                "status": product_status,
                "variant_count": product.variant_count,
                "total_inventory": product.total_inventory_all_variants,
                "created_on": product.created_on,
                "modified_on": product.modified_on,
                "gdp_metadata": product.gdp_metadata,
            })

        context["products"] = products_data
        context["total"] = len(products_data)
        # Chỉ hiển thị nhãn hiệu đã bật trong filter
        context["brands"] = get_enabled_brands(sorted(list(brands_set)))
        context["statuses"] = sorted(list(statuses_set))  # Danh sách statuses để tạo filter buttons

    except Exception as e:
        logger.error(f"Error in product_list: {e}", exc_info=True)
        context["error"] = str(e)

    return render(request, "products/product_list.html", context)


@admin_only
def product_detail(request: HttpRequest, product_id: int):
    """
    Chi tiết sản phẩm:
    - Hiển thị thông tin chi tiết sản phẩm
    - Có thể sửa thông tin
    """
    context = {
        "title": "Chi tiết sản phẩm",
        "product": None,
    }

    try:
        sapo_client = get_sapo_client()
        product_service = SapoProductService(sapo_client)

        product = product_service.get_product(product_id)
        if not product:
            context["error"] = "Không tìm thấy sản phẩm"
            return render(request, "products/product_detail.html", context)

        context["product"] = product

    except Exception as e:
        logger.error(f"Error in product_detail: {e}", exc_info=True)
        context["error"] = str(e)

    return render(request, "products/product_detail.html", context)


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


@admin_only
def variant_list(request: HttpRequest):
    """
    Danh sách phân loại (variants):
    - Hiển thị variants theo brand_id (mặc định = 833608)
    - Filter server-side để giảm tải
    - Có thể tìm kiếm theo SKU, barcode, tên
    - Có thể sửa, xoá variant
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
        "title": "Danh sách phân loại",
        "variants": [],
        "total": 0,
        "selected_brand_id": brand_id,
        "brands": [],
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
        
        # Lấy products từ Sapo API (đã bao gồm variants và inventories)
        # Thử filter theo brand_id nếu API hỗ trợ, nếu không thì filter ở client-side
        all_products = []
        page = 1
        limit = 250  # Sapo API limit tối đa là 250
        
        logger.info(f"[variant_list] Starting to fetch products (with variants) for brand_id={brand_id}")
        
        while True:
            # Thử filter theo brand_id nếu API hỗ trợ
            filters = {
                "page": page,
                "limit": limit,
                "status": "active"  # Có thể bỏ nếu muốn lấy cả inactive
            }
            # Thử thêm brand_ids filter (có thể không hỗ trợ, nhưng thử xem)
            try:
                filters["brand_ids"] = brand_id
            except:
                pass
            
            products_response = core_repo.list_products_raw(**filters)
            products_data = products_response.get("products", [])
            
            if not products_data:
                logger.info(f"[variant_list] No more products at page {page}")
                break
            
            all_products.extend(products_data)
            logger.info(f"[variant_list] Fetched page {page}: {len(products_data)} products (total so far: {len(all_products)})")
            
            # Nếu số products trả về ít hơn limit, có nghĩa là đã hết
            if len(products_data) < limit:
                logger.info(f"[variant_list] Received fewer products than limit ({len(products_data)} < {limit}), assuming last page")
                break
            
            page += 1
            
            # Safety limit để tránh vòng lặp vô hạn
            if page > 100:
                logger.warning(f"[variant_list] Reached safety limit of 100 pages, stopping")
                break
        
        # Parse products và extract variants
        # Tạo map product_id -> product để parse metadata
        product_map = {}
        all_variants_from_products = []
        
        for product_data in all_products:
            product_id = product_data.get("id")
            if not product_id:
                continue
            
            # Lấy brand_id từ product_data (có sẵn trong JSON)
            brand_id_from_product = product_data.get("brand_id")
            
            # Parse product để có metadata
            try:
                product = product_service.get_product(product_id)
                if product:
                    product_map[product_id] = product
            except Exception as e:
                logger.warning(f"Failed to parse product {product_id}: {e}")
                # Vẫn dùng product_data nếu parse lỗi
                product = None
            
            # Extract variants từ product (đã có inventories sẵn)
            variants = product_data.get("variants", [])
            for variant_data in variants:
                variant_id = variant_data.get("id")
                if not variant_id:
                    continue
                
                # Lưu variant với product_id và brand_id để filter sau
                variant_data["_product_id"] = product_id
                variant_data["_brand_id"] = brand_id_from_product
                variant_data["_product"] = product  # Lưu product object nếu có
                all_variants_from_products.append(variant_data)
        
        logger.info(f"[variant_list] Extracted {len(all_variants_from_products)} variants from {len(all_products)} products")
        
        # Parse variants và lấy metadata, filter theo brand_id
        variants_data = []
        brands_set = set()
        statuses_set = set()
        
        for variant_data in all_variants_from_products:
            variant_id = variant_data.get("id")
            product_id = variant_data.get("_product_id")
            product = variant_data.get("_product")
            
            # Lấy brand_id từ variant_data (đã lưu từ product_data)
            variant_brand_id = variant_data.get("_brand_id")
            
            # Filter theo brand_id (client-side)
            if variant_brand_id != brand_id:
                continue
            
            # Lấy brand name từ product hoặc all_brands
            brand = ""
            if product:
                brand = product.brand or ""
            else:
                # Fallback: tìm brand name từ all_brands
                for b in all_brands:
                    if b.get("id") == variant_brand_id:
                        brand = b.get("name", "")
                        break
            
            # Chỉ thêm variants nếu nhãn hiệu được bật
            if brand and not is_brand_enabled(brand):
                continue
            
            if brand:
                brands_set.add(brand)
            
            variant_status = variant_data.get("status", "")
            if variant_status:
                statuses_set.add(variant_status)
            
            # Lấy metadata từ product nếu có
            variant_meta = None
            if product:
                # Tìm variant trong product để lấy metadata
                for v in product.variants:
                    if v.id == variant_id:
                        variant_meta = v.gdp_metadata
                        break
            
            # Sử dụng inventories từ variant_data (đã có sẵn trong products)
            inventories = variant_data.get("inventories", [])
            total_inventory = sum(inv.get("on_hand", 0) or 0 for inv in inventories)
            total_available = sum(inv.get("available", 0) or 0 for inv in inventories)
            
            # Lấy opt1, opt2, opt3 - kiểm tra cả opt1 và option1
            opt1_raw = variant_data.get("opt1")
            if opt1_raw is None:
                opt1_raw = variant_data.get("option1")
            opt1 = opt1_raw or ""
            
            opt2_raw = variant_data.get("opt2")
            if opt2_raw is None:
                opt2_raw = variant_data.get("option2")
            opt2 = opt2_raw or ""
            
            opt3_raw = variant_data.get("opt3")
            if opt3_raw is None:
                opt3_raw = variant_data.get("option3")
            opt3 = opt3_raw or ""
            
            # Lấy product name
            product_name = ""
            if product:
                product_name = product.name
            else:
                variant_name = variant_data.get("name", "")
                if variant_name:
                    product_name = variant_name.split(" - ")[0]
            
            variants_data.append({
                "id": variant_id,
                "product_id": product_id,
                "product_name": product_name,
                "brand": brand,
                "sku": variant_data.get("sku", ""),
                "barcode": variant_data.get("barcode") or "",
                "name": variant_data.get("name", ""),
                "opt1": opt1,
                "opt2": opt2,
                "opt3": opt3,
                "status": variant_status,
                "variant_retail_price": variant_data.get("variant_retail_price", 0) or 0,
                "variant_whole_price": variant_data.get("variant_whole_price", 0) or 0,
                "total_inventory": total_inventory,
                "total_available": total_available,
                "weight_value": variant_data.get("weight_value", 0) or 0,
                "weight_unit": variant_data.get("weight_unit", "g"),
                "gdp_metadata": variant_meta,
                # Extract metadata fields
                "price_tq": variant_meta.price_tq if variant_meta else None,
                "sku_tq": variant_meta.sku_tq if variant_meta else None,
                "name_tq": variant_meta.name_tq if variant_meta else None,
                "sku_model_xnk": variant_meta.sku_model_xnk if variant_meta else None,
                "box_info": variant_meta.box_info if variant_meta else None,
                "packed_info": variant_meta.packed_info if variant_meta else None,
            })
        
        # Sắp xếp variants theo SKU: nhóm theo mã số, sắp xếp suffix
        # Ví dụ: ER-0746-4XM, ER-0746-5XM, ER-0746-6XM, ER-0746-4XR, ER-0746-5XR
        variants_data.sort(key=lambda v: _parse_sku_for_sorting(v.get("sku", "")))
        
        logger.info(f"[variant_list] Sorted {len(variants_data)} variants by SKU pattern")
        
        # Luôn hiển thị tất cả variants
        context["variants"] = variants_data
        context["total"] = len(variants_data)
        context["total_variants"] = len(variants_data)
        context["statuses"] = sorted(list(statuses_set))

    except Exception as e:
        logger.error(f"Error in variant_list: {e}", exc_info=True)
        context["error"] = str(e)

    return render(request, "products/variant_list.html", context)


@admin_only
def variant_detail(request: HttpRequest, variant_id: int):
    """
    Chi tiết phân loại:
    - Hiển thị thông tin chi tiết variant
    - Có thể sửa thông tin
    """
    context = {
        "title": "Chi tiết phân loại",
        "variant": None,
    }

    try:
        sapo_client = get_sapo_client()
        core_repo = sapo_client.core

        # Lấy variant từ Sapo
        variant_response = core_repo.get_variant_raw(variant_id)
        variant_data = variant_response.get("variant")

        if not variant_data:
            context["error"] = "Không tìm thấy phân loại"
            return render(request, "products/variant_detail.html", context)

        # Lấy product để có thông tin đầy đủ
        product_id = variant_data.get("product_id")
        if product_id:
            product_service = SapoProductService(sapo_client)
            product = product_service.get_product(product_id)
            if product:
                # Tìm variant trong product
                for v in product.variants:
                    if v.id == variant_id:
                        context["variant"] = v
                        context["product"] = product
                        break

        if not context.get("variant"):
            context["error"] = "Không tìm thấy phân loại trong product"

    except Exception as e:
        logger.error(f"Error in variant_detail: {e}", exc_info=True)
        context["error"] = str(e)

    return render(request, "products/variant_detail.html", context)


@admin_only
@require_POST
def init_all_products_metadata(request: HttpRequest):
    """
    Init metadata cho sản phẩm.
    
    Endpoint: POST /products/init-all-metadata/
    
    Query parameters:
    - test_mode: true/false - Nếu true: init tất cả sản phẩm (kể cả đã có metadata)
                   Nếu false: chỉ init sản phẩm chưa có metadata
    
    Tự động init metadata cho products, thêm vào cuối description nếu có nội dung.
    """
    try:
        # Lấy test_mode từ request body hoặc query params
        test_mode = False
        if request.content_type == 'application/json':
            try:
                import json
                body = json.loads(request.body)
                test_mode = body.get('test_mode', False)
            except:
                pass
        else:
            test_mode = request.POST.get('test_mode', 'false').lower() == 'true'
        
        sapo_client = get_sapo_client()
        product_service = SapoProductService(sapo_client)
        
        # Lấy tất cả products (active)
        all_products = []
        page = 1
        limit = 250
        max_pages = 100  # Giới hạn để tránh quá tải
        
        while page <= max_pages:
            products = product_service.list_products(page=page, limit=limit, status="active")
            if not products:
                break
            all_products.extend(products)
            if len(products) < limit:
                break
            page += 1
        
        # Xác định products cần init
        products_to_init = []
        products_already_have = []
        products_skipped = []
        
        for product in all_products:
            if test_mode:
                # Test mode: init tất cả sản phẩm
                products_to_init.append(product.id)
            else:
                # Normal mode: chỉ init sản phẩm chưa có metadata
                if product.gdp_metadata:
                    products_already_have.append(product.id)
                else:
                    products_to_init.append(product.id)
        
        # Init metadata cho các products
        success_count = 0
        error_count = 0
        errors = []
        
        for product_id in products_to_init:
            try:
                # Nếu test_mode, force init bằng cách update trực tiếp
                if test_mode:
                    # Lấy product hiện tại
                    product = product_service.get_product(product_id)
                    if product:
                        # Tạo metadata mới với structure đầy đủ
                        from products.services.metadata_helper import init_empty_metadata
                        variant_ids = [v.id for v in product.variants]
                        metadata = init_empty_metadata(product_id, variant_ids)
                        
                        # Update metadata (preserve description nếu có)
                        success = product_service.update_product_metadata(
                            product_id, 
                            metadata, 
                            preserve_description=True
                        )
                        if success:
                            success_count += 1
                        else:
                            error_count += 1
                            errors.append(f"Product {product_id}: Failed to update")
                    else:
                        error_count += 1
                        errors.append(f"Product {product_id}: Not found")
                else:
                    # Normal mode: dùng init_product_metadata (chỉ init nếu chưa có)
                    success = product_service.init_product_metadata(product_id)
                    if success:
                        success_count += 1
                    else:
                        error_count += 1
                        errors.append(f"Product {product_id}: Failed to init")
            except Exception as e:
                error_count += 1
                errors.append(f"Product {product_id}: {str(e)}")
                logger.error(f"Error init metadata for product {product_id}: {e}", exc_info=True)
        
        return JsonResponse({
            "status": "success",
            "test_mode": test_mode,
            "total_products": len(all_products),
            "products_to_init": len(products_to_init),
            "products_already_have": len(products_already_have),
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors[:10] if len(errors) > 10 else errors,  # Chỉ trả về 10 lỗi đầu
        })
        
    except Exception as e:
        logger.error(f"Error in init_all_products_metadata: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


@admin_only
def brand_settings(request: HttpRequest):
    """
    Quản lý cài đặt nhãn hiệu (bật/tắt).
    - Hiển thị danh sách tất cả nhãn hiệu từ sản phẩm
    - Cho phép bật/tắt nhãn hiệu
    """
    context = {
        "title": "Cài đặt nhãn hiệu",
        "brands": [],
        "error": None,
    }
    
    try:
        # Reload settings trước để đảm bảo có dữ liệu mới nhất
        reload_settings()
        
        # Lấy tất cả nhãn hiệu từ API search (đầy đủ hơn)
        sapo_client = get_sapo_client()
        core_repo = sapo_client.core
        
        # Lấy brands từ API search
        brands_response = core_repo.list_brands_search_raw(page=1, limit=220)
        all_brands = brands_response.get("brands", [])
        
        # Đồng bộ brands mới từ API vào settings (tự động thêm brands mới)
        sync_brands_from_api(all_brands)
        
        # Reload lại settings sau khi sync
        reload_settings()
        
        # Lấy danh sách nhãn hiệu bị tắt
        disabled_brands = get_disabled_brands()
        
        # Tạo danh sách nhãn hiệu với trạng thái
        brands_data = []
        for brand in all_brands:
            brand_name = brand.get("name", "")
            if brand_name:
                brands_data.append({
                    "name": brand_name,
                    "id": brand.get("id"),
                    "is_enabled": is_brand_enabled(brand_name),
                })
        
        # Sắp xếp theo tên
        brands_data.sort(key=lambda x: x.get("name", ""))
        
        context["brands"] = brands_data
        context["disabled_count"] = len(disabled_brands)
        context["enabled_count"] = len(brands_data) - len(disabled_brands)
        
    except Exception as e:
        logger.error(f"Error in brand_settings: {e}", exc_info=True)
        context["error"] = str(e)
    
    return render(request, "products/brand_settings.html", context)


@admin_only
@require_POST
def toggle_brand(request: HttpRequest):
    """
    API để bật/tắt nhãn hiệu.
    
    POST data:
    - brand_name: Tên nhãn hiệu
    - enabled: true/false (bật/tắt)
    """
    try:
        # Lấy dữ liệu từ request
        if request.content_type == 'application/json':
            import json
            data = json.loads(request.body)
            brand_name = data.get('brand_name', '').strip()
            enabled = data.get('enabled', True)
        else:
            brand_name = request.POST.get('brand_name', '').strip()
            enabled = request.POST.get('enabled', 'true').lower() == 'true'
        
        if not brand_name:
            return JsonResponse({
                "status": "error",
                "message": "Tên nhãn hiệu không được để trống"
            }, status=400)
        
        # Cập nhật settings
        success = set_brand_enabled(brand_name, enabled)
        
        if success:
            return JsonResponse({
                "status": "success",
                "message": f"Đã {'bật' if enabled else 'tắt'} nhãn hiệu '{brand_name}'"
            })
        else:
            return JsonResponse({
                "status": "error",
                "message": "Không thể lưu cài đặt"
            }, status=500)
            
    except Exception as e:
        logger.error(f"Error in toggle_brand: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


@admin_only
@require_POST
def init_variants_from_old_notes(request: HttpRequest):
    """
    Init variant metadata từ dữ liệu cũ trong customer notes.
    
    Endpoint: POST /products/init-variants-from-old-notes/
    
    Body (JSON):
    - test_mode: true/false - Nếu true: chỉ log không update
    - limit: Số lượng variants tối đa để migrate (optional)
    """
    try:
        # Lấy parameters
        test_mode = False
        limit = None
        
        if request.content_type == 'application/json':
            try:
                import json
                body = json.loads(request.body)
                test_mode = body.get('test_mode', False)
                limit = body.get('limit')
            except:
                pass
        else:
            test_mode = request.POST.get('test_mode', 'false').lower() == 'true'
            limit_str = request.POST.get('limit')
            if limit_str:
                try:
                    limit = int(limit_str)
                except:
                    pass
        
        # Import migration service
        from products.services.variant_migration import init_variants_from_old_data
        
        # Thực hiện migration
        result = init_variants_from_old_data(test_mode=test_mode, limit=limit)
        
        return JsonResponse({
            "status": "success",
            "test_mode": test_mode,
            "result": result
        })
        
    except Exception as e:
        logger.error(f"Error in init_variants_from_old_notes: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


@admin_only
@require_POST
def update_variant_metadata(request: HttpRequest, variant_id: int):
    """
    API endpoint để cập nhật variant metadata.
    Chỉ cập nhật các field có thể edit: price_tq, sku_tq, name_tq, box_info, sku_model_xnk
    """
    try:
        # Lấy dữ liệu từ request body
        import json
        data = json.loads(request.body)
        
        sapo_client = get_sapo_client()
        product_service = SapoProductService(sapo_client)
        
        # Lấy variant để biết product_id
        variant_response = sapo_client.core.get_variant_raw(variant_id)
        variant = variant_response.get("variant", {})
        
        if not variant:
            return JsonResponse({
                "status": "error",
                "message": f"Variant {variant_id} không tồn tại"
            }, status=404)
        
        product_id = variant.get("product_id")
        if not product_id:
            return JsonResponse({
                "status": "error",
                "message": f"Variant {variant_id} không có product_id"
            }, status=400)
        
        # Lấy product hiện tại
        product = product_service.get_product(product_id)
        if not product:
            return JsonResponse({
                "status": "error",
                "message": f"Product {product_id} không tồn tại"
            }, status=404)
        
        # Lấy metadata hiện tại
        from products.services.metadata_helper import init_empty_metadata, update_variant_metadata
        from products.services.dto import VariantMetadataDTO, BoxInfoDTO, PackedInfoDTO, NhanPhuInfoDTO
        
        current_metadata = product.gdp_metadata
        if not current_metadata:
            variant_ids = [v.id for v in product.variants]
            current_metadata = init_empty_metadata(product_id, variant_ids)
        
        # Tìm variant metadata hiện tại
        variant_meta = None
        for vm in current_metadata.variants:
            if vm.id == variant_id:
                variant_meta = vm
                break
        
        if not variant_meta:
            variant_meta = VariantMetadataDTO(id=variant_id)
        
        # Helper functions
        def to_float_safe(val, default=None):
            try:
                if val is None or val == "":
                    return default
                return float(val)
            except:
                return default
        
        def to_int_safe(val, default=None):
            try:
                if val is None or val == "":
                    return default
                return int(float(val))
            except:
                return default
        
        # Cập nhật từ request data
        price_tq = to_float_safe(data.get('price_tq'))
        sku_tq = data.get('sku_tq', '').strip() if data.get('sku_tq') else None
        name_tq = data.get('name_tq', '').strip() if data.get('name_tq') else None
        sku_model_xnk = data.get('sku_model_xnk', '').strip() if data.get('sku_model_xnk') else None
        
        # Update box_info
        full_box = to_int_safe(data.get('full_box'))
        box_length = to_float_safe(data.get('box_length_cm'))
        box_width = to_float_safe(data.get('box_width_cm'))
        box_height = to_float_safe(data.get('box_height_cm'))
        
        box_info = None
        if full_box is not None or box_length is not None or box_width is not None or box_height is not None:
            box_info = BoxInfoDTO(
                full_box=full_box if full_box is not None else (variant_meta.box_info.full_box if variant_meta.box_info else None),
                length_cm=box_length if box_length is not None else (variant_meta.box_info.length_cm if variant_meta.box_info else None),
                width_cm=box_width if box_width is not None else (variant_meta.box_info.width_cm if variant_meta.box_info else None),
                height_cm=box_height if box_height is not None else (variant_meta.box_info.height_cm if variant_meta.box_info else None)
            )
        elif variant_meta.box_info:
            box_info = variant_meta.box_info
        
        # Update packed_info
        packed_length = to_float_safe(data.get('packed_length_cm'))
        packed_width = to_float_safe(data.get('packed_width_cm'))
        packed_height = to_float_safe(data.get('packed_height_cm'))
        packed_weight_with_box = to_float_safe(data.get('packed_weight_with_box_g'))
        packed_weight_without_box = to_float_safe(data.get('packed_weight_without_box_g'))
        
        packed_info = None
        if packed_length is not None or packed_width is not None or packed_height is not None or packed_weight_with_box is not None or packed_weight_without_box is not None:
            packed_info = PackedInfoDTO(
                length_cm=packed_length if packed_length is not None else (variant_meta.packed_info.length_cm if variant_meta.packed_info else None),
                width_cm=packed_width if packed_width is not None else (variant_meta.packed_info.width_cm if variant_meta.packed_info else None),
                height_cm=packed_height if packed_height is not None else (variant_meta.packed_info.height_cm if variant_meta.packed_info else None),
                weight_with_box_g=packed_weight_with_box if packed_weight_with_box is not None else (variant_meta.packed_info.weight_with_box_g if variant_meta.packed_info else None),
                weight_without_box_g=packed_weight_without_box if packed_weight_without_box is not None else (variant_meta.packed_info.weight_without_box_g if variant_meta.packed_info else None)
            )
        elif variant_meta.packed_info:
            packed_info = variant_meta.packed_info
        
        # Update nhanphu_info (product level)
        nhanphu_vi_name = data.get('nhanphu_vi_name', '').strip() if data.get('nhanphu_vi_name') else None
        nhanphu_en_name = data.get('nhanphu_en_name', '').strip() if data.get('nhanphu_en_name') else None
        nhanphu_description = data.get('nhanphu_description', '').strip() if data.get('nhanphu_description') else None
        nhanphu_material = data.get('nhanphu_material', '').strip() if data.get('nhanphu_material') else None
        
        nhanphu_info = None
        if nhanphu_vi_name is not None or nhanphu_en_name is not None or nhanphu_description is not None or nhanphu_material is not None:
            nhanphu_info = NhanPhuInfoDTO(
                vi_name=nhanphu_vi_name if nhanphu_vi_name else (current_metadata.nhanphu_info.vi_name if current_metadata.nhanphu_info else None),
                en_name=nhanphu_en_name if nhanphu_en_name else (current_metadata.nhanphu_info.en_name if current_metadata.nhanphu_info else None),
                description=nhanphu_description if nhanphu_description else (current_metadata.nhanphu_info.description if current_metadata.nhanphu_info else None),
                material=nhanphu_material if nhanphu_material else (current_metadata.nhanphu_info.material if current_metadata.nhanphu_info else None),
                hdsd=current_metadata.nhanphu_info.hdsd if current_metadata.nhanphu_info else None
            )
        elif current_metadata.nhanphu_info:
            nhanphu_info = current_metadata.nhanphu_info
        
        # Tạo variant metadata mới
        new_variant_meta = VariantMetadataDTO(
            id=variant_id,
            price_tq=price_tq if price_tq is not None else variant_meta.price_tq,
            sku_tq=sku_tq if sku_tq else variant_meta.sku_tq,
            name_tq=name_tq if name_tq else variant_meta.name_tq,
            box_info=box_info,
            packed_info=packed_info,
            sku_model_xnk=sku_model_xnk if sku_model_xnk else variant_meta.sku_model_xnk,
            web_variant_id=variant_meta.web_variant_id if variant_meta.web_variant_id else []
        )
        
        # Update product level nhanphu_info nếu có
        if nhanphu_info:
            current_metadata.nhanphu_info = nhanphu_info
        
        # Update variant metadata
        current_metadata = update_variant_metadata(
            current_metadata,
            variant_id,
            new_variant_meta
        )
        
        # Lưu vào Sapo
        success = product_service.update_product_metadata(
            product_id,
            current_metadata,
            preserve_description=True
        )
        
        if success:
            return JsonResponse({
                "status": "success",
                "message": "Đã cập nhật thành công"
            })
        else:
            return JsonResponse({
                "status": "error",
                "message": "Không thể lưu variant metadata"
            }, status=500)
        
    except Exception as e:
        logger.error(f"Error updating variant metadata {variant_id}: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


# ========================= XNK MODEL MANAGEMENT =========================

def _get_xnk_service():
    """
    Helper để lấy XNKModelService với session phù hợp.
    Sử dụng loginss từ thamkhao nếu có, nếu không thì dùng SapoClient.core_session.
    """
    if loginss is not None:
        return XNKModelService(loginss)
    else:
        # Fallback: dùng SapoClient
        sapo_client = get_sapo_client()
        # Đảm bảo core session đã được init (gọi private method nếu cần)
        try:
            sapo_client._ensure_logged_in()
        except:
            pass  # Nếu không login được, vẫn dùng session hiện tại
        return XNKModelService(sapo_client.core_session)


@admin_only
def xnk_model_list(request: HttpRequest):
    """
    Danh sách Model Xuất Nhập Khẩu:
    - Hiển thị danh sách tất cả model XNK từ customer notes
    - Có thể tìm kiếm, sửa, xóa
    """
    context = {
        "title": "Quản lý Model Xuất Nhập Khẩu",
        "models": [],
        "total": 0,
        "error": None,
    }
    
    try:
        xnk_service = _get_xnk_service()
        all_models = xnk_service.get_all_models()
        
        # Sắp xếp theo SKU
        all_models.sort(key=lambda x: str(x.get("sku", "")).lower())
        
        context["models"] = all_models
        context["total"] = len(all_models)
        
    except Exception as e:
        logger.error(f"Error in xnk_model_list: {e}", exc_info=True)
        context["error"] = str(e)
    
    return render(request, "products/xnk_model_list.html", context)


@admin_only
@require_http_methods(["GET"])
def api_xnk_search(request: HttpRequest):
    """
    API tìm kiếm model XNK theo SKU và tên tiếng anh.
    
    Query params:
    - q: Từ khóa tìm kiếm (SKU hoặc tên tiếng anh)
    
    Returns:
        JSON với danh sách model XNK khớp
    """
    try:
        query = request.GET.get("q", "").strip()
        
        xnk_service = _get_xnk_service()
        results = xnk_service.search_models(query)
        
        return JsonResponse({
            "status": "success",
            "results": results,
            "count": len(results)
        })
        
    except Exception as e:
        logger.error(f"Error in api_xnk_search: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


@admin_only
@require_POST
@csrf_exempt
def api_xnk_edit(request: HttpRequest):
    """
    API chỉnh sửa model XNK.
    
    Body (JSON):
    {
        "sku": "SKU123",
        "field1": "value1",
        "field2": "value2",
        ...
    }
    
    Returns:
        JSON với status và message
    """
    try:
        import json
        data = json.loads(request.body)
        
        sku = data.get("sku", "").strip()
        if not sku:
            return JsonResponse({
                "status": "error",
                "message": "Thiếu SKU trong dữ liệu gửi lên"
            }, status=400)
        
        # Loại bỏ SKU khỏi updates (vì SKU là key để tìm)
        updates = {k: v for k, v in data.items() if k != "sku"}
        
        if not updates:
            return JsonResponse({
                "status": "error",
                "message": "Không có dữ liệu cập nhật"
            }, status=400)
        
        xnk_service = _get_xnk_service()
        result = xnk_service.update_model(sku, updates)
        
        if result.get("status") == "success":
            return JsonResponse({
                "status": "success",
                "message": result.get("msg", "Cập nhật thành công")
            })
        else:
            return JsonResponse({
                "status": "error",
                "message": result.get("msg", "Lỗi khi cập nhật")
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Dữ liệu JSON không hợp lệ"
        }, status=400)
    except Exception as e:
        logger.error(f"Error in api_xnk_edit: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


@admin_only
@require_POST
@csrf_exempt
def api_xnk_create(request: HttpRequest):
    """
    API tạo model XNK mới.
    
    Body (JSON):
    {
        "sku": "SKU123",
        "hs_code": "...",
        "en_name": "...",
        ...
    }
    
    Returns:
        JSON với status và message
    """
    try:
        import json
        data = json.loads(request.body)
        
        sku = data.get("sku", "").strip()
        if not sku:
            return JsonResponse({
                "status": "error",
                "message": "Thiếu SKU trong dữ liệu gửi lên"
            }, status=400)
        
        xnk_service = _get_xnk_service()
        result = xnk_service.create_model(data)
        
        if result.get("status") == "success":
            return JsonResponse({
                "status": "success",
                "message": result.get("msg", "Tạo mới thành công"),
                "note_id": result.get("note_id")
            })
        else:
            return JsonResponse({
                "status": "error",
                "message": result.get("msg", "Lỗi khi tạo mới")
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Dữ liệu JSON không hợp lệ"
        }, status=400)
    except Exception as e:
        logger.error(f"Error in api_xnk_create: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


@admin_only
@require_POST
@csrf_exempt
def api_xnk_delete(request: HttpRequest):
    """
    API xóa model XNK (set status = inactive).
    
    Body (JSON):
    {
        "sku": "SKU123"
    }
    
    Returns:
        JSON với status và message
    """
    try:
        import json
        data = json.loads(request.body)
        
        sku = data.get("sku", "").strip()
        if not sku:
            return JsonResponse({
                "status": "error",
                "message": "Thiếu SKU trong dữ liệu gửi lên"
            }, status=400)
        
        xnk_service = _get_xnk_service()
        result = xnk_service.delete_model(sku)
        
        if result.get("status") == "success":
            return JsonResponse({
                "status": "success",
                "message": result.get("msg", "Xóa thành công")
            })
        else:
            return JsonResponse({
                "status": "error",
                "message": result.get("msg", "Lỗi khi xóa")
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Dữ liệu JSON không hợp lệ"
        }, status=400)
    except Exception as e:
        logger.error(f"Error in api_xnk_delete: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


# ========================= SUPPLIER MANAGEMENT =========================

@admin_only
def supplier_list(request: HttpRequest):
    """
    Danh sách nhà cung cấp:
    - Hiển thị danh sách nhà cung cấp đang hoạt động
    - Tên - Logo - Vùng (Tỉnh) - Link web
    - Tags loại phân phối hay độc quyền
    - Mô tả
    - Số sản phẩm thuộc nhà cung cấp đó
    """
    context = {
        "title": "Danh sách nhà cung cấp",
        "suppliers": [],
        "total": 0,
    }

    try:
        from products.services.sapo_supplier_service import SapoSupplierService
        
        sapo_client = get_sapo_client()
        supplier_service = SapoSupplierService(sapo_client)

        # Lấy tất cả suppliers đang hoạt động
        all_suppliers = supplier_service.get_all_suppliers(status="active")
        
        # Bổ sung số lượng sản phẩm
        all_suppliers = supplier_service.enrich_suppliers_with_product_count(all_suppliers)
        
        # Convert to dict for template
        suppliers_data = []
        group_names_set = set()
        
        for supplier in all_suppliers:
            if supplier.group_name:
                group_names_set.add(supplier.group_name)
            
            # Parse websites
            websites_dict = supplier.websites_dict
            
            suppliers_data.append({
                "id": supplier.id,
                "code": supplier.code,
                "name": supplier.name,
                "description": supplier.description,
                "logo_path": supplier.logo_path,
                "province": supplier.province,
                "company_name": supplier.company_name,
                "group_name": supplier.group_name,
                "tags": supplier.tags,
                "websites": websites_dict,
                "product_count": supplier.product_count,
                "debt": supplier.debt,
                "status": supplier.status,
            })

        # Sắp xếp: ưu tiên ĐỘC QUYỀN trước PHÂN PHỐI
        def sort_key(supplier):
            group_name = supplier.get("group_name", "") or ""
            # ĐỘC QUYỀN = 0 (ưu tiên cao nhất), PHÂN PHỐI = 1, khác = 2
            if group_name == "ĐỘC QUYỀN":
                return (0, supplier.get("name", ""))
            elif group_name == "PHÂN PHỐI":
                return (1, supplier.get("name", ""))
            else:
                return (2, supplier.get("name", ""))
        
        suppliers_data.sort(key=sort_key)

        context["suppliers"] = suppliers_data
        context["total"] = len(suppliers_data)
        context["group_names"] = sorted(list(group_names_set))

    except Exception as e:
        logger.error(f"Error in supplier_list: {e}", exc_info=True)
        context["error"] = str(e)

    return render(request, "products/supplier_list.html", context)


@admin_only
@require_POST
@csrf_exempt
def upload_supplier_logo(request: HttpRequest, supplier_id: int):
    """
    API endpoint để upload logo cho nhà cung cấp.
    
    POST data:
    - file: File ảnh (jpg hoặc png)
    
    Returns:
        JSON với status và logo_path
    """
    try:
        from django.conf import settings
        import os
        from pathlib import Path
        
        # Kiểm tra file được upload
        if 'file' not in request.FILES:
            return JsonResponse({
                "status": "error",
                "message": "Không có file được upload"
            }, status=400)
        
        uploaded_file = request.FILES['file']
        
        # Kiểm tra định dạng file
        allowed_extensions = ['.jpg', '.jpeg', '.png']
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        if file_ext not in allowed_extensions:
            return JsonResponse({
                "status": "error",
                "message": f"Chỉ chấp nhận file {', '.join(allowed_extensions)}"
            }, status=400)
        
        # Lấy thông tin supplier từ SAPO
        sapo_client = get_sapo_client()
        supplier_response = sapo_client.core.get_supplier_raw(supplier_id)
        supplier_data = supplier_response.get('supplier')
        
        if not supplier_data:
            return JsonResponse({
                "status": "error",
                "message": f"Không tìm thấy nhà cung cấp với ID {supplier_id}"
            }, status=404)
        
        supplier_code = supplier_data.get('code', '')
        
        # Tạo tên file: id_code.jpg hoặc id_code.png
        file_name = f"{supplier_id}_{supplier_code}{file_ext}"
        
        # Tạo đường dẫn thư mục: assets/supplier/logo/
        logo_dir = Path(settings.BASE_DIR) / 'assets' / 'supplier' / 'logo'
        logo_dir.mkdir(parents=True, exist_ok=True)
        
        # Đường dẫn đầy đủ của file
        file_path = logo_dir / file_name
        
        # Lưu file
        with open(file_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
        
        # Đường dẫn URL để hiển thị: /static/supplier/logo/id_code.jpg
        logo_url = f"/static/supplier/logo/{file_name}"
        
        # Update supplier address trong SAPO
        # Lấy address đầu tiên (hoặc tạo mới nếu chưa có)
        addresses = supplier_data.get('addresses', [])
        if not addresses:
            return JsonResponse({
                "status": "error",
                "message": "Nhà cung cấp chưa có địa chỉ. Vui lòng thêm địa chỉ trước."
            }, status=400)
        
        address = addresses[0]
        address_id = address.get('id')
        
        if not address_id:
            return JsonResponse({
                "status": "error",
                "message": "Địa chỉ không có ID"
            }, status=400)
        
        # Build address payload với tất cả fields hiện có + update first_name
        address_payload = {
            "id": address_id,
            "country": address.get("country"),
            "city": address.get("city"),
            "district": address.get("district"),
            "ward": address.get("ward"),
            "address1": address.get("address1"),  # Giữ nguyên tỉnh
            "address2": address.get("address2"),
            "zip_code": address.get("zip_code"),
            "email": address.get("email"),
            "first_name": logo_url,  # ⭐ Update logo path vào đây
            "last_name": address.get("last_name"),
            "full_name": address.get("full_name"),  # Tên công ty
            "label": address.get("label"),  # Không dùng đến
            "phone_number": address.get("phone_number"),
            "status": address.get("status", "active"),
        }
        
        # Gọi API update address
        try:
            sapo_client.core.update_supplier_address(
                supplier_id=supplier_id,
                address_id=address_id,
                address_data=address_payload
            )
            logger.info(f"[upload_supplier_logo] ✅ Updated logo for supplier {supplier_id}: {logo_url}")
        except Exception as e:
            logger.error(f"[upload_supplier_logo] Failed to update supplier address: {e}", exc_info=True)
            # Xóa file đã lưu nếu update thất bại
            if file_path.exists():
                file_path.unlink()
            return JsonResponse({
                "status": "error",
                "message": f"Không thể cập nhật địa chỉ trên SAPO: {str(e)}"
            }, status=500)
        
        return JsonResponse({
            "status": "success",
            "message": "Upload logo thành công",
            "logo_path": logo_url
        })
        
    except Exception as e:
        logger.error(f"Error in upload_supplier_logo: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


@admin_only
@require_POST
@csrf_exempt
def add_supplier_website(request: HttpRequest, supplier_id: int):
    """
    API endpoint để thêm website cho nhà cung cấp.
    
    POST data (JSON):
    - website_type: Loại website (1688, tmall, taobao, douyin, other)
    - website_url: URL của website
    
    Returns:
        JSON với status và websites dict
    """
    try:
        import json
        
        # Lấy dữ liệu từ request
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST
        
        website_type = data.get('website_type', '').strip()
        website_url = data.get('website_url', '').strip()
        
        if not website_type or not website_url:
            return JsonResponse({
                "status": "error",
                "message": "Thiếu website_type hoặc website_url"
            }, status=400)
        
        # Validate URL
        if not website_url.startswith(('http://', 'https://')):
            website_url = 'https://' + website_url
        
        # Lấy thông tin supplier từ SAPO
        sapo_client = get_sapo_client()
        supplier_response = sapo_client.core.get_supplier_raw(supplier_id)
        supplier_data = supplier_response.get('supplier')
        
        if not supplier_data:
            return JsonResponse({
                "status": "error",
                "message": f"Không tìm thấy nhà cung cấp với ID {supplier_id}"
            }, status=404)
        
        # Parse website hiện tại (có thể là JSON string hoặc string đơn giản)
        current_website = supplier_data.get('website', '')
        websites_dict = {}
        
        if current_website:
            try:
                # Thử parse JSON
                if current_website.startswith('{'):
                    websites_dict = json.loads(current_website)
                else:
                    # Nếu là string đơn giản, lưu vào key "default"
                    websites_dict = {"default": current_website}
            except:
                # Nếu không parse được, coi như string đơn giản
                websites_dict = {"default": current_website}
        
        # Thêm website mới vào dict
        # Nếu là "other", dùng URL làm key (hoặc tên domain)
        if website_type == 'other':
            # Extract domain từ URL để làm key
            from urllib.parse import urlparse
            parsed = urlparse(website_url)
            key = parsed.netloc.replace('www.', '') or 'other'
            websites_dict[key] = website_url
        else:
            websites_dict[website_type] = website_url
        
        # Convert dict thành JSON string
        new_website_json = json.dumps(websites_dict, ensure_ascii=False)
        
        # Build supplier update payload với tất cả fields hiện có
        supplier_payload = {
            "id": supplier_data.get("id"),
            "tenant_id": supplier_data.get("tenant_id"),
            "code": supplier_data.get("code"),
            "name": supplier_data.get("name"),
            "description": supplier_data.get("description"),
            "email": supplier_data.get("email"),
            "fax": supplier_data.get("fax"),
            "phone_number": supplier_data.get("phone_number"),
            "tax_number": supplier_data.get("tax_number"),
            "website": new_website_json,  # ⭐ Update website field
            "supplier_group_id": supplier_data.get("supplier_group_id"),
            "assignee_id": supplier_data.get("assignee_id"),
            "default_payment_term_id": supplier_data.get("default_payment_term_id"),
            "default_payment_method_id": supplier_data.get("default_payment_method_id"),
            "default_tax_type_id": supplier_data.get("default_tax_type_id"),
            "default_discount_rate": supplier_data.get("default_discount_rate"),
            "default_price_list_id": supplier_data.get("default_price_list_id"),
            "tags": supplier_data.get("tags", []),
            "status": supplier_data.get("status", "active"),
            "is_default": supplier_data.get("is_default", False),
        }
        
        # Gọi API update supplier
        try:
            sapo_client.core.update_supplier(
                supplier_id=supplier_id,
                supplier_data=supplier_payload
            )
            logger.info(f"[add_supplier_website] ✅ Added website for supplier {supplier_id}: {website_type}={website_url}")
        except Exception as e:
            logger.error(f"[add_supplier_website] Failed to update supplier: {e}", exc_info=True)
            return JsonResponse({
                "status": "error",
                "message": f"Không thể cập nhật nhà cung cấp trên SAPO: {str(e)}"
            }, status=500)
        
        return JsonResponse({
            "status": "success",
            "message": "Thêm website thành công",
            "websites": websites_dict
        })
        
    except Exception as e:
        logger.error(f"Error in add_supplier_website: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


# ========================= SALES FORECAST =========================

@admin_only
def sales_forecast_list(request: HttpRequest):
    """
    Danh sách dự báo bán hàng & cảnh báo tồn kho:
    - Hiển thị danh sách variants với dự báo bán hàng
    - Có nút refresh data để tính toán lại
    - Cảnh báo màu: đỏ (< 30 ngày), vàng (30-60 ngày), xanh (> 60 ngày)
    - Có thể sắp xếp theo các cột
    """
    context = {
        "title": "Dự báo bán hàng & Cảnh báo tồn kho",
        "variants": [],
        "total": 0,
        "days": 7,  # Mặc định 7 ngày
    }
    
    try:
        from products.services.sales_forecast_service import SalesForecastService
        
        sapo_client = get_sapo_client()
        forecast_service = SalesForecastService(sapo_client)
        
        # Lấy số ngày từ query param (mặc định 7)
        days = int(request.GET.get('days', 7))
        context["days"] = days
        
        # KHÔNG force refresh mặc định - chỉ load từ metadata
        # Chỉ refresh khi bấm nút "Refresh Data"
        force_refresh = False
        
        # Load dữ liệu từ GDP_META (không tính toán lại)
        logger.info(f"[sales_forecast_list] Loading forecast data from GDP_META for {days} days")
        forecast_map, all_products, all_variants_map = forecast_service.calculate_sales_forecast(
            days=days,
            force_refresh=force_refresh
        )
        
        # Lấy thông tin đầy đủ cho từng variant (dùng variant_data đã có sẵn)
        print(f"[DEBUG] [VIEW] Lấy thông tin tồn kho cho {len(forecast_map)} variants...")
        import time
        view_start = time.time()
        
        # Tạo map variant_id -> product_data để lấy brand
        variant_to_product: Dict[int, Dict[str, Any]] = {}
        for product in all_products:
            product_id = product.get("id")
            variants = product.get("variants", [])
            for variant in variants:
                variant_id = variant.get("id")
                if variant_id:
                    variant_to_product[variant_id] = product
        
        variants_data = []
        processed = 0
        for variant_id, forecast in forecast_map.items():
            # Lấy variant_data từ map (đã có sẵn inventories)
            variant_data = all_variants_map.get(variant_id)
            product_data = variant_to_product.get(variant_id)
            variant_info = forecast_service.get_variant_forecast_with_inventory(
                variant_id,
                forecast_map,
                variant_data=variant_data,  # Truyền variant_data đã có sẵn
                product_data=product_data  # Truyền product_data để lấy brand
            )
            variants_data.append(variant_info)
            processed += 1
            
            # Log progress mỗi 100 variants
            if processed % 100 == 0:
                print(f"[DEBUG] [VIEW] Đã xử lý {processed}/{len(forecast_map)} variants...")
        
        print(f"[DEBUG] [VIEW] ✅ Đã lấy thông tin cho {len(variants_data)} variants ({time.time() - view_start:.2f}s)")
        
        # Sắp xếp mặc định: theo days_remaining (tăng dần - nguy hiểm nhất trước)
        print(f"[DEBUG] [VIEW] Sắp xếp danh sách...")
        sort_start = time.time()
        variants_data.sort(key=lambda x: (
            0 if x["days_remaining"] == float('inf') else x["days_remaining"],
            -x["total_inventory"]
        ))
        print(f"[DEBUG] [VIEW] ✅ Đã sắp xếp ({time.time() - sort_start:.2f}s)")
        
        context["variants"] = variants_data
        context["total"] = len(variants_data)
        
    except Exception as e:
        logger.error(f"Error in sales_forecast_list: {e}", exc_info=True)
        context["error"] = str(e)
    
    return render(request, "products/sales_forecast_list.html", context)


@admin_only
@require_POST
def refresh_sales_forecast(request: HttpRequest):
    """
    API endpoint để refresh dữ liệu dự báo bán hàng.
    
    POST data:
    - days: Số ngày để tính toán (mặc định 7)
    
    Returns:
        JSON với status và message
    """
    try:
        import json
        
        # Lấy days từ request
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            days = int(data.get('days', 7))
        else:
            days = int(request.POST.get('days', 7))
        
        from products.services.sales_forecast_service import SalesForecastService
        
        sapo_client = get_sapo_client()
        forecast_service = SalesForecastService(sapo_client)
        
        # Tính toán lại với force_refresh=True
        logger.info(f"[refresh_sales_forecast] Refreshing forecast for {days} days")
        forecast_map, all_products, all_variants_map = forecast_service.calculate_sales_forecast(
            days=days,
            force_refresh=True
        )
        
        return JsonResponse({
            "status": "success",
            "message": f"Đã tính toán lại dự báo cho {len(forecast_map)} variants",
            "count": len(forecast_map)
        })
        
    except Exception as e:
        logger.error(f"Error in refresh_sales_forecast: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)

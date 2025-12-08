from django.shortcuts import render, redirect, get_object_or_404
from kho.utils import admin_only
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from typing import List, Dict, Any
from decimal import Decimal
from datetime import date
import logging
import io
import os
import requests
from PIL import Image
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None

from core.sapo_client import get_sapo_client
from products.services.sapo_product_service import SapoProductService
from products.services.dto import ProductDTO, ProductVariantDTO
from products.models import (
    ContainerTemplate,
    ContainerTemplateSupplier,
    SumPurchaseOrder,
    SPOPurchaseOrder,
    SPOCost,
    SPODocument,
    PurchaseOrder,
    PurchaseOrderCost,
    PurchaseOrderPayment
)
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
            
            # Lấy ảnh default
            default_image = None
            if product.images:
                for img in product.images:
                    if img.is_default:
                        default_image = img.full_path
                        break
                # Nếu không có ảnh default, lấy ảnh đầu tiên
                if not default_image and len(product.images) > 0:
                    default_image = product.images[0].full_path
            
            # Parse tags
            tags_list = []
            if product.tags:
                tags_list = [tag.strip() for tag in product.tags.split(',') if tag.strip()]
            
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
                "image_url": default_image,
                "tags": tags_list,
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
        "brands_map": {},  # Khởi tạo brands_map để tránh lỗi template
        "brand_filter": None,  # Khởi tạo brand_filter
    }
    
    try:
        from products.services.sales_forecast_service import SalesForecastService
        
        sapo_client = get_sapo_client()
        forecast_service = SalesForecastService(sapo_client)
        
        # Lấy brand filter từ query param (mặc định None = tất cả)
        brand_filter = request.GET.get('brand', '').strip()
        if brand_filter == 'all' or not brand_filter:
            brand_filter = None
        context["brand_filter"] = brand_filter
        
        # KHÔNG force refresh mặc định - chỉ load từ database
        # Chỉ refresh khi bấm nút "Sync Data"
        force_refresh = False
        
        # Load dữ liệu cho cả 30 ngày và 10 ngày
        logger.info(f"[sales_forecast_list] Loading forecast data for 30 days and 10 days")
        forecast_map_30, all_products_30, all_variants_map_30 = forecast_service.calculate_sales_forecast(
            days=30,
            force_refresh=force_refresh
        )
        forecast_map_10, all_products_10, all_variants_map_10 = forecast_service.calculate_sales_forecast(
            days=10,
            force_refresh=force_refresh
        )
        
        # Dùng all_products và all_variants_map từ 30 ngày (giống nhau)
        all_products = all_products_30
        all_variants_map = all_variants_map_30
        
        # Lấy thông tin đầy đủ cho từng variant (dùng variant_data đã có sẵn)
        all_variant_ids = set(forecast_map_30.keys()) | set(forecast_map_10.keys())
        print(f"[DEBUG] [VIEW] Lấy thông tin tồn kho cho {len(all_variant_ids)} variants...")
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
        
        # Collect brands từ SUPPLIERS ĐANG HOẠT ĐỘNG (nhanh hơn, chỉ lấy active suppliers)
        # Học từ suppliers page: lấy suppliers active, rồi lấy brands từ đó
        from products.services.sapo_supplier_service import SapoSupplierService
        supplier_service = SapoSupplierService(sapo_client)
        
        print(f"[DEBUG] [VIEW] Lấy suppliers đang hoạt động...")
        active_suppliers = supplier_service.get_all_suppliers(status="active")
        
        # Tạo set các brand names từ suppliers (code và name, case-insensitive)
        active_brand_names = set()
        for supplier in active_suppliers:
            if supplier.code:
                active_brand_names.add(supplier.code.upper())
            if supplier.name:
                active_brand_names.add(supplier.name.upper())
        
        print(f"[DEBUG] [VIEW] Có {len(active_suppliers)} suppliers đang hoạt động, {len(active_brand_names)} brand names")
        
        # Collect brands từ variants, nhưng CHỈ giữ lại những brands có trong suppliers active
        all_brands_map = {}
        for variant_id, variant_data in all_variants_map.items():
            # Ưu tiên lấy brand từ product_data, fallback về variant_data
            product_data = variant_to_product.get(variant_id)
            brand = ""
            if product_data:
                brand = product_data.get("brand") or ""
            if not brand:
                brand = variant_data.get("brand") or ""
            brand = brand.strip()
            
            # CHỈ đếm nếu brand có trong suppliers active (case-insensitive)
            if brand and brand.upper() in active_brand_names:
                all_brands_map[brand] = all_brands_map.get(brand, 0) + 1
        
        print(f"[DEBUG] [VIEW] ✅ Đã collect {len(all_brands_map)} brands (chỉ từ suppliers active) từ {len(all_variants_map)} variants")
        if all_brands_map:
            print(f"[DEBUG] [VIEW] Brands: {list(all_brands_map.keys())[:10]}")
        
        variants_data = []
        processed = 0
        
        for variant_id in all_variant_ids:
            # Lấy forecast cho 30 ngày và 10 ngày
            forecast_30 = forecast_map_30.get(variant_id)
            forecast_10 = forecast_map_10.get(variant_id)
            
            # Lấy variant_data từ map (đã có sẵn inventories)
            variant_data = all_variants_map.get(variant_id)
            product_data = variant_to_product.get(variant_id)
            
            # Dùng forecast_30 làm chính (hoặc forecast_10 nếu không có 30)
            main_forecast = forecast_30 or forecast_10
            if not main_forecast:
                continue
                
            variant_info = forecast_service.get_variant_forecast_with_inventory(
                variant_id,
                {variant_id: main_forecast},  # Truyền map với 1 item
                variant_data=variant_data,  # Truyền variant_data đã có sẵn
                product_data=product_data  # Truyền product_data để lấy brand
            )
            
            # Tính tỉ lệ % cho 30 ngày và 10 ngày
            if forecast_30:
                variant_info["forecast_30"] = {
                    "total_sold": forecast_30.total_sold,
                    "total_sold_previous_period": forecast_30.total_sold_previous_period,
                    "growth_percentage": forecast_30.growth_percentage,
                    "sales_rate": forecast_30.sales_rate
                }
                # Tính tỉ lệ %: (hiện tại - cùng kỳ) / cùng kỳ * 100
                if forecast_30.total_sold_previous_period > 0:
                    variant_info["growth_percentage_30"] = ((forecast_30.total_sold - forecast_30.total_sold_previous_period) / forecast_30.total_sold_previous_period) * 100
                else:
                    variant_info["growth_percentage_30"] = None
            else:
                variant_info["forecast_30"] = None
                variant_info["growth_percentage_30"] = None
                
            if forecast_10:
                variant_info["forecast_10"] = {
                    "total_sold": forecast_10.total_sold,
                    "total_sold_previous_period": forecast_10.total_sold_previous_period,
                    "growth_percentage": forecast_10.growth_percentage,
                    "sales_rate": forecast_10.sales_rate
                }
                # Tính tỉ lệ %: (hiện tại - cùng kỳ) / cùng kỳ * 100
                if forecast_10.total_sold_previous_period > 0:
                    variant_info["growth_percentage_10"] = ((forecast_10.total_sold - forecast_10.total_sold_previous_period) / forecast_10.total_sold_previous_period) * 100
                else:
                    variant_info["growth_percentage_10"] = None
            else:
                variant_info["forecast_10"] = None
                variant_info["growth_percentage_10"] = None
            
            variants_data.append(variant_info)
            processed += 1
            
            # Log progress mỗi 100 variants
            if processed % 100 == 0:
                print(f"[DEBUG] [VIEW] Đã xử lý {processed}/{len(all_variant_ids)} variants...")
        
        print(f"[DEBUG] [VIEW] ✅ Đã lấy thông tin cho {len(variants_data)} variants ({time.time() - view_start:.2f}s)")
        
        # Filter theo brand (server-side)
        total_before_filter = len(variants_data)
        if brand_filter:
            print(f"[DEBUG] [VIEW] Filter theo brand: {brand_filter}")
            variants_data = [v for v in variants_data if v.get("brand", "").strip() == brand_filter]
            print(f"[DEBUG] [VIEW] Sau khi filter: {len(variants_data)}/{total_before_filter} variants")
        
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
        context["brands_map"] = all_brands_map  # Tất cả brands để hiển thị filter buttons
        # Convert dict thành sorted list để dễ iterate trong template
        context["brands_list"] = sorted(all_brands_map.items(), key=lambda x: x[0])  # Sort theo tên brand
        
        # Debug: Log brands_map để kiểm tra
        print(f"[DEBUG] [VIEW] brands_map có {len(all_brands_map)} brands: {list(all_brands_map.keys())[:10]}...")
        print(f"[DEBUG] [VIEW] Context brands_map type: {type(context.get('brands_map'))}, size: {len(context.get('brands_map', {}))}")
        print(f"[DEBUG] [VIEW] brands_list có {len(context['brands_list'])} items")
        
    except Exception as e:
        logger.error(f"Error in sales_forecast_list: {e}", exc_info=True)
        context["error"] = str(e)
        # Đảm bảo brands_map luôn có trong context (ngay cả khi lỗi)
        if "brands_map" not in context:
            context["brands_map"] = {}
    
    return render(request, "products/sales_forecast_list.html", context)


# ========================= CONTAINER TEMPLATE =========================

@admin_only
def container_template_list(request: HttpRequest):
    """
    Danh sách INIT CONTAINER.
    """
    context = {
        "title": "Quản lý Container Template",
        "templates": [],
        "total": 0,
    }

    try:
        templates = ContainerTemplate.objects.filter(is_active=True).order_by('code')
        # Preload suppliers và format money cho mỗi template
        for template in templates:
            template.suppliers_list = list(template.suppliers.all().order_by('supplier_name'))
            
            # Lấy danh sách SPOs sử dụng container template này
            template.spos_list = list(template.sum_purchase_orders.all().order_by('-created_at'))
            
            # Format avg_total_amount (e.g. 1.200.000.000 -> 1B2, 300.000.000 -> 300M)
            val = template.avg_total_amount or 0
            if val >= 1_000_000_000:
                billions = int(val // 1_000_000_000)
                remainder = int((val % 1_000_000_000) // 100_000_000)
                if remainder > 0:
                    template.formatted_avg_total = f"{billions}B{remainder}"
                else:
                    template.formatted_avg_total = f"{billions}B"
            elif val >= 1_000_000:
                millions = int(val // 1_000_000)
                template.formatted_avg_total = f"{millions}M"
            else:
                template.formatted_avg_total = f"{int(val):,}"

        context["templates"] = templates
        context["total"] = templates.count()
    except Exception as e:
        logger.error(f"Error in container_template_list: {e}", exc_info=True)
        context["error"] = str(e)

    return render(request, "products/container_template_list.html", context)


@admin_only
def container_template_detail(request: HttpRequest, template_id: int):
    """
    Chi tiết INIT CONTAINER.
    """
    context = {
        "title": "Chi tiết Container Template",
        "template": None,
        "suppliers": [],
    }
    
    try:
        from products.services.container_template_service import ContainerTemplateService
        
        sapo_client = get_sapo_client()
        template_service = ContainerTemplateService(sapo_client)
        
        template_data = template_service.get_template_with_suppliers(template_id)
        context["template"] = template_data["template"]
        context["suppliers"] = template_data["suppliers"]
    except ContainerTemplate.DoesNotExist:
        context["error"] = "Container template không tồn tại"
    except Exception as e:
        logger.error(f"Error in container_template_detail: {e}", exc_info=True)
        context["error"] = str(e)
    
    return render(request, "products/container_template_detail.html", context)


@admin_only
@require_POST
def create_container_template(request: HttpRequest):
    """
    API endpoint để tạo container template mới.
    
    POST data:
    - code: str (required)
    - name: str (optional)
    - container_type: str (default: "40ft")
    - volume_cbm: float (default: 65.0)
    - default_supplier_id: int (optional)
    - ship_time_avg_hn: int (default: 0)
    - ship_time_avg_hcm: int (default: 0)
    - departure_port: str (optional)
    
    Returns:
        JSON: {status, message, template_id, template_code}
    """
    try:
        import json
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        from products.services.container_template_service import ContainerTemplateService
        
        sapo_client = get_sapo_client()
        template_service = ContainerTemplateService(sapo_client)
        
        # Thêm created_by
        data['created_by'] = request.user
        
        template = template_service.create_template(data)
        
        return JsonResponse({
            "status": "success",
            "message": f"Đã tạo container template {template.code}",
            "template_id": template.id,
            "template_code": template.code
        })
        
    except Exception as e:
        logger.error(f"Error in create_container_template: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def update_container_template(request: HttpRequest, template_id: int):
    """
    API endpoint để cập nhật container template.
    
    POST data:
    - name, container_type, volume_cbm, etc.
    
    Returns:
        JSON: {status, message}
    """
    try:
        import json
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        from products.services.container_template_service import ContainerTemplateService
        
        sapo_client = get_sapo_client()
        template_service = ContainerTemplateService(sapo_client)
        
        template = template_service.update_template(template_id, data)
        
        return JsonResponse({
            "status": "success",
            "message": f"Đã cập nhật container template {template.code}"
        })
        
    except ContainerTemplate.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Container template không tồn tại"
        }, status=404)
    except Exception as e:
        logger.error(f"Error in update_container_template: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def add_supplier_to_container(request: HttpRequest):
    """
    API endpoint để thêm supplier vào container template.
    
    POST data:
    - container_template_id: int
    - supplier_id: int (Sapo supplier_id)
    
    Returns:
        JSON: {status, message, supplier_data}
    """
    try:
        import json
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        template_id = int(data.get('container_template_id'))
        supplier_id = int(data.get('supplier_id'))
        
        from products.services.container_template_service import ContainerTemplateService
        
        sapo_client = get_sapo_client()
        template_service = ContainerTemplateService(sapo_client)
        
        template_supplier = template_service.add_supplier(template_id, supplier_id)
        
        return JsonResponse({
            "status": "success",
            "message": f"Đã thêm supplier {template_supplier.supplier_name} vào container template",
            "container_template_id": template_id,
            "supplier": {
                "id": template_supplier.supplier_id,
                "code": template_supplier.supplier_code,
                "name": template_supplier.supplier_name,
                "logo_path": template_supplier.supplier_logo_path
            },
            "supplier_data": {
                "id": template_supplier.supplier_id,
                "code": template_supplier.supplier_code,
                "name": template_supplier.supplier_name,
                "logo_path": template_supplier.supplier_logo_path
            }
        })
        
    except Exception as e:
        logger.error(f"Error in add_supplier_to_container: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def set_default_supplier(request: HttpRequest, template_id: int):
    """
    API endpoint để đặt NSX mặc định cho container template.
    
    POST data:
    - supplier_id: int (Sapo supplier_id, có thể null để xóa)
    
    Returns:
        JSON: {status, message}
    """
    try:
        import json
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        supplier_id = data.get('supplier_id')
        if supplier_id:
            supplier_id = int(supplier_id)
        else:
            supplier_id = None
        
        template = ContainerTemplate.objects.get(id=template_id)
        
        # Kiểm tra supplier có trong danh sách suppliers của template không
        if supplier_id:
            supplier_exists = template.suppliers.filter(supplier_id=supplier_id).exists()
            if not supplier_exists:
                return JsonResponse({
                    "status": "error",
                    "message": "Supplier này chưa được thêm vào container template"
                }, status=400)
            
            # Lấy thông tin supplier từ ContainerTemplateSupplier
            template_supplier = template.suppliers.get(supplier_id=supplier_id)
            template.default_supplier_id = supplier_id
            template.default_supplier_code = template_supplier.supplier_code
            template.default_supplier_name = template_supplier.supplier_name
        else:
            # Xóa default supplier
            template.default_supplier_id = None
            template.default_supplier_code = ''
            template.default_supplier_name = ''
        
        template.save()
        
        return JsonResponse({
            "status": "success",
            "message": f"Đã {'đặt' if supplier_id else 'xóa'} NSX mặc định cho container template {template.code}"
        })
        
    except ContainerTemplate.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Container template không tồn tại"
        }, status=404)
    except Exception as e:
        logger.error(f"Error in set_default_supplier: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def resync_container_template_stats(request: HttpRequest, template_id: int):
    """
    API endpoint để tính toán lại avg_total_amount và avg_import_cycle_days từ các SPO completed.
    
    POST /products/container-templates/{template_id}/resync-stats/
    
    Returns:
        JSON: {status, message, avg_total_amount, avg_import_cycle_days, spo_count}
    """
    try:
        from products.services.container_template_service import ContainerTemplateService
        from products.models import ContainerTemplate
        
        template = ContainerTemplate.objects.get(id=template_id)
        
        sapo_client = get_sapo_client()
        template_service = ContainerTemplateService(sapo_client)
        
        result = template_service.resync_template_stats(template_id)
        
        if result['status'] == 'success':
            return JsonResponse({
                "status": "success",
                "message": result['message'],
                "avg_total_amount": result['avg_total_amount'],
                "avg_import_cycle_days": result['avg_import_cycle_days'],
                "spo_count": result['spo_count']
            })
        else:
            return JsonResponse({
                "status": "warning",
                "message": result['message'],
                "spo_count": result['spo_count']
            })
            
    except ContainerTemplate.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Container template không tồn tại"
        }, status=404)
    except Exception as e:
        logger.error(f"Error in resync_container_template_stats: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
def get_suppliers_for_select(request: HttpRequest):
    """
    API endpoint để lấy danh sách suppliers với logo (cho select dropdown).
    
    Returns:
        JSON: {status, suppliers: [{id, code, name, logo_path}, ...]}
    """
    try:
        from products.services.sapo_supplier_service import SapoSupplierService
        
        sapo_client = get_sapo_client()
        supplier_service = SapoSupplierService(sapo_client)
        
        # Lấy tất cả suppliers đang hoạt động
        all_suppliers = supplier_service.get_all_suppliers(status="active")
        
        # Convert to simple dict
        suppliers_data = []
        for supplier in all_suppliers:
            suppliers_data.append({
                "id": supplier.id,
                "code": supplier.code,
                "name": supplier.name,
                "logo_path": supplier.logo_path or "",
            })
        
        # Sort by name
        suppliers_data.sort(key=lambda x: x["name"])
        
        return JsonResponse({
            "status": "success",
            "suppliers": suppliers_data
        })
        
    except Exception as e:
        logger.error(f"Error in get_suppliers_for_select: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def remove_supplier_from_container(request: HttpRequest):
    """
    API endpoint để xóa supplier khỏi container template.
    
    POST data:
    - container_template_id: int
    - supplier_id: int
    
    Returns:
        JSON: {status, message}
    """
    try:
        import json
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        template_id = int(data.get('container_template_id'))
        supplier_id = int(data.get('supplier_id'))
        
        from products.services.container_template_service import ContainerTemplateService
        
        sapo_client = get_sapo_client()
        template_service = ContainerTemplateService(sapo_client)
        
        template_service.remove_supplier(template_id, supplier_id)
        
        return JsonResponse({
            "status": "success",
            "message": "Đã xóa supplier khỏi container template"
        })
        
    except Exception as e:
        logger.error(f"Error in remove_supplier_from_container: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


# ========================= SUM PURCHASE ORDER (SPO) =========================

@admin_only
def sum_purchase_order_list(request: HttpRequest):
    """
    Danh sách SPO.
    """
    context = {
        "title": "Quản lý Đợt Nhập Container (SPO)",
        "spos": [],
        "total": 0,
        "container_templates": [],
        "status_choices": SumPurchaseOrder.STATUS_CHOICES,
    }
    
    try:
        # Lấy container templates để hiển thị trong form tạo SPO
        context["container_templates"] = ContainerTemplate.objects.filter(is_active=True).order_by('code')
        
        # Get all SPOs
        from django.db.models import Count
        from products.services.spo_po_service import SPOPOService
        from products.services.sapo_supplier_service import SapoSupplierService
        
        # Order by created_date (nếu có) hoặc created_at (fallback)
        # Lưu ý: Cần chạy migration 0013_sumpurchaseorder_created_date.py trên server Ubuntu
        try:
            spos = SumPurchaseOrder.objects.select_related('container_template') \
                .prefetch_related('spo_purchase_orders') \
                .annotate(
                    po_count=Count('spo_purchase_orders', distinct=True)
                ).order_by('created_date', 'created_at')
        except Exception as e:
            # Fallback nếu migration chưa chạy (created_date chưa có trong DB)
            logger.warning(f"Ordering by created_date failed, using created_at only: {e}")
            spos = SumPurchaseOrder.objects.select_related('container_template') \
                .prefetch_related('spo_purchase_orders') \
                .annotate(
                    po_count=Count('spo_purchase_orders', distinct=True)
                ).order_by('created_at')
        
        # Tính toán động từ Sapo cho mỗi SPO
        sapo_client = get_sapo_client()
        spo_po_service = SPOPOService(sapo_client)
        supplier_service = SapoSupplierService(sapo_client)

        # Lấy tất cả active suppliers để map tên, logo
        all_suppliers = supplier_service.get_all_suppliers(status="active")
        supplier_map = {s.id: s for s in all_suppliers}
        
        for spo in spos:
            po_ids = [spo_po.purchase_order.sapo_order_supplier_id for spo_po in spo.spo_purchase_orders.all() if spo_po.purchase_order]
            
            # Init list supplier để hiển thị
            spo.suppliers_display_list = []
            
            if po_ids:
                try:
                    # Tính tổng amount và quantity từ Sapo
                    total_amount = Decimal('0')
                    total_quantity = 0
                    
                    # Aggregate theo supplier
                    spo_supplier_map = {} # supplier_id -> {'name': '', 'logo': '', 'cbm': 0, 'count': 0}
                    
                    for po_id in po_ids:
                        po_data = spo_po_service.get_po_from_sapo(po_id)
                        total_amount += po_data.get('total_amount', Decimal('0'))
                        total_quantity += po_data.get('total_quantity', 0)
                        
                        # Supplier info
                        # API PO trả về supplier_id
                        s_id = po_data.get('supplier_id')
                        s_cbm = po_data.get('total_cpm', Decimal('0'))
                        
                        if s_id:
                            if s_id not in spo_supplier_map:
                                # Lookup info từ supplier_map (đã lấy từ trước)
                                s_info = supplier_map.get(s_id)
                                spo_supplier_map[s_id] = {
                                    'id': s_id,
                                    'name': s_info.name if s_info else po_data.get('supplier_name', f'Supplier {s_id}'),
                                    'logo_path': s_info.logo_path if s_info else '',
                                    'cbm': Decimal('0'),
                                    'count': 0
                                }
                            
                            spo_supplier_map[s_id]['cbm'] += s_cbm
                            spo_supplier_map[s_id]['count'] += 1
                    
                    # Convert map to list & sort by CBM desc
                    spo.suppliers_display_list = list(spo_supplier_map.values())
                    spo.suppliers_display_list.sort(key=lambda x: x['cbm'], reverse=True)
                    
                    # Gán vào SPO object (không lưu DB, chỉ để hiển thị)
                    spo.total_po_amount_val = total_amount
                    spo.total_po_quantity_val = total_quantity
                except Exception as e:
                    logger.warning(f"Error calculating totals for SPO {spo.id}: {e}")
                    spo.total_po_amount_val = Decimal('0')
                    spo.total_po_quantity_val = 0
            else:
                spo.total_po_amount_val = Decimal('0')
                spo.total_po_quantity_val = 0
        
        context["spos"] = spos
        context["total"] = spos.count()
    except Exception as e:
        logger.error(f"Error in sum_purchase_order_list: {e}", exc_info=True)
        context["error"] = str(e)
    
    return render(request, "products/sum_purchase_order_list.html", context)


@admin_only
def sum_purchase_order_detail(request: HttpRequest, spo_id: int):
    """
    Chi tiết SPO.
    """
    context = {
        "title": "Chi tiết Đợt Nhập Container",
        "spo": None,
        "purchase_orders": [],
        "line_items": [],
    }
    
    try:
        from products.services.sum_purchase_order_service import SumPurchaseOrderService
        from products.services.spo_po_service import SPOPOService
        
        spo = SumPurchaseOrder.objects.select_related('container_template').prefetch_related(
            'costs',
            'documents'
        ).get(id=spo_id)
        context["spo"] = spo
        
        # Lấy danh sách PO từ SPOPurchaseOrder với đầy đủ thông tin từ PurchaseOrder model
        spo_po_relations = spo.spo_purchase_orders.select_related('purchase_order').prefetch_related(
            'purchase_order__costs',
            'purchase_order__payments'
        ).all()
        
        # Lấy thông tin PO từ Sapo API và kết hợp với PurchaseOrder model
        sapo_client = get_sapo_client()
        spo_po_service = SPOPOService(sapo_client)
        
        purchase_orders_data = []
        all_line_items = []
        total_quantity = 0
        total_amount = Decimal('0')
        total_packages = 0
        
        for spo_po_rel in spo_po_relations:
            if not spo_po_rel.purchase_order:
                continue
                
            po = spo_po_rel.purchase_order
            po_id = po.sapo_order_supplier_id
            
            try:
                # Lấy thông tin từ Sapo API
                po_data = spo_po_service.get_po_from_sapo(po_id)
                
                # Cập nhật product_amount_cny từ Sapo API (tính từ price_tq trong metadata)
                product_amount_cny_from_api = float(po_data.get('product_amount_cny', 0))
                if product_amount_cny_from_api > 0:
                    # Cập nhật vào DB nếu khác với giá trị hiện tại
                    if po.product_amount_cny != Decimal(str(product_amount_cny_from_api)):
                        po.product_amount_cny = Decimal(str(product_amount_cny_from_api))
                        po.calculate_total_amount()  # Tính lại total_amount_cny
                        po.save()
                
                # Bổ sung thông tin từ PurchaseOrder model
                po_data['po_id'] = po.id
                po_data['delivery_status'] = po.delivery_status
                po_data['delivery_status_display'] = po.get_delivery_status_display()
                po_data['delivery_timeline'] = po.delivery_timeline
                po_data['expected_delivery_date'] = po.expected_delivery_date
                # Sử dụng giá trị từ API nếu có, nếu không thì dùng từ DB
                po_data['product_amount_cny'] = product_amount_cny_from_api if product_amount_cny_from_api > 0 else float(po.product_amount_cny)
                po_data['total_amount_cny'] = float(po.total_amount_cny)
                po_data['paid_amount_cny'] = float(po.paid_amount_cny)
                po_data['remaining_amount_cny'] = float(po.total_amount_cny - po.paid_amount_cny)
                
                # Lấy costs và gộp theo cost_type (mỗi loại chỉ 1 dòng)
                # Lấy total_cbm từ po_data (đã tính từ Sapo API)
                po_total_cbm = float(po_data.get('total_cbm', 0) or 0)
                
                # Gộp costs theo cost_type
                costs_by_type = {}
                for cost in po.costs.all():
                    cost_type = cost.cost_type
                    if cost_type not in costs_by_type:
                        costs_by_type[cost_type] = {
                            'id': cost.id,  # Giữ ID đầu tiên để delete
                            'cost_type': cost_type,
                            'cost_type_display': cost.get_cost_type_display(),
                            'amount_cny': Decimal('0'),
                            'cbm': None,
                            'description': '',  # Gộp descriptions nếu cần
                            'cost_ids': [],  # Lưu tất cả IDs để delete
                        }
                    
                    costs_by_type[cost_type]['amount_cny'] += cost.amount_cny
                    costs_by_type[cost_type]['cost_ids'].append(cost.id)
                    # Lấy CBM từ cost đầu tiên có CBM
                    if not costs_by_type[cost_type]['cbm'] and cost.cbm:
                        costs_by_type[cost_type]['cbm'] = float(cost.cbm)
                    # Gộp description (nếu có)
                    if cost.description:
                        if costs_by_type[cost_type]['description']:
                            costs_by_type[cost_type]['description'] += '; ' + cost.description
                        else:
                            costs_by_type[cost_type]['description'] = cost.description
                
                # Chuyển sang list và tính giá/m³
                import json
                po_data['costs'] = []
                for cost_type, cost_data in costs_by_type.items():
                    amount_cny = float(cost_data['amount_cny'])
                    
                    # Tính giá/m³: ưu tiên dùng CBM của cost, nếu không có thì dùng total_cbm của PO
                    cbm_for_calc = None
                    if cost_data['cbm'] and cost_data['cbm'] > 0:
                        cbm_for_calc = cost_data['cbm']
                    elif po_total_cbm > 0:
                        cbm_for_calc = po_total_cbm
                    
                    final_cost_data = {
                        'id': cost_data['id'],  # ID đầu tiên (để tương thích với delete)
                        'cost_ids': cost_data['cost_ids'],  # Tất cả IDs để delete (list)
                        'cost_ids_json': json.dumps(cost_data['cost_ids']),  # JSON string cho template
                        'cost_type': cost_type,
                        'cost_type_display': cost_data['cost_type_display'],
                        'amount_cny': amount_cny,
                        'cbm': cost_data['cbm'],
                        'description': cost_data['description'],
                    }
                    
                    if cbm_for_calc and cbm_for_calc > 0:
                        final_cost_data['price_per_cbm'] = round(amount_cny / cbm_for_calc, 2)
                    else:
                        final_cost_data['price_per_cbm'] = None
                    
                    po_data['costs'].append(final_cost_data)
                # Tính tổng phí từ costs
                total_costs_cny = sum(float(cost.amount_cny) for cost in po.costs.all())
                po_data['total_costs_cny'] = total_costs_cny
                
                # Lấy payments
                po_data['payments'] = [
                    {
                        'id': payment.id,
                        'payment_type': payment.payment_type,
                        'payment_type_display': payment.get_payment_type_display(),
                        'amount_cny': float(payment.amount_cny),
                        'amount_vnd': float(payment.amount_vnd) if payment.amount_vnd else None,
                        'exchange_rate': float(payment.exchange_rate) if payment.exchange_rate else None,
                        'payment_date': payment.payment_date,
                        'description': payment.description,
                    }
                    for payment in po.payments.all().order_by('-payment_date')
                ]
                
                purchase_orders_data.append(po_data)
                all_line_items.extend(po_data.get('line_items', []))
                total_quantity += po_data.get('total_quantity', 0)
                total_amount += po_data.get('total_amount', Decimal('0'))
                total_packages += po_data.get('total_quantity', 0)  # Giả định 1 item = 1 package
            except Exception as e:
                logger.warning(f"Error getting PO {po_id}: {e}")
        
        context["purchase_orders"] = purchase_orders_data
        context["line_items"] = all_line_items
        context["total_packages"] = total_packages
        context["total_quantity"] = total_quantity
        context["total_amount"] = total_amount
        
        # Tính lại total_cbm của SPO
        spo_service = SumPurchaseOrderService(sapo_client)
        spo_service._recalculate_spo_cbm(spo)
        spo.refresh_from_db()
        
        # Lấy ngày dự kiến từ warehouse stage trong timeline
        warehouse_planned_date = None
        if spo.timeline:
            warehouse_stage_name = None
            if spo.destination_port == 'hcm':
                warehouse_stage_name = 'arrived_warehouse_hcm'
            elif spo.destination_port == 'haiphong':
                warehouse_stage_name = 'arrived_warehouse_hn'
            
            if warehouse_stage_name:
                for stage in spo.timeline:
                    if stage.get('stage') == warehouse_stage_name and stage.get('planned_date'):
                        from datetime import datetime
                        try:
                            # Parse date string YYYY-MM-DD
                            d_str = stage['planned_date']
                            if 'T' in d_str:
                                warehouse_planned_date = datetime.fromisoformat(d_str.replace('Z', '+00:00'))
                            else:
                                warehouse_planned_date = datetime.strptime(d_str, '%Y-%m-%d')
                        except:
                            pass
                        break
        
        context["warehouse_planned_date"] = warehouse_planned_date
        
        # Analyze timeline stages for display
        from datetime import datetime, timedelta
        today = datetime.now().date()
        stage_analysis = {}
        
        for stage_data in spo.timeline:
            stage_code = stage_data.get('stage')
            planned_date = stage_data.get('planned_date')
            actual_date = stage_data.get('actual_date')
            
            analysis = {
                'has_actual': bool(actual_date),
                'has_planned': bool(planned_date),
                'tag': None,
                'tag_color': None,
                'days_diff': None
            }
            
            # Parse dates
            planned_dt = None
            actual_dt = None
            
            if planned_date:
                try:
                    if 'T' in planned_date:
                        planned_dt = datetime.fromisoformat(planned_date.replace('Z', '+00:00')).date()
                    else:
                        planned_dt = datetime.strptime(planned_date, '%Y-%m-%d').date()
                except: 
                    pass
            
            if actual_date:
                try:
                    if 'T' in actual_date:
                        actual_dt = datetime.fromisoformat(actual_date.replace('Z', '+00:00')).date()
                    else:
                        actual_dt = datetime.strptime(actual_date, '%Y-%m-%d').date()
                except: 
                    pass
            
            # Generate tags
            if actual_dt:
                # Case A: Completed
                if planned_dt:
                    days_diff = (actual_dt - planned_dt).days
                    if days_diff <= 0:
                        analysis['tag'] = 'Đúng hẹn'
                        analysis['tag_color'] = 'emerald'
                    else:
                        analysis['tag'] = f'Trễ {days_diff} ngày'
                        analysis['tag_color'] = 'red'
                    analysis['days_diff'] = days_diff
            elif planned_dt:
                # Case B: Planned but not completed
                days_diff = (planned_dt - today).days
                if days_diff > 0:
                    analysis['tag'] = f'Còn {days_diff} ngày'
                    analysis['tag_color'] = 'blue'
                elif days_diff < 0:
                    analysis['tag'] = f'Trễ deadline {abs(days_diff)} ngày'
                    analysis['tag_color'] = 'red'
                else:
                    analysis['tag'] = 'Hôm nay'
                    analysis['tag_color'] = 'amber'
                analysis['days_diff'] = days_diff
            
            stage_analysis[stage_code] = analysis
        
        context['stage_analysis'] = stage_analysis
        context['today'] = today
        
        # Lấy SPO Costs (dynamic costs)
        spo_costs = spo.costs.all().order_by('-created_at')
        context["spo_costs"] = [
            {
                'id': cost.id,
                'name': cost.name,
                'amount_vnd': float(cost.amount_vnd),
                'note': cost.note,
                'created_at': cost.created_at,
            }
            for cost in spo_costs
        ]
        total_spo_costs = sum(float(cost.amount_vnd) for cost in spo_costs)
        context["total_spo_costs"] = total_spo_costs
        
        # Lấy SPO Documents
        spo_documents = spo.documents.all().order_by('-uploaded_at')
        context["spo_documents"] = [
            {
                'id': doc.id,
                'name': doc.name or doc.file.name.split('/')[-1],
                'file': doc.file,
                'file_url': doc.file.url if doc.file else None,
                'uploaded_at': doc.uploaded_at,
                'uploaded_by': doc.uploaded_by.username if doc.uploaded_by else None,
            }
            for doc in spo_documents
        ]
    except SumPurchaseOrder.DoesNotExist:
        context["error"] = "SPO không tồn tại"
    except Exception as e:
        logger.error(f"Error in sum_purchase_order_detail: {e}", exc_info=True)
        context["error"] = str(e)
    
    return render(request, "products/sum_purchase_order_detail.html", context)


@admin_only
@require_POST
def create_sum_purchase_order(request: HttpRequest):
    """
    API endpoint để tạo SPO mới.
    
    POST data:
    - container_template_id: int (required)
    - name: str (optional)
    - destination_port: str ('hcm' hoặc 'haiphong', optional)
    - expected_arrival_date: str (YYYY-MM-DD format, optional)
    - created_date: str (YYYY-MM-DD format, optional)
    
    Returns:
        JSON: {status, message, spo_id, spo_code}
    """
    try:
        import json
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        container_template_id = int(data.get('container_template_id'))
        name = data.get('name', '').strip() or None
        destination_port = data.get('destination_port', '').strip() or None
        expected_arrival_date = data.get('expected_arrival_date', '').strip() or None
        created_date = data.get('created_date', '').strip() or None
        
        from products.services.sum_purchase_order_service import SumPurchaseOrderService
        
        sapo_client = get_sapo_client()
        spo_service = SumPurchaseOrderService(sapo_client)
        
        spo = spo_service.create_spo(
            container_template_id, 
            name=name,
            destination_port=destination_port,
            expected_arrival_date=expected_arrival_date,
            created_date=created_date
        )
        
        return JsonResponse({
            "status": "success",
            "message": f"Đã tạo SPO {spo.code}",
            "spo_id": spo.id,
            "spo_code": spo.code
        })
        
    except Exception as e:
        logger.error(f"Error in create_sum_purchase_order: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def add_po_to_spo(request: HttpRequest):
    """
    API endpoint để thêm PO vào SPO.
    
    POST data:
    - spo_id: int (required)
    - po_ids: List[int] (optional) - Sapo order_supplier IDs
    - tag: str (optional) - Tag để tìm PO
    
    Returns:
        JSON: {status, message, added_count}
    """
    try:
        import json
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        spo_id = int(data.get('spo_id'))
        po_ids = data.get('po_ids', [])
        tag = data.get('tag', '').strip() or None
        domestic_shipping_cn = data.get('domestic_shipping_cn')
        expected_production_date = data.get('expected_production_date')
        expected_delivery_date = data.get('expected_delivery_date')
        
        # Convert po_ids to list of ints
        if po_ids and isinstance(po_ids, str):
            import ast
            po_ids = ast.literal_eval(po_ids)
        if po_ids:
            po_ids = [int(pid) for pid in po_ids]
        
        # Parse dates
        prod_date = None
        deliv_date = None
        if expected_production_date:
            try:
                prod_date = date.fromisoformat(expected_production_date)
            except:
                pass
        if expected_delivery_date:
            try:
                deliv_date = date.fromisoformat(expected_delivery_date)
            except:
                pass
        
        # Parse domestic_shipping_cn
        shipping_cn = Decimal('0')
        if domestic_shipping_cn:
            try:
                shipping_cn = Decimal(str(domestic_shipping_cn))
            except:
                pass
        
        from products.services.sum_purchase_order_service import SumPurchaseOrderService
        
        sapo_client = get_sapo_client()
        spo_service = SumPurchaseOrderService(sapo_client)
        
        spo = spo_service.add_po_to_spo(
            spo_id, 
            po_ids=po_ids, 
            tag=tag,
            domestic_shipping_cn=shipping_cn,
            expected_production_date=prod_date,
            expected_delivery_date=deliv_date
        )
        
        added_count = spo.spo_purchase_orders.count()
        
        return JsonResponse({
            "status": "success",
            "message": f"Đã thêm {added_count} PO vào SPO {spo.code}",
            "added_count": added_count
        })
        
    except Exception as e:
        logger.error(f"Error in add_po_to_spo: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def sync_po_from_sapo(request: HttpRequest):
    """
    API endpoint để lấy thông tin PO từ Sapo API (không lưu DB).
    
    POST data:
    - po_id: int (Sapo order_supplier_id) hoặc
    - tag: str (lấy tất cả PO có tag)
    
    Returns:
        JSON: {status, message, po_data hoặc po_list}
    """
    try:
        import json
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        po_id = data.get('po_id')
        tag = data.get('tag', '').strip() or None
        
        from products.services.sum_purchase_order_service import SumPurchaseOrderService
        
        sapo_client = get_sapo_client()
        spo_service = SumPurchaseOrderService(sapo_client)
        
        from products.services.spo_po_service import SPOPOService
        spo_po_service = SPOPOService(sapo_client)
        
        synced_count = 0
        
        if po_id:
            # Lấy 1 PO từ Sapo
            po_id = int(po_id)
            try:
                po_data = spo_po_service.get_po_from_sapo(po_id)
                return JsonResponse({
                    "status": "success",
                    "message": f"Đã lấy thông tin PO {po_data.get('code')}",
                    "po_data": po_data
                })
            except Exception as e:
                return JsonResponse({
                    "status": "error",
                    "message": str(e)
                }, status=400)
        elif tag:
            # Lấy tất cả PO có tag từ Sapo
            response = sapo_client.core.list_order_suppliers_raw(tags=tag, limit=250)
            order_suppliers = response.get('order_suppliers', [])
            po_ids = [os.get('id') for os in order_suppliers if os.get('id')]
            
            po_list = []
            for po_id in po_ids:
                try:
                    po_data = spo_po_service.get_po_from_sapo(po_id)
                    po_list.append(po_data)
                    synced_count += 1
                except Exception as e:
                    logger.warning(f"Error getting PO {po_id}: {e}")
            
            return JsonResponse({
                "status": "success",
                "message": f"Đã lấy {synced_count} PO từ Sapo",
                "po_list": po_list,
                "synced_count": synced_count
            })
        else:
            return JsonResponse({
                "status": "error",
                "message": "Phải cung cấp po_id hoặc tag"
            }, status=400)
        
    except Exception as e:
        logger.error(f"Error in sync_po_from_sapo: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def update_spo_status(request: HttpRequest):
    """
    API endpoint để cập nhật trạng thái SPO.
    
    POST data:
    - spo_id: int
    - status: str
    - actual_date: str (ISO datetime, optional)
    - note: str (optional)
    
    Returns:
        JSON: {status, message}
    """
    try:
        import json
        from datetime import datetime
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        spo_id = int(data.get('spo_id'))
        new_status = data.get('status')
        actual_date_str = data.get('actual_date', '').strip()
        note = data.get('note', '').strip()
        
        spo = SumPurchaseOrder.objects.get(id=spo_id)
        
        # Validate status
        valid_statuses = [choice[0] for choice in SumPurchaseOrder.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return JsonResponse({
                "status": "error",
                "message": f"Status không hợp lệ. Phải là một trong: {', '.join(valid_statuses)}"
            }, status=400)
        
        # Parse actual_date nếu có
        actual_date = None
        if actual_date_str:
            try:
                actual_date = datetime.fromisoformat(actual_date_str.replace('Z', '+00:00'))
            except ValueError:
                actual_date = None
        
        # Update status
        spo.update_status(new_status, actual_date=actual_date, note=note)
        
        return JsonResponse({
            "status": "success",
            "message": f"Đã cập nhật trạng thái SPO {spo.code} thành {spo.get_status_display()}"
        })
        
    except SumPurchaseOrder.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "SPO không tồn tại"
        }, status=404)
    except Exception as e:
        logger.error(f"Error in update_spo_status: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def update_timeline_planned_date(request: HttpRequest):
    """
    API endpoint để cập nhật planned_date cho một stage trong timeline.
    
    POST data:
    - spo_id: int
    - stage: str (stage name)
    - planned_date: str (YYYY-MM-DD format)
    
    Returns:
        JSON: {status, message}
    """
    try:
        import json
        from datetime import date
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        spo_id = int(data.get('spo_id'))
        stage_name = data.get('stage')
        planned_date_str = data.get('planned_date', '').strip()
        
        if not stage_name:
            return JsonResponse({
                "status": "error",
                "message": "Stage name là bắt buộc"
            }, status=400)
        
        if not planned_date_str:
            return JsonResponse({
                "status": "error",
                "message": "Planned date là bắt buộc"
            }, status=400)
        
        spo = SumPurchaseOrder.objects.get(id=spo_id)
        
        # Parse planned_date
        try:
            planned_date = date.fromisoformat(planned_date_str)
        except ValueError:
            return JsonResponse({
                "status": "error",
                "message": f"Ngày không hợp lệ: {planned_date_str}. Vui lòng dùng format YYYY-MM-DD"
            }, status=400)
        
        # Custom Logic: Sync Expected Arrival Date
        # Nếu stage là 'arrived_vn' hoặc 'completed', cập nhật luôn vào model field
        if stage_name in ['arrived_vn', 'completed']:
             spo.expected_arrival_date = planned_date
             # Không cần lưu vào timeline JSON để tránh duplicate dữ liệu
             # Nhưng để đảm bảo hiển thị đúng ở các chỗ khác, ta vẫn có thể lưu hoặc chỉ lưu model field.
             # Theo yêu cầu "Bỏ 1 trong 2", ta sẽ ưu tiên lưu vào model field.
             # Tuy nhiên, timeline cần record để hiển thị trên UI nếu UI loop qua timeline.
             # Giải pháp: UI sẽ check model field cho stage này. Timeline chỉ lưu record để biết là đã có plan.
             
        # Tìm và cập nhật stage trong timeline
        stage_found = False
        for stage in spo.timeline:
            if stage.get('stage') == stage_name:
                stage['planned_date'] = planned_date.isoformat()
                stage_found = True
                break
        
        # Nếu chưa có trong timeline, thêm mới (để đảm bảo hiển thị trên UI)
        if not stage_found:
             spo.timeline.append({
                'stage': stage_name,
                'planned_date': planned_date.isoformat(),
                'actual_date': None,
                'note': ""
            })
        
        spo.save()
        
        return JsonResponse({
            "status": "success",
            "message": f"Đã cập nhật ngày dự kiến cho stage {stage_name}"
        })
        
    except SumPurchaseOrder.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "SPO không tồn tại"
        }, status=404)
    except Exception as e:
        logger.error(f"Error in update_timeline_planned_date: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def allocate_costs(request: HttpRequest):
    """
    API endpoint để phân bổ chi phí chung của SPO.
    
    POST data:
    - spo_id: int
    
    Returns:
        JSON: {status, message, allocation_details}
    """
    try:
        import json
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        spo_id = int(data.get('spo_id'))
        
        from products.services.sum_purchase_order_service import SumPurchaseOrderService
        
        sapo_client = get_sapo_client()
        spo_service = SumPurchaseOrderService(sapo_client)
        
        result = spo_service.calculate_cost_allocation(spo_id)
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error in allocate_costs: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def add_spo_cost(request: HttpRequest):
    """
    API endpoint để thêm chi phí SPO.
    
    POST data:
    - spo_id: int
    - name: str
    - amount_vnd: float
    - note: str (optional)
    
    Returns:
        JSON: {status, message, cost_id}
    """
    try:
        import json
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        spo_id = int(data.get('spo_id'))
        name = data.get('name', '').strip()
        amount_vnd = Decimal(str(data.get('amount_vnd', 0)))
        note = data.get('note', '').strip()
        
        if not name:
            return JsonResponse({
                "status": "error",
                "message": "Tên chi phí không được để trống"
            }, status=400)
        
        spo = get_object_or_404(SumPurchaseOrder, id=spo_id)
        
        cost = SPOCost.objects.create(
            sum_purchase_order=spo,
            name=name,
            amount_vnd=amount_vnd,
            note=note,
            created_by=request.user if request.user.is_authenticated else None
        )
        
        return JsonResponse({
            "status": "success",
            "message": "Thêm chi phí thành công",
            "cost_id": cost.id
        })
        
    except Exception as e:
        logger.error(f"Error in add_spo_cost: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_http_methods(["DELETE"])
def delete_spo_cost(request: HttpRequest, cost_id: int):
    """
    API endpoint để xóa chi phí SPO.
    
    Returns:
        JSON: {status, message}
    """
    try:
        cost = get_object_or_404(SPOCost, id=cost_id)
        cost.delete()
        
        return JsonResponse({
            "status": "success",
            "message": "Xóa chi phí thành công"
        })
        
    except Exception as e:
        logger.error(f"Error in delete_spo_cost: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def upload_spo_document(request: HttpRequest):
    """
    API endpoint để upload chứng từ SPO.
    
    POST data (multipart/form-data):
    - spo_id: int
    - file: File
    - name: str (optional)
    
    Returns:
        JSON: {status, message, document_id}
    """
    try:
        spo_id = int(request.POST.get('spo_id'))
        file = request.FILES.get('file')
        name = request.POST.get('name', '').strip()
        
        if not file:
            return JsonResponse({
                "status": "error",
                "message": "Vui lòng chọn file"
            }, status=400)
        
        spo = get_object_or_404(SumPurchaseOrder, id=spo_id)
        
        document = SPODocument.objects.create(
            sum_purchase_order=spo,
            file=file,
            name=name or file.name,
            uploaded_by=request.user if request.user.is_authenticated else None
        )
        
        return JsonResponse({
            "status": "success",
            "message": "Upload chứng từ thành công",
            "document_id": document.id,
            "document_name": document.name,
            "document_url": document.file.url if document.file else None
        })
        
    except Exception as e:
        logger.error(f"Error in upload_spo_document: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_http_methods(["DELETE"])
def delete_spo_document(request: HttpRequest, document_id: int):
    """
    API endpoint để xóa chứng từ SPO.
    
    Returns:
        JSON: {status, message}
    """
    try:
        document = get_object_or_404(SPODocument, id=document_id)
        document.delete()
        
        return JsonResponse({
            "status": "success",
            "message": "Xóa chứng từ thành công"
        })
        
    except Exception as e:
        logger.error(f"Error in delete_spo_document: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def update_po_delivery_status(request: HttpRequest, po_id: int):
    """
    API endpoint để cập nhật trạng thái giao hàng của PO.
    
    POST data:
    - delivery_status: str (ordered, sent_label, production, delivered)
    - date: str (YYYY-MM-DD format, optional)
    - note: str (optional)
    
    Returns:
        JSON: {status, message}
    """
    try:
        import json
        from datetime import datetime
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        delivery_status = data.get('delivery_status', '').strip()
        date_str = data.get('date', '').strip()
        note = data.get('note', '').strip()
        
        if not delivery_status:
            return JsonResponse({
                "status": "error",
                "message": "Trạng thái không được để trống"
            }, status=400)
        
        # Validate delivery_status
        valid_statuses = ['ordered', 'sent_label', 'production', 'delivered']
        if delivery_status not in valid_statuses:
            return JsonResponse({
                "status": "error",
                "message": f"Trạng thái không hợp lệ. Phải là một trong: {', '.join(valid_statuses)}"
            }, status=400)
        
        # Parse date
        date_obj = None
        if date_str:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({
                    "status": "error",
                    "message": "Định dạng ngày không hợp lệ. Phải là YYYY-MM-DD"
                }, status=400)
        
        # Get PO
        po = get_object_or_404(PurchaseOrder, id=po_id)
        
        # Update delivery status
        po.update_delivery_status(delivery_status, date_obj, note)
        
        return JsonResponse({
            "status": "success",
            "message": "Cập nhật trạng thái thành công"
        })
        
    except Exception as e:
        logger.error(f"Error in update_po_delivery_status: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def add_po_cost(request: HttpRequest, po_id: int):
    """
    API endpoint để thêm chi phí cho PO.
    Chi phí tự động phân bổ theo CBM của PO (không cần nhập CBM thủ công).
    
    POST data:
    - cost_type: str
    - amount_cny: float
    - description: str (optional)
    
    Returns:
        JSON: {status, message, cost_id, price_per_cbm}
    """
    try:
        import json
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        cost_type = data.get('cost_type', '').strip()
        amount_cny = Decimal(str(data.get('amount_cny', 0)))
        description = data.get('description', '').strip()
        
        if not cost_type:
            return JsonResponse({
                "status": "error",
                "message": "Loại chi phí không được để trống"
            }, status=400)
        
        if amount_cny <= 0:
            return JsonResponse({
                "status": "error",
                "message": "Số tiền phải lớn hơn 0"
            }, status=400)
        
        # Get PO
        po = get_object_or_404(PurchaseOrder, id=po_id)
        
        # Lấy total_cbm của PO từ Sapo API
        from products.services.spo_po_service import SPOPOService
        sapo_client = get_sapo_client()
        spo_po_service = SPOPOService(sapo_client)
        
        try:
            po_data = spo_po_service.get_po_from_sapo(po.sapo_order_supplier_id)
            total_cbm = float(po_data.get('total_cbm', 0))
        except Exception as e:
            logger.warning(f"Error getting PO CBM: {e}")
            total_cbm = 0
        
        # Tính CBM tự động (toàn bộ CBM của PO)
        cbm_value = Decimal(str(total_cbm)) if total_cbm > 0 else None
        
        # Tính giá/m³
        price_per_cbm = None
        if cbm_value and cbm_value > 0:
            price_per_cbm = float(amount_cny / cbm_value)
        
        # Create cost
        cost = PurchaseOrderCost.objects.create(
            purchase_order=po,
            cost_type=cost_type,
            amount_cny=amount_cny,
            cbm=cbm_value,
            description=description,
            created_by=request.user if request.user.is_authenticated else None
        )
        
        # Update PO total_amount
        po.calculate_total_amount()
        
        return JsonResponse({
            "status": "success",
            "message": "Thêm chi phí thành công",
            "cost_id": cost.id,
            "price_per_cbm": round(price_per_cbm, 2) if price_per_cbm else None,
            "cbm": float(cbm_value) if cbm_value else None
        })
        
    except Exception as e:
        logger.error(f"Error in add_po_cost: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_http_methods(["DELETE"])
def delete_po_cost(request: HttpRequest, po_id: int, cost_id: int):
    """
    API endpoint để xóa chi phí PO.
    
    Returns:
        JSON: {status, message}
    """
    try:
        cost = get_object_or_404(PurchaseOrderCost, id=cost_id, purchase_order_id=po_id)
        po = cost.purchase_order
        cost.delete()
        
        # Update PO total_amount
        po.calculate_total_amount()
        
        return JsonResponse({
            "status": "success",
            "message": "Xóa chi phí thành công"
        })
        
    except Exception as e:
        logger.error(f"Error in delete_po_cost: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def add_po_payment(request: HttpRequest, po_id: int):
    """
    API endpoint để thêm thanh toán cho PO.
    
    POST data:
    - payment_type: str
    - amount_cny: float
    - amount_vnd: float (optional)
    - payment_date: str (YYYY-MM-DD, optional)
    - description: str (optional)
    
    Returns:
        JSON: {status, message, payment_id}
    """
    try:
        import json
        from datetime import datetime
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        payment_type = data.get('payment_type', '').strip()
        amount_cny = Decimal(str(data.get('amount_cny', 0)))
        amount_vnd = data.get('amount_vnd')
        payment_date_str = data.get('payment_date', '').strip()
        description = data.get('description', '').strip()
        
        if not payment_type:
            return JsonResponse({
                "status": "error",
                "message": "Loại thanh toán không được để trống"
            }, status=400)
        
        if amount_cny <= 0:
            return JsonResponse({
                "status": "error",
                "message": "Số tiền phải lớn hơn 0"
            }, status=400)
        
        # Parse date
        payment_date = None
        if payment_date_str:
            try:
                payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({
                    "status": "error",
                    "message": "Định dạng ngày không hợp lệ. Phải là YYYY-MM-DD"
                }, status=400)
        
        # Get PO
        po = get_object_or_404(PurchaseOrder, id=po_id)
        
        # Parse amount_vnd
        amount_vnd_decimal = None
        if amount_vnd:
            amount_vnd_decimal = Decimal(str(amount_vnd))
        
        # Create payment
        payment = PurchaseOrderPayment.objects.create(
            purchase_order=po,
            payment_type=payment_type,
            amount_cny=amount_cny,
            amount_vnd=amount_vnd_decimal,
            payment_date=payment_date or timezone.now().date(),
            description=description,
            created_by=request.user if request.user.is_authenticated else None
        )
        
        # Update PO paid_amount
        po.calculate_paid_amount()
        
        return JsonResponse({
            "status": "success",
            "message": "Thêm thanh toán thành công",
            "payment_id": payment.id
        })
        
    except Exception as e:
        logger.error(f"Error in add_po_payment: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_http_methods(["DELETE"])
def delete_po_payment(request: HttpRequest, po_id: int, payment_id: int):
    """
    API endpoint để xóa thanh toán PO.
    
    Returns:
        JSON: {status, message}
    """
    try:
        payment = get_object_or_404(PurchaseOrderPayment, id=payment_id, purchase_order_id=po_id)
        po = payment.purchase_order
        payment.delete()
        
        # Update PO paid_amount
        po.calculate_paid_amount()
        
        return JsonResponse({
            "status": "success",
            "message": "Xóa thanh toán thành công"
        })
        
    except Exception as e:
        logger.error(f"Error in delete_po_payment: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_http_methods(["GET"])
def export_po_excel(request: HttpRequest, po_id: int):
    """
    Xuất Excel PO để gửi cho NSX.
    Bao gồm: Ảnh, SKU, Tên VN, Tên TQ, Giá, Số lượng, Số thùng, Kích thước thùng, CBM, Tổng tiền.
    """
    try:
        if not xlsxwriter:
            return JsonResponse({
                "status": "error",
                "message": "Thư viện xlsxwriter chưa được cài đặt"
            }, status=500)
        
        # Get PO
        po = get_object_or_404(PurchaseOrder, id=po_id)
        
        # Lấy thông tin PO từ Sapo API
        from products.services.spo_po_service import SPOPOService
        sapo_client = get_sapo_client()
        spo_po_service = SPOPOService(sapo_client)
        
        po_data = spo_po_service.get_po_from_sapo(po.sapo_order_supplier_id)
        line_items = po_data.get('line_items', [])
        
        if not line_items:
            return JsonResponse({
                "status": "error",
                "message": "PO không có line items"
            }, status=400)
        
        # Tạo thư mục nếu chưa có
        excel_dir = "assets/excel_po"
        os.makedirs(excel_dir, exist_ok=True)
        os.makedirs("assets/saveimage", exist_ok=True)
        
        # Tên file
        supplier_name = po_data.get('supplier_name', 'Supplier').replace('/', '_').replace('\\', '_')
        po_code = po_data.get('code', f'PO-{po_id}').replace('/', '_').replace('\\', '_')
        filename = f"{supplier_name}-{po_code}.xlsx"
        filepath = os.path.join(excel_dir, filename)
        
        # Tạo workbook
        workbook = xlsxwriter.Workbook(filepath)
        worksheet = workbook.add_worksheet()
        worksheet.set_default_row(60)
        worksheet.set_row(0, 20)
        worksheet.set_column('A:A', 5)
        worksheet.set_column('B:B', 40)
        worksheet.set_column('C:C', 15)
        worksheet.set_column('D:D', 20)
        worksheet.set_column('E:E', 20)
        worksheet.set_column('F:F', 12)
        worksheet.set_column('G:G', 12)
        worksheet.set_column('H:H', 12)
        worksheet.set_column('I:I', 20)
        worksheet.set_column('J:J', 12)
        worksheet.set_column('K:K', 15)
        
        # Formats
        cell_text_wrap = workbook.add_format({'text_wrap': True, 'align': 'center', 'valign': 'vcenter'})
        cell_align = workbook.add_format({'align': 'center', 'valign': 'vcenter'})
        cell_first = workbook.add_format({'bold': True, 'bg_color': "#D8E4BC"})
        
        # Headers
        row = 0
        col = 0
        headers = ["#", "Image", "SKU", "VN_Variant", "名称", "单价", "数量", "箱数", "装箱数", "外箱尺寸", "总体积", "总价"]
        for i, header in enumerate(headers):
            worksheet.write(row, col + i, header, cell_first)
        
        # Process line items
        row = 1
        count = 0
        
        for item in line_items:
            variant_id = item.get('variant_id')
            quantity = item.get('quantity', 0)
            sku = item.get('sku', '')
            
            if quantity <= 0:
                continue
            
            # Lấy thông tin variant từ Sapo để có ảnh và metadata
            try:
                variant_data = sapo_client.core.get_variant_raw(variant_id)
                if not variant_data:
                    logger.warning(f"Variant {variant_id} not found")
                    continue
                
                # Lấy product để có metadata
                product_id = variant_data.get('product_id')
                product_dto = None
                variant_meta = None
                
                if product_id:
                    product_dto = SapoProductService(sapo_client).get_product(product_id)
                    if product_dto and product_dto.gdp_metadata:
                        # Tìm variant metadata
                        for v_meta in product_dto.gdp_metadata.variants:
                            if v_meta.id == variant_id:
                                variant_meta = v_meta
                                break
                
                # Lấy ảnh
                images = variant_data.get('images', [])
                image_url = images[0].get('full_path') if images else None
                
                # Tính toán thông tin
                price_cny = item.get('price_cny', 0)
                box_info = variant_meta.box_info if variant_meta else None
                
                # Tính số thùng và CBM
                full_box = box_info.full_box if box_info and box_info.full_box else 1
                num_boxes = round(float(quantity) / full_box, 1) if full_box > 0 else quantity
                
                box_size_str = ""
                total_cbm = 0.0
                if box_info and box_info.length_cm and box_info.width_cm and box_info.height_cm:
                    box_size_str = f"{box_info.height_cm} * {box_info.length_cm} * {box_info.width_cm} cm"
                    # CBM = (dài * rộng * cao * quantity) / 1,000,000 / full_box
                    total_cbm = (box_info.length_cm * box_info.width_cm * box_info.height_cm * quantity) / 1000000 / full_box
                
                # Tên TQ
                name_tq = variant_meta.name_tq if variant_meta and variant_meta.name_tq else ""
                
                # Tên VN variant
                variant_name = item.get('variant_name', '')
                opt1 = variant_data.get('opt1', '')
                
                # Download và lưu ảnh
                image_path = None
                if image_url:
                    try:
                        image_path = f"assets/saveimage/{variant_id}.jpg"
                        if not os.path.exists(image_path):
                            r = requests.get(image_url, allow_redirects=True, timeout=10)
                            if r.status_code == 200:
                                os.makedirs(os.path.dirname(image_path), exist_ok=True)
                                with open(image_path, 'wb') as f:
                                    f.write(r.content)
                    except Exception as e:
                        logger.warning(f"Error downloading image for variant {variant_id}: {e}")
                
                # Write row
                worksheet.write(row, col, count, cell_align)
                
                # Insert image nếu có
                if image_path and os.path.exists(image_path):
                    try:
                        with Image.open(image_path) as img:
                            img_width, img_height = img.size
                            cell_width = 75
                            cell_height = 75
                            x_scale = float(cell_width) / float(img_width)
                            y_scale = float(cell_height) / float(img_height)
                            
                            image_options = {
                                'x_offset': 5,
                                'y_offset': 5,
                                'x_scale': x_scale,
                                'y_scale': y_scale,
                            }
                            worksheet.insert_image(row, col + 1, image_path, image_options)
                    except Exception as e:
                        logger.warning(f"Error inserting image: {e}")
                
                worksheet.write(row, col + 2, sku, cell_align)
                worksheet.write(row, col + 3, opt1 or variant_name, cell_align)
                worksheet.write(row, col + 4, name_tq, cell_text_wrap)
                worksheet.write(row, col + 5, price_cny, cell_align)
                worksheet.write(row, col + 6, quantity, cell_align)
                worksheet.write(row, col + 7, num_boxes, cell_align)
                worksheet.write(row, col + 8, f"{full_box} pcs/box", cell_align)
                worksheet.write(row, col + 9, box_size_str, cell_align)
                worksheet.write(row, col + 10, round(total_cbm * 1.05, 2), cell_align)  # Thêm 5% buffer
                worksheet.write(row, col + 11, float(quantity * price_cny), cell_align)
                
                row += 1
                count += 1
                
            except Exception as e:
                logger.error(f"Error processing line item {variant_id}: {e}", exc_info=True)
                continue
        
        workbook.close()
        
        # Return file
        with open(filepath, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        
    except Exception as e:
        logger.error(f"Error in export_po_excel: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


@admin_only
@require_http_methods(["GET"])
def export_po_labels(request: HttpRequest, po_id: int):
    """
    Xuất nhãn phụ (HTML) cho PO - nhãn xuất nhập khẩu 10x15 (A6).
    Mỗi SKU có 1 nhãn, kết hợp thông tin sản phẩm và model XNK.
    """
    try:
        # Get PO
        po = get_object_or_404(PurchaseOrder, id=po_id)
        
        # Lấy thông tin PO từ Sapo API
        from products.services.spo_po_service import SPOPOService
        from products.services.xnk_model_service import XNKModelService
        
        sapo_client = get_sapo_client()
        spo_po_service = SPOPOService(sapo_client)
        xnk_service = XNKModelService(sapo_client.core_session)
        
        po_data = spo_po_service.get_po_from_sapo(po.sapo_order_supplier_id)
        line_items = po_data.get('line_items', [])
        
        if not line_items:
            return JsonResponse({
                "status": "error",
                "message": "PO không có line items"
            }, status=400)
        
        # ===== BƯỚC 1: Load toàn bộ XNK models =====
        logger.info(f"[export_po_labels] [BƯỚC 1] Loading all XNK models...")
        all_xnk_models = xnk_service.get_all_models()
        # Tạo map với key là SKU (trimmed, normalized)
        xnk_model_map = {}
        for model in all_xnk_models:
            sku = model.get('sku', '').strip()
            if sku:
                # Lưu với key là SKU đã trim (case-sensitive để chính xác)
                xnk_model_map[sku] = model
        
        logger.info(f"[export_po_labels] [BƯỚC 1] ✅ Loaded {len(all_xnk_models)} XNK models. Map has {len(xnk_model_map)} unique SKUs")
        
        # ===== BƯỚC 2: Lấy thông tin supplier và brand =====
        supplier_name = po_data.get('supplier_name', '')
        supplier_code = po_data.get('supplier_code', '')
        supplier_id = po_data.get('supplier_id')
        
        # Lấy supplier address và brand_id từ Sapo
        supplier_address = ""
        brand_id = None
        
        try:
            if supplier_id:
                supplier_data = sapo_client.core.get_supplier_raw(supplier_id)
                if supplier_data:
                    # Lấy address
                    if supplier_data.get('addresses'):
                        addr = supplier_data['addresses'][0]
                        supplier_address = addr.get('address1', '')
                    
                    # Lấy brand_id từ supplier code
                    supplier_code_from_api = supplier_data.get('code', '') or supplier_code
                    if supplier_code_from_api:
                        logger.info(f"[export_po_labels] [BƯỚC 2] Looking for brand with code/name: {supplier_code_from_api}")
                        # Tìm brand theo code hoặc name
                        brands_response = sapo_client.core.list_brands_search_raw(page=1, limit=250, query=supplier_code_from_api)
                        brands = brands_response.get("brands", [])
                        for brand in brands:
                            if brand.get('code', '').upper() == supplier_code_from_api.upper() or brand.get('name', '').upper() == supplier_code_from_api.upper():
                                brand_id = brand.get('id')
                                logger.info(f"[export_po_labels] [BƯỚC 2] ✅ Found brand_id: {brand_id} for supplier {supplier_code_from_api}")
                                break
        except Exception as e:
            logger.warning(f"[export_po_labels] Error getting supplier/brand info: {e}")
        
        # ===== BƯỚC 3: Load toàn bộ variants của NSX (theo brand_id) =====
        variant_sku_xnk_map = {}  # Map: variant_id -> sku_model_xnk
        
        if brand_id:
            logger.info(f"[export_po_labels] [BƯỚC 3] Loading all variants for brand_id={brand_id}...")
            product_service = SapoProductService(sapo_client)
            core_repo = sapo_client.core
            
            # Load tất cả products của brand này (giống variant_list)
            all_products = []
            page = 1
            limit = 250
            
            while True:
                filters = {
                    "page": page,
                    "limit": limit,
                    "status": "active"
                }
                
                products_response = core_repo.list_products_raw(**filters)
                products_data = products_response.get("products", [])
                
                if not products_data:
                    break
                
                # Filter theo brand_id (client-side)
                for product_data in products_data:
                    if product_data.get("brand_id") == brand_id:
                        all_products.append(product_data)
                
                if len(products_data) < limit:
                    break
                
                page += 1
                if page > 100:  # Safety limit
                    break
            
            logger.info(f"[export_po_labels] [BƯỚC 3] Found {len(all_products)} products for brand_id={brand_id}")
            
            # Parse variants và lấy sku_model_xnk từ metadata
            for product_data in all_products:
                product_id = product_data.get("id")
                if not product_id:
                    continue
                
                try:
                    product_dto = product_service.get_product(product_id)
                    if product_dto and product_dto.gdp_metadata:
                        # Lấy sku_model_xnk từ tất cả variants
                        for v_meta in product_dto.gdp_metadata.variants:
                            variant_id = v_meta.id
                            sku_model_xnk = v_meta.sku_model_xnk
                            if sku_model_xnk:
                                variant_sku_xnk_map[variant_id] = sku_model_xnk.strip()
                except Exception as e:
                    logger.warning(f"[export_po_labels] Error parsing product {product_id}: {e}")
                    continue
            
            logger.info(f"[export_po_labels] [BƯỚC 3] ✅ Loaded {len(variant_sku_xnk_map)} variants with sku_model_xnk")
        else:
            logger.warning(f"[export_po_labels] [BƯỚC 3] ⚠️ No brand_id found, skipping variant loading")
        
        # Process line items để tạo labels
        label_items = []
        
        for item in line_items:
            variant_id = item.get('variant_id')
            quantity = item.get('quantity', 0)
            sku = item.get('sku', '')
            
            if quantity <= 0:
                continue
            
            try:
                # Lấy variant từ Sapo (chỉ cần basic info)
                variant_data = sapo_client.core.get_variant_raw(variant_id)
                if not variant_data:
                    continue
                
                # ===== BƯỚC 4: So trùng SKU nhập khẩu với XNK models =====
                xnk_model = None
                nsx_address = supplier_address  # Mặc định dùng supplier address
                sku_model_xnk_value = variant_sku_xnk_map.get(variant_id)  # Lấy từ map đã load
                
                if sku_model_xnk_value:
                    logger.info(f"[export_po_labels] [BƯỚC 4] Variant {variant_id} (SKU: {sku}) - sku_model_xnk: {sku_model_xnk_value}")
                    
                    # Tìm trong XNK model map (exact match)
                    xnk_model = xnk_model_map.get(sku_model_xnk_value)
                    
                    # Nếu không tìm thấy, thử case-insensitive search
                    if not xnk_model:
                        for map_sku, map_model in xnk_model_map.items():
                            if map_sku.upper() == sku_model_xnk_value.upper():
                                xnk_model = map_model
                                break
                    
                    if xnk_model:
                        logger.info(f"[export_po_labels] [BƯỚC 4] ✅ Found XNK model for SKU: '{sku_model_xnk_value}' -> Model SKU: '{xnk_model.get('sku', '')}'")
                        
                        # Lấy NSX address từ XNK model nếu có
                        nsx_address = (
                            xnk_model.get('nsx_address', '') or 
                            xnk_model.get('supplier_address', '') or 
                            xnk_model.get('address', '') or 
                            supplier_address
                        )
                    else:
                        # Log để debug - chỉ lấy 10 SKUs đầu tiên
                        available_skus = list(xnk_model_map.keys())[:10]
                        logger.warning(f"[export_po_labels] [BƯỚC 4] ⚠️ XNK model NOT found for SKU: '{sku_model_xnk_value}'. Available SKUs sample: {available_skus}")
                else:
                    logger.warning(f"[export_po_labels] [BƯỚC 4] ⚠️ Variant {variant_id} (SKU: {sku}) - No sku_model_xnk in variant map")
                
                # Lấy các field từ XNK model (xử lý cả en_name và name_en)
                hs_code = ''
                en_name = ''
                vn_name = ''
                nsx_name = supplier_name
                unit = ''
                
                if xnk_model:
                    hs_code = xnk_model.get('hs_code', '') or ''
                    # Xử lý cả en_name và name_en
                    en_name = xnk_model.get('en_name', '') or xnk_model.get('name_en', '') or ''
                    vn_name = xnk_model.get('vn_name', '') or xnk_model.get('name_vn', '') or ''
                    nsx_name = xnk_model.get('nsx_name', '') or supplier_name
                    unit = xnk_model.get('unit', '') or ''
                
                # Lấy opt1 từ nhiều nguồn (variant_data, item, hoặc parse từ variant_name)
                opt1 = (
                    variant_data.get('opt1', '') or 
                    item.get('opt1', '') or 
                    item.get('variant_options', '') or
                    ''
                )
                
                # Nếu vẫn không có, thử parse từ variant_name (format: "Product Name - opt1")
                if not opt1 and item.get('variant_name'):
                    variant_name = item.get('variant_name', '')
                    if ' - ' in variant_name:
                        parts = variant_name.split(' - ', 1)
                        if len(parts) > 1:
                            opt1 = parts[1].strip()
                
                # Tạo label data cho mỗi sản phẩm (1 label = 1 SKU)
                label_data = {
                    'sku': sku,
                    'barcode': variant_data.get('barcode', ''),
                    'opt1': opt1,
                    'product_name': item.get('product_name', ''),
                    'variant_name': item.get('variant_name', ''),
                    'quantity': quantity,
                    # XNK Model info (từ SKU nhập khẩu)
                    'hs_code': hs_code,
                    'en_name_xnk': en_name,
                    'vn_name_xnk': vn_name,
                    'nsx_name': nsx_name,
                    'nsx_address': nsx_address,
                    'unit': unit,
                    # Debug info
                    'sku_model_xnk': sku_model_xnk_value or '',
                }
                
                # Tạo 1 label cho mỗi SKU (không phải mỗi quantity)
                label_items.append(label_data)
                
            except Exception as e:
                logger.error(f"Error processing label for variant {variant_id}: {e}", exc_info=True)
                continue
        
        # Render template
        context = {
            'po': po,
            'po_data': po_data,
            'label_items': label_items,
        }
        
        return render(request, 'products/po_labels.html', context)
        
    except Exception as e:
        logger.error(f"Error in export_po_labels: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


@admin_only
@require_POST
def delete_container_template(request: HttpRequest, template_id: int):
    """
    API endpoint để xóa container template.
    
    Returns:
        JSON: {status, message}
    """
    try:
        template = get_object_or_404(ContainerTemplate, id=template_id)
        
        # Kiểm tra xem template có đang được sử dụng bởi SPO nào không
        spo_count = template.sum_purchase_orders.count()
        if spo_count > 0:
            return JsonResponse({
                "status": "error",
                "message": f"Không thể xóa template này vì đang được sử dụng bởi {spo_count} SPO. Vui lòng xóa các SPO liên quan trước."
            }, status=400)
        
        # Xóa template (sẽ tự động xóa các suppliers liên quan do CASCADE)
        template_code = template.code
        template.delete()
        
        return JsonResponse({
            "status": "success",
            "message": f"Đã xóa container template {template_code}"
        })
        
    except ContainerTemplate.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Container template không tồn tại"
        }, status=404)
    except Exception as e:
        logger.error(f"Error in delete_container_template: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def delete_sum_purchase_order(request: HttpRequest, spo_id: int):
    """
    API endpoint để xóa Sum Purchase Order (SPO).
    
    Returns:
        JSON: {status, message}
    """
    try:
        spo = get_object_or_404(SumPurchaseOrder, id=spo_id)
        
        # Kiểm tra trạng thái - chỉ cho phép xóa nếu ở trạng thái draft hoặc cancelled
        if spo.status not in ['draft', 'cancelled']:
            return JsonResponse({
                "status": "error",
                "message": f"Không thể xóa SPO ở trạng thái '{spo.get_status_display()}'. Chỉ có thể xóa SPO ở trạng thái 'Nháp' hoặc 'Đã hủy'."
            }, status=400)
        
        # Xóa SPO (sẽ tự động xóa các SPOPurchaseOrder liên quan do CASCADE)
        spo_code = spo.code
        spo.delete()
        
        return JsonResponse({
            "status": "success",
            "message": f"Đã xóa SPO {spo_code}"
        })
        
    except SumPurchaseOrder.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "SPO không tồn tại"
        }, status=404)
    except Exception as e:
        logger.error(f"Error in delete_sum_purchase_order: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def refresh_sales_forecast(request: HttpRequest):
    """
    API endpoint để refresh dữ liệu dự báo bán hàng.
    Tự động tính cả 30 ngày và 10 ngày.
    
    Returns:
        JSON với status và message
    """
    try:
        from products.services.sales_forecast_service import SalesForecastService
        
        sapo_client = get_sapo_client()
        forecast_service = SalesForecastService(sapo_client)
        
        # Tính toán lại với force_refresh=True cho cả 30 và 10 ngày
        logger.info(f"[refresh_sales_forecast] Refreshing forecast for 30 days and 10 days")
        
        # Tính 30 ngày
        forecast_map_30, all_products_30, all_variants_map_30 = forecast_service.calculate_sales_forecast(
            days=30,
            force_refresh=True
        )
        
        # Tính 10 ngày
        forecast_map_10, all_products_10, all_variants_map_10 = forecast_service.calculate_sales_forecast(
            days=10,
            force_refresh=True
        )
        
        return JsonResponse({
            "status": "success",
            "message": f"Đã tính toán lại dự báo cho {len(forecast_map_30)} variants (30 ngày) và {len(forecast_map_10)} variants (10 ngày)",
            "count_30": len(forecast_map_30),
            "count_10": len(forecast_map_10)
        })
        
    except Exception as e:
        logger.error(f"Error in refresh_sales_forecast: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods, require_POST
from typing import List, Dict, Any
import logging

from core.sapo_client import get_sapo_client
from products.services.sapo_product_service import SapoProductService
from products.services.dto import ProductDTO, ProductVariantDTO

logger = logging.getLogger(__name__)


@login_required
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

        # Convert to dict for template và collect brands
        products_data = []
        brands_set = set()
        statuses_set = set()
        
        for product in all_products:
            brand = product.brand or ""
            product_status = product.status or ""
            
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
        context["brands"] = sorted(list(brands_set))  # Danh sách brands để tạo filter buttons
        context["statuses"] = sorted(list(statuses_set))  # Danh sách statuses để tạo filter buttons

    except Exception as e:
        logger.error(f"Error in product_list: {e}", exc_info=True)
        context["error"] = str(e)

    return render(request, "products/product_list.html", context)


@login_required
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


@login_required
def variant_list(request: HttpRequest):
    """
    Danh sách phân loại (variants):
    - Hiển thị danh sách TẤT CẢ variants từ tất cả products (không phân trang)
    - Có thể tìm kiếm theo SKU, barcode, tên
    - Có thể sửa, xoá variant
    """
    context = {
        "title": "Danh sách phân loại",
        "variants": [],
        "total": 0,
    }

    try:
        sapo_client = get_sapo_client()
        product_service = SapoProductService(sapo_client)

        # Lấy TẤT CẢ products để lấy variants (loop qua nhiều pages) - KHÔNG CÓ FILTER GÌ HẾT
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
                logger.warning("Reached max pages limit (1000) in variant_list")
                break

        # Flatten variants từ tất cả products - KHÔNG FILTER GÌ, LẤY TẤT CẢ
        variants_data = []
        brands_set = set()
        statuses_set = set()
        
        for product in all_products:
            brand = product.brand or ""
            if brand:
                brands_set.add(brand)
                
            for variant in product.variants:
                variant_status = variant.status or ""
                if variant_status:
                    statuses_set.add(variant_status)
                
                variants_data.append({
                    "id": variant.id,
                    "product_id": variant.product_id,
                    "product_name": product.name,
                    "brand": brand,  # Thêm brand từ product
                    "sku": variant.sku,
                    "barcode": variant.barcode or "",
                    "name": variant.name,
                    "opt1": variant.opt1 or "",
                    "opt2": variant.opt2 or "",
                    "opt3": variant.opt3 or "",
                    "status": variant_status,
                    "variant_retail_price": variant.variant_retail_price,
                    "variant_whole_price": variant.variant_whole_price,
                    "total_inventory": variant.total_inventory,
                    "total_available": variant.total_available,
                    "weight_value": variant.weight_value,
                    "weight_unit": variant.weight_unit,
                    "gdp_metadata": variant.gdp_metadata,
                })

        context["variants"] = variants_data
        context["total"] = len(variants_data)
        context["brands"] = sorted(list(brands_set))  # Danh sách brands từ products
        context["statuses"] = sorted(list(statuses_set))  # Danh sách statuses từ variants

    except Exception as e:
        logger.error(f"Error in variant_list: {e}", exc_info=True)
        context["error"] = str(e)

    return render(request, "products/variant_list.html", context)


@login_required
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


@login_required
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

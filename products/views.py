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
    - Hiển thị danh sách tất cả sản phẩm từ Sapo
    - Có thể tìm kiếm, lọc theo brand, category, status
    - Có thể sửa, xoá sản phẩm
    """
    context = {
        "title": "Danh sách sản phẩm",
        "products": [],
        "page": 1,
        "limit": 50,
        "total": 0,
    }

    try:
        sapo_client = get_sapo_client()
        product_service = SapoProductService(sapo_client)

        # Lấy query parameters
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 50))
        status = request.GET.get("status", "active")
        search = request.GET.get("search", "").strip()

        # Build filters
        filters = {
            "page": page,
            "limit": limit,
            "status": status,
        }

        if search:
            filters["query"] = search

        # Fetch products
        products = product_service.list_products(**filters)

        # Convert to dict for template
        products_data = []
        for product in products:
            products_data.append({
                "id": product.id,
                "name": product.name,
                "brand": product.brand or "",
                "category": product.category or "",
                "status": product.status,
                "variant_count": product.variant_count,
                "total_inventory": product.total_inventory_all_variants,
                "created_on": product.created_on,
                "modified_on": product.modified_on,
                "gdp_metadata": product.gdp_metadata,
            })

        context["products"] = products_data
        context["page"] = page
        context["limit"] = limit
        context["status"] = status
        context["search"] = search

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
    - Hiển thị danh sách tất cả variants từ tất cả products
    - Có thể tìm kiếm theo SKU, barcode, tên
    - Có thể sửa, xoá variant
    """
    context = {
        "title": "Danh sách phân loại",
        "variants": [],
        "page": 1,
        "limit": 50,
    }

    try:
        sapo_client = get_sapo_client()
        product_service = SapoProductService(sapo_client)

        # Lấy query parameters
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 50))
        status = request.GET.get("status", "active")
        search = request.GET.get("search", "").strip()

        # Fetch products để lấy variants
        filters = {
            "page": page,
            "limit": limit,
            "status": status,
        }

        if search:
            filters["query"] = search

        products = product_service.list_products(**filters)

        # Flatten variants từ tất cả products
        variants_data = []
        for product in products:
            for variant in product.variants:
                # Filter by search nếu có
                if search:
                    search_lower = search.lower()
                    if (search_lower not in (variant.sku or "").lower() and
                        search_lower not in (variant.barcode or "").lower() and
                        search_lower not in (variant.name or "").lower()):
                        continue

                variants_data.append({
                    "id": variant.id,
                    "product_id": variant.product_id,
                    "product_name": product.name,
                    "sku": variant.sku,
                    "barcode": variant.barcode or "",
                    "name": variant.name,
                    "opt1": variant.opt1 or "",
                    "opt2": variant.opt2 or "",
                    "opt3": variant.opt3 or "",
                    "status": variant.status,
                    "variant_retail_price": variant.variant_retail_price,
                    "variant_whole_price": variant.variant_whole_price,
                    "total_inventory": variant.total_inventory,
                    "total_available": variant.total_available,
                    "weight_value": variant.weight_value,
                    "weight_unit": variant.weight_unit,
                    "gdp_metadata": variant.gdp_metadata,
                })

        context["variants"] = variants_data
        context["page"] = page
        context["limit"] = limit
        context["status"] = status
        context["search"] = search

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
    Init metadata cho tất cả sản phẩm chưa có GDP_META.
    
    Endpoint: POST /products/init-all-metadata/
    Tự động init metadata cho tất cả products chưa có, thêm vào cuối description nếu có nội dung.
    """
    try:
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
        
        # Đếm số products cần init
        products_to_init = []
        products_already_have = []
        
        for product in all_products:
            if product.gdp_metadata:
                products_already_have.append(product.id)
            else:
                products_to_init.append(product.id)
        
        # Init metadata cho các products chưa có
        success_count = 0
        error_count = 0
        errors = []
        
        for product_id in products_to_init:
            try:
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

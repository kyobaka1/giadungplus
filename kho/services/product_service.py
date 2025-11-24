# kho/services/product_service.py
"""
Product Service - Lấy và cache thông tin sản phẩm từ Sapo API.
Chủ yếu dùng để lấy hình ảnh sản phẩm cho đơn hàng.
"""

from typing import Dict, Optional, Set
import logging

from core.sapo_client import get_sapo_client

logger = logging.getLogger(__name__)

# Cache mapping variant_id -> image_url
_variant_image_cache: Dict[int, str] = {}
_products_loaded: bool = False


def load_all_products(force_reload: bool = False) -> Dict[int, str]:
    """
    Lấy toàn bộ products từ Sapo API và cache mapping variant_id -> image_url.
    
    Args:
        force_reload: Nếu True, reload lại cache dù đã load rồi
        
    Returns:
        Dict mapping {variant_id: image_url}
        
    Note:
        - Pagination với limit=250 (max)
        - Lấy image đầu tiên của variant (images[0].full_path nếu có)
        - Cache trong memory cho request hiện tại
    """
    global _variant_image_cache, _products_loaded
    
    # Nếu đã load và không force reload, trả về cache
    if _products_loaded and not force_reload:
        return _variant_image_cache
    
    logger.info("[ProductService] Loading all products from Sapo API...")
    
    sapo = get_sapo_client()
    core_repo = sapo.core
    
    # Clear cache nếu force reload
    if force_reload:
        _variant_image_cache.clear()
    
    variant_image_map: Dict[int, str] = {}
    page = 1
    limit = 250  # Max limit theo Sapo API
    max_pages = 100  # Giới hạn an toàn (25000 products)
    
    total_products = 0
    total_variants = 0
    
    while page <= max_pages:
        try:
            # Lấy products với pagination
            response = core_repo.list_products_raw(
                page=page,
                limit=limit,
                status="active"  # Chỉ lấy products active
            )
            
            products = response.get("products", [])
            
            if not products:
                break
            
            # Process từng product
            for product in products:
                total_products += 1
                
                # Lấy variants từ product
                variants = product.get("variants", [])
                
                for variant in variants:
                    variant_id = variant.get("id")
                    if not variant_id:
                        continue
                    
                    total_variants += 1
                    
                    # Lấy image đầu tiên của variant (nếu có)
                    image_url = None
                    images = variant.get("images", [])
                    if images and len(images) > 0:
                        image_url = images[0].get("full_path") or images[0].get("path")
                    
                    # Nếu variant không có image, thử lấy từ product images
                    if not image_url:
                        product_images = product.get("images", [])
                        if product_images and len(product_images) > 0:
                            image_url = product_images[0].get("full_path") or product_images[0].get("path")
                    
                    # Lưu image URL nếu có
                    if image_url:
                        variant_image_map[variant_id] = image_url
            
            logger.debug(f"[ProductService] Loaded page {page}: {len(products)} products, total variants mapped: {len(variant_image_map)}")
            
            # Check nếu hết products (ít hơn limit)
            if len(products) < limit:
                break
            
            page += 1
            
        except Exception as e:
            logger.error(f"[ProductService] Error loading products page {page}: {e}", exc_info=True)
            break
    
    # Update cache
    _variant_image_cache.update(variant_image_map)
    _products_loaded = True
    
    logger.info(f"[ProductService] Loaded {total_products} products, {total_variants} variants, {len(variant_image_map)} variants with images")
    
    return _variant_image_cache


def get_variant_image(variant_id: Optional[int]) -> str:
    """
    Lấy image URL của variant.
    
    Args:
        variant_id: Variant ID
        
    Returns:
        Image URL hoặc empty string nếu không tìm thấy
    """
    if not variant_id:
        return ""
    
    # Ensure products are loaded
    if not _products_loaded:
        load_all_products()
    
    return _variant_image_cache.get(variant_id, "")


def clear_cache():
    """Xóa cache (dùng khi cần reload products)"""
    global _variant_image_cache, _products_loaded
    _variant_image_cache.clear()
    _products_loaded = False


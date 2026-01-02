# kho/services/product_service.py
"""
Product Service - Lấy và cache thông tin sản phẩm từ database cache.
Chủ yếu dùng để lấy hình ảnh sản phẩm cho đơn hàng.
"""

from typing import Dict, Optional, Set
import logging
import time

from products.services.product_cache_service import ProductCacheService

logger = logging.getLogger(__name__)

# Debug print function (tắt mặc định để tránh spam log)
DEBUG_PRINT_ENABLED = False
def debug_print(*args, **kwargs):
    if DEBUG_PRINT_ENABLED:
        print("[DEBUG]", *args, **kwargs)

# Cache mapping variant_id -> image_url (in-memory cache for performance)
_variant_image_cache: Dict[int, str] = {}
_products_loaded: bool = False

# Service instance
_cache_service = ProductCacheService()


def load_all_products(force_reload: bool = False) -> Dict[int, str]:
    """
    Lấy toàn bộ products từ database cache và cache mapping variant_id -> image_url.
    
    Args:
        force_reload: Nếu True, reload lại cache dù đã load rồi
        
    Returns:
        Dict mapping {variant_id: image_url}
        
    Note:
        - Lấy từ database cache (SapoProductCache, SapoVariantCache)
        - Cache trong memory cho request hiện tại để tăng performance
    """
    global _variant_image_cache, _products_loaded
    
    # Nếu đã load và không force reload, trả về cache
    if _products_loaded and not force_reload:
        debug_print("[ProductService] Using cached products (already loaded)")
        return _variant_image_cache
    
    # ========== DEBUG: Track thời gian ==========
    start_time = time.time()
    
    debug_print("[ProductService] Loading all products from database cache...")
    
    # Clear cache nếu force reload
    if force_reload:
        _variant_image_cache.clear()
    
    # Load từ database cache
    load_start = time.time()
    variant_image_map = _cache_service.get_all_variant_images()
    load_time = time.time() - load_start
    
    # Update in-memory cache
    cache_start = time.time()
    _variant_image_cache.update(variant_image_map)
    cache_time = time.time() - cache_start
    _products_loaded = True
    
    total_time = time.time() - start_time
    debug_print(f"[ProductService] TOTAL TIME: {total_time:.2f}s | "
                f"Load from DB: {load_time:.2f}s | "
                f"Cache update: {cache_time:.2f}s | "
                f"Variants with images: {len(variant_image_map)}")
    logger.info(f"[ProductService] Loaded {len(variant_image_map)} variant images from database cache")
    
    return _variant_image_cache


def get_variant_image(variant_id: Optional[int]) -> str:
    """
    Lấy image URL của variant từ database cache.
    
    Args:
        variant_id: Variant ID
        
    Returns:
        Image URL hoặc empty string nếu không tìm thấy
    """
    if not variant_id:
        return ""
    
    # Ensure products are loaded (in-memory cache)
    if not _products_loaded:
        load_all_products()
    
    # Check in-memory cache first
    if variant_id in _variant_image_cache:
        return _variant_image_cache[variant_id]
    
    # Fallback to database cache (single variant lookup)
    image_url = _cache_service.get_variant_image(variant_id)
    if image_url:
        _variant_image_cache[variant_id] = image_url
    
    return image_url


def clear_cache():
    """Xóa cache (dùng khi cần reload products)"""
    global _variant_image_cache, _products_loaded
    _variant_image_cache.clear()
    _products_loaded = False


# products/services/product_cache_service.py
"""
Service để lấy products và variants từ database cache.
Thay thế việc request từ Sapo API.
"""

from typing import Optional, List, Dict, Any
import logging

from products.models import SapoProductCache, SapoVariantCache
from products.services.dto import (
    ProductDTO,
    ProductVariantDTO,
    ProductMetadataDTO,
)
from products.services.metadata_helper import extract_gdp_metadata

logger = logging.getLogger(__name__)


class ProductCacheService:
    """
    Service để lấy products và variants từ database cache.
    """
    
    def get_product(self, product_id: int) -> Optional[ProductDTO]:
        """
        Lấy product từ database cache.
        
        Args:
            product_id: Sapo product ID
            
        Returns:
            ProductDTO với gdp_metadata đã được parse, hoặc None nếu không tìm thấy
        """
        try:
            # Get from cache
            cache = SapoProductCache.objects.filter(product_id=product_id).first()
            
            if not cache:
                logger.debug(f"Product {product_id} not found in cache")
                return None
            
            product_data = cache.data
            
            # Normalize data: convert None lists to empty lists
            if 'variants' in product_data and product_data['variants']:
                for variant_data in product_data['variants']:
                    # Fix images field: None -> []
                    if 'images' in variant_data and variant_data['images'] is None:
                        variant_data['images'] = []
                    # Fix variant_prices field: None -> []
                    if 'variant_prices' in variant_data and variant_data['variant_prices'] is None:
                        variant_data['variant_prices'] = []
                    # Fix inventories field: None -> []
                    if 'inventories' in variant_data and variant_data['inventories'] is None:
                        variant_data['inventories'] = []
            
            # Fix product images field: None -> []
            if 'images' in product_data and product_data['images'] is None:
                product_data['images'] = []
            
            # Parse product DTO
            product_dto = ProductDTO.from_dict(product_data)
            
            # Extract GDP metadata from description field
            metadata, original_desc = extract_gdp_metadata(product_dto.description)
            product_dto.gdp_metadata = metadata
            
            # Assign metadata to each variant
            if metadata and metadata.variants:
                variant_meta_map = {vm.id: vm for vm in metadata.variants}
                for variant in product_dto.variants:
                    variant.gdp_metadata = variant_meta_map.get(variant.id)
            
            logger.debug(f"Fetched product {product_id} from cache: {product_dto.name} ({len(product_dto.variants)} variants)")
            return product_dto
            
        except Exception as e:
            logger.error(f"Error fetching product {product_id} from cache: {e}", exc_info=True)
            return None
    
    def get_variant(self, variant_id: int) -> Optional[ProductVariantDTO]:
        """
        Lấy variant từ database cache.
        
        Args:
            variant_id: Sapo variant ID
            
        Returns:
            ProductVariantDTO hoặc None nếu không tìm thấy
        """
        try:
            # Get from cache
            cache = SapoVariantCache.objects.filter(variant_id=variant_id).first()
            
            if not cache:
                logger.debug(f"Variant {variant_id} not found in cache")
                return None
            
            variant_data = cache.data
            
            # Normalize data
            if 'images' in variant_data and variant_data['images'] is None:
                variant_data['images'] = []
            if 'variant_prices' in variant_data and variant_data['variant_prices'] is None:
                variant_data['variant_prices'] = []
            if 'inventories' in variant_data and variant_data['inventories'] is None:
                variant_data['inventories'] = []
            
            # Parse variant DTO
            variant_dto = ProductVariantDTO.from_dict(variant_data)
            
            logger.debug(f"Fetched variant {variant_id} from cache: {variant_dto.name}")
            return variant_dto
            
        except Exception as e:
            logger.error(f"Error fetching variant {variant_id} from cache: {e}", exc_info=True)
            return None
    
    def get_variant_image(self, variant_id: int) -> str:
        """
        Lấy image URL của variant từ cache.
        
        Args:
            variant_id: Sapo variant ID
            
        Returns:
            Image URL hoặc empty string nếu không tìm thấy
        """
        try:
            cache = SapoVariantCache.objects.filter(variant_id=variant_id).first()
            
            if not cache:
                return ""
            
            variant_data = cache.data
            images = variant_data.get("images", [])
            
            if images and len(images) > 0:
                return images[0].get("full_path") or images[0].get("path") or ""
            
            # Nếu variant không có image, thử lấy từ product
            product_id = variant_data.get("product_id")
            if product_id:
                product_cache = SapoProductCache.objects.filter(product_id=product_id).first()
                if product_cache:
                    product_images = product_cache.data.get("images", [])
                    if product_images and len(product_images) > 0:
                        return product_images[0].get("full_path") or product_images[0].get("path") or ""
            
            return ""
            
        except Exception as e:
            logger.error(f"Error fetching variant image {variant_id} from cache: {e}", exc_info=True)
            return ""
    
    def get_all_variant_images(self) -> Dict[int, str]:
        """
        Lấy mapping variant_id -> image_url cho tất cả variants trong cache.
        
        Returns:
            Dict mapping {variant_id: image_url}
        """
        try:
            variant_images = {}
            
            # Get all variants from cache
            variants = SapoVariantCache.objects.all()
            
            for cache in variants:
                variant_id = cache.variant_id
                variant_data = cache.data
                
                # Lấy image từ variant
                image_url = None
                images = variant_data.get("images", [])
                if images and len(images) > 0:
                    image_url = images[0].get("full_path") or images[0].get("path")
                
                # Nếu variant không có image, thử lấy từ product
                if not image_url:
                    product_id = cache.product_id
                    product_cache = SapoProductCache.objects.filter(product_id=product_id).first()
                    if product_cache:
                        product_images = product_cache.data.get("images", [])
                        if product_images and len(product_images) > 0:
                            image_url = product_images[0].get("full_path") or product_images[0].get("path")
                
                if image_url:
                    variant_images[variant_id] = image_url
            
            logger.info(f"Loaded {len(variant_images)} variant images from cache")
            return variant_images
            
        except Exception as e:
            logger.error(f"Error fetching all variant images from cache: {e}", exc_info=True)
            return {}
    
    def list_products(self, status: Optional[str] = None) -> List[ProductDTO]:
        """
        Lấy danh sách tất cả products từ database cache.
        
        Args:
            status: Filter theo status (optional, nếu None thì lấy tất cả)
            
        Returns:
            List of ProductDTO
        """
        try:
            # Query từ cache
            queryset = SapoProductCache.objects.all()
            
            # Filter theo status nếu có (status được lưu trong data JSON)
            if status:
                # Note: Status filter sẽ được apply sau khi parse data
                pass
            
            products = []
            for cache in queryset:
                try:
                    product_data = cache.data
                    
                    # Filter theo status nếu có
                    if status and product_data.get('status') != status:
                        continue
                    
                    # Normalize data
                    if 'variants' in product_data and product_data['variants']:
                        for variant_data in product_data['variants']:
                            if 'images' in variant_data and variant_data['images'] is None:
                                variant_data['images'] = []
                            if 'variant_prices' in variant_data and variant_data['variant_prices'] is None:
                                variant_data['variant_prices'] = []
                            if 'inventories' in variant_data and variant_data['inventories'] is None:
                                variant_data['inventories'] = []
                    
                    if 'images' in product_data and product_data['images'] is None:
                        product_data['images'] = []
                    
                    # Parse product DTO
                    product_dto = ProductDTO.from_dict(product_data)
                    
                    # Extract GDP metadata
                    metadata, _ = extract_gdp_metadata(product_dto.description)
                    product_dto.gdp_metadata = metadata
                    
                    # Assign metadata to variants
                    if metadata and metadata.variants:
                        variant_meta_map = {vm.id: vm for vm in metadata.variants}
                        for variant in product_dto.variants:
                            variant.gdp_metadata = variant_meta_map.get(variant.id)
                    
                    products.append(product_dto)
                except Exception as parse_error:
                    logger.warning(f"Error parsing product {cache.product_id}: {parse_error}")
                    continue
            
            logger.info(f"Fetched {len(products)} products from cache")
            return products
            
        except Exception as e:
            logger.error(f"Error listing products from cache: {e}", exc_info=True)
            return []
    
    def list_products_raw(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lấy danh sách products dưới dạng raw dict từ database cache.
        Tương tự như list_products_raw từ API.
        
        Args:
            status: Filter theo status (optional)
            
        Returns:
            List of product dicts (raw JSON data)
        """
        try:
            queryset = SapoProductCache.objects.all()
            
            products_data = []
            for cache in queryset:
                product_data = cache.data
                
                # Filter theo status nếu có
                if status and product_data.get('status') != status:
                    continue
                
                products_data.append(product_data)
            
            logger.debug(f"Fetched {len(products_data)} products (raw) from cache")
            return products_data
            
        except Exception as e:
            logger.error(f"Error listing products (raw) from cache: {e}", exc_info=True)
            return []


# ========================= EXPORTS =========================

__all__ = [
    'ProductCacheService',
]

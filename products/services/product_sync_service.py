# products/services/product_sync_service.py
"""
Service để sync products và variants từ Sapo API vào database cache.
Sử dụng pagination với limit=250 để tối ưu performance.
"""

from typing import Dict, Any, Optional
import logging
from django.utils import timezone
from django.db import transaction

from core.sapo_client import get_sapo_client
from products.models import SapoProductCache, SapoVariantCache

logger = logging.getLogger(__name__)


class ProductSyncService:
    """
    Service để sync products và variants từ Sapo API vào database.
    """
    
    def __init__(self):
        self.sapo_client = get_sapo_client()
        self.core_api = self.sapo_client.core
    
    def sync_all_products(self, status: str = "active") -> Dict[str, Any]:
        """
        Sync toàn bộ products từ Sapo API vào database.
        
        Args:
            status: Status filter (default: "active")
            
        Returns:
            Dict chứa thống kê:
            {
                "total_pages": int,
                "total_products": int,
                "total_variants": int,
                "updated_products": int,
                "created_products": int,
                "updated_variants": int,
                "created_variants": int,
                "errors": list
            }
        """
        logger.info(f"[ProductSyncService] Starting sync all products (status={status})...")
        
        stats = {
            "total_pages": 0,
            "total_products": 0,
            "total_variants": 0,
            "updated_products": 0,
            "created_products": 0,
            "updated_variants": 0,
            "created_variants": 0,
            "errors": []
        }
        
        page = 1
        limit = 250  # Max limit theo Sapo API
        max_pages = 1000  # Giới hạn an toàn
        
        while page <= max_pages:
            try:
                # Fetch products với pagination
                logger.debug(f"[ProductSyncService] Fetching page {page}...")
                response = self.core_api.list_products_raw(
                    page=page,
                    limit=limit,
                    status=status
                )
                
                products_data = response.get("products", [])
                
                if not products_data:
                    logger.info(f"[ProductSyncService] Page {page} returned no products, stopping pagination")
                    break
                
                # Process từng product
                for product_data in products_data:
                    try:
                        product_stats = self._sync_product(product_data)
                        stats["total_products"] += 1
                        stats["total_variants"] += product_stats["variants_count"]
                        stats["updated_products"] += product_stats["updated"]
                        stats["created_products"] += product_stats["created"]
                        stats["updated_variants"] += product_stats["variants_updated"]
                        stats["created_variants"] += product_stats["variants_created"]
                    except Exception as e:
                        product_id = product_data.get("id", "unknown")
                        error_msg = f"Error syncing product {product_id}: {str(e)}"
                        logger.error(error_msg, exc_info=True)
                        stats["errors"].append(error_msg)
                
                stats["total_pages"] = page
                
                # Check nếu hết products (ít hơn limit)
                if len(products_data) < limit:
                    break
                
                page += 1
                
            except Exception as e:
                error_msg = f"Error fetching page {page}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                stats["errors"].append(error_msg)
                break
        
        logger.info(
            f"[ProductSyncService] Sync completed: "
            f"{stats['total_products']} products, "
            f"{stats['total_variants']} variants, "
            f"{stats['created_products']} created, "
            f"{stats['updated_products']} updated"
        )
        
        return stats
    
    def _sync_product(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sync một product và các variants của nó vào database.
        
        Args:
            product_data: Dict chứa product data từ Sapo API
            
        Returns:
            Dict chứa thống kê:
            {
                "variants_count": int,
                "updated": int (0 or 1),
                "created": int (0 or 1),
                "variants_updated": int,
                "variants_created": int
            }
        """
        product_id = product_data.get("id")
        if not product_id:
            raise ValueError("Product data missing 'id' field")
        
        stats = {
            "variants_count": 0,
            "updated": 0,
            "created": 0,
            "variants_updated": 0,
            "variants_created": 0
        }
        
        # Normalize data: convert None lists to empty lists
        variants_data = product_data.get("variants", []) or []
        stats["variants_count"] = len(variants_data)
        
        # Normalize variant data
        for variant_data in variants_data:
            if variant_data.get("images") is None:
                variant_data["images"] = []
            if variant_data.get("variant_prices") is None:
                variant_data["variant_prices"] = []
            if variant_data.get("inventories") is None:
                variant_data["inventories"] = []
        
        # Normalize product images
        if product_data.get("images") is None:
            product_data["images"] = []
        
        # Save/update product cache
        with transaction.atomic():
            product_cache, created = SapoProductCache.objects.update_or_create(
                product_id=product_id,
                defaults={
                    "data": product_data
                }
            )
            
            if created:
                stats["created"] = 1
            else:
                stats["updated"] = 1
            
            # Save/update variants
            for variant_data in variants_data:
                variant_id = variant_data.get("id")
                if not variant_id:
                    continue
                
                variant_cache, variant_created = SapoVariantCache.objects.update_or_create(
                    variant_id=variant_id,
                    defaults={
                        "product_id": product_id,
                        "data": variant_data
                    }
                )
                
                if variant_created:
                    stats["variants_created"] += 1
                else:
                    stats["variants_updated"] += 1
        
        return stats
    
    def sync_single_product(self, product_id: int) -> bool:
        """
        Sync một product cụ thể từ Sapo API.
        
        Args:
            product_id: Sapo product ID
            
        Returns:
            True nếu thành công, False nếu thất bại
        """
        try:
            logger.debug(f"[ProductSyncService] Syncing product {product_id}...")
            response = self.core_api.get_product_raw(product_id)
            product_data = response.get("product")
            
            if not product_data:
                logger.warning(f"[ProductSyncService] Product {product_id} not found in Sapo")
                return False
            
            self._sync_product(product_data)
            logger.info(f"[ProductSyncService] Successfully synced product {product_id}")
            return True
            
        except Exception as e:
            logger.error(f"[ProductSyncService] Error syncing product {product_id}: {e}", exc_info=True)
            return False


# ========================= EXPORTS =========================

__all__ = [
    'ProductSyncService',
]

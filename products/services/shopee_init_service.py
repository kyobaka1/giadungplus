# products/services/shopee_init_service.py
"""
Service để init dữ liệu Shopee products từ Sapo Marketplace API.
Lấy thông tin sản phẩm từ các shop trên Sapo MP và lưu vào product metadata.
"""

from typing import Dict, Any, List, Optional
import logging

from core.sapo_client import SapoClient
from core.system_settings import get_connection_ids
from products.services.sapo_product_service import SapoProductService
from products.services.metadata_helper import (
    extract_gdp_metadata,
    inject_gdp_metadata,
    init_empty_metadata,
    update_variant_metadata
)
from products.services.dto import VariantMetadataDTO

logger = logging.getLogger(__name__)


class ShopeeInitService:
    """
    Service để init dữ liệu Shopee products từ Sapo MP.
    """
    
    def __init__(self, sapo_client: SapoClient):
        """
        Initialize service với SapoClient.
        
        Args:
            sapo_client: Instance của SapoClient (initialized with tokens)
        """
        self.sapo_client = sapo_client
        self.product_service = SapoProductService(sapo_client)
        self.mp_repo = sapo_client.marketplace
    
    def init_shopee_products(
        self,
        tenant_id: int,
        connection_ids: Optional[str] = None,
        limit_per_page: int = 250
    ) -> Dict[str, Any]:
        """
        Init dữ liệu Shopee products từ Sapo MP API.
        
        Lấy toàn bộ products từ Sapo MP (tất cả các shop với connection IDs)
        và lưu thông tin vào product metadata:
        - Lưu item_id - shop_id mapping vào product level
        - Lưu connectionIds, variation_id, item_id vào variant metadata
        
        Args:
            tenant_id: Sapo tenant ID (vd: 1262)
            connection_ids: Comma-separated connection IDs. Nếu None, lấy tất cả từ config
            limit_per_page: Số items mỗi page (default: 250)
            
        Returns:
            {
                "success": True/False,
                "total_products": 355,
                "processed": 100,
                "updated": 50,
                "errors": [...]
            }
        """
        if not connection_ids:
            connection_ids = get_connection_ids()
        
        logger.info(f"[ShopeeInitService] Starting init with tenant_id={tenant_id}, connection_ids={connection_ids}")
        
        result = {
            "success": True,
            "total_products": 0,
            "processed": 0,
            "updated": 0,
            "errors": []
        }
        
        # Fetch all products từ Sapo MP (paginate)
        page = 1
        all_products = []
        
        try:
            while True:
                logger.info(f"[ShopeeInitService] Fetching page {page}...")
                response = self.mp_repo.list_products_raw(
                    tenant_id=tenant_id,
                    connection_ids=connection_ids,
                    page=page,
                    limit=limit_per_page,
                    mapping_status=2,  # has_mapping=true
                    sync_status=0
                )
                
                products = response.get("products", [])
                if not products:
                    break
                
                all_products.extend(products)
                
                metadata = response.get("metadata", {})
                total = metadata.get("total", 0)
                current_page = metadata.get("page", page)
                limit = metadata.get("limit", limit_per_page)
                
                # Calculate total_pages if not provided
                if total > 0 and limit > 0:
                    total_pages = (total + limit - 1) // limit  # Ceiling division
                else:
                    total_pages = current_page
                
                logger.info(f"[ShopeeInitService] Page {current_page}/{total_pages}: {len(products)} products (Total: {total})")
                
                # Update result total from metadata (first time or if changed)
                if result["total_products"] == 0 or total > result["total_products"]:
                    result["total_products"] = total
                
                # Check if there are more pages
                # Continue if: we got products AND (current_page < total_pages OR we haven't reached total yet)
                if len(products) < limit:
                    # Last page (got fewer products than limit)
                    break
                
                if current_page >= total_pages:
                    break
                
                # Also check if we've already collected all products
                if total > 0 and len(all_products) >= total:
                    break
                
                page += 1
            
            # Process từng variant (không cần sapo_product_id ở product level)
            logger.info(f"[ShopeeInitService] Processing variants from {len(all_products)} products...")
            
            # Group variants by sapo_product_id để tránh fetch product nhiều lần
            variants_by_product: Dict[int, List[Dict[str, Any]]] = {}
            
            for product_data in all_products:
                variants_data = product_data.get("variants", [])
                for variant_data in variants_data:
                    sapo_variant_id = variant_data.get("sapo_variant_id")
                    sapo_product_id = variant_data.get("sapo_product_id")
                    
                    if not sapo_variant_id or not sapo_product_id:
                        continue
                    
                    if sapo_product_id not in variants_by_product:
                        variants_by_product[sapo_product_id] = []
                    variants_by_product[sapo_product_id].append(variant_data)
            
            # Process từng product group
            for sapo_product_id, variants_list in variants_by_product.items():
                try:
                    result["processed"] += len(variants_list)
                    updated = self._process_variants(sapo_product_id, variants_list)
                    if updated:
                        result["updated"] += 1
                except Exception as e:
                    error_msg = f"Error processing product {sapo_product_id}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    result["errors"].append(error_msg)
                    result["success"] = False
            
            logger.info(f"[ShopeeInitService] Completed: {result['updated']}/{result['processed']} products updated")
            
        except Exception as e:
            error_msg = f"Error in init_shopee_products: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result["errors"].append(error_msg)
            result["success"] = False
        
        return result
    
    def _process_variants(self, sapo_product_id: int, variants_data: List[Dict[str, Any]]) -> bool:
        """
        Process các variants từ Sapo MP và update metadata.
        
        Args:
            sapo_product_id: Sapo product ID (từ variant.sapo_product_id)
            variants_data: List các variant data từ Sapo MP API
            
        Returns:
            True nếu đã update, False nếu không cần update
        """
        # Get product từ Sapo
        product = self.product_service.get_product(sapo_product_id)
        if not product:
            logger.warning(f"Product {sapo_product_id} not found in Sapo, skipping")
            return False
        
        # Get or init metadata
        if not product.gdp_metadata:
            product.gdp_metadata = init_empty_metadata(
                product_id=product.id,
                variant_ids=[v.id for v in product.variants]
            )
        
        updated = False
        
        for variant_data in variants_data:
            sapo_variant_id = variant_data.get("sapo_variant_id")
            if not sapo_variant_id:
                continue
            
            # Find variant in product
            variant = None
            for v in product.variants:
                if v.id == sapo_variant_id:
                    variant = v
                    break
            
            if not variant:
                logger.warning(f"Variant {sapo_variant_id} not found in product {sapo_product_id}")
                continue
            
            # Get or create variant metadata
            from products.services.metadata_helper import get_variant_metadata
            variant_meta = get_variant_metadata(product.gdp_metadata, variant.id)
            if not variant_meta:
                variant_meta = VariantMetadataDTO(id=variant.id)
            
            # Update shopee_connections
            connection_id = variant_data.get("connection_id")
            variation_id = variant_data.get("variation_id")
            item_id = variant_data.get("item_id")
            
            if connection_id and variation_id and item_id:
                # Check if this connection already exists
                connection_exists = False
                for conn in variant_meta.shopee_connections:
                    if (conn.get("connection_id") == connection_id and 
                        conn.get("variation_id") == variation_id):
                        connection_exists = True
                        # Update item_id if changed
                        if conn.get("item_id") != item_id:
                            conn["item_id"] = item_id
                            updated = True
                        break
                
                if not connection_exists:
                    variant_meta.shopee_connections.append({
                        "connection_id": connection_id,
                        "variation_id": variation_id,
                        "item_id": item_id
                    })
                    updated = True
            
            # Update variant metadata in product metadata
            product.gdp_metadata = update_variant_metadata(
                product.gdp_metadata,
                variant.id,
                variant_meta
            )
        
        # Save updated metadata
        # Note: update_product_metadata sẽ tự động preserve description gốc
        # và inject metadata vào description field theo format [GDP_META]...[/GDP_META]
        if updated:
            success = self.product_service.update_product_metadata(
                product_id=product.id,
                metadata=product.gdp_metadata,
                preserve_description=True  # Giữ nguyên description gốc, chỉ thêm/update metadata
            )
            if success:
                logger.info(f"✓ Updated shopee connections metadata for product {product.id} (sapo_product_id={sapo_product_id}, {len(variants_data)} variants)")
                return True
            else:
                logger.error(f"✗ Failed to save metadata for product {product.id} (sapo_product_id={sapo_product_id})")
                return False
        
        return False


# products/services/sapo_product_service.py
"""
Service layer for interacting with Sapo Products API.
Handles fetching, parsing, and updating products with GDP metadata.
"""

from typing import Optional, List, Dict, Any
import logging

from core.sapo_client import SapoClient
from products.services.dto import (
    ProductDTO, 
    ProductVariantDTO, 
    ProductMetadataDTO,
    VariantMetadataDTO
)
from products.services.metadata_helper import (
    extract_gdp_metadata, 
    inject_gdp_metadata, 
    init_empty_metadata,
    update_description_metadata,
    get_variant_metadata,
    update_variant_metadata
)

logger = logging.getLogger(__name__)


class SapoProductService:
    """
    Service để giao tiếp với Sapo Products API.
    
    Chức năng chính:
    - Fetch products từ Sapo và parse GDP metadata
    - Update GDP metadata vào product.description
    - Quản lý variant metadata
    """
    
    def __init__(self, sapo_client: SapoClient):
        """
        Initialize service với SapoClient.
        
        Args:
            sapo_client: Instance của SapoClient (initialized with tokens)
        """
        self.sapo_client = sapo_client
        self.core_api = sapo_client.core
    
    def get_product(self, product_id: int) -> Optional[ProductDTO]:
        """
        Lấy product từ Sapo và parse GDP metadata.
        
        Args:
            product_id: Sapo product ID
            
        Returns:
            ProductDTO với gdp_metadata đã được parse, hoặc None nếu không tìm thấy
            
        Example:
            >>> service = SapoProductService(sapo_client)
            >>> product = service.get_product(42672265)
            >>> product.name
            'Kệ chén/ bát dán tường'
            >>> product.gdp_metadata.web_product_id
            '123'
        """
        try:
            # Fetch product from Sapo
            response = self.core_api.get_product_raw(product_id)
            product_data = response.get('product')
            
            if not product_data:
                logger.warning(f"Product {product_id} not found in Sapo")
                return None
            
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
            
            logger.info(f"Fetched product {product_id}: {product_dto.name} ({len(product_dto.variants)} variants)")
            return product_dto
            
        except Exception as e:
            logger.error(f"Error fetching product {product_id}: {e}", exc_info=True)
            return None
    
    def list_products(self, **filters) -> List[ProductDTO]:
        """
        Lấy danh sách products từ Sapo.
        
        Args:
            **filters: Query parameters (page, limit, status, etc.)
            
        Returns:
            List of ProductDTO
            
        Example:
            >>> products = service.list_products(page=1, limit=50, status='active')
            >>> len(products)
            50
        """
        try:
            response = self.core_api.list_products_raw(**filters)
            products_data = response.get('products', [])
            
            products = []
            for product_data in products_data:
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
                
                try:
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
                    logger.warning(f"Error parsing product {product_data.get('id', 'unknown')}: {parse_error}")
                    # Skip product này và tiếp tục
                    continue
            
            logger.info(f"Fetched {len(products)} products from Sapo")
            return products
            
        except Exception as e:
            logger.error(f"Error listing products: {e}", exc_info=True)
            return []
    
    def update_product_metadata(
        self, 
        product_id: int, 
        metadata: ProductMetadataDTO,
        preserve_description: bool = True
    ) -> bool:
        """
        Update GDP metadata của product.
        
        Args:
            product_id: Sapo product ID
            metadata: ProductMetadataDTO cần lưu
            preserve_description: Nếu True, giữ nguyên description gốc
            
        Returns:
            True nếu thành công, False nếu thất bại
            
        Example:
            >>> metadata = ProductMetadataDTO(
            ...     web_product_id="123",
            ...     variants=[VariantMetadataDTO(id=62457516)]
            ... )
            >>> service.update_product_metadata(42672265, metadata)
            True
        """
        try:
            # Lấy product hiện tại
            product = self.get_product(product_id)
            if not product:
                logger.error(f"Cannot update metadata: Product {product_id} not found")
                return False
            
            # Determine original description
            if preserve_description:
                original_desc = product.original_description
            else:
                original_desc = ""
            
            # Inject metadata into description
            new_description = inject_gdp_metadata(original_desc, metadata)
            
            # Update via Sapo API
            update_data = {"description": new_description}
            response = self.core_api.update_product(product_id, update_data)
            
            if response.get('product'):
                logger.info(f"Updated GDP metadata for product {product_id}")
                return True
            else:
                logger.error(f"Failed to update product {product_id}: No product in response")
                return False
                
        except Exception as e:
            logger.error(f"Error updating product metadata {product_id}: {e}", exc_info=True)
            return False
    
    def update_variant_metadata_only(
        self,
        product_id: int,
        variant_id: int,
        variant_metadata: VariantMetadataDTO
    ) -> bool:
        """
        Update metadata của một variant cụ thể.
        
        Args:
            product_id: Sapo product ID
            variant_id: Variant ID cần update
            variant_metadata: VariantMetadataDTO mới
            
        Returns:
            True nếu thành công
            
        Example:
            >>> variant_meta = VariantMetadataDTO(
            ...     id=62457516,
            ...     import_info=ImportInfoDTO(china_price_cny=50.0)
            ... )
            >>> service.update_variant_metadata_only(42672265, 62457516, variant_meta)
            True
        """
        try:
            # Lấy product hiện tại
            product = self.get_product(product_id)
            if not product:
                logger.error(f"Product {product_id} not found")
                return False
            
            # Get or init product metadata
            if product.gdp_metadata:
                product_metadata = product.gdp_metadata
            else:
                # Init empty metadata
                variant_ids = [v.id for v in product.variants]
                product_metadata = init_empty_metadata(product_id, variant_ids)
            
            # Update specific variant metadata
            product_metadata = update_variant_metadata(
                product_metadata, 
                variant_id, 
                variant_metadata
            )
            
            # Save back to Sapo
            return self.update_product_metadata(product_id, product_metadata)
            
        except Exception as e:
            logger.error(f"Error updating variant metadata {variant_id}: {e}", exc_info=True)
            return False
    
    def init_product_metadata(self, product_id: int) -> bool:
        """
        Khởi tạo metadata rỗng cho product chưa có GDP_META.
        
        Args:
            product_id: Sapo product ID
            
        Returns:
            True nếu thành công
            
        Example:
            >>> service.init_product_metadata(42672265)
            True
        """
        try:
            product = self.get_product(product_id)
            if not product:
                logger.error(f"Product {product_id} not found")
                return False
            
            # If already has metadata, skip
            if product.gdp_metadata:
                logger.info(f"Product {product_id} already has GDP metadata, skipping init")
                return True
            
            # Init empty metadata structure
            variant_ids = [v.id for v in product.variants]
            metadata = init_empty_metadata(product_id, variant_ids)
            
            # Save to Sapo
            success = self.update_product_metadata(product_id, metadata)
            
            if success:
                logger.info(f"Initialized GDP metadata for product {product_id} with {len(variant_ids)} variants")
            
            return success
            
        except Exception as e:
            logger.error(f"Error initializing metadata for product {product_id}: {e}", exc_info=True)
            return False
    
    def get_variant_metadata(
        self,
        product_id: int,
        variant_id: int
    ) -> Optional[VariantMetadataDTO]:
        """
        Lấy metadata của một variant cụ thể.
        
        Args:
            product_id: Sapo product ID
            variant_id: Variant ID
            
        Returns:
            VariantMetadataDTO hoặc None
        """
        try:
            product = self.get_product(product_id)
            if not product or not product.gdp_metadata:
                return None
            
            return get_variant_metadata(product.gdp_metadata, variant_id)
            
        except Exception as e:
            logger.error(f"Error getting variant metadata {variant_id}: {e}", exc_info=True)
            return None


# ========================= EXPORTS =========================

__all__ = [
    'SapoProductService',
]

# products/services/metadata_helper.py
"""
Utilities for parsing and injecting GDP metadata into product.description field.

GDP metadata is stored in Sapo product.description with format:
[GDP_META]{...JSON...}[/GDP_META]

This allows us to store extended custom fields without modifying Sapo's database schema.
"""

import re
import json
from typing import Optional, Tuple
import logging

from products.services.dto import (
    ProductMetadataDTO, 
    VariantMetadataDTO,
    VideoInfoDTO,
    NhanPhuInfoDTO,
    BoxInfoDTO,
    PackedInfoDTO,
)

logger = logging.getLogger(__name__)

# Markers for GDP metadata in description field
GDP_META_START = "[GDP_META]"
GDP_META_END = "[/GDP_META]"


def extract_gdp_metadata(description: Optional[str]) -> Tuple[Optional[ProductMetadataDTO], str]:
    """
    Extract GDP metadata từ product.description.
    
    Args:
        description: Product description string (có thể chứa [GDP_META]...[/GDP_META])
        
    Returns:
        Tuple of (metadata_dto, original_description)
        - metadata_dto: ProductMetadataDTO hoặc None nếu không có metadata
        - original_description: Description gốc (đã remove GDP_META marker)
        
    Example:
        >>> desc = "Sản phẩm tốt\\n[GDP_META]{\"web_product_id\": \"123\"}[/GDP_META]"
        >>> metadata, original = extract_gdp_metadata(desc)
        >>> original
        'Sản phẩm tốt'
        >>> metadata.web_product_id
        '123'
    """
    if not description:
        return None, ""
    
    # Find [GDP_META]...[/GDP_META] pattern
    pattern = re.compile(
        rf'{re.escape(GDP_META_START)}(.*?){re.escape(GDP_META_END)}', 
        re.DOTALL
    )
    match = pattern.search(description)
    
    if not match:
        # No GDP_META found
        return None, description.strip()
    
    # Extract JSON string
    json_str = match.group(1).strip()
    
    # Remove GDP_META from description to get original
    original_desc = pattern.sub('', description).strip()
    
    # Parse JSON to DTO
    try:
        json_data = json.loads(json_str)
        metadata = ProductMetadataDTO.from_dict(json_data)
        logger.debug(f"Extracted GDP metadata: {len(metadata.variants)} variants")
        return metadata, original_desc
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid GDP_META JSON: {e}")
        return None, original_desc
    except Exception as e:
        logger.error(f"Error parsing GDP metadata: {e}")
        return None, original_desc


def inject_gdp_metadata(
    original_description: str, 
    metadata: ProductMetadataDTO
) -> str:
    """
    Inject GDP metadata vào product description.
    
    Args:
        original_description: Mô tả gốc (không có GDP_META marker)
        metadata: ProductMetadataDTO cần inject
        
    Returns:
        Description đầy đủ có chứa [GDP_META]...[/GDP_META]
        
    Example:
        >>> original = "Sản phẩm tốt"
        >>> metadata = ProductMetadataDTO(web_product_id="123", variants=[])
        >>> inject_gdp_metadata(original, metadata)
        'Sản phẩm tốt\\n\\n[GDP_META]{...}[/GDP_META]'
    """
    # Serialize metadata to compact JSON (no indents for space saving)
    json_str = metadata.to_json_str(exclude_none=True, indent=None)
    
    # Append GDP_META to end of description
    if original_description:
        return f"{original_description}\n\n{GDP_META_START}{json_str}{GDP_META_END}"
    else:
        return f"{GDP_META_START}{json_str}{GDP_META_END}"


def update_description_metadata(
    current_description: Optional[str],
    metadata: ProductMetadataDTO
) -> str:
    """
    Update metadata trong description hiện tại, giữ nguyên original description.
    
    Args:
        current_description: Description hiện tại (có thể đã có hoặc chưa có GDP_META)
        metadata: ProductMetadataDTO mới cần update
        
    Returns:
        Description mới với metadata đã được update
    """
    # Extract original description (remove old GDP_META if exists)
    _, original_desc = extract_gdp_metadata(current_description)
    
    # Inject new metadata
    return inject_gdp_metadata(original_desc, metadata)


def init_empty_metadata(product_id: int, variant_ids: list[int]) -> ProductMetadataDTO:
    """
    Khởi tạo metadata rỗng cho product và variants với đầy đủ các trường bắt buộc.
    
    Args:
        product_id: Sapo product ID
        variant_ids: List of variant IDs
        
    Returns:
        ProductMetadataDTO với structure đầy đủ (có thể rỗng/null) cho tất cả variants
        
    Example:
        >>> metadata = init_empty_metadata(42672265, [62457516, 62457517])
        >>> len(metadata.variants)
        2
        >>> metadata.variants[0].id
        62457516
        >>> metadata.variants[0].price_tq is None
        True
    """
    # Tạo variant metadata với đầy đủ các trường bắt buộc (có thể null)
    variant_metadata_list = []
    for vid in variant_ids:
        variant_meta = VariantMetadataDTO(
            id=vid,
            price_tq=None,
            sku_tq=None,
            name_tq=None,
            box_info=BoxInfoDTO(
                full_box=None,
                length_cm=None,
                width_cm=None,
                height_cm=None
            ),
            packed_info=PackedInfoDTO(
                length_cm=None,
                width_cm=None,
                height_cm=None,
                weight_with_box_g=None,
                weight_without_box_g=None,
                converted_weight_g=None
            ),
            sku_model_xnk=None,
            web_variant_id=[]
        )
        variant_metadata_list.append(variant_meta)
    
    return ProductMetadataDTO(
        description=None,  # HTML description
        videos=[],
        video_primary=None,
        nhanphu_info=NhanPhuInfoDTO(
            vi_name=None,
            en_name=None,
            description=None,
            material=None,
            hdsd=None
        ),
        warranty_months=None,
        variants=variant_metadata_list
    )


def get_variant_metadata(
    product_metadata: Optional[ProductMetadataDTO],
    variant_id: int
) -> Optional[VariantMetadataDTO]:
    """
    Lấy metadata của một variant cụ thể từ product metadata.
    
    Args:
        product_metadata: ProductMetadataDTO
        variant_id: Variant ID cần tìm
        
    Returns:
        VariantMetadataDTO hoặc None nếu không tìm thấy
    """
    if not product_metadata or not product_metadata.variants:
        return None
    
    for variant_meta in product_metadata.variants:
        if variant_meta.id == variant_id:
            return variant_meta
    
    return None


def update_variant_metadata(
    product_metadata: ProductMetadataDTO,
    variant_id: int,
    updated_variant_metadata: VariantMetadataDTO
) -> ProductMetadataDTO:
    """
    Update metadata của một variant trong product metadata.
    
    Args:
        product_metadata: ProductMetadataDTO hiện tại
        variant_id: Variant ID cần update
        updated_variant_metadata: VariantMetadataDTO mới
        
    Returns:
        ProductMetadataDTO đã được update
        
    Note:
        Nếu variant chưa có trong metadata, sẽ tự động thêm mới
    """
    # Find and update existing variant metadata
    found = False
    for i, variant_meta in enumerate(product_metadata.variants):
        if variant_meta.id == variant_id:
            product_metadata.variants[i] = updated_variant_metadata
            found = True
            break
    
    # If not found, append new variant metadata
    if not found:
        product_metadata.variants.append(updated_variant_metadata)
    
    return product_metadata


# ========================= EXPORTS =========================

__all__ = [
    'extract_gdp_metadata',
    'inject_gdp_metadata',
    'update_description_metadata',
    'init_empty_metadata',
    'get_variant_metadata',
    'update_variant_metadata',
]

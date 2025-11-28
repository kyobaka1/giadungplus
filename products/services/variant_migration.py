"""
Migration service để chuyển đổi dữ liệu variant từ customer notes (format cũ) 
sang product.description với GDP_META (format mới).

Logic cũ:
- Lưu variant info vào customer note với ID [759999534, 792508285, 792508285]
- Format JSON: {"sku": "...", "vari_id": 123, "price_tq": 8.8, ...}

Logic mới:
- Lưu trong product.description với [GDP_META]...[/GDP_META]
- Format theo VariantMetadataDTO
"""

import json
import logging
from typing import List, Dict, Optional, Any
from collections import defaultdict

from core.sapo_client import get_sapo_client
from products.services.dto import (
    VariantMetadataDTO,
    ProductMetadataDTO,
    BoxInfoDTO,
    PackedInfoDTO,
)
from products.services.metadata_helper import (
    extract_gdp_metadata,
    update_description_metadata,
    get_variant_metadata,
    update_variant_metadata,
)
from products.services.sapo_product_service import SapoProductService

logger = logging.getLogger(__name__)

# Customer IDs chứa variant data cũ
OLD_VARIANT_CUSTOMER_IDS = [759999534, 792508285]


def get_old_variant_data_from_notes(sapo_client) -> Dict[int, Dict[str, Any]]:
    """
    Lấy dữ liệu variant cũ từ customer notes.
    
    Args:
        sapo_client: Sapo client instance
        
    Returns:
        Dict mapping variant_id -> old_data
        {
            variant_id: {
                "sku": "...",
                "price_tq": 8.8,
                "sku_tq": "...",
                "sku_nhapkhau": "...",
                "box_dai": 24.0,
                "box_rong": 23.0,
                "box_cao": 8.0,
                "fullbox": 1,
                "sp_dai": 0.0,
                "sp_rong": 0.0,
                "sp_cao": 0.0,
                "name_vn": "",
                ...
            }
        }
    """
    variant_data_map = {}
    
    try:
        core_repo = sapo_client.core
        
        print(f"[DEBUG] Bắt đầu lấy dữ liệu từ {len(OLD_VARIANT_CUSTOMER_IDS)} customer(s)...")
        
        for idx, customer_id in enumerate(OLD_VARIANT_CUSTOMER_IDS, 1):
            try:
                print(f"[DEBUG] [{idx}/{len(OLD_VARIANT_CUSTOMER_IDS)}] Đang lấy customer {customer_id}...")
                # Lấy customer info
                customer_response = core_repo.get_customer_raw(customer_id)
                customer = customer_response.get("customer", {})
                
                if not customer:
                    print(f"[DEBUG] Customer {customer_id} không có dữ liệu")
                    continue
                
                # Lấy active notes
                notes = customer.get("notes", [])
                active_notes = [n for n in notes if n.get("status") == "active"]
                print(f"[DEBUG] Customer {customer_id}: {len(active_notes)} active notes")
                
                for note_idx, note in enumerate(active_notes, 1):
                    try:
                        content_str = note.get("content", "{}")
                        content = json.loads(content_str)
                        
                        # Kiểm tra có vari_id không
                        vari_id = content.get("vari_id")
                        if not vari_id:
                            continue
                        
                        vari_id = int(float(vari_id))  # Convert to int
                        
                        # Lưu vào map (nếu đã có thì giữ nguyên, không overwrite)
                        if vari_id not in variant_data_map:
                            variant_data_map[vari_id] = content
                            
                    except (json.JSONDecodeError, ValueError, KeyError) as e:
                        if note_idx % 100 == 0:
                            print(f"[DEBUG] Đã xử lý {note_idx}/{len(active_notes)} notes...")
                        logger.debug(f"Skip note {note.get('id')}: {e}")
                        continue
                
                print(f"[DEBUG] Customer {customer_id}: Đã xử lý xong, tìm thấy {len(variant_data_map)} variants")
                        
            except Exception as e:
                print(f"[ERROR] Lỗi khi lấy customer {customer_id}: {e}")
                logger.warning(f"Error getting customer {customer_id}: {e}")
                continue
        
        print(f"[DEBUG] Tổng cộng: {len(variant_data_map)} variants từ customer notes")
        logger.info(f"Loaded {len(variant_data_map)} variants from old customer notes")
        return variant_data_map
        
    except Exception as e:
        logger.error(f"Error loading old variant data: {e}", exc_info=True)
        return {}


def convert_old_to_new_format(old_data: Dict[str, Any], variant_id: int) -> VariantMetadataDTO:
    """
    Convert dữ liệu variant từ format cũ sang VariantMetadataDTO mới.
    
    Args:
        old_data: Dữ liệu cũ từ customer note
        variant_id: Variant ID
        
    Returns:
        VariantMetadataDTO với dữ liệu đã convert
    """
    def to_float_safe(val, default=0.0):
        """Convert value to float safely."""
        try:
            if val is None or val == "":
                return default
            return float(val)
        except (ValueError, TypeError):
            return default
    
    def to_int_safe(val, default=0):
        """Convert value to int safely."""
        try:
            if val is None or val == "":
                return default
            return int(float(val))
        except (ValueError, TypeError):
            return default
    
    # Convert box info
    box_info = None
    if old_data.get("box_dai") or old_data.get("box_rong") or old_data.get("box_cao"):
        box_info = BoxInfoDTO(
            full_box=to_int_safe(old_data.get("fullbox")),
            length_cm=to_float_safe(old_data.get("box_dai")),
            width_cm=to_float_safe(old_data.get("box_rong")),
            height_cm=to_float_safe(old_data.get("box_cao"))
        )
    
    # Convert packed info (sp_dai, sp_rong, sp_cao)
    packed_info = None
    if old_data.get("sp_dai") or old_data.get("sp_rong") or old_data.get("sp_cao"):
        packed_info = PackedInfoDTO(
            length_cm=to_float_safe(old_data.get("sp_dai")),
            width_cm=to_float_safe(old_data.get("sp_rong")),
            height_cm=to_float_safe(old_data.get("sp_cao")),
            weight_with_box_g=None,
            weight_without_box_g=None,
            converted_weight_g=None
        )
    
    # Convert các field khác
    price_tq = to_float_safe(old_data.get("price_tq"))
    if price_tq == 0.0:
        price_tq = None
    
    sku_tq = old_data.get("sku_tq", "").strip()
    if not sku_tq:
        sku_tq = None
    
    name_tq = old_data.get("name_tq", "").strip()
    if not name_tq:
        name_tq = None
    
    sku_model_xnk = old_data.get("sku_nhapkhau", "").strip()
    if not sku_model_xnk:
        sku_model_xnk = None
    
    # Tạo VariantMetadataDTO
    variant_meta = VariantMetadataDTO(
        id=variant_id,
        price_tq=price_tq,
        sku_tq=sku_tq,
        name_tq=name_tq,
        box_info=box_info,
        packed_info=packed_info,
        sku_model_xnk=sku_model_xnk,
        web_variant_id=[],
        # Legacy fields (để tương thích)
        import_info=None,
        packaging_info=None,
        website_info=None
    )
    
    return variant_meta


def migrate_product_variants(
    product_id: int,
    variants_data: Dict[int, Dict[str, Any]],  # {variant_id: old_data}
    product_service: SapoProductService
) -> bool:
    """
    Migrate tất cả variants của một product cùng lúc (update một lần).
    
    Args:
        product_id: Product ID
        variants_data: Dict mapping variant_id -> old_data
        product_service: SapoProductService instance
        
    Returns:
        True nếu thành công, False nếu có lỗi
    """
    try:
        # Lấy product hiện tại
        product = product_service.get_product(product_id)
        if not product:
            logger.warning(f"Product {product_id} not found")
            return False
        
        # Lấy metadata hiện tại của product
        current_metadata = product.gdp_metadata
        
        if not current_metadata:
            # Nếu chưa có metadata, init empty metadata trước
            from products.services.metadata_helper import init_empty_metadata
            variant_ids = [v.id for v in product.variants]
            current_metadata = init_empty_metadata(product_id, variant_ids)
        
        # Convert và update từng variant
        for variant_id, old_data in variants_data.items():
            new_variant_meta = convert_old_to_new_format(old_data, variant_id)
            current_metadata = update_variant_metadata(
                current_metadata,
                variant_id,
                new_variant_meta
            )
        
        # Lưu vào product description (chỉ update một lần)
        success = product_service.update_product_metadata(
            product_id,
            current_metadata,
            preserve_description=True
        )
        
        if success:
            logger.info(f"Migrated {len(variants_data)} variants for product {product_id}")
        else:
            logger.error(f"Failed to save {len(variants_data)} variants for product {product_id}")
        
        return success
        
    except Exception as e:
        logger.error(f"Error migrating product {product_id}: {e}", exc_info=True)
        return False


def migrate_variant_data(
    product_id: int,
    variant_id: int,
    old_data: Dict[str, Any],
    product_service: SapoProductService
) -> bool:
    """
    Migrate dữ liệu variant từ format cũ sang format mới.
    
    Args:
        product_id: Product ID
        variant_id: Variant ID
        old_data: Dữ liệu cũ từ customer note
        product_service: SapoProductService instance
        
    Returns:
        True nếu thành công, False nếu có lỗi
    """
    try:
        # Lấy product hiện tại
        product = product_service.get_product(product_id)
        if not product:
            logger.warning(f"Product {product_id} not found")
            return False
        
        # Convert dữ liệu cũ sang format mới
        new_variant_meta = convert_old_to_new_format(old_data, variant_id)
        
        # Lấy metadata hiện tại của product
        current_metadata = product.gdp_metadata
        
        if not current_metadata:
            # Nếu chưa có metadata, init empty metadata trước
            from products.services.metadata_helper import init_empty_metadata
            variant_ids = [v.id for v in product.variants]
            current_metadata = init_empty_metadata(product_id, variant_ids)
        
        # Update variant metadata
        current_metadata = update_variant_metadata(
            current_metadata,
            variant_id,
            new_variant_meta
        )
        
        # Lưu vào product description
        success = product_service.update_product_metadata(
            product_id,
            current_metadata,
            preserve_description=True
        )
        
        if success:
            logger.info(f"Migrated variant {variant_id} (product {product_id})")
        else:
            logger.error(f"Failed to save variant {variant_id} (product {product_id})")
        
        return success
        
    except Exception as e:
        logger.error(f"Error migrating variant {variant_id} (product {product_id}): {e}", exc_info=True)
        return False


def init_variants_from_old_data(
    test_mode: bool = False,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Init variant metadata từ dữ liệu cũ trong customer notes.
    
    Args:
        test_mode: Nếu True, chỉ log không thực sự update
        limit: Giới hạn số lượng variants để migrate (None = tất cả)
        
    Returns:
        Dict với thống kê:
        {
            "total_old_variants": 100,
            "migrated": 80,
            "skipped": 20,
            "errors": 0,
            "details": [...]
        }
    """
    result = {
        "total_old_variants": 0,
        "migrated": 0,
        "skipped": 0,
        "errors": 0,
        "details": []
    }
    
    try:
        print("[DEBUG] Đang khởi tạo Sapo client...")
        sapo_client = get_sapo_client()
        print("[DEBUG] Sapo client đã sẵn sàng")
        
        product_service = SapoProductService(sapo_client)
        
        # Lấy dữ liệu cũ từ customer notes
        print("[DEBUG] Bắt đầu lấy dữ liệu từ customer notes...")
        logger.info("Loading old variant data from customer notes...")
        old_variant_data = get_old_variant_data_from_notes(sapo_client)
        result["total_old_variants"] = len(old_variant_data)
        print(f"[DEBUG] Đã lấy được {len(old_variant_data)} variants từ customer notes")
        
        if not old_variant_data:
            print("[WARNING] Không có dữ liệu variant nào từ customer notes!")
            logger.warning("No old variant data found")
            return result
        
        # Group by product_id (cần lấy từ variant)
        print(f"[DEBUG] Đang lấy product_id cho {len(old_variant_data)} variants...")
        logger.info("Grouping variants by product...")
        variant_to_product = {}
        
        # Lấy product_id cho mỗi variant
        processed = 0
        for variant_id in old_variant_data.keys():
            processed += 1
            if processed % 50 == 0:
                print(f"[DEBUG] Đã xử lý {processed}/{len(old_variant_data)} variants...")
            try:
                variant_response = sapo_client.core.get_variant_raw(variant_id)
                variant = variant_response.get("variant", {})
                if variant:
                    variant_to_product[variant_id] = variant.get("product_id")
            except Exception as e:
                if processed % 100 == 0:
                    print(f"[DEBUG] Một số variants không tìm thấy product_id (đây là bình thường)")
                logger.debug(f"Could not get product_id for variant {variant_id}: {e}")
                continue
        
        print(f"[DEBUG] Đã lấy product_id cho {len(variant_to_product)}/{len(old_variant_data)} variants")
        
        # Group variants by product_id để update một lần cho mỗi product
        print(f"[DEBUG] Đang group variants theo product...")
        product_variants_map = defaultdict(dict)  # {product_id: {variant_id: old_data}}
        
        for variant_id, old_data in old_variant_data.items():
            product_id = variant_to_product.get(variant_id)
            if product_id:
                product_variants_map[product_id][variant_id] = old_data
            else:
                result["skipped"] += 1
                result["details"].append({
                    "variant_id": variant_id,
                    "status": "skipped",
                    "reason": "Product not found"
                })
        
        print(f"[DEBUG] Có {len(product_variants_map)} products cần migrate")
        
        # Migrate từng product (mỗi product update một lần với tất cả variants)
        print(f"[DEBUG] Bắt đầu migrate {len(product_variants_map)} products...")
        logger.info(f"Starting migration of {len(product_variants_map)} products...")
        
        processed = 0
        for product_id, variants_data in product_variants_map.items():
            if limit and processed >= limit:
                break
            
            processed += 1
            if processed % 10 == 0:
                print(f"[DEBUG] Đã xử lý {processed}/{len(product_variants_map)} products...")
            
            try:
                if test_mode:
                    # Chỉ log, không update
                    print(f"[TEST] Product {product_id}: {len(variants_data)} variants")
                    for variant_id, old_data in variants_data.items():
                        new_meta = convert_old_to_new_format(old_data, variant_id)
                        logger.debug(f"[TEST] Would migrate variant {variant_id}: {new_meta.to_dict()}")
                    result["migrated"] += len(variants_data)
                else:
                    # Thực sự migrate - update một lần cho tất cả variants của product
                    success = migrate_product_variants(
                        product_id, 
                        variants_data, 
                        product_service
                    )
                    
                    if success:
                        result["migrated"] += len(variants_data)
                        for variant_id in variants_data.keys():
                            result["details"].append({
                                "variant_id": variant_id,
                                "product_id": product_id,
                                "status": "success"
                            })
                    else:
                        result["errors"] += len(variants_data)
                        for variant_id in variants_data.keys():
                            result["details"].append({
                                "variant_id": variant_id,
                                "product_id": product_id,
                                "status": "error"
                            })
            except Exception as e:
                logger.error(f"Error migrating product {product_id}: {e}", exc_info=True)
                result["errors"] += len(variants_data)
                for variant_id in variants_data.keys():
                    result["details"].append({
                        "variant_id": variant_id,
                        "product_id": product_id,
                        "status": "error",
                        "reason": str(e)
                    })
        
        logger.info(f"Migration completed: {result['migrated']} migrated, {result['errors']} errors, {result['skipped']} skipped")
        return result
        
    except Exception as e:
        logger.error(f"Error in init_variants_from_old_data: {e}", exc_info=True)
        result["errors"] += 1
        return result


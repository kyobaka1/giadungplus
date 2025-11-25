"""
Service để quản lý và áp dụng promotions/gifts cho orders.

Workflow:
1. Fetch promotions từ Sapo API
2. Cache vào JSON file
3. Load từ cache khi cần
4. Apply gifts cho OrderDTO dựa trên conditions
"""

import json
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from core.sapo_client import SapoClient
from orders.services.promotion_dto import (
    PromotionProgramDTO,
    PromotionConditionItemDTO,
    GiftItemDetailDTO
)
from orders.services.dto import OrderDTO, OrderLineItemDTO, GiftItemDTO

logger = logging.getLogger(__name__)


def debug_print(*args, **kwargs):
    """Print debug messages to console for debugging."""
    print(*args, **kwargs)


class PromotionService:
    """
    Service xử lý promotions và tự động áp dụng gifts cho orders.
    """
    
    # Cache file path
    CACHE_DIR = Path("core") / "data"
    CACHE_FILE = CACHE_DIR / "promotions_cache.json"
    
    def __init__(self, sapo_client: SapoClient):
        """
        Initialize PromotionService.
        
        Args:
            sapo_client: SapoClient instance
        """
        self._sapo = sapo_client
        self._promotions: List[PromotionProgramDTO] = []
        
        # Ensure cache directory exists
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    def fetch_and_cache_promotions(self) -> List[PromotionProgramDTO]:
        """
        Fetch promotions từ Sapo API và lưu vào cache.
        
        Returns:
            List of PromotionProgramDTO
            
        Workflow:
            1. Fetch list of active promotion programs
            2. For each program, fetch its conditions
            3. Parse into DTOs
            4. Save to JSON cache
        """
        logger.info("[PromotionService] Fetching promotions from Sapo API...")
        
        promotions = []
        
        try:
            # Step 1: Fetch promotion programs list
            response = self._sapo.promotion.list_programs(
                statuses="active",
                page=1,
                limit=100
            )
            
            programs = response.get('promotion_list', [])
            logger.info(f"[PromotionService] Found {len(programs)} active promotions")
            
            # Step 2: For each program, fetch conditions
            for program in programs:
                program_id = program['id']
                debug_print(f"PromotionService Fetching conditions for program {program_id}...")
                
                try:
                    conditions_response = self._sapo.promotion.get_conditions(program_id)
                    
                    # Step 3: Collect all variant_ids từ gifts để fetch thông tin
                    variant_ids_to_fetch = set()
                    for ci_data in conditions_response.get('condition_items', []):
                        for item in ci_data.get('items', []):
                            if item.get('type') == 'gift':
                                detail_dict = json.loads(item.get('detail', '{}'))
                                variant_id = detail_dict.get('condition_include')
                                if variant_id:
                                    try:
                                        variant_ids_to_fetch.add(int(variant_id))
                                    except (ValueError, TypeError):
                                        pass
                    
                    # Step 4: Fetch variant info cho tất cả gifts
                    variant_info_cache = {}
                    for variant_id in variant_ids_to_fetch:
                        try:
                            variant_response = self._sapo.core.get_variant_raw(variant_id)
                            variant_info_cache[variant_id] = variant_response
                            debug_print(f"PromotionService ✓ Fetched variant info: {variant_id}")
                        except Exception as e:
                            logger.warning(f"[PromotionService] Failed to fetch variant {variant_id}: {e}")
                            variant_info_cache[variant_id] = None
                    
                    # Step 5: Parse into DTO với variant_info
                    promotion_dto = PromotionProgramDTO.from_dict(
                        program_data=program,
                        conditions_data=conditions_response,
                        variant_info_cache=variant_info_cache
                    )
                    
                    promotions.append(promotion_dto)
                    debug_print(f"PromotionService ✓ Loaded: {promotion_dto.name}")
                    
                except Exception as e:
                    logger.error(f"[PromotionService] Failed to load conditions for {program_id}: {e}")
                    continue
            
            # Step 4: Save to cache
            self._save_to_cache(promotions)
            self._promotions = promotions
            
            logger.info(f"[PromotionService] ✓ Cached {len(promotions)} promotions")
            return promotions
            
        except Exception as e:
            logger.error(f"[PromotionService] Failed to fetch promotions: {e}")
            raise
    
    def load_from_cache(self) -> List[PromotionProgramDTO]:
        """
        Load promotions từ JSON cache.
        
        Returns:
            List of PromotionProgramDTO
        """
        if not self.CACHE_FILE.exists():
            logger.warning("[PromotionService] Cache file not found, fetching from API...")
            return self.fetch_and_cache_promotions()
        
        debug_print(f"PromotionService Loading promotions from cache: {self.CACHE_FILE}")
        
        try:
            with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            promotions = [
                PromotionProgramDTO.from_cache_dict(p)
                for p in cache_data.get('promotions', [])
            ]
            
            self._promotions = promotions
            logger.info(f"[PromotionService] ✓ Loaded {len(promotions)} promotions from cache")
            return promotions
            
        except Exception as e:
            logger.error(f"[PromotionService] Failed to load cache: {e}")
            logger.info("[PromotionService] Falling back to API fetch...")
            return self.fetch_and_cache_promotions()
    
    def _save_to_cache(self, promotions: List[PromotionProgramDTO]) -> None:
        """Save promotions to JSON cache."""
        cache_data = {
            'cached_at': datetime.now().isoformat(),
            'promotions': [p.to_dict() for p in promotions]
        }
        
        with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        
        debug_print(f"PromotionService ✓ Saved cache to {self.CACHE_FILE}")
    
    def apply_gifts_to_order(self, order_dto: OrderDTO) -> OrderDTO:
        """
        Áp dụng gifts cho order dựa trên promotions.
        
        Args:
            order_dto: OrderDTO cần apply gifts
            
        Returns:
            OrderDTO với gifts field được populate
            
        Logic:
            1. Loop qua tất cả active promotions
            2. Check conditions (date, location, source)
            3. Check variant conditions và quantity
            4. Apply gifts (với multiple logic)
        """
        if not self._promotions:
            self.load_from_cache()
        
        debug_print(f"PromotionService Applying gifts to order {order_dto.code}...")

        
        all_gifts: List[GiftItemDTO] = []
        
        # Loop qua tất cả promotions
        for promotion in self._promotions:
            # Check basic conditions
            if not self._check_promotion_applicable(promotion, order_dto):
                continue
            
            debug_print(f"PromotionService Checking promotion: {promotion.name}")
            
            # Check each condition_item
            for condition_item in promotion.condition_items:
                gifts = self._apply_condition_item(
                    condition_item=condition_item,
                    order_dto=order_dto,
                    promotion_name=promotion.name
                )
                
                if gifts:
                    all_gifts.extend(gifts)
                    logger.info(
                        f"[PromotionService] ✓ Applied {len(gifts)} gift(s) from '{promotion.name}'"
                    )
        
        # Update order DTO
        order_dto.gifts = all_gifts
        
        if all_gifts:
            logger.info(
                f"[PromotionService] ✓ Total {len(all_gifts)} gift(s) applied to order"
            )
            # Debug print chi tiết danh sách gifts
            debug_print(f"PromotionService ✓ Applied {len(all_gifts)} gift(s) to order {order_dto.code}:")
            for idx, gift in enumerate(all_gifts, 1):
                gift_info = f"  {idx}. {gift.variant_name} (ID: {gift.variant_id}) x{gift.quantity}"
                if gift.sku:
                    gift_info += f" - SKU: {gift.sku}"
                if gift.unit:
                    gift_info += f" - Unit: {gift.unit}"
                if gift.opt1:
                    gift_info += f" - Opt1: {gift.opt1}"
                gift_info += f" - from '{gift.promotion_name}'"
                debug_print(gift_info)
        else:
            debug_print("PromotionService No gifts applicable for this order")
        
        return order_dto
    
    def _check_promotion_applicable(
        self, 
        promotion: PromotionProgramDTO, 
        order_dto: OrderDTO
    ) -> bool:
        """
        Check xem promotion có applicable cho order không.
        
        Checks:
        - Status = active
        - Date range (start_date, end_date)
        - Location IDs (nếu có)
        - Order source IDs (nếu có)
        """
        # Check status
        if promotion.status != "active":
            return False
        
        # Check date range
        now = datetime.now()
        
        if promotion.start_date:
            try:
                start = datetime.fromisoformat(promotion.start_date.replace('Z', '+00:00'))
                if now < start:
                    debug_print(f"PromotionService Promotion not started yet: {promotion.name}")
                    return False
            except Exception as e:
                logger.warning(f"[PromotionService] Invalid start_date: {e}")
        
        if promotion.end_date:
            try:
                end = datetime.fromisoformat(promotion.end_date.replace('Z', '+00:00'))
                if now > end:
                    debug_print(f"PromotionService Promotion expired: {promotion.name}")
                    return False
            except Exception as e:
                logger.warning(f"[PromotionService] Invalid end_date: {e}")
        
        # Check location_ids (nếu có thì order phải match)
        if promotion.location_ids:
            if order_dto.location_id not in promotion.location_ids:
                debug_print(
                    f"PromotionService Location mismatch for {promotion.name}: "
                    f"order={order_dto.location_id}, required={promotion.location_ids}"
                )
                return False
        
        # Check order_source_ids (nếu có thì order phải match)
        if promotion.order_source_ids:
            if order_dto.source_id not in promotion.order_source_ids:
                debug_print(
                    f"PromotionService Source mismatch for {promotion.name}: "
                    f"order={order_dto.source_id}, required={promotion.order_source_ids}"
                )
                return False
        
        return True
    
    def _apply_condition_item(
        self,
        condition_item: PromotionConditionItemDTO,
        order_dto: OrderDTO,
        promotion_name: str
    ) -> List[GiftItemDTO]:
        """
        Apply một condition_item cho order.
        
        Returns:
            List of GiftItemDTO nếu điều kiện thoả mãn, ngược lại []
        """
        # Check conditions
        for condition in condition_item.conditions:
            # Count matching items trong order
            matched_quantity = self._count_matching_items(condition, order_dto)
            
            # Check goods_range_from
            required_quantity = condition.goods_range_from or 1
            
            if matched_quantity < required_quantity:
                debug_print(
                    f"PromotionService Insufficient quantity: "
                    f"got {matched_quantity}, required {required_quantity}"
                )
                continue
            
            # Điều kiện thoả mãn -> apply gifts
            return self._create_gift_items(
                gifts=condition_item.gifts,
                matched_quantity=matched_quantity,
                required_quantity=required_quantity,
                multiple=condition_item.multiple,
                promotion_name=promotion_name
            )
        
        return []
    
    def _count_matching_items(
        self,
        condition: 'PromotionConditionDTO',
        order_dto: OrderDTO
    ) -> int:
        """
        Đếm số lượng items trong order match với condition.
        
        Args:
            condition: PromotionConditionDTO
            order_dto: OrderDTO
            
        Returns:
            Tổng quantity của các items match variant_ids
        """
        total = 0
        
        for line_item in order_dto.line_items:
            if line_item.variant_id in condition.goods_condition:
                total += line_item.quantity
        
        return total
    
    def _create_gift_items(
        self,
        gifts: List[GiftItemDetailDTO],
        matched_quantity: int,
        required_quantity: int,
        multiple: bool,
        promotion_name: str
    ) -> List[GiftItemDTO]:
        """
        Tạo GiftItemDTO dựa trên logic multiple.
        
        Args:
            gifts: List gift items từ promotion
            matched_quantity: Số lượng sản phẩm match điều kiện
            required_quantity: Số lượng tối thiểu yêu cầu
            multiple: False = áp dụng nhiều lần, True = chỉ 1 lần
            promotion_name: Tên chương trình khuyến mãi
            
        Returns:
            List of GiftItemDTO
        """
        result = []
        
        # Calculate multiplier
        if multiple:
            # Multiple = True -> chỉ tặng 1 lần dù mua bao nhiêu
            multiplier = 1
        else:
            # Multiple = False -> tặng theo bội số
            # Ví dụ: mua 2 tặng 2, mua 4 tặng 4, mua 5 tặng 4 (làm tròn xuống)
            multiplier = matched_quantity // required_quantity
        
        for gift in gifts:
            result.append(GiftItemDTO(
                variant_id=gift.variant_id,
                variant_name=gift.variant_name,
                quantity=gift.quantity * multiplier,
                promotion_name=promotion_name,
                sku=gift.sku,
                unit=gift.unit,
                opt1=gift.opt1
            ))
        
        return result

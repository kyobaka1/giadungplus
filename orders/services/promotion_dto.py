"""
Data Transfer Objects cho Sapo Promotion Programs.

DTOs này map với data structure từ Sapo Promotion API:
- GET /admin/promotion_programs_v2/list.json
- GET /admin/promotion_programs_v2/{id}/conditions.json
"""

from dataclasses import dataclass, field
from typing import List, Optional
import json


@dataclass
class PromotionConditionDTO:
    """Điều kiện áp dụng khuyến mãi cho sản phẩm."""
    
    id: int
    condition_item_id: int
    goods_range_from: Optional[int]  # Mua từ bao nhiêu sản phẩm
    goods_range_to: Optional[int]
    goods_condition: List[int]  # List variant_ids áp dụng khuyến mãi
    goods_condition_labels: List[dict]  # [{"goods_id": int, "goods_label": str}]
    promotion_type: str  # e.g., "gift_by_variant"
    limit: Optional[int]
    
    @classmethod
    def from_dict(cls, data: dict) -> 'PromotionConditionDTO':
        """Parse từ Sapo API response."""
        # Parse goods_condition từ string thành list int
        goods_condition = []
        if data.get('goods_condition'):
            goods_condition = [
                int(vid.strip()) 
                for vid in str(data['goods_condition']).split(',')
                if vid.strip()
            ]
        
        return cls(
            id=data['id'],
            condition_item_id=data['condition_item_id'],
            goods_range_from=data.get('goods_range_from'),
            goods_range_to=data.get('goods_range_to'),
            goods_condition=goods_condition,
            goods_condition_labels=data.get('goods_condition_label', []),
            promotion_type=data.get('promotion_type', ''),
            limit=data.get('limit')
        )


@dataclass
class GiftItemDetailDTO:
    """Chi tiết quà tặng cho một promotion."""
    
    variant_id: int
    quantity: int
    variant_name: str  # Lấy từ goods_condition_label
    sku: Optional[str] = None  # SKU của variant
    unit: Optional[str] = None  # Đơn vị tính
    opt1: Optional[str] = None  # Option 1 (phân loại 1)
    
    @classmethod
    def from_item_detail(cls, item: dict, variant_info: Optional[dict] = None) -> 'GiftItemDetailDTO':
        """
        Parse từ promotion item.
        
        Args:
            item: Promotion item dict từ Sapo API
            variant_info: Optional dict chứa thông tin variant từ Sapo API (sku, unit, opt1)
        
        item = {
            "id": 21537143,
            "type": "gift",
            "detail": '{"discount_type":"gift","condition_include":"123996615","quantity":1,"type":"variant"}',
            "goods_condition_label": [{"goods_id": 123996615, "goods_label": "Keo dán..."}]
        }
        
        variant_info = {
            "variant": {
                "sku": "ABC123",
                "unit": "cái",
                "opt1": "Màu đỏ",
                ...
            }
        }
        """
        # Parse JSON detail string
        detail_dict = json.loads(item.get('detail', '{}'))
        variant_id = int(detail_dict.get('condition_include', 0))
        quantity = int(detail_dict.get('quantity', 1))
        
        # Lấy variant name từ goods_condition_label
        variant_name = "Unknown Product"
        labels = item.get('goods_condition_label', [])
        if labels:
            variant_name = labels[0].get('goods_label', variant_name)
        
        # Lấy thông tin variant từ variant_info nếu có
        sku = None
        unit = None
        opt1 = None
        
        if variant_info:
            variant_data = variant_info.get('variant', {})
            sku = variant_data.get('sku')
            unit = variant_data.get('unit')
            opt1 = variant_data.get('opt1')
        
        return cls(
            variant_id=variant_id,
            quantity=quantity,
            variant_name=variant_name,
            sku=sku,
            unit=unit,
            opt1=opt1
        )


@dataclass
class PromotionConditionItemDTO:
    """
    Condition item - bao gồm conditions và gifts tương ứng.
    
    Mỗi condition_item định nghĩa:
    - Điều kiện: sản phẩm nào, mua bao nhiêu
    - Quà tặng: tặng gì, tặng bao nhiêu
    - Áp dụng: một lần hay nhiều lần
    """
    
    id: int
    conditions: List[PromotionConditionDTO]
    gifts: List[GiftItemDetailDTO]
    multiple: bool  # False = áp dụng nhiều lần, True = chỉ 1 lần
    limit: Optional[int]
    group: Optional[str]
    group_limit: Optional[int]
    
    @classmethod
    def from_dict(cls, data: dict, variant_info_cache: dict = None) -> 'PromotionConditionItemDTO':
        """
        Parse từ Sapo API response.
        
        Args:
            data: Condition item data từ Sapo API
            variant_info_cache: Dict {variant_id: variant_response} chứa thông tin variant đã fetch
        """
        conditions = [
            PromotionConditionDTO.from_dict(c) 
            for c in data.get('conditions', [])
        ]
        
        # Parse gifts với variant_info
        gifts = []
        for item in data.get('items', []):
            if item.get('type') == 'gift':
                # Lấy variant_id từ item detail
                detail_dict = json.loads(item.get('detail', '{}'))
                variant_id = detail_dict.get('condition_include')
                
                # Lấy variant_info từ cache nếu có
                variant_info = None
                if variant_info_cache and variant_id:
                    try:
                        variant_id_int = int(variant_id)
                        variant_info = variant_info_cache.get(variant_id_int)
                    except (ValueError, TypeError):
                        pass
                
                gift = GiftItemDetailDTO.from_item_detail(item, variant_info=variant_info)
                gifts.append(gift)
        
        return cls(
            id=data['id'],
            conditions=conditions,
            gifts=gifts,
            multiple=data.get('multiple', False),
            limit=data.get('limit'),
            group=data.get('group'),
            group_limit=data.get('group_limit')
        )


@dataclass
class PromotionProgramDTO:
    """
    Chương trình khuyến mãi từ Sapo.
    
    Bao gồm thông tin chương trình và các condition_items
    định nghĩa điều kiện áp dụng và quà tặng.
    """
    
    id: int
    tenant_id: int
    name: str
    code: str
    type: str  # e.g., "gift_by_variant"
    status: str  # "active", "inactive", etc.
    start_date: Optional[str]  # ISO format string
    end_date: Optional[str]  # ISO format string
    description: str
    location_ids: List[int]  # Nếu có thì chỉ áp dụng cho location này
    order_source_ids: List[int]  # Nếu có thì chỉ áp dụng cho source này
    condition_items: List[PromotionConditionItemDTO] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, program_data: dict, conditions_data: dict = None, variant_info_cache: dict = None) -> 'PromotionProgramDTO':
        """
        Parse từ Sapo API response.
        
        Args:
            program_data: Response từ /promotion_programs_v2/list.json
            conditions_data: Response từ /promotion_programs_v2/{id}/conditions.json
            variant_info_cache: Dict {variant_id: variant_response} chứa thông tin variant đã fetch
        """
        condition_items = []
        if conditions_data:
            condition_items = [
                PromotionConditionItemDTO.from_dict(item, variant_info_cache=variant_info_cache or {})
                for item in conditions_data.get('condition_items', [])
            ]
        
        return cls(
            id=program_data['id'],
            tenant_id=program_data['tenant_id'],
            name=program_data['name'],
            code=program_data['code'],
            type=program_data['type'],
            status=program_data['status'],
            start_date=program_data.get('start_date'),
            end_date=program_data.get('end_date'),
            description=program_data.get('description', ''),
            location_ids=program_data.get('location_ids', []),
            order_source_ids=program_data.get('order_source_ids', []),
            condition_items=condition_items
        )
    
    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'code': self.code,
            'type': self.type,
            'status': self.status,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'description': self.description,
            'location_ids': self.location_ids,
            'order_source_ids': self.order_source_ids,
            'condition_items': [
                {
                    'id': ci.id,
                    'multiple': ci.multiple,
                    'limit': ci.limit,
                    'group': ci.group,
                    'group_limit': ci.group_limit,
                    'conditions': [
                        {
                            'id': c.id,
                            'condition_item_id': c.condition_item_id,
                            'goods_range_from': c.goods_range_from,
                            'goods_range_to': c.goods_range_to,
                            'goods_condition': c.goods_condition,
                            'goods_condition_labels': c.goods_condition_labels,
                            'promotion_type': c.promotion_type,
                            'limit': c.limit
                        }
                        for c in ci.conditions
                    ],
                    'gifts': [
                        {
                            'variant_id': g.variant_id,
                            'quantity': g.quantity,
                            'variant_name': g.variant_name,
                            'sku': g.sku,
                            'unit': g.unit,
                            'opt1': g.opt1
                        }
                        for g in ci.gifts
                    ]
                }
                for ci in self.condition_items
            ]
        }
    
    @classmethod
    def from_cache_dict(cls, data: dict) -> 'PromotionProgramDTO':
        """Load từ cached JSON dict."""
        condition_items = []
        for ci_data in data.get('condition_items', []):
            conditions = [
                PromotionConditionDTO(
                    id=c['id'],
                    condition_item_id=c['condition_item_id'],
                    goods_range_from=c.get('goods_range_from'),
                    goods_range_to=c.get('goods_range_to'),
                    goods_condition=c.get('goods_condition', []),
                    goods_condition_labels=c.get('goods_condition_labels', []),
                    promotion_type=c.get('promotion_type', ''),
                    limit=c.get('limit')
                )
                for c in ci_data.get('conditions', [])
            ]
            
            gifts = [
                GiftItemDetailDTO(
                    variant_id=g['variant_id'],
                    quantity=g['quantity'],
                    variant_name=g['variant_name'],
                    sku=g.get('sku'),
                    unit=g.get('unit'),
                    opt1=g.get('opt1')
                )
                for g in ci_data.get('gifts', [])
            ]
            
            condition_items.append(PromotionConditionItemDTO(
                id=ci_data['id'],
                conditions=conditions,
                gifts=gifts,
                multiple=ci_data.get('multiple', False),
                limit=ci_data.get('limit'),
                group=ci_data.get('group'),
                group_limit=ci_data.get('group_limit')
            ))
        
        return cls(
            id=data['id'],
            tenant_id=data['tenant_id'],
            name=data['name'],
            code=data['code'],
            type=data['type'],
            status=data['status'],
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            description=data.get('description', ''),
            location_ids=data.get('location_ids', []),
            order_source_ids=data.get('order_source_ids', []),
            condition_items=condition_items
        )

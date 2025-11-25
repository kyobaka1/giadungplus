# settings/services/gift_service.py
"""
Service layer for Gift Rule business logic
"""
from typing import List, Dict, Optional
from django.db import transaction
from django.utils import timezone
from ..models import GiftRule, GiftRuleGift


class GiftRuleService:
    """
    Service để quản lý Gift Rules
    """

    @staticmethod
    def get_all_rules(active_only: bool = False, shop_code: Optional[str] = None) -> List[GiftRule]:
        """
        Lấy tất cả gift rules, có thể filter theo active status và shop
        
        Args:
            active_only: Chỉ lấy rules đang active
            shop_code: Filter theo shop code
        
        Returns:
            QuerySet của GiftRule
        """
        queryset = GiftRule.objects.prefetch_related('gifts').all()
        
        if active_only:
            queryset = queryset.filter(is_active=True)
        
        if shop_code:
            # Lấy rules không có shop_code (áp dụng cho tất cả) hoặc match shop_code
            queryset = queryset.filter(
                models.Q(shop_code__isnull=True) | models.Q(shop_code=shop_code)
            )
        
        return queryset

    @staticmethod
    def get_active_rules(shop_code: Optional[str] = None) -> List[GiftRule]:
        """
        Lấy các rules đang active và trong thời gian hiệu lực
        
        Args:
            shop_code: Filter theo shop code
        
        Returns:
            List các GiftRule đang active
        """
        from django.db.models import Q
        
        now = timezone.now()
        queryset = GiftRule.objects.prefetch_related('gifts').filter(
            is_active=True
        ).filter(
            Q(start_at__isnull=True) | Q(start_at__lte=now)
        ).filter(
            Q(end_at__isnull=True) | Q(end_at__gte=now)
        )
        
        if shop_code:
            queryset = queryset.filter(
                Q(shop_code__isnull=True) | Q(shop_code=shop_code)
            )
        
        return list(queryset)

    @staticmethod
    def get_rule_by_id(rule_id: int) -> Optional[GiftRule]:
        """
        Lấy gift rule theo ID
        
        Args:
            rule_id: ID của rule
        
        Returns:
            GiftRule hoặc None
        """
        try:
            return GiftRule.objects.prefetch_related('gifts').get(id=rule_id)
        except GiftRule.DoesNotExist:
            return None

    @staticmethod
    def validate_rule_data(data: Dict) -> Dict[str, str]:
        """
        Validate dữ liệu rule
        
        Args:
            data: Dict chứa thông tin rule
        
        Returns:
            Dict chứa errors (nếu có), empty dict nếu valid
        """
        errors = {}
        
        scope = data.get('scope')
        if not scope:
            errors['scope'] = 'Scope là bắt buộc'
            return errors
        
        # Validate scope-specific fields
        if scope == 'line':
            variant_ids = data.get('required_variant_ids', [])
            if not variant_ids or len(variant_ids) == 0:
                errors['required_variant_ids'] = 'Phải có ít nhất 1 Variant ID khi scope=line'
            if not data.get('required_min_qty'):
                errors['required_min_qty'] = 'Số lượng tối thiểu là bắt buộc khi scope=line'
        
        elif scope == 'order':
            if not data.get('min_order_total'):
                errors['min_order_total'] = 'Giá trị đơn tối thiểu là bắt buộc khi scope=order'
        
        # Validate gifts
        gifts = data.get('gifts', [])
        if not gifts:
            errors['gifts'] = 'Phải có ít nhất 1 quà tặng'
        else:
            for idx, gift in enumerate(gifts):
                if not gift.get('gift_variant_id'):
                    errors[f'gift_{idx}_variant'] = 'Variant ID quà tặng là bắt buộc'
                if not gift.get('gift_qty') or int(gift.get('gift_qty', 0)) <= 0:
                    errors[f'gift_{idx}_qty'] = 'Số lượng quà tặng phải > 0'
        
        return errors

    @staticmethod
    @transaction.atomic
    def create_rule(data: Dict) -> GiftRule:
        """
        Tạo gift rule mới
        
        Args:
            data: Dict chứa thông tin rule và gifts
        
        Returns:
            GiftRule đã tạo
        """
        # Extract gifts data
        gifts_data = data.pop('gifts', [])
        
        # Create rule
        rule = GiftRule.objects.create(**data)
        
        # Create gifts
        for gift_data in gifts_data:
            GiftRuleGift.objects.create(
                rule=rule,
                gift_variant_id=gift_data['gift_variant_id'],
                gift_qty=gift_data['gift_qty'],
                match_quantity=gift_data.get('match_quantity', False)
            )
        
        return rule

    @staticmethod
    @transaction.atomic
    def update_rule(rule_id: int, data: Dict) -> Optional[GiftRule]:
        """
        Cập nhật gift rule
        
        Args:
            rule_id: ID của rule cần update
            data: Dict chứa thông tin mới
        
        Returns:
            GiftRule đã update hoặc None nếu không tìm thấy
        """
        try:
            rule = GiftRule.objects.get(id=rule_id)
        except GiftRule.DoesNotExist:
            return None
        
        # Extract gifts data
        gifts_data = data.pop('gifts', None)
        
        # Update rule fields
        for field, value in data.items():
            setattr(rule, field, value)
        rule.save()
        
        # Update gifts if provided
        if gifts_data is not None:
            # Delete existing gifts
            rule.gifts.all().delete()
            
            # Create new gifts
            for gift_data in gifts_data:
                GiftRuleGift.objects.create(
                    rule=rule,
                    gift_variant_id=gift_data['gift_variant_id'],
                    gift_qty=gift_data['gift_qty'],
                    match_quantity=gift_data.get('match_quantity', False)
                )
        
        return rule

    @staticmethod
    def delete_rule(rule_id: int) -> bool:
        """
        Xóa gift rule (cascade delete gifts)
        
        Args:
            rule_id: ID của rule cần xóa
        
        Returns:
            True nếu xóa thành công, False nếu không tìm thấy
        """
        try:
            rule = GiftRule.objects.get(id=rule_id)
            rule.delete()
            return True
        except GiftRule.DoesNotExist:
            return False

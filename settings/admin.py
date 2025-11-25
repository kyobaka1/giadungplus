from django.contrib import admin
from .models import GiftRule, GiftRuleGift


class GiftRuleGiftInline(admin.TabularInline):
    model = GiftRuleGift
    extra = 1


@admin.register(GiftRule)
class GiftRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'scope', 'shop_code', 'priority', 'is_active', 'start_at', 'end_at']
    list_filter = ['scope', 'is_active', 'shop_code']
    search_fields = ['name', 'shop_code']
    inlines = [GiftRuleGiftInline]
    
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('name', 'scope', 'shop_code', 'priority', 'is_active', 'stop_further')
        }),
        ('Điều kiện đơn hàng (Order-level)', {
            'fields': ('min_order_total', 'max_order_total'),
            'classes': ('collapse',),
        }),
        ('Điều kiện sản phẩm (Line-level)', {
            'fields': ('required_variant_id', 'required_min_qty', 'required_max_qty'),
            'classes': ('collapse',),
        }),
        ('Thời gian hiệu lực', {
            'fields': ('start_at', 'end_at'),
        }),
    )


@admin.register(GiftRuleGift)
class GiftRuleGiftAdmin(admin.ModelAdmin):
    list_display = ['rule', 'gift_variant_id', 'gift_qty']
    list_filter = ['rule']

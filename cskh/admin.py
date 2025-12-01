from django.contrib import admin
from .models import Feedback, FeedbackLog, Ticket, TicketCost, TicketEvent, TicketView


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    """Admin interface cho Feedback model"""
    list_display = [
        'feedback_id', 'buyer_user_name', 'rating', 'product_name', 
        'channel_order_number', 'sapo_order_id', 'sapo_variant_id',
        'status_reply', 'create_time', 'created_at'
    ]
    list_filter = [
        'rating', 'status_reply', 'connection_id',
        'created_at', 'updated_at'
    ]
    search_fields = [
        'feedback_id', 'buyer_user_name', 'product_name', 
        'channel_order_number', 'comment', 'reply'
    ]
    readonly_fields = [
        'feedback_id', 'tenant_id', 'connection_id', 'cmt_id', 'item_id',
        'create_time', 'created_at', 'updated_at',
        'sapo_customer_id', 'sapo_order_id', 'sapo_product_id', 'sapo_variant_id',
        'is_replied', 'is_good_review', 'is_bad_review', 'shop_name'
    ]
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('feedback_id', 'tenant_id', 'connection_id', 'cmt_id', 'item_id')
        }),
        ('Sản phẩm', {
            'fields': ('product_name', 'product_image', 'sapo_product_id', 'sapo_variant_id')
        }),
        ('Đơn hàng', {
            'fields': ('channel_order_number', 'sapo_order_id')
        }),
        ('Khách hàng', {
            'fields': ('buyer_user_name', 'sapo_customer_id')
        }),
        ('Đánh giá', {
            'fields': ('rating', 'comment', 'images', 'create_time')
        }),
        ('Phản hồi', {
            'fields': ('status_reply', 'reply', 'reply_time', 'user_reply', 'reply_type')
        }),
        ('Liên kết', {
            'fields': ('ticket',)
        }),
        ('AI Processing', {
            'fields': ('ai_processed_name', 'ai_processed_gender', 'ai_suggested_reply', 'ai_processed_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    date_hierarchy = 'created_at'
    ordering = ['-create_time']


@admin.register(FeedbackLog)
class FeedbackLogAdmin(admin.ModelAdmin):
    """Admin interface cho FeedbackLog model"""
    list_display = [
        'id', 'feedback', 'action_type', 'user_name', 
        'rating_before', 'rating_after', 'created_at'
    ]
    list_filter = ['action_type', 'created_at']
    search_fields = ['feedback__feedback_id', 'user_name', 'note']
    readonly_fields = ['feedback', 'action_type', 'action_data', 'user', 'user_name', 
                      'rating_before', 'rating_after', 'created_at', 'note']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']

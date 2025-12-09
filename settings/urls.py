from django.urls import path
from .views import settings_views, gift_views, variant_tags_views

urlpatterns = [
    path('', settings_views.settings_dashboard, name='settings_dashboard'),
    path('sapo/', settings_views.sapo_config_view, name='sapo_config'),
    path('shopee/', settings_views.shopee_dashboard_view, name='shopee_settings'),
    path('shopee/<str:shop_name>/', settings_views.shopee_cookie_view, name='shopee_cookie_edit'),

    # Push Notification
    path('push-notification/', settings_views.push_notification_view, name='push_notification'),

    # Init data routes
    path('init-data/', settings_views.init_data_view, name='init_data'),
    path('init-data/init-shopee-products/', settings_views.init_shopee_products_api, name='init_shopee_products_api'),

    # Gift/Promotion routes (read-only from Sapo)
    path('gifts/', gift_views.gift_list, name='gift_list'),
    path('gifts/sync/', gift_views.gift_sync, name='gift_sync'),
    path('gifts/<int:promotion_id>/', gift_views.gift_detail, name='gift_detail'),

    # Variant Tags routes
    path('variant-tags/', variant_tags_views.variant_tags_list, name='variant_tags_list'),
    path('variant-tags/create/', variant_tags_views.variant_tag_create, name='variant_tag_create'),
    path('variant-tags/<int:tag_id>/edit/', variant_tags_views.variant_tag_edit, name='variant_tag_edit'),
    path('variant-tags/<int:tag_id>/delete/', variant_tags_views.variant_tag_delete, name='variant_tag_delete'),
    path('variant-tags/api/list/', variant_tags_views.variant_tags_api_list, name='variant_tags_api_list'),

    # Test route
    path('test/', settings_views.test_view, name='settings_test'),
]

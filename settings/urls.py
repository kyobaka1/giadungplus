from django.urls import path
from .views import settings_views, gift_views

urlpatterns = [
    path('', settings_views.settings_dashboard, name='settings_dashboard'),
    path('sapo/', settings_views.sapo_config_view, name='sapo_config'),
    path('shopee/', settings_views.shopee_dashboard_view, name='shopee_settings'),
    path('shopee/<str:shop_name>/', settings_views.shopee_cookie_view, name='shopee_cookie_edit'),
    
    # Gift/Promotion routes (read-only from Sapo)
    path('gifts/', gift_views.gift_list, name='gift_list'),
    path('gifts/sync/', gift_views.gift_sync, name='gift_sync'),
    path('gifts/<int:promotion_id>/', gift_views.gift_detail, name='gift_detail'),
    
    # Test route
    path('test/', settings_views.test_view, name='settings_test'),
]

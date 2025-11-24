from django.urls import path
from .views import settings_views

urlpatterns = [
    path('', settings_views.settings_dashboard, name='settings_dashboard'),
    path('sapo/', settings_views.sapo_config_view, name='sapo_config'),
    path('shopee/', settings_views.shopee_dashboard_view, name='shopee_settings'),
    path('shopee/<str:shop_name>/', settings_views.shopee_cookie_view, name='shopee_cookie_edit'),
]

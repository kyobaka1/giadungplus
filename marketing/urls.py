from django.urls import path
from marketing import views

app_name = "marketing"

urlpatterns = [
    # Dashboard
    path("", views.dashboard, name="dashboard"),
    
    # Shopee Shop Manager
    path("shopee/overview/", views.shopee_overview, name="shopee_overview"),
    path("shopee/product/", views.shopee_product, name="shopee_product"),
    path("shopee/roas-manager/", views.shopee_roas_manager, name="shopee_roas_manager"),
    path("shopee/flash-sale/", views.shopee_flash_sale, name="shopee_flash_sale"),
    
    # Tiktok Booking
    path("tiktok/overview/", views.tiktok_overview, name="tiktok_overview"),
    path("tiktok/koc-kol-list/", views.tiktok_koc_kol_list, name="tiktok_koc_kol_list"),
    path("tiktok/booking-contact/", views.tiktok_booking_contact, name="tiktok_booking_contact"),
    path("tiktok/booking-manager/", views.tiktok_booking_manager, name="tiktok_booking_manager"),
    path("tiktok/tracking-video-booking/", views.tiktok_tracking_video_booking, name="tiktok_tracking_video_booking"),
    
    # Tools
    path("tools/copy-images/", views.tools_copy_images, name="tools_copy_images"),
    path("tools/copy-images/api/", views.tools_copy_images_api, name="tools_copy_images_api"),
    path("tools/copy-images/download/", views.tools_copy_images_download, name="tools_copy_images_download"),
    path("tools/get-videos/", views.tools_get_videos, name="tools_get_videos"),
    path("tools/get-videos/api/", views.tools_get_videos_api, name="tools_get_videos_api"),
]

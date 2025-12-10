from django.urls import path
from marketing import views
from marketing import views_booking
from marketing import views_campaigns

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
    
    # Booking Center - KOC/KOL Database
    path("booking/creators/", views_booking.booking_creator_list, name="booking_creator_list"),
    path("booking/creators/create/", views_booking.booking_creator_create, name="booking_creator_create"),
    path("booking/creators/<int:creator_id>/", views_booking.booking_creator_detail, name="booking_creator_detail"),
    path("booking/creators/<int:creator_id>/edit/", views_booking.booking_creator_edit, name="booking_creator_edit"),
    path("booking/creators/<int:creator_id>/delete/", views_booking.booking_creator_delete, name="booking_creator_delete"),
    
    # Channels
    path("booking/creators/<int:creator_id>/channels/create/", views_booking.booking_channel_create, name="booking_channel_create"),
    path("booking/creators/<int:creator_id>/channels/<int:channel_id>/delete/", views_booking.booking_channel_delete, name="booking_channel_delete"),
    
    # Contacts
    path("booking/creators/<int:creator_id>/contacts/create/", views_booking.booking_contact_create, name="booking_contact_create"),
    path("booking/creators/<int:creator_id>/contacts/<int:contact_id>/set-primary/", views_booking.booking_contact_set_primary, name="booking_contact_set_primary"),
    path("booking/creators/<int:creator_id>/contacts/<int:contact_id>/delete/", views_booking.booking_contact_delete, name="booking_contact_delete"),
    
    # Tags
    path("booking/tags/", views_booking.booking_tag_list, name="booking_tag_list"),
    path("booking/tags/create/", views_booking.booking_tag_create, name="booking_tag_create"),
    path("booking/tags/<int:tag_id>/delete/", views_booking.booking_tag_delete, name="booking_tag_delete"),
    path("booking/creators/<int:creator_id>/tags/assign/", views_booking.booking_tag_assign, name="booking_tag_assign"),
    
    # Notes
    path("booking/creators/<int:creator_id>/notes/create/", views_booking.booking_note_create, name="booking_note_create"),
    path("booking/creators/<int:creator_id>/notes/<int:note_id>/delete/", views_booking.booking_note_delete, name="booking_note_delete"),
    
    # Rate Cards
    path("booking/creators/<int:creator_id>/ratecards/create/", views_booking.booking_ratecard_create, name="booking_ratecard_create"),
    path("booking/creators/<int:creator_id>/ratecards/<int:ratecard_id>/delete/", views_booking.booking_ratecard_delete, name="booking_ratecard_delete"),
    
    # Import/Export
    path("booking/import-export/", views_booking.booking_import_export, name="booking_import_export"),
    path("booking/import/process/", views_booking.booking_import_process, name="booking_import_process"),
    path("booking/export/", views_booking.booking_export, name="booking_export"),
    path("booking/export/template/", views_booking.booking_export_template, name="booking_export_template"),
    
    # Campaigns
    path("tiktok_booking/campaigns/", views_campaigns.campaign_list, name="campaign_list"),
    path("tiktok_booking/campaigns/new/", views_campaigns.campaign_create, name="campaign_create"),
    path("tiktok_booking/campaigns/<int:campaign_id>/", views_campaigns.campaign_detail, name="campaign_detail"),
    path("tiktok_booking/campaigns/<int:campaign_id>/edit/", views_campaigns.campaign_edit, name="campaign_edit"),
    path("tiktok_booking/campaigns/<int:campaign_id>/delete/", views_campaigns.campaign_delete, name="campaign_delete"),
    path("tiktok_booking/campaigns/<int:campaign_id>/duplicate/", views_campaigns.campaign_duplicate, name="campaign_duplicate"),
    path("tiktok_booking/campaigns/<int:campaign_id>/change-status/", views_campaigns.campaign_change_status, name="campaign_change_status"),
    path("tiktok_booking/campaigns/<int:campaign_id>/export/", views_campaigns.campaign_export, name="campaign_export"),
    path("tiktok_booking/campaigns/export/", views_campaigns.campaign_export, name="campaign_export"),
    
    # Campaign Products
    path("tiktok_booking/campaigns/<int:campaign_id>/products/add/", views_campaigns.campaign_product_add, name="campaign_product_add"),
    path("tiktok_booking/campaigns/<int:campaign_id>/products/bulk-add/", views_campaigns.campaign_product_bulk_add, name="campaign_product_bulk_add"),
    path("tiktok_booking/campaigns/<int:campaign_id>/products/<int:product_id>/remove/", views_campaigns.campaign_product_remove, name="campaign_product_remove"),
    
    # Campaign Creators
    path("tiktok_booking/campaigns/<int:campaign_id>/creators/add/", views_campaigns.campaign_creator_add, name="campaign_creator_add"),
    path("tiktok_booking/campaigns/<int:campaign_id>/creators/bulk-add/", views_campaigns.campaign_creator_bulk_add, name="campaign_creator_bulk_add"),
    path("tiktok_booking/campaigns/<int:campaign_id>/creators/<int:creator_id>/remove/", views_campaigns.campaign_creator_remove, name="campaign_creator_remove"),
    
    # Tools
    path("tools/copy-images/", views.tools_copy_images, name="tools_copy_images"),
    path("tools/copy-images/api/", views.tools_copy_images_api, name="tools_copy_images_api"),
    path("tools/copy-images/download/", views.tools_copy_images_download, name="tools_copy_images_download"),
    path("tools/get-videos/", views.tools_get_videos, name="tools_get_videos"),
    path("tools/get-videos/api/", views.tools_get_videos_api, name="tools_get_videos_api"),
    path("tools/get-videos/delete/<int:track_id>/", views.tools_get_videos_delete, name="tools_get_videos_delete"),
    path("tools/get-videos/clear-all/", views.tools_get_videos_clear_all, name="tools_get_videos_clear_all"),
]

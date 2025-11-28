from django.urls import path
from products import views

app_name = "products"

urlpatterns = [
    # Danh sách sản phẩm
    path("", views.product_list, name="product_list"),
    
    # Chi tiết sản phẩm
    path("<int:product_id>/", views.product_detail, name="product_detail"),
    
    # Danh sách phân loại
    path("variants/", views.variant_list, name="variant_list"),
    
    # Chi tiết phân loại
    path("variants/<int:variant_id>/", views.variant_detail, name="variant_detail"),
    
    # Init metadata cho tất cả sản phẩm
    path("init-all-metadata/", views.init_all_products_metadata, name="init_all_metadata"),
    
    # Cài đặt nhãn hiệu
    path("brand-settings/", views.brand_settings, name="brand_settings"),
    path("brand-settings/toggle/", views.toggle_brand, name="toggle_brand"),
    
    # Init variant từ dữ liệu cũ
    path("init-variants-from-old-notes/", views.init_variants_from_old_notes, name="init_variants_from_old_notes"),
    
    # Export/Import Excel
    path("variants/export-excel/", views.export_variants_excel, name="export_variants_excel"),
    path("variants/import-excel/", views.import_variants_excel, name="import_variants_excel"),
    
    # Update variant metadata
    path("variants/<int:variant_id>/update-metadata/", views.update_variant_metadata, name="update_variant_metadata"),
    
    # XNK Model Management
    path("xnk-models/", views.xnk_model_list, name="xnk_model_list"),
    path("xnk-models/search/", views.api_xnk_search, name="api_xnk_search"),
    path("xnk-models/create/", views.api_xnk_create, name="api_xnk_create"),
    path("xnk-models/edit/", views.api_xnk_edit, name="api_xnk_edit"),
    path("xnk-models/delete/", views.api_xnk_delete, name="api_xnk_delete"),
]


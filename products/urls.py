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
]


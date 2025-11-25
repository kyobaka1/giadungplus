# kho/urls.py
from django.urls import path
from . import views

app_name = 'cskh'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Ticket URLs
    path('tickets/', views.ticket_overview, name='ticket_overview'),
    path('tickets/list/', views.ticket_list, name='ticket_list'),
    path('tickets/<int:ticket_id>/', views.ticket_detail, name='ticket_detail'),
    path('tickets/create/', views.ticket_create, name='ticket_create'),
    
    # Warranty URLs
    path('warranty/', views.warranty_overview, name='warranty_overview'),
    path('warranty/list/', views.warranty_list, name='warranty_list'),
    path('warranty/<int:warranty_id>/', views.warranty_detail, name='warranty_detail'),
    
    # Review URLs
    path('reviews/', views.review_overview, name='review_overview'),
    path('reviews/list/', views.review_list, name='review_list'),
    
    # Orders & Products
    path('orders/', views.orders_view, name='orders_view'),
    path('products/', views.products_view, name='products_view'),
]

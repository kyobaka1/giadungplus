# cskh/urls.py
from django.urls import path
from . import views
from . import views_api

app_name = 'cskh'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Ticket URLs
    path('tickets/', views.ticket_overview, name='ticket_overview'),
    path('tickets/list/', views.ticket_list, name='ticket_list'),
    path('tickets/costs/', views.ticket_cost_overview, name='ticket_cost_overview'),
    path('tickets/compensation/', views.ticket_compensation_overview, name='ticket_compensation_overview'),
    path('tickets/<int:ticket_id>/', views.ticket_detail, name='ticket_detail'),
    path('tickets/create/', views.ticket_create, name='ticket_create'),
    path('tickets/config/', views.ticket_config, name='ticket_config'),
    
    # Ticket API URLs
    path('api/tickets/<int:ticket_id>/add-cost/', views_api.api_add_cost, name='api_add_cost'),
    path('api/tickets/<int:ticket_id>/update-process-order/', views_api.api_update_process_order, name='api_update_process_order'),
    path('api/tickets/<int:ticket_id>/update-responsible/', views_api.api_update_responsible, name='api_update_responsible'),
    path('api/tickets/<int:ticket_id>/costs/<int:cost_id>/upload-files/', views_api.api_upload_cost_files, name='api_upload_cost_files'),
    path('api/tickets/<int:ticket_id>/update-reason/', views_api.api_update_reason, name='api_update_reason'),
    path('api/tickets/<int:ticket_id>/update-status/', views_api.api_update_status, name='api_update_status'),
    path('api/tickets/<int:ticket_id>/update-note/', views_api.api_update_note, name='api_update_note'),
    path('api/tickets/<int:ticket_id>/save/', views_api.api_save_ticket, name='api_save_ticket'),
    path('api/tickets/<int:ticket_id>/upload-files/', views_api.api_upload_ticket_files, name='api_upload_ticket_files'),
    path('api/tickets/<int:ticket_id>/add-event/', views_api.api_add_event, name='api_add_event'),
    path('api/tickets/<int:ticket_id>/update-sugget-process/', views_api.api_update_sugget_process, name='api_update_sugget_process'),
    path('api/reason-types/', views_api.api_get_reason_types, name='api_get_reason_types'),
    path('api/search-order/', views_api.api_search_order, name='api_search_order'),
    
    # Warranty URLs
    path('warranty/', views.warranty_overview, name='warranty_overview'),
    path('warranty/list/', views.warranty_list, name='warranty_list'),
    path('warranty/<int:warranty_id>/', views.warranty_detail, name='warranty_detail'),
    
    # Feedback Center URLs
    path('feedback/', views.feedback_overview, name='feedback_overview'),
    path('feedback/list/', views.feedback_list, name='feedback_list'),
    
    # Feedback API URLs
    path('api/feedback/sync/', views_api.api_sync_feedbacks, name='api_sync_feedbacks'),
    path('api/feedback/<int:feedback_id>/reply/', views_api.api_reply_feedback, name='api_reply_feedback'),
    path('api/feedback/<int:feedback_id>/create-ticket/', views_api.api_create_ticket_from_feedback, name='api_create_ticket_from_feedback'),
    path('api/feedback/<int:feedback_id>/ai-suggest/', views_api.api_ai_suggest_reply, name='api_ai_suggest_reply'),
    
    # Orders & Products
    path('orders/', views.orders_view, name='orders_view'),
    path('products/', views.products_view, name='products_view'),
]

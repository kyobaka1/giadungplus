from django.urls import path
from products import views
from products import views_payment_spo

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
    
    # Supplier Management
    path("suppliers/", views.supplier_list, name="supplier_list"),
    path("suppliers/<int:supplier_id>/upload-logo/", views.upload_supplier_logo, name="upload_supplier_logo"),
    path("suppliers/<int:supplier_id>/add-website/", views.add_supplier_website, name="add_supplier_website"),
    path("suppliers/<int:supplier_id>/create-purchase-order/", views.create_purchase_order_from_supplier, name="create_purchase_order_from_supplier"),
    path("suppliers/create-purchase-order/submit/", views.submit_purchase_order_draft, name="submit_purchase_order_draft"),
    path("purchase-orders/<int:po_id>/view-draft/", views.view_purchase_order_draft, name="view_purchase_order_draft"),
    
    # Sales Forecast
    path("sales-forecast/", views.sales_forecast_list, name="sales_forecast_list"),
    path("sales-forecast/refresh/", views.refresh_sales_forecast, name="refresh_sales_forecast"),
    
    # Container Template
    path("container-templates/", views.container_template_list, name="container_template_list"),
    path("container-templates/<int:template_id>/", views.container_template_detail, name="container_template_detail"),
    path("container-templates/create/", views.create_container_template, name="create_container_template"),
    path("container-templates/<int:template_id>/update/", views.update_container_template, name="update_container_template"),
    path("container-templates/add-supplier/", views.add_supplier_to_container, name="add_supplier_to_container"),
    path("container-templates/remove-supplier/", views.remove_supplier_from_container, name="remove_supplier_from_container"),
    path("container-templates/get-suppliers/", views.get_suppliers_for_select, name="get_suppliers_for_select"),
    path("container-templates/<int:template_id>/set-default-supplier/", views.set_default_supplier, name="set_default_supplier"),
    path("container-templates/<int:template_id>/resync-stats/", views.resync_container_template_stats, name="resync_container_template_stats"),
    path("container-templates/<int:template_id>/delete/", views.delete_container_template, name="delete_container_template"),
    
    # Sum Purchase Order (SPO)
    path("sum-purchase-orders/", views.sum_purchase_order_list, name="sum_purchase_order_list"),
    path("sum-purchase-orders/<int:spo_id>/", views.sum_purchase_order_detail, name="sum_purchase_order_detail"),
    path("sum-purchase-orders/<int:spo_id>/export-packing-list/", views.export_spo_packing_list, name="export_spo_packing_list"),
    path("sum-purchase-orders/<int:spo_id>/remove-po/<int:po_id>/", views.remove_po_from_spo, name="remove_po_from_spo"),
    path("sum-purchase-orders/create/", views.create_sum_purchase_order, name="create_sum_purchase_order"),
    path("sum-purchase-orders/add-po/", views.add_po_to_spo, name="add_po_to_spo"),
    path("sum-purchase-orders/sync-po/", views.sync_po_from_sapo, name="sync_po_from_sapo"),
    path("sum-purchase-orders/<int:spo_id>/get-valid-pos/", views.get_valid_pos_for_spo, name="get_valid_pos_for_spo"),
    path("sum-purchase-orders/<int:spo_id>/update-ship-info/", views.update_ship_info, name="update_ship_info"),
    path("sum-purchase-orders/update-status/", views.update_spo_status, name="update_spo_status"),
    path("sum-purchase-orders/update-planned-date/", views.update_timeline_planned_date, name="update_timeline_planned_date"),
    path("sum-purchase-orders/allocate-costs/", views.allocate_costs, name="allocate_costs"),
    path("sum-purchase-orders/<int:spo_id>/delete/", views.delete_sum_purchase_order, name="delete_sum_purchase_order"),
    
    # SPO Costs
    path("sum-purchase-orders/costs/add/", views.add_spo_cost, name="add_spo_cost"),
    path("sum-purchase-orders/costs/<int:cost_id>/edit/", views.edit_spo_cost, name="edit_spo_cost"),
    path("sum-purchase-orders/costs/<int:cost_id>/delete/", views.delete_spo_cost, name="delete_spo_cost"),
    
    # SPO Documents
    path("sum-purchase-orders/documents/upload/", views.upload_spo_document, name="upload_spo_document"),
    path("sum-purchase-orders/documents/<int:document_id>/delete/", views.delete_spo_document, name="delete_spo_document"),
    
    # Purchase Order Management
    path("purchase-orders/<int:po_id>/update-delivery-status/", views.update_po_delivery_status, name="update_po_delivery_status"),
    path("purchase-orders/<int:po_id>/costs/", views.add_po_cost, name="add_po_cost"),
    path("purchase-orders/<int:po_id>/costs/<int:cost_id>/", views.delete_po_cost, name="delete_po_cost"),
    path("purchase-orders/<int:po_id>/payments/", views.add_po_payment, name="add_po_payment"),
    path("purchase-orders/<int:po_id>/payments/<int:payment_id>/", views.delete_po_payment, name="delete_po_payment"),
    path("purchase-orders/<int:po_id>/export-excel/", views.export_po_excel, name="export_po_excel"),
    path("purchase-orders/<int:po_id>/export-labels/", views.export_po_labels, name="export_po_labels"),
    
    # Payment SPO (Thanh toán XNK)
    path("payment-spo/", views_payment_spo.payment_spo_list, name="payment_spo_list"),
    path("payment-spo/periods/", views_payment_spo.payment_periods, name="payment_periods"),
    path("payment-spo/transactions/add/", views_payment_spo.add_balance_transaction, name="add_balance_transaction"),
    path("payment-spo/transactions/<int:txn_id>/edit/", views_payment_spo.edit_balance_transaction, name="edit_balance_transaction"),
    path("payment-spo/transactions/<int:txn_id>/delete/", views_payment_spo.delete_balance_transaction, name="delete_balance_transaction"),
    path("payment-spo/periods/create/", views_payment_spo.create_payment_period, name="create_payment_period"),
    path("payment-spo/periods/<int:period_id>/delete/", views_payment_spo.delete_payment_period, name="delete_payment_period"),
    path("payment-spo/transactions/<int:txn_id>/add-to-period/", views_payment_spo.add_transaction_to_period, name="add_transaction_to_period"),
]


from django.urls import path
from kho.views import overview, orders, management, tickets, printing, packing_api, excel

app_name = "kho"

urlpatterns = [
    # ----- OVERVIEW -----
    path("", overview.dashboard, name="overview"),  # /kho/

    # ----- ĐƠN HÀNG -----
    path("orders/shopee_orders/", orders.shopee_orders, name="shopee_orders"),
    path("orders/sapo_orders/", orders.sapo_orders, name="sapo_orders"),
    path("orders/express/", orders.express_orders, name="orders_express"),
    path("orders/pickup/", orders.pickup_orders, name="orders_pickup"),
    path("orders/packing_orders/", orders.packing_orders, name="packing_orders"),
    path("orders/connect_shipping/", orders.connect_shipping, name="connect_shipping"),
    path("orders/sos_shopee/", orders.sos_shopee, name="sos_shopee"),
    path("orders/packing_cancel/", orders.packing_cancel, name="packing_cancel"),
    path("orders/packing_cancel/mark_received/", orders.mark_received_cancel, name="mark_received_cancel"),
    path("orders/return_orders/", orders.return_orders, name="return_orders"),
    path("orders/print_now/", orders.print_now, name="print_now"),
    path("orders/print_now/pdf/", orders.print_now_pdf, name="print_now_pdf"),
    path("orders/packing/", orders.packing_board, name="orders_packing"),  # Legacy - có thể xóa sau
    
    # Packing Orders API
    path("orders/packing/get_order/", packing_api.get_order, name="packing_get_order"),
    path("orders/packing/complete/", packing_api.complete, name="packing_complete"),

    # ----- QUẢN TRỊ -----
    path("management/stats/", management.stats, name="management_stats"),
    path("management/packing_settings/", management.get_packing_settings, name="packing_settings_get"),
    path("management/packing_settings/toggle/", management.toggle_packing_setting, name="packing_settings_toggle"),

    # ----- TICKET -----
    path("tickets/", tickets.ticket_list, name="ticket_list"),
    path("tickets/<int:ticket_id>/", tickets.ticket_detail, name="ticket_detail"),
    path("tickets/<int:ticket_id>/confirm-error/", tickets.ticket_confirm_error, name="ticket_confirm_error"),

    # ----- IN ẤN -----
    path("print/sorry_letter/", printing.sorry_letter, name="sorry_letter"),
    path("print/sorry_letter/print/", printing.sorry_letter_print, name="sorry_letter_print"),
    path("print/barcode/", printing.product_barcode, name="product_barcode"),
    
    # ----- SẢN PHẨM -----
    path("products/", printing.product, name="product"),
    path("products/export-excel/", excel.export_products_excel, name="products_export_excel"),
    path("products/import-excel/", excel.import_products_excel, name="products_import_excel"),
    path("products/print-label/", printing.print_product_label, name="products_print_label"),
    path("products/print-barcode/", printing.print_product_barcode, name="products_print_barcode"),
    path("products/inventory-history/", printing.get_variant_inventory_history, name="products_inventory_history"),
]

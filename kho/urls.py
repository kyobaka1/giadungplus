from django.urls import path
from kho.views import overview, orders, management, tickets, printing

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
    path("orders/return_orders/", orders.return_orders, name="return_orders"),
    path("orders/print_now/", orders.print_now, name="print_now"),
    path("orders/packing/", orders.packing_board, name="orders_packing"),  # Legacy - có thể xóa sau

    # ----- QUẢN TRỊ -----
    path("management/stats/", management.stats, name="management_stats"),

    # ----- TICKET -----
    path("tickets/", tickets.ticket_list, name="ticket_list"),
    path("tickets/<int:ticket_id>/", tickets.ticket_detail, name="ticket_detail"),
    path("tickets/<int:ticket_id>/confirm-error/", tickets.ticket_confirm_error, name="ticket_confirm_error"),

    # ----- IN ẤN -----
    path("print/sorry_letter/", printing.sorry_letter, name="sorry_letter"),
    path("print/barcode/", printing.product_barcode, name="product_barcode"),
]

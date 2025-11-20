from django.urls import path
from kho.views import overview, orders, management, tickets, printing

app_name = "kho"

urlpatterns = [
    # ----- OVERVIEW -----
    path("", overview.dashboard, name="overview"),  # /kho/

    # ----- ĐƠN HÀNG -----
    path("orders/shopee_orders/", orders.shopee_orders, name="shopee_orders"),
    path("orders/express/", orders.express_orders, name="orders_express"),
    path("orders/pickup/", orders.pickup_orders, name="orders_pickup"),
    path("orders/print_now/", orders.print_now, name="print_now"),
    path("orders/packing/", orders.packing_board, name="orders_packing"),

    # ----- QUẢN TRỊ -----
    path("management/sos-shopee/", management.sos_shopee, name="management_sos_shopee"),
    path("management/packed-canceled/", management.packed_canceled, name="management_packed_canceled"),
    path("management/stats/", management.stats, name="management_stats"),

    # ----- TICKET -----
    path("tickets/", tickets.ticket_list, name="ticket_list"),
    path("tickets/<int:ticket_id>/", tickets.ticket_detail, name="ticket_detail"),
    path("tickets/<int:ticket_id>/confirm-error/", tickets.ticket_confirm_error, name="ticket_confirm_error"),

    # ----- IN ẤN -----
    path("printing/return-letter/", printing.return_letter, name="printing_return_letter"),
    path("printing/product-barcode/", printing.product_barcode, name="printing_product_barcode"),

]

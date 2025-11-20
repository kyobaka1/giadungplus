from django.shortcuts import render

def sos_shopee(request):
    """
    SOS Shopee:
    - Đơn có vấn đề: sai địa chỉ, bị khiếu nại, cần kho xử lý gấp
    - Có thể lấy từ Sapo + log CSKH
    """
    context = {
        "title": "SOS Shopee",
        "orders": [],
    }
    return render(request, "kho/management/sos_shopee.html", context)


def packed_canceled(request):
    """
    Đơn đã gói nhưng bị huỷ:
    - Để kho xử lý: trả hàng về vị trí, check lại tồn, phiếu phạt...
    """
    context = {
        "title": "Đã gói nhưng bị huỷ",
        "orders": [],
    }
    return render(request, "kho/management/packed_canceled.html", context)


def stats(request):
    """
    Thống kê kho:
    - Số đơn/ngày
    - Số đơn/nhân viên
    - Tỷ lệ lỗi kho...
    """
    context = {
        "title": "Thống kê kho",
        "stats": {},
    }
    return render(request, "kho/management/stats.html", context)

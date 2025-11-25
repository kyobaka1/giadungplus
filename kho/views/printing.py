# kho/views/printing.py
from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required


@login_required
def sorry_letter(request):
    """
    Thư cảm ơn/xin lỗi:
    - Tạo file PDF thư cảm ơn, thư xin lỗi, thư ngỏ
    - Gửi kèm đơn / in bỏ vào hộp
    """
    if request.method == "POST":
        order_code = request.POST.get("order_code")
        letter_type = request.POST.get("letter_type", "sorry")  # sorry, thank_you, etc.
        customer_name = request.POST.get("customer_name", "")
        
        # TODO: generate PDF using reportlab/fpdf, trả về file download
        # from reportlab.pdfgen import canvas
        # ...
        
        return HttpResponse(f"Generate {letter_type} letter for {order_code}")

    context = {
        "title": "Thư Cảm Ơn/Xin Lỗi - GIA DỤNG PLUS",
        "current_kho": request.session.get("current_kho", "geleximco"),
        "letter_types": [
            ("sorry", "Thư xin lỗi"),
            ("thank_you", "Thư cảm ơn"),
            ("compensation", "Thư gửi bù"),
        ],
    }
    return render(request, "kho/printing/sorry_letter.html", context)


@login_required
def product_barcode(request):
    """
    In barcode sản phẩm:
    - Lựa chọn SKU / scan SKU
    - In mã vạch theo template
    """
    if request.method == "POST":
        sku = request.POST.get("sku")
        quantity = int(request.POST.get("quantity", 1))
        
        # TODO: generate PDF/barcode image using python-barcode
        # import barcode
        # from barcode.writer import ImageWriter
        # ...
        
        return HttpResponse(f"Generate {quantity} barcodes for {sku}")

    context = {
        "title": "In Barcode Sản Phẩm - GIA DỤNG PLUS",
        "current_kho": request.session.get("current_kho", "geleximco"),
    }
    return render(request, "kho/printing/product_barcode.html", context)

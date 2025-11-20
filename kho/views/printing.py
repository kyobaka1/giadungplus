from django.shortcuts import render
from django.http import HttpResponse

# sau này sẽ gọi core.services.pdf_service, barcode_service...

def return_letter(request):
    """
    Thư đổi trả:
    - Tạo file PDF thư đổi trả (gửi kèm đơn / in bỏ vào hộp)
    """
    if request.method == "POST":
        order_code = request.POST.get("order_code")
        # TODO: generate PDF, trả về file download
        return HttpResponse(f"Generate return letter for {order_code}")

    return render(request, "kho/printing/return_letter.html")


def product_barcode(request):
    """
    In barcode sản phẩm:
    - Lựa chọn SKU / scan SKU
    - In mã vạch theo template
    """
    if request.method == "POST":
        sku = request.POST.get("sku")
        # TODO: generate PDF/barcode image
        return HttpResponse(f"Generate barcode for {sku}")

    return render(request, "kho/printing/product_barcode.html")

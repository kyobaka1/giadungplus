from django.shortcuts import render
from django.http import JsonResponse

def ticket_list(request):
    """
    Danh sách ticket:
    - Ticket từ CSKH gửi sang kho (thiếu hàng, sai hàng, vỡ...)
    """
    context = {
        "title": "Danh sách ticket kho",
        "tickets": [],
    }
    return render(request, "kho/tickets/ticket_list.html", context)


def ticket_detail(request, ticket_id: int):
    """
    Chi tiết 1 ticket:
    - Thông tin đơn hàng
    - Hình ảnh lỗi
    - Ý kiến kho / CSKH
    """
    context = {
        "title": f"Ticket #{ticket_id}",
        "ticket_id": ticket_id,
    }
    return render(request, "kho/tickets/ticket_detail.html", context)


def ticket_confirm_error(request, ticket_id: int):
    """
    Xác nhận lỗi:
    - Kho chọn: Lỗi kho / Lỗi vận chuyển / Lỗi nhà cung cấp / Lỗi khách...
    - Trả về JSON cho frontend (AJAX)
    """
    if request.method == "POST":
        # TODO: lưu xác nhận lỗi vào DB (hoặc Sapo note)
        error_type = request.POST.get("error_type")
        note = request.POST.get("note", "")
        # gọi service ticket_service.confirm_error(...)
        return JsonResponse({"status": "ok"})

    # Nếu GET: có thể trả form đơn giản
    context = {
        "ticket_id": ticket_id,
    }
    return render(request, "kho/tickets/ticket_confirm.html", context)

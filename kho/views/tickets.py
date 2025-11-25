# kho/views/tickets.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from kho.models import Ticket, TicketComment


@login_required
def ticket_list(request):
    """
    Danh sách ticket:
    - Ticket từ CSKH gửi sang kho (thiếu hàng, sai hàng, vỡ...)
    """
    # TODO: Lấy tickets từ database, filter theo status
    tickets = Ticket.objects.all().order_by('-created_at')[:50]
    
    context = {
        "title": "Danh Sách Ticket Kho - GIA DỤNG PLUS",
        "tickets": tickets,
        "current_kho": request.session.get("current_kho", "geleximco"),
    }
    return render(request, "kho/tickets/ticket_list.html", context)


@login_required
def ticket_detail(request, ticket_id: int):
    """
    Chi tiết 1 ticket:
    - Thông tin đơn hàng
    - Hình ảnh lỗi
    - Ý kiến kho / CSKH
    """
    # TODO: Lấy ticket từ database
    ticket = get_object_or_404(Ticket, id=ticket_id)
    comments = ticket.comments.all().order_by('created_at')
    
    context = {
        "title": f"Ticket #{ticket_id} - {ticket.order_code}",
        "ticket": ticket,
        "comments": comments,
        "current_kho": request.session.get("current_kho", "geleximco"),
    }
    return render(request, "kho/tickets/ticket_detail.html", context)


@login_required
def ticket_confirm_error(request, ticket_id: int):
    """
    Xác nhận lỗi:
    - Kho chọn: Lỗi kho / Lỗi vận chuyển / Lỗi nhà cung cấp / Lỗi khách...
    - Trả về JSON cho frontend (AJAX)
    """
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    if request.method == "POST":
        # TODO: lưu xác nhận lỗi vào DB
        error_type = request.POST.get("error_type")
        note = request.POST.get("note", "")
        
        # Update ticket
        ticket.error_type = error_type
        ticket.warehouse_note = note
        ticket.confirmed_by = request.user
        ticket.status = 'processing'
        ticket.save()
        
        # Add comment
        if note:
            TicketComment.objects.create(
                ticket=ticket,
                user=request.user,
                content=f"Xác nhận lỗi: {error_type}\n{note}"
            )
        
        return JsonResponse({
            "status": "ok",
            "message": "Đã xác nhận lỗi thành công"
        })

    # Nếu GET: trả form xác nhận
    context = {
        "title": f"Xác Nhận Lỗi - Ticket #{ticket_id}",
        "ticket": ticket,
        "error_types": Ticket.ERROR_TYPE_CHOICES,
    }
    return render(request, "kho/tickets/ticket_confirm.html", context)

# kho/views/tickets.py
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, Http404
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q, Count, Sum, Avg, F, ExpressionWrapper, DurationField
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.urls import reverse

from kho.utils import group_required
# Import models từ cskh để dùng chung logic
from cskh.models import (
    Ticket,
    TicketCost,
    TicketEvent,
    TicketView,
)
from cskh.services.ticket_service import TicketService
from cskh.settings import (
    get_reason_sources, get_reason_types_by_source, get_cost_types,
    REASON_SOURCES
)
from cskh.utils import log_ticket_action, get_ticket_logs
from settings.services.cskh_ticket_config_service import CSKHTicketConfigService

logger = logging.getLogger(__name__)

# Map kho code -> Sapo location_id (giống orders.py)
LOCATION_BY_KHO = {
    "geleximco": 241737,  # HN
    "toky": 548744,       # HCM
}


@group_required("WarehouseManager")
def ticket_list(request):
    """Danh sách tickets - Logic từ cskh"""
    
    tickets = Ticket.objects.all()
    
    # Lọc theo kho đang chọn (location_id của đơn hàng / đơn xử lý gắn với ticket)
    current_kho = request.session.get("current_kho", "geleximco")
    allowed_location_id = LOCATION_BY_KHO.get(current_kho)
    
    # Bộ lọc lồng nhau (AND): loại ticket, bộ phận xử lý, trạng thái
    # Mặc định lọc theo bộ phận xử lý: KHO
    ticket_type_filter = request.GET.get('ticket_type', '')
    depart_filter = request.GET.get('depart', 'warehouse')  # Mặc định KHO
    status_filter = request.GET.get('status', '')

    if ticket_type_filter:
        # Return Center: lọc theo OR các điều kiện liên quan đổi trả
        if ticket_type_filter == 'return_exchange':
            tickets = tickets.filter(
                Q(ticket_type='return_exchange') |
                Q(process_order_id__isnull=False) |
                Q(sugget_process__sugget_main__in=['Gửi bù hàng', 'Đổi hàng'])
            )
        else:
            tickets = tickets.filter(ticket_type=ticket_type_filter)

    if depart_filter:
        tickets = tickets.filter(depart=depart_filter)

    if status_filter:
        tickets = tickets.filter(ticket_status=status_filter)
    
    # Chỉ hiển thị ticket thuộc kho đang filter
    if allowed_location_id:
        tickets = tickets.filter(location_id=allowed_location_id)
    
    tickets = tickets.select_related('created_by', 'assigned_to').annotate(
        total_cost=Sum('costs__amount')
    ).order_by('-created_at')[:100]
    
    # Tính số event mới chưa xem cho mỗi ticket
    ticket_ids = [t.id for t in tickets]
    ticket_views = TicketView.objects.filter(
        ticket_id__in=ticket_ids,
        user=request.user
    ).select_related('ticket')
    
    # Tạo dict {ticket_id: last_viewed_at}
    views_dict = {tv.ticket_id: tv.last_viewed_at for tv in ticket_views}
    
    # Đếm số event mới cho mỗi ticket và gắn vào ticket object
    for ticket in tickets:
        last_viewed = views_dict.get(ticket.id)
        if last_viewed:
            # Đếm event được tạo sau lần xem cuối
            count = TicketEvent.objects.filter(
                ticket=ticket,
                created_at__gt=last_viewed
            ).count()
        else:
            # Nếu chưa xem lần nào, đếm tất cả event
            count = ticket.events.count()
        ticket.new_events_count = count
    
    context = {
        'tickets': tickets,
        'total_count': len(list(tickets)),
        'ticket_type_filter': ticket_type_filter,
        'depart_filter': depart_filter,
        'status_filter': status_filter,
        'status_choices': Ticket.STATUS_CHOICES,
        'ticket_type_choices': Ticket.TICKET_TYPE_CHOICES,
        'depart_choices': Ticket.DEPART_CHOICES,
    }
    return render(request, 'kho/tickets/list.html', context)


@group_required("WarehouseManager")
def ticket_create(request):
    """Tạo ticket mới - Logic từ cskh"""
    import os
    from pathlib import Path
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile
    
    ticket_service = TicketService()
    
    if request.method == 'POST':
        # Lấy order_id từ hidden field (đã tìm trước đó)
        order_id = request.POST.get('order_id')
        order_code = request.POST.get('order_code', '')
        reference_number = request.POST.get('reference_number', '')
        
        if not order_id:
            messages.error(request, 'Vui lòng tìm đơn hàng trước khi tạo ticket')
            return redirect('kho:ticket_create')
        
        # Lấy order để lấy thông tin đầy đủ
        try:
            order = ticket_service.order_service.get_order_dto(int(order_id))
            order_info = ticket_service.extract_order_info(order)
        except Exception as e:
            messages.error(request, f'Không thể lấy thông tin đơn hàng: {str(e)}')
            return redirect('kho:ticket_create')
        
        # Kiểm tra xem đã có ticket nào với cùng order_code hoặc reference_number chưa
        final_order_code = order_code or order_info.get('order_code', '')
        final_reference_number = reference_number or order_info.get('reference_number', '')
        
        existing_ticket = None
        if final_order_code:
            existing_ticket = Ticket.objects.filter(order_code=final_order_code).first()
        if not existing_ticket and final_reference_number:
            existing_ticket = Ticket.objects.filter(reference_number=final_reference_number).first()
        
        if existing_ticket:
            ticket_url = reverse('kho:ticket_detail', args=[existing_ticket.id])
            error_msg = mark_safe(
                f'Đơn hàng này đã có ticket: <strong>{existing_ticket.ticket_number}</strong>. '
                f'Vui lòng xem ticket <a href="{ticket_url}" class="underline font-semibold text-blue-600 hover:text-blue-800">#{existing_ticket.ticket_number}</a>'
            )
            messages.error(request, error_msg)
            return redirect('kho:ticket_create')
        
        # Xử lý upload files
        uploaded_files = []
        if 'images' in request.FILES:
            # Tạo thư mục assets/cskh nếu chưa có
            upload_dir = Path('assets/cskh')
            upload_dir.mkdir(parents=True, exist_ok=True)
            
            for file in request.FILES.getlist('images'):
                # Tạo tên file unique
                from datetime import datetime
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                file_ext = os.path.splitext(file.name)[1]
                file_name = f"{timestamp}{file_ext}"
                file_path = upload_dir / file_name
                
                # Lưu file
                with open(file_path, 'wb') as f:
                    for chunk in file.chunks():
                        f.write(chunk)
                
                # Lưu path relative để dễ truy cập
                uploaded_files.append(f"cskh/{file_name}")
        
        note_text = request.POST.get('note', '').strip()
        
        # Xử lý ngày tạo ticket (nếu có)
        created_at = None
        created_at_str = request.POST.get('created_at', '').strip()
        if created_at_str:
            try:
                # Parse datetime-local format (YYYY-MM-DDTHH:mm)
                from datetime import datetime
                # Parse naive datetime từ form
                naive_dt = datetime.strptime(created_at_str, '%Y-%m-%dT%H:%M')
                # Chuyển sang timezone-aware (dùng timezone mặc định của Django)
                created_at = timezone.make_aware(naive_dt)
            except ValueError:
                # Thử format khác nếu cần
                try:
                    from django.utils.dateparse import parse_datetime
                    created_at = parse_datetime(created_at_str)
                    if created_at and timezone.is_naive(created_at):
                        created_at = timezone.make_aware(created_at)
                except Exception:
                    created_at = None
            except Exception as e:
                logger.warning(f"Error parsing created_at: {e}, using current time")
                created_at = None

        # Tạo ticket
        ticket = Ticket.objects.create(
            order_id=order_info['order_id'],
            order_code=order_code or order_info['order_code'],
            reference_number=reference_number or order_info['reference_number'],
            customer_id=order_info['customer_id'],
            customer_name=order_info['customer_name'],
            customer_phone=order_info['customer_phone'],
            location_id=order_info['location_id'],
            shop=order_info['shop'],
            # Ticket từ kho: loại vấn đề luôn là "Kho hàng"
            ticket_type="Kho hàng",
            ticket_status=request.POST.get('ticket_status', 'new'),
            # Ticket tạo từ kho nhưng mặc định chuyển sang CSKH xử lý
            source_ticket='cskh_created',
            depart='cskh',
            # Nguồn lỗi & loại lỗi dùng cấu hình riêng cho ticket kho
            source_reason=request.POST.get('source_reason', ''),
            reason_type=request.POST.get('reason_type', ''),
            note=note_text,
            images=uploaded_files,
            created_by=request.user,
            created_at=created_at if created_at else timezone.now(),
        )

        # Tạo Trouble & Event đầu tiên:
        # - Nội dung: CHUYỂN SANG CSKH (bắt buộc)
        # - Nếu có ghi chú note_text thì nối thêm bên dưới
        initial_content = "CHUYỂN SANG CSKH"
        if note_text:
            initial_content = initial_content + "\n\n" + note_text
        TicketEvent.objects.create(
            ticket=ticket,
            content=initial_content,
            tags="Khởi tạo ticket",
            created_by=request.user,
        )
        
        # Lưu variants_issue nếu có
        variants_issue = request.POST.getlist('variants_issue')
        if variants_issue:
            ticket.variants_issue = [int(v) for v in variants_issue if v]
            ticket.save()
        
        # Log action
        log_ticket_action(
            ticket.ticket_number,
            request.user.username,
            'created',
            {'order_code': order_code, 'ticket_type': ticket.ticket_type}
        )
        
        messages.success(request, f'Ticket {ticket.ticket_number} đã được tạo thành công')
        return redirect('kho:ticket_detail', ticket_id=ticket.id)
    
    # GET request - hiển thị form
    ticket_config = CSKHTicketConfigService.get_config()

    # Các dropdown lấy trực tiếp từ file config:
    # - nguon_loi_kho, loai_loi_kho: dùng cho ticket kho
    # - loai_chi_phi: dùng cho "Loại chi phí"
    reason_sources = ticket_config.get('nguon_loi_kho', []) or ticket_config.get('nguon_loi', []) or []
    warehouse_error_types = ticket_config.get('loai_loi_kho', []) or ticket_config.get('loai_loi', []) or []
    cost_types = ticket_config.get('loai_chi_phi', []) or []

    context = {
        # Nguồn lỗi, loại lỗi, loại chi phí lấy từ cấu hình
        'reason_sources': reason_sources,
        'warehouse_error_types': warehouse_error_types,
        'cost_types': cost_types,
        # Các trường khác vẫn dùng choices mặc định của model (nếu cần sau này có thể cấu hình thêm)
        'status_choices': Ticket.STATUS_CHOICES,
        'source_choices': Ticket.SOURCE_CHOICES,
    }
    return render(request, 'kho/tickets/create.html', context)


@group_required("WarehouseManager")
def ticket_detail(request, ticket_id):
    """Chi tiết ticket - Logic từ cskh"""
    from datetime import datetime
    
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    # Cập nhật lần xem cuối của user hiện tại
    TicketView.objects.update_or_create(
        ticket=ticket,
        user=request.user,
        defaults={'last_viewed_at': timezone.now()}
    )
    
    costs = ticket.costs.all()
    logs = get_ticket_logs(ticket.ticket_number)
    
    # Format timestamp cho logs
    for log in logs:
        if log.get('timestamp'):
            try:
                # Parse ISO format timestamp
                ts_str = log['timestamp']
                if ts_str.endswith('Z'):
                    ts_str = ts_str.replace('Z', '+00:00')
                dt = datetime.fromisoformat(ts_str)
                log['formatted_time'] = dt.strftime('%d/%m/%Y %H:%M')
            except Exception:
                # Fallback: format đơn giản
                log['formatted_time'] = ts_str[:16].replace('T', ' ') if len(ts_str) > 16 else ts_str
    
    # Tính tổng chi phí
    total_cost = costs.aggregate(total=Sum('amount'))['total'] or 0

    # Cấu hình ticket CSKH/Kho (nguồn lỗi, loại lỗi, hướng xử lý, loại chi phí, ...)
    ticket_config = CSKHTicketConfigService.get_config()

    # Các dropdown lấy từ config (nếu cần về sau)
    issue_type_options = ticket_config.get('loai_van_de', []) or []

    # Nguồn lỗi & loại lỗi kho
    reason_sources = ticket_config.get('nguon_loi_kho', []) or ticket_config.get('nguon_loi', []) or []
    warehouse_error_types = ticket_config.get('loai_loi_kho', []) or ticket_config.get('loai_loi', []) or []

    # Hướng xử lý: ưu tiên cấu hình riêng cho kho, sau đó là cấu hình CSKH
    warehouse_hx = ticket_config.get('huong_xu_ly_kho', []) or []
    cskh_hx = ticket_config.get('huong_xu_ly', []) or []
    # Ghép list kho + CSKH, loại bỏ trùng, giữ thứ tự
    combined_hx = []
    for item in warehouse_hx + cskh_hx:
        if item and item not in combined_hx:
            combined_hx.append(item)

    # Sugget process (hướng xử lý) - chuẩn hoá để dễ hiển thị
    raw_sugget = ticket.sugget_process or {}
    sugget_process = {}
    if isinstance(raw_sugget, dict) and raw_sugget:
        sugget_process = raw_sugget.copy()
        ts_str = raw_sugget.get('time') or ''
        if ts_str:
            try:
                if ts_str.endswith('Z'):
                    ts_str = ts_str.replace('Z', '+00:00')
                dt = datetime.fromisoformat(ts_str)
                sugget_process['formatted_time'] = dt.strftime('%d/%m/%Y %H:%M')
            except Exception:
                sugget_process['formatted_time'] = ts_str[:16].replace('T', ' ') if len(ts_str) > 16 else ts_str

    # Trouble & Event timeline
    events = ticket.events.select_related('created_by').order_by('created_at').all()
    
    # Đánh dấu event nào cần hiển thị avatar/name (chỉ event đầu tiên trong nhóm cùng người tạo)
    # và event nào là cuối cùng trong nhóm (để hiển thị thời gian)
    prev_creator_id = None
    events_list = list(events)
    for i, ev in enumerate(events_list):
        current_creator_id = ev.created_by.id if ev.created_by else None
        ev.show_avatar = (current_creator_id != prev_creator_id)
        
        # Đánh dấu event cuối cùng trong nhóm (event trước khi creator_id thay đổi hoặc là event cuối cùng)
        next_ev = events_list[i + 1] if i + 1 < len(events_list) else None
        next_creator_id = next_ev.created_by.id if next_ev and next_ev.created_by else None
        ev.is_last_in_group = (current_creator_id != next_creator_id)
        
        prev_creator_id = current_creator_id
    
    # Xác định kho hiển thị theo location_id
    warehouse_name = None
    if ticket.location_id == 241737:
        warehouse_name = "Kho Geleximco"
    elif ticket.location_id == 548744:
        warehouse_name = "Kho Tô Ký"

    # Lấy thông tin order nếu có order_id
    order_info = None
    process_order_info = None
    variants = []

    if ticket.order_id:
        try:
            ticket_service = TicketService()
            order = ticket_service.order_service.get_order_dto(ticket.order_id)
            order_info = ticket_service.extract_order_info(order)
            
            # Thêm packing_status và nguoi_goi từ order DTO
            order_info['packing_status'] = getattr(order, 'packing_status', 0) or 0
            order_info['nguoi_goi'] = getattr(order, 'nguoi_goi', None)
            
            # Lấy variants từ order (kèm giá bán & số lượng để phục vụ tính thiệt hại)
            variant_ids = set()
            if hasattr(order, 'line_items') and order.line_items:
                for item in order.line_items:
                    vid = item.variant_id
                    variants.append({
                        'variant_id': vid,
                        'product_name': item.product_name or '',
                        'variant_name': item.variant_name or '',
                        'sku': item.sku or '',
                        'price': float(getattr(item, 'price', 0) or 0),
                        'quantity': float(getattr(item, 'quantity', 0) or 0),
                        'is_selected': vid in (ticket.variants_issue or []),
                    })
                    if vid:
                        variant_ids.add(vid)
            
            # Lấy image_url từ cache hoặc Sapo
            from cskh.models import VariantImageCache
            image_map = {v.variant_id: v.image_url for v in VariantImageCache.objects.filter(variant_id__in=variant_ids)}
            missing_ids = [vid for vid in variant_ids if vid not in image_map]
            
            if missing_ids:
                from core.sapo_client import get_sapo_client
                sapo = get_sapo_client()
                core_api = sapo.core
                for vid in missing_ids:
                    try:
                        raw = core_api.get_variant_raw(vid)
                        variant_data = raw.get('variant') or {}
                        images = variant_data.get('images') or []
                        if images:
                            url = images[0].get('full_path')
                            if url:
                                image_map[vid] = url
                                VariantImageCache.objects.update_or_create(
                                    variant_id=vid,
                                    defaults={'image_url': url},
                                )
                    except Exception:
                        continue
            
            # Gắn image_url vào variants
            for v in variants:
                vid = v.get('variant_id')
                v['image_url'] = image_map.get(vid, '')
            
            # Sắp xếp: đã tick lên đầu, chưa tick xuống dưới
            variants.sort(key=lambda x: (not x.get('is_selected', False), x.get('variant_id', 0)))
            
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"Could not load order info for ticket {ticket.id}: {e}")

    # Lấy thông tin đơn xử lý nếu có
    if ticket.process_order_id:
        try:
            ticket_service = TicketService()
            process_order = ticket_service.order_service.get_order_dto(ticket.process_order_id)
            process_order_info = ticket_service.extract_order_info(process_order)
            
            # Thêm packing_status và nguoi_goi từ order DTO
            process_order_info['packing_status'] = getattr(process_order, 'packing_status', 0) or 0
            process_order_info['nguoi_goi'] = getattr(process_order, 'nguoi_goi', None)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"Could not load process order info for ticket {ticket.id}: {e}")
    
    # Lấy danh sách users & bộ phận để chọn người chịu trách nhiệm
    # Bộ phận lấy từ last_name của user, ví dụ: QUẢN TRỊ VIÊN, KHO_HN, KHO_HCM, CSKH, MARKETING
    users = User.objects.filter(is_active=True).order_by("first_name", "username")
    
    departments_set = set()
    users_with_dept = []
    for user in users:
        dept_name = (user.last_name or "").strip()
        if dept_name:
            departments_set.add(dept_name)
        users_with_dept.append({
            "id": user.id,
            "username": user.username,
            "full_name": user.first_name or user.username,
            "department": dept_name,
        })
    
    # Danh sách bộ phận để hiển thị trong select
    departments = sorted(departments_set)
    # Nếu ticket đang lưu bộ phận nhưng không còn trong groups, vẫn thêm để không mất dữ liệu
    if ticket.responsible_department and ticket.responsible_department not in departments:
        departments.append(ticket.responsible_department)
    
    context = {
        'ticket': ticket,
        'costs': costs,
        'total_cost': total_cost,
        'logs': logs,
        'events': events,
        'order_info': order_info,
        'process_order_info': process_order_info,
        'variants': variants,
        'variants_json': json.dumps(variants) if variants else '[]',
        'users': users_with_dept,
        'departments': departments,
        'sugget_process': sugget_process,
        # Lý do, loại lỗi, chi phí, hướng xử lý lấy từ cấu hình
        'issue_type_options': issue_type_options,
        'reason_sources': reason_sources,
        'warehouse_error_types': warehouse_error_types,
        'cost_types': ticket_config.get('loai_chi_phi', []),
        'huong_xu_ly_list': combined_hx,
        'status_choices': Ticket.STATUS_CHOICES,
        'ticket_type_choices': Ticket.TICKET_TYPE_CHOICES,
        'warehouse_name': warehouse_name,
    }
    return render(request, 'kho/tickets/detail.html', context)


@group_required("WarehouseManager")
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

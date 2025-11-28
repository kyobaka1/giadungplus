# cskh/views.py
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.urls import reverse

from .models import Ticket, TicketCost, TicketEvent, TicketView
from .services.ticket_service import TicketService
from .settings import (
    get_reason_sources, get_reason_types_by_source, get_cost_types,
    REASON_SOURCES
)
from .utils import log_ticket_action, get_ticket_logs

logger = logging.getLogger(__name__)

# =======================
# DASHBOARD
# =======================

@login_required
def dashboard(request):
    """Dashboard tổng quan CSKH"""
    
    ticket_stats = Ticket.objects.aggregate(
        new=Count('id', filter=Q(ticket_status='new')),
        processing=Count('id', filter=Q(ticket_status='processing')),
        total=Count('id')
    )
    
    context = {
        'ticket_stats': {
            'new': ticket_stats['new'] or 0,
            'processing': ticket_stats['processing'] or 0,
            'total': ticket_stats['total'] or 0,
        },
        'warranty_stats': {
            'expiring_soon': 5,
            'newly_activated': 15,
            'active': 120,
        },
        'review_stats': {
            'average_rating': 4.5,
            'total_reviews': 230,
            'positive': 180,
            'negative': 50,
        },
        'order_stats': {
            'pending_support': 7,
            'resolved_today': 15,
        }
    }
    return render(request, 'cskh/dashboard.html', context)


# =======================
# TICKET VIEWS
# =======================

@login_required
def ticket_overview(request):
    """Tổng quan ticket"""
    
    metrics = Ticket.objects.aggregate(
        unprocessed=Count('id', filter=Q(ticket_status='new')),
        processing=Count('id', filter=Q(ticket_status='processing')),
        completed_today=Count('id', filter=Q(
            ticket_status='resolved',
            resolved_at__date=timezone.now().date()
        ))
    )
    
    # Category breakdown
    category_breakdown = Ticket.objects.values('ticket_type').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    context = {
        'metrics': {
            'unprocessed': metrics['unprocessed'] or 0,
            'processing': metrics['processing'] or 0,
            'completed_today': metrics['completed_today'] or 0,
        },
        'category_breakdown': [
            {
                'name': dict(Ticket.TICKET_TYPE_CHOICES).get(item['ticket_type'], item['ticket_type']),
                'count': item['count']
            }
            for item in category_breakdown
        ]
    }
    return render(request, 'cskh/tickets/overview.html', context)


@login_required
def ticket_list(request):
    """Danh sách tickets"""
    
    tickets = Ticket.objects.all()
    
    # Bộ lọc lồng nhau (AND): loại ticket, bộ phận xử lý, trạng thái
    ticket_type_filter = request.GET.get('ticket_type', '')
    depart_filter = request.GET.get('depart', '')
    status_filter = request.GET.get('status', '')

    if ticket_type_filter:
        tickets = tickets.filter(ticket_type=ticket_type_filter)

    if depart_filter:
        tickets = tickets.filter(depart=depart_filter)

    if status_filter:
        tickets = tickets.filter(ticket_status=status_filter)
    else:
        # Mặc định: danh sách ticket loại trừ ticket đã đóng
        tickets = tickets.exclude(ticket_status='closed')
    
    tickets = tickets.select_related('created_by', 'assigned_to').annotate(
        total_cost=Sum('costs__amount')
    )[:100]
    
    # Tính số event mới chưa xem cho mỗi ticket
    ticket_ids = [t.id for t in tickets]
    ticket_views = TicketView.objects.filter(
        ticket_id__in=ticket_ids,
        user=request.user
    ).select_related('ticket')
    
    # Tạo dict {ticket_id: last_viewed_at}
    views_dict = {tv.ticket_id: tv.last_viewed_at for tv in ticket_views}
    
    # Đếm số event mới cho mỗi ticket và gắn vào ticket object
    from django.db.models import Count, Q
    from .models import TicketEvent
    
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
        'total_count': tickets.count(),
        'ticket_type_filter': ticket_type_filter,
        'depart_filter': depart_filter,
        'status_filter': status_filter,
        'status_choices': Ticket.STATUS_CHOICES,
        'ticket_type_choices': Ticket.TICKET_TYPE_CHOICES,
        'depart_choices': Ticket.DEPART_CHOICES,
    }
    return render(request, 'cskh/tickets/list.html', context)


@login_required
def ticket_detail(request, ticket_id):
    """Chi tiết ticket"""
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

    # Trouble & Event timeline
    events = ticket.events.select_related('created_by').all()
    
    # Đánh dấu event nào cần hiển thị avatar/name (chỉ event đầu tiên trong nhóm cùng người tạo)
    prev_creator_id = None
    for ev in events:
        current_creator_id = ev.created_by.id if ev.created_by else None
        ev.show_avatar = (current_creator_id != prev_creator_id)
        prev_creator_id = current_creator_id
    
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
            from .models import VariantImageCache
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
        'users': users_with_dept,
        'departments': departments,
        'reason_sources': get_reason_sources(),
        'cost_types': get_cost_types(),
        'status_choices': Ticket.STATUS_CHOICES,
        'ticket_type_choices': Ticket.TICKET_TYPE_CHOICES,
    }
    return render(request, 'cskh/tickets/detail.html', context)


@login_required
def ticket_create(request):
    """Tạo ticket mới"""
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
            return redirect('cskh:ticket_create')
        
        # Lấy order để lấy thông tin đầy đủ
        try:
            order = ticket_service.order_service.get_order_dto(int(order_id))
            order_info = ticket_service.extract_order_info(order)
        except Exception as e:
            messages.error(request, f'Không thể lấy thông tin đơn hàng: {str(e)}')
            return redirect('cskh:ticket_create')
        
        # Kiểm tra xem đã có ticket nào với cùng order_code hoặc reference_number chưa
        final_order_code = order_code or order_info.get('order_code', '')
        final_reference_number = reference_number or order_info.get('reference_number', '')
        
        existing_ticket = None
        if final_order_code:
            existing_ticket = Ticket.objects.filter(order_code=final_order_code).first()
        if not existing_ticket and final_reference_number:
            existing_ticket = Ticket.objects.filter(reference_number=final_reference_number).first()
        
        if existing_ticket:
            ticket_url = reverse('cskh:ticket_detail', args=[existing_ticket.id])
            error_msg = mark_safe(
                f'Đơn hàng này đã có ticket: <strong>{existing_ticket.ticket_number}</strong>. '
                f'Vui lòng xem ticket <a href="{ticket_url}" class="underline font-semibold text-blue-600 hover:text-blue-800">#{existing_ticket.ticket_number}</a>'
            )
            messages.error(request, error_msg)
            return redirect('cskh:ticket_create')
        
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
            ticket_type=request.POST.get('ticket_type', ''),
            ticket_status=request.POST.get('ticket_status', 'new'),
            source_ticket=request.POST.get('source_ticket', 'cskh_created'),
            depart=request.POST.get('depart', 'cskh'),
            source_reason=request.POST.get('source_reason', ''),
            reason_type=request.POST.get('reason_type', ''),
            note=note_text,
            images=uploaded_files,
            created_by=request.user,
        )

        # Tạo Trouble & Event đầu tiên từ ghi chú khi tạo ticket
        if note_text:
            TicketEvent.objects.create(
                ticket=ticket,
                content=note_text,
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
        return redirect('cskh:ticket_detail', ticket_id=ticket.id)
    
    # GET request - hiển thị form
    context = {
        'ticket_type_choices': Ticket.TICKET_TYPE_CHOICES,
        'status_choices': Ticket.STATUS_CHOICES,
        'source_choices': Ticket.SOURCE_CHOICES,
        'reason_sources': get_reason_sources(),
        'cost_types': get_cost_types(),
    }
    return render(request, 'cskh/tickets/create.html', context)


# =======================
# WARRANTY VIEWS
# =======================

@login_required
def warranty_overview(request):
    """Tổng quan bảo hành"""
    context = {
        'metrics': {
            'active_warranties': 120,
            'expiring_soon': 5,
            'newly_activated': 15,
            'pending_claims': 8,
        },
        'chart_data': {
            'labels': ['Tháng 1', 'Tháng 2', 'Tháng 3', 'Tháng 4'],
            'activated': [10, 15, 12, 18],
            'expired': [5, 8, 6, 10],
        }
    }
    return render(request, 'cskh/warranty/overview.html', context)


@login_required
def warranty_list(request):
    """Danh sách bảo hành"""
    # Mock data
    warranties = [
        {
            'id': 1,
            'order_code': 'GDP001234',
            'customer_name': 'Nguyễn Văn A',
            'customer_phone': '0901234567',
            'product_name': 'Nồi chiên không dầu 5L',
            'purchase_date': '2024-11-01',
            'warranty_end': '2025-11-01',
            'status': 'active',
            'days_remaining': 342,
        },
        {
            'id': 2,
            'order_code': 'GDP001235',
            'customer_name': 'Lê Thị C',
            'customer_phone': '0902345678',
            'product_name': 'Máy xay sinh tố',
            'purchase_date': '2024-10-15',
            'warranty_end': '2025-10-15',
            'status': 'active',
            'days_remaining': 325,
        },
    ]
    
    context = {
        'warranties': warranties,
        'total_count': len(warranties),
    }
    return render(request, 'cskh/warranty/list.html', context)


@login_required
def warranty_detail(request, warranty_id):
    """Chi tiết bảo hành"""
    warranty = {
        'id': warranty_id,
        'order_code': 'GDP001234',
        'customer_name': 'Nguyễn Văn A',
        'customer_phone': '0901234567',
        'customer_email': 'nguyenvana@email.com',
        'product_name': 'Nồi chiên không dầu 5L',
        'product_sku': 'NCK-5L-001',
        'purchase_date': '2024-11-01',
        'warranty_period': 12,
        'warranty_end': '2025-11-01',
        'status': 'active',
        'days_remaining': 342,
        'claims': []
    }
    
    context = {'warranty': warranty}
    return render(request, 'cskh/warranty/detail.html', context)


# =======================
# REVIEW VIEWS
# =======================

@login_required
def review_overview(request):
    """Tổng quan đánh giá"""
    context = {
        'metrics': {
            'total_reviews': 230,
            'average_rating': 4.5,
            'positive_count': 180,
            'negative_count': 50,
            'pending_response': 12,
        },
        'rating_breakdown': [
            {'stars': 5, 'count': 120, 'percentage': 52},
            {'stars': 4, 'count': 60, 'percentage': 26},
            {'stars': 3, 'count': 30, 'percentage': 13},
            {'stars': 2, 'count': 15, 'percentage': 7},
            {'stars': 1, 'count': 5, 'percentage': 2},
        ]
    }
    return render(request, 'cskh/reviews/overview.html', context)


@login_required
def review_list(request):
    """Danh sách đánh giá"""
    # Mock data
    reviews = [
        {
            'id': 1,
            'customer_name': 'Nguyễn Văn A',
            'product_name': 'Nồi chiên không dầu 5L',
            'rating': 5,
            'content': 'Sản phẩm rất tốt, giao hàng nhanh!',
            'images': [],
            'sentiment': 'positive',
            'has_response': False,
            'created_at': '2025-11-24 10:30',
            'platform': 'Shopee',
        },
        {
            'id': 2,
            'customer_name': 'Lê Thị C',
            'product_name': 'Máy xay sinh tố',
            'rating': 3,
            'content': 'Sản phẩm tạm ổn, nhưng hơi ồn.',
            'images': [],
            'sentiment': 'neutral',
            'has_response': True,
            'created_at': '2025-11-24 09:15',
            'platform': 'Shopee',
        },
        {
            'id': 3,
            'customer_name': 'Hoàng Văn E',
            'product_name': 'Bình đun siêu tốc',
            'rating': 2,
            'content': 'Sản phẩm không như mong đợi, chất lượng kém.',
            'images': [],
            'sentiment': 'negative',
            'has_response': False,
            'created_at': '2025-11-23 14:20',
            'platform': 'Shopee',
        },
    ]
    
    context = {
        'reviews': reviews,
        'total_count': len(reviews),
    }
    return render(request, 'cskh/reviews/list.html', context)


# =======================
# ORDERS & PRODUCTS LOOKUP
# =======================

@login_required
def orders_view(request):
    """Tra cứu đơn hàng"""
    context = {
        'search_placeholder': 'Nhập mã đơn hàng, SĐT, hoặc tên khách hàng...',
    }
    return render(request, 'cskh/lookup/orders.html', context)


@login_required
def products_view(request):
    """Tra cứu sản phẩm"""
    context = {
        'search_placeholder': 'Nhập tên sản phẩm hoặc SKU...',
    }
    return render(request, 'cskh/lookup/products.html', context)

def order_list(request):
    return render(request, "kho/order_list.html")

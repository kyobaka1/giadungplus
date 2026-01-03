# cskh/views.py
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from cskh.utils import group_required
from django.http import JsonResponse, Http404
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q, Count, Sum, Avg, F, ExpressionWrapper, DurationField
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.urls import reverse

from .models import (
    Ticket,
    TicketCost,
    TicketEvent,
    TicketView,
    Feedback,
    FeedbackLog,
    TrainingDocument,
)
from .services.ticket_service import TicketService
from .settings import (
    get_reason_sources, get_reason_types_by_source, get_cost_types,
    REASON_SOURCES
)
from .utils import log_ticket_action, get_ticket_logs
from django.utils import timezone as dj_timezone
from settings.services.cskh_ticket_config_service import CSKHTicketConfigService
from django.core.paginator import Paginator

logger = logging.getLogger(__name__)

# =======================
# DASHBOARD
# =======================

@group_required("CSKHManager", "CSKHStaff")
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

@group_required("CSKHManager", "CSKHStaff")
def ticket_overview(request):
    """
    Ticket Overview Dashboard – theo yêu cầu trong TICKET_OVERVIEW.md

    Tất cả thống kê đều chạy trên queryset đã được lọc theo bộ lọc phía trên.
    """
    from datetime import timedelta

    # -----------------------------
    # 1. ĐỌC BỘ LỌC TỪ REQUEST
    # -----------------------------
    date_field = request.GET.get('date_field', 'created_at')  # created_at | closed_at
    quick_range = request.GET.get('quick_range', 'last_30d')
    date_from_raw = request.GET.get('date_from', '')
    date_to_raw = request.GET.get('date_to', '')

    source_ticket = request.GET.get('source_ticket', '')
    ticket_type = request.GET.get('ticket_type', '')
    source_reason = request.GET.get('source_reason', '')
    reason_type = request.GET.get('reason_type', '')
    ticket_status = request.GET.get('ticket_status', '')
    depart = request.GET.get('depart', '')
    responsible_department = request.GET.get('responsible_department', '')
    created_by_raw = request.GET.get('created_by', '')
    assigned_to_raw = request.GET.get('assigned_to', '')
    responsible_user_raw = request.GET.get('responsible_user', '')

    # Chuẩn hoá id nhân sự về kiểu int hoặc None để tránh lỗi so sánh trong template
    def to_int_or_none(value: str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    created_by_id = to_int_or_none(created_by_raw) if created_by_raw else None
    assigned_to_id = to_int_or_none(assigned_to_raw) if assigned_to_raw else None
    responsible_user_id = to_int_or_none(responsible_user_raw) if responsible_user_raw else None

    # -----------------------------
    # 2. XÂY DỰNG QUERYSET CƠ BẢN
    # -----------------------------
    tickets_qs = Ticket.objects.all()

    # --- Thời gian ---
    # Nếu người dùng không chọn from/to thì áp dụng quick_range.
    today = timezone.localdate()
    date_from = None
    date_to = None

    if date_from_raw or date_to_raw:
        # Ưu tiên from/to nếu có
        if date_from_raw:
            try:
                date_from = timezone.datetime.fromisoformat(date_from_raw).date()
            except Exception:
                date_from = None
        if date_to_raw:
            try:
                date_to = timezone.datetime.fromisoformat(date_to_raw).date()
            except Exception:
                date_to = None
    else:
        # Áp dụng quick range mặc định
        if quick_range == 'today':
            date_from = today
            date_to = today
        elif quick_range == 'last_7d':
            date_from = today - timedelta(days=7)
            date_to = today
        elif quick_range == 'last_30d':
            date_from = today - timedelta(days=30)
            date_to = today
        elif quick_range == 'this_month':
            date_from = today.replace(day=1)
            date_to = today
        elif quick_range == 'this_quarter':
            # Quý hiện tại: 1-3, 4-6, 7-9, 10-12
            month = today.month
            if month <= 3:
                start_month = 1
            elif month <= 6:
                start_month = 4
            elif month <= 9:
                start_month = 7
            else:
                start_month = 10
            date_from = today.replace(month=start_month, day=1)
            date_to = today

    target_field = 'created_at'
    if date_field == 'closed_at':
        target_field = 'closed_at'

    if date_from:
        tickets_qs = tickets_qs.filter(**{f'{target_field}__date__gte': date_from})
    if date_to:
        tickets_qs = tickets_qs.filter(**{f'{target_field}__date__lte': date_to})

    # --- Các filter khác ---
    if source_ticket:
        tickets_qs = tickets_qs.filter(source_ticket=source_ticket)
    if ticket_type:
        tickets_qs = tickets_qs.filter(ticket_type=ticket_type)
    if source_reason:
        tickets_qs = tickets_qs.filter(source_reason=source_reason)
    if reason_type:
        tickets_qs = tickets_qs.filter(reason_type=reason_type)
    if ticket_status:
        tickets_qs = tickets_qs.filter(ticket_status=ticket_status)
    if depart:
        tickets_qs = tickets_qs.filter(depart=depart)
    if responsible_department:
        tickets_qs = tickets_qs.filter(responsible_department=responsible_department)

    if created_by_id is not None:
        tickets_qs = tickets_qs.filter(created_by_id=created_by_id)
    if assigned_to_id is not None:
        tickets_qs = tickets_qs.filter(assigned_to_id=assigned_to_id)
    if responsible_user_id is not None:
        tickets_qs = tickets_qs.filter(responsible_user_id=responsible_user_id)

    # Gắn lại from/to hiển thị (nếu dùng quick_range)
    if not date_from_raw and date_from:
        date_from_raw = date_from.isoformat()
    if not date_to_raw and date_to:
        date_to_raw = date_to.isoformat()

    # Lấy danh sách user phục vụ filter & People KPI
    users = User.objects.filter(is_active=True).order_by("first_name", "username")

    # -----------------------------
    # 3. KPI TỔNG QUAN
    # -----------------------------
    total_tickets = tickets_qs.count()

    # Số ticket mới trong kỳ – đếm theo created_at trên tickets_qs (đã lọc time)
    new_tickets = total_tickets

    # Số ticket đã đóng trong kỳ (closed_at trong range)
    closed_in_range = tickets_qs.filter(closed_at__isnull=False).count()

    # Số ticket đang mở (status khác closed) và đã đóng
    open_tickets = tickets_qs.exclude(ticket_status='closed').count()
    closed_tickets = closed_in_range
    # Tỷ lệ theo %, để hiển thị dễ hiểu trên UI
    open_ticket_rate = (open_tickets / total_tickets * 100) if total_tickets else 0
    closed_ticket_rate = (closed_tickets / total_tickets * 100) if total_tickets else 0

    # Thời gian xử lý trung bình
    resolution_expr = ExpressionWrapper(F('closed_at') - F('created_at'), output_field=DurationField())
    resolved_qs = tickets_qs.filter(closed_at__isnull=False).annotate(
        resolution_time=resolution_expr
    )
    avg_resolution_seconds = None
    avg_resolution_hours = None
    if resolved_qs.exists():
        # Dùng aggregate để tính trung bình (Django 3.x không support Avg(DurationField) chuẩn ở mọi DB -> dùng Python)
        total_seconds = 0
        for t in resolved_qs.values_list('resolution_time', flat=True):
            if t is not None:
                total_seconds += t.total_seconds()
        if resolved_qs.count():
            avg_resolution_seconds = total_seconds / resolved_qs.count()
            avg_resolution_hours = avg_resolution_seconds / 3600.0

    # Chi phí
    from .models import TicketCost

    costs_qs = TicketCost.objects.filter(ticket__in=tickets_qs)
    total_cost = costs_qs.aggregate(total=Sum('amount'))['total'] or 0

    # Số ticket có cost > 0
    ticket_with_cost = tickets_qs.filter(costs__amount__gt=0).distinct().count()
    avg_cost_per_ticket = (total_cost / ticket_with_cost) if ticket_with_cost else 0

    # -----------------------------
    # 4. PROCESS & SLA
    # -----------------------------
    # Phân bổ thời gian xử lý theo bucket
    buckets = {
        'lt_1h': 0,
        '1_4h': 0,
        '4_24h': 0,
        '1_3d': 0,
        'gt_3d': 0,
    }
    for t in resolved_qs.values_list('resolution_time', flat=True):
        if not t:
            continue
        hours = t.total_seconds() / 3600
        if hours <= 1:
            buckets['lt_1h'] += 1
        elif hours <= 4:
            buckets['1_4h'] += 1
        elif hours <= 24:
            buckets['4_24h'] += 1
        elif hours <= 72:
            buckets['1_3d'] += 1
        else:
            buckets['gt_3d'] += 1
    # Chuẩn hoá bucket để render dễ trong template
    resolution_bucket_list = [
        {'label': '0–1h', 'key': 'lt_1h', 'count': buckets['lt_1h']},
        {'label': '1–4h', 'key': '1_4h', 'count': buckets['1_4h']},
        {'label': '4–24h', 'key': '4_24h', 'count': buckets['4_24h']},
        {'label': '1–3 ngày', 'key': '1_3d', 'count': buckets['1_3d']},
        {'label': '> 3 ngày', 'key': 'gt_3d', 'count': buckets['gt_3d']},
    ]

    # SLA đơn giản: xử lý xong trong 24h kể từ created_at
    sla_ok_count = 0
    sla_violate_count = 0
    for t in resolved_qs.values_list('resolution_time', flat=True):
        if not t:
            continue
        hours = t.total_seconds() / 3600
        if hours <= 24:
            sla_ok_count += 1
        else:
            sla_violate_count += 1

    total_sla = sla_ok_count + sla_violate_count
    sla_ok_rate = (sla_ok_count / total_sla) if total_sla else 0
    sla_violate_rate = (sla_violate_count / total_sla) if total_sla else 0

    # Transfers – số lần chuyển phòng ban
    from .models import TicketEvent, TicketTransfer

    transfers_qs = TicketTransfer.objects.filter(ticket__in=tickets_qs)
    transfers_by_ticket = transfers_qs.values('ticket_id').annotate(count=Count('id'))
    transfer_bucket = {'0': 0, '1': 0, '2': 0, '3_plus': 0}
    total_transfer_tickets = total_tickets
    total_transfer_times = 0

    transfer_count_map = {row['ticket_id']: row['count'] for row in transfers_by_ticket}
    for ticket_id in tickets_qs.values_list('id', flat=True):
        c = transfer_count_map.get(ticket_id, 0)
        total_transfer_times += c
        if c == 0:
            transfer_bucket['0'] += 1
        elif c == 1:
            transfer_bucket['1'] += 1
        elif c == 2:
            transfer_bucket['2'] += 1
        else:
            transfer_bucket['3_plus'] += 1

    avg_transfers_per_ticket = (total_transfer_times / total_transfer_tickets) if total_transfer_tickets else 0
    tickets_gt2_transfer = sum(
        1 for c in transfer_count_map.values() if c > 2
    )
    percent_gt2_transfer = (tickets_gt2_transfer / total_tickets) if total_tickets else 0

    # Interaction (Event) – số lần "chạm"
    events_qs = TicketEvent.objects.filter(ticket__in=tickets_qs)
    events_by_ticket = events_qs.values('ticket_id').annotate(count=Count('id'))
    total_events = sum(row['count'] for row in events_by_ticket)
    avg_interaction_per_ticket = (total_events / total_tickets) if total_tickets else 0

    # Top ticket bị "sờ" nhiều nhất
    top_interaction_tickets = list(
        events_by_ticket.order_by('-count')[:5]
    )
    # Gắn thêm ticket_number
    ticket_map = {
        t.id: t.ticket_number for t in tickets_qs.only('id', 'ticket_number')
    }
    for item in top_interaction_tickets:
        item['ticket_number'] = ticket_map.get(item['ticket_id'], '')

    # -----------------------------
    # 5. ROOT CAUSE & COST
    # -----------------------------
    # 5.1 Theo ticket_type (stacked: open vs closed)
    type_status_stats = tickets_qs.values('ticket_type', 'ticket_status').annotate(
        count=Count('id')
    )
    ticket_type_labels = dict(Ticket.TICKET_TYPE_CHOICES)
    ticket_type_stats = {}
    for row in type_status_stats:
        t_type = row['ticket_type'] or 'other'
        status = row['ticket_status']
        if t_type not in ticket_type_stats:
            ticket_type_stats[t_type] = {'open': 0, 'closed': 0}
        if status == 'closed':
            ticket_type_stats[t_type]['closed'] += row['count']
        else:
            ticket_type_stats[t_type]['open'] += row['count']
    # Đưa về list để template xử lý gọn
    ticket_type_list = []
    for code, data in ticket_type_stats.items():
        total_type = (data['open'] or 0) + (data['closed'] or 0)
        ticket_type_list.append({
            'code': code,
            'label': ticket_type_labels.get(code, code),
            'open': data['open'],
            'closed': data['closed'],
            'total': total_type,
        })

    # 5.2 Pareto theo source_reason
    reason_stats = list(
        tickets_qs.values('source_reason').annotate(count=Count('id')).order_by('-count')
    )
    total_reason_tickets = sum(r['count'] for r in reason_stats) or 1
    cumulative = 0
    for r in reason_stats:
        cumulative += r['count']
        r['percentage'] = (r['count'] / total_reason_tickets) * 100
        r['cumulative_percentage'] = (cumulative / total_reason_tickets) * 100

    # Drill-down reason_type cho 1 source_reason có thể render lazy bằng link filter;
    # ở đây chỉ chuẩn bị stats tổng theo reason_type.
    reason_type_stats = list(
        tickets_qs.values('source_reason', 'reason_type').annotate(count=Count('id')).order_by('-count')
    )

    # 5.3 Chi phí theo loại chi phí
    cost_by_type = list(
        costs_qs.values('cost_type').annotate(
            total_amount=Sum('amount'),
            count=Count('id'),
        ).order_by('-total_amount')
    )

    # 5.4 Heatmap chi phí theo responsible_department x cost_type
    heatmap_cost = list(
        costs_qs.values('ticket__responsible_department', 'cost_type').annotate(
            total_amount=Sum('amount')
        )
    )

    # 5.5 Top SKU gây thiệt hại
    sku_stats = list(
        costs_qs.exclude(sku='').values('sku', 'product_name').annotate(
            total_amount=Sum('amount'),
            ticket_count=Count('ticket', distinct=True),
        ).order_by('-total_amount')[:10]
    )

    # -----------------------------
    # 6. PEOPLE & TEAM PERFORMANCE
    # -----------------------------
    # Theo nhân sự (assigned_to)
    people_stats = list(
        tickets_qs.values('assigned_to_id').annotate(
            total_tickets=Count('id'),
            closed_tickets=Count('id', filter=Q(ticket_status='closed')),
        ).order_by('-total_tickets')
    )
    user_map = {
        u.id: (u.first_name or u.username) for u in users
    }
    for p in people_stats:
        uid = p['assigned_to_id']
        p['name'] = user_map.get(uid, 'Chưa gán')

    # Theo phòng ban chịu trách nhiệm
    department_stats = list(
        tickets_qs.values('responsible_department').annotate(
            total_tickets=Count('id'),
            total_cost=Sum('costs__amount'),
        ).order_by('-total_tickets')
    )

    # 6.3 Mức độ xem ticket theo user
    from .models import TicketView

    views_qs = TicketView.objects.filter(ticket__in=tickets_qs)
    views_by_user = list(
        views_qs.values('user_id').annotate(
            view_count=Count('id'),
            ticket_count=Count('ticket', distinct=True),
        ).order_by('-view_count')[:10]
    )
    for v in views_by_user:
        uid = v['user_id']
        v['name'] = user_map.get(uid, 'N/A')

    # -----------------------------
    # 7. TIMELINE & TABLE
    # -----------------------------
    # Timeline mở / đóng theo ngày
    # (chỉ tính trong khoảng filter đang chọn)
    timeline_open = tickets_qs.extra(
        select={'day': "date(created_at)"}
    ).values('day').annotate(count=Count('id')).order_by('day')

    timeline_closed = tickets_qs.filter(closed_at__isnull=False).extra(
        select={'day': "date(closed_at)"}
    ).values('day').annotate(count=Count('id')).order_by('day')

    # Gom timeline để template không phải tính toán phức tạp
    timeline_open_list = list(timeline_open)
    timeline_closed_list = list(timeline_closed)
    closed_map = {row['day']: row['count'] for row in timeline_closed_list}
    timeline_rows = []
    for row in timeline_open_list:
        day = row['day']
        open_count = row['count']
        closed_count = closed_map.get(day, 0)
        timeline_rows.append({
            'day': day,
            'open': open_count,
            'closed': closed_count,
            'delta': open_count - closed_count,
        })

    # Bảng ticket chi tiết (limit 200)
    tickets_list = tickets_qs.select_related(
        'created_by', 'assigned_to', 'responsible_user'
    ).annotate(
        total_cost=Sum('costs__amount'),
        resolution_time=resolution_expr,
    )[:200]

    # -----------------------------
    # OPTIONS CHO BỘ LỌC
    # -----------------------------
    # source_reason & reason_type lấy từ dữ liệu hiện có để gợi ý
    distinct_source_reason = (
        Ticket.objects.exclude(source_reason='')
        .values_list('source_reason', flat=True)
        .distinct()
        .order_by('source_reason')
    )
    distinct_reason_type = (
        Ticket.objects.exclude(reason_type='')
        .values_list('reason_type', flat=True)
        .distinct()
        .order_by('reason_type')
    )
    distinct_responsible_department = (
        Ticket.objects.exclude(responsible_department='')
        .values_list('responsible_department', flat=True)
        .distinct()
        .order_by('responsible_department')
    )

    context = {
        # Bộ lọc + options
        'filter': {
            'date_field': date_field,
            'quick_range': quick_range,
            'date_from': date_from_raw,
            'date_to': date_to_raw,
            'source_ticket': source_ticket,
            'ticket_type': ticket_type,
            'source_reason': source_reason,
            'reason_type': reason_type,
            'ticket_status': ticket_status,
            'depart': depart,
            'responsible_department': responsible_department,
            'created_by': created_by_id,
            'assigned_to': assigned_to_id,
            'responsible_user': responsible_user_id,
        },
        'ticket_status_choices': Ticket.STATUS_CHOICES,
        'ticket_type_choices': Ticket.TICKET_TYPE_CHOICES,
        'source_ticket_choices': Ticket.SOURCE_CHOICES,
        'depart_choices': Ticket.DEPART_CHOICES,
        'source_reason_options': distinct_source_reason,
        'reason_type_options': distinct_reason_type,
        'responsible_department_options': distinct_responsible_department,
        'users': users,

        # KPI tổng quan
        'kpi': {
            'total_tickets': total_tickets,
            'new_tickets': new_tickets,
            'closed_tickets': closed_in_range,
            'open_tickets': open_tickets,
            'open_ticket_rate': open_ticket_rate,
            'closed_ticket_rate': closed_ticket_rate,
            'avg_resolution_seconds': avg_resolution_seconds,
            'avg_resolution_hours': avg_resolution_hours,
            'total_cost': total_cost,
            'avg_cost_per_ticket': avg_cost_per_ticket,
        },

        # Process & SLA
        'resolution_buckets': buckets,
        'resolution_bucket_list': resolution_bucket_list,
        'sla': {
            'ok_count': sla_ok_count,
            'violate_count': sla_violate_count,
            'ok_rate': sla_ok_rate,
            'violate_rate': sla_violate_rate,
        },
        'transfer_stats': {
            'buckets': transfer_bucket,
            'avg_transfers_per_ticket': avg_transfers_per_ticket,
            'percent_gt2_transfer': percent_gt2_transfer,
        },
        'interaction_stats': {
            'avg_interaction_per_ticket': avg_interaction_per_ticket,
            'top_tickets': top_interaction_tickets,
        },

        # Root cause & Cost
        'ticket_type_stats': ticket_type_stats,
        'ticket_type_labels': ticket_type_labels,
        'ticket_type_list': ticket_type_list,
        'reason_stats': reason_stats,
        'reason_type_stats': reason_type_stats,
        'cost_summary': {
            'total_cost': total_cost,
            'by_type': cost_by_type,
            'heatmap': heatmap_cost,
            'sku_stats': sku_stats,
        },

        # People & department
        'people_stats': people_stats,
        'department_stats': department_stats,
        'views_by_user': views_by_user,

        # Timeline & table
        'timeline_rows': timeline_rows,
        'tickets_list': tickets_list,
    }
    return render(request, 'cskh/tickets/overview.html', context)


@group_required("CSKHManager", "CSKHStaff")
def ticket_list(request):
    """Danh sách tickets"""
    
    tickets = Ticket.objects.all()
    
    # Bộ lọc lồng nhau (AND): loại ticket, bộ phận xử lý, trạng thái, nguồn tạo, người tạo, thời gian
    ticket_type_filter = request.GET.get('ticket_type', '')
    depart_filter = request.GET.get('depart', '')
    status_filter = request.GET.get('status', '')
    source_ticket_filter = request.GET.get('source_ticket', '')
    created_by_filter = request.GET.get('created_by', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

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
    
    if source_ticket_filter:
        tickets = tickets.filter(source_ticket=source_ticket_filter)
    
    if created_by_filter:
        try:
            created_by_id = int(created_by_filter)
            tickets = tickets.filter(created_by_id=created_by_id)
        except (ValueError, TypeError):
            pass
    
    # Lọc theo thời gian (created_at)
    if start_date:
        try:
            from django.utils.dateparse import parse_date
            from datetime import datetime
            start = parse_date(start_date)
            if start:
                start_datetime = datetime.combine(start, datetime.min.time())
                tickets = tickets.filter(created_at__gte=timezone.make_aware(start_datetime))
        except (ValueError, TypeError):
            pass
    
    if end_date:
        try:
            from django.utils.dateparse import parse_date
            from datetime import datetime
            end = parse_date(end_date)
            if end:
                end_datetime = datetime.combine(end, datetime.max.time())
                tickets = tickets.filter(created_at__lte=timezone.make_aware(end_datetime))
        except (ValueError, TypeError):
            pass
    
    tickets = tickets.select_related('created_by', 'assigned_to').annotate(
        total_cost=Sum('costs__amount')
    ).order_by('-created_at')[:100]
    
    # --- Bulk fetch order data for search ---
    order_ids = [t.order_id for t in tickets if t.order_id]
    if order_ids:
        try:
            from orders.services.sapo_service import SapoCoreOrderService
            from core.sapo_client import BaseFilter
            
            sapo_service = SapoCoreOrderService()
            ids_str = ",".join(map(str, order_ids))
            # Fetch orders with minimal fields if possible, but search needs details
            # Sapo API supports 'ids' param
            orders_result = sapo_service.list_orders(BaseFilter(params={"ids": ids_str, "limit": 100}))
            orders_data = orders_result.get("orders", [])
            
            # Create map for quick lookup
            order_map = {order["id"]: order for order in orders_data}
            
            # Attach to tickets
            for ticket in tickets:
                if ticket.order_id and ticket.order_id in order_map:
                    ticket.order_data = order_map[ticket.order_id]
        except Exception as e:
            logger.error(f"Failed to fetch order data for tickets: {e}")
            
    # Tính số event mới chưa xem cho mỗi ticket
    ticket_ids = [t.id for t in tickets]
    ticket_views = TicketView.objects.filter(
        ticket_id__in=ticket_ids,
        user=request.user
    ).select_related('ticket')
    
    # Tạo dict {ticket_id: last_viewed_at}
    views_dict = {tv.ticket_id: tv.last_viewed_at for tv in ticket_views}
    
    # Đếm số event mới cho mỗi ticket và gắn vào ticket object
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
    
    # Lấy danh sách users đã tạo ticket để hiển thị trong dropdown
    created_by_users = User.objects.filter(
        cskh_tickets_created__isnull=False
    ).distinct().order_by('first_name', 'username')
    
    context = {
        'tickets': tickets,
        'total_count': tickets.count(),
        'ticket_type_filter': ticket_type_filter,
        'depart_filter': depart_filter,
        'status_filter': status_filter,
        'source_ticket_filter': source_ticket_filter,
        'created_by_filter': created_by_filter,
        'start_date': start_date,
        'end_date': end_date,
        'status_choices': Ticket.STATUS_CHOICES,
        'ticket_type_choices': Ticket.TICKET_TYPE_CHOICES,
        'depart_choices': Ticket.DEPART_CHOICES,
        'source_ticket_choices': Ticket.SOURCE_CHOICES,
        'created_by_users': created_by_users,
    }
    return render(request, 'cskh/tickets/list.html', context)


@group_required("CSKHManager", "CSKHStaff")
def ticket_cost_overview(request):
    """
    Ticket free – Tổng hợp & danh sách chi phí cho toàn bộ ticket.
    """
    from django.db.models import Count

    # Bộ lọc
    payment_from_raw = request.GET.get("payment_from", "")
    payment_to_raw = request.GET.get("payment_to", "")
    cost_type_filters = request.GET.getlist("cost_type") or []
    person_id_filter = request.GET.get("person_id", "") or ""

    costs_qs = TicketCost.objects.select_related("ticket", "person").all()

    # Mặc định: 30 ngày gần nhất nếu không truyền cả from & to
    from datetime import timedelta
    if not payment_from_raw and not payment_to_raw:
        today = timezone.localdate()
        payment_to = today.isoformat()
        payment_from = (today - timedelta(days=30)).isoformat()
    else:
        payment_from = payment_from_raw or ""
        payment_to = payment_to_raw or ""

    # Lọc theo ngày thanh toán (ưu tiên payment_date, fallback created_at nếu cần sau này)
    if payment_from:
        costs_qs = costs_qs.filter(payment_date__gte=payment_from)
    if payment_to:
        costs_qs = costs_qs.filter(payment_date__lte=payment_to)

    # Lọc theo loại chi phí (có thể chọn nhiều)
    if cost_type_filters:
        costs_qs = costs_qs.filter(cost_type__in=cost_type_filters)

    # Lọc theo người thanh toán
    if person_id_filter:
        try:
            pid = int(person_id_filter)
            costs_qs = costs_qs.filter(person_id=pid)
        except ValueError:
            pass

    # Tổng hợp theo filter hiện tại
    cost_summary = costs_qs.aggregate(
        total_amount=Sum('amount'),
        total_items=Count('id'),
    )

    # Nhóm theo loại chi phí (theo filter)
    cost_by_type = (
        costs_qs
        .values('cost_type')
        .annotate(
            total_amount=Sum('amount'),
            count=Count('id'),
        )
        .order_by('-total_amount')
    )

    # Danh sách chi phí (phân trang, mỗi trang 100 bản ghi, mới nhất trước)
    costs_qs = costs_qs.order_by('-payment_date', '-created_at')
    paginator = Paginator(costs_qs, 100)
    page_number = request.GET.get("page") or 1
    costs_page = paginator.get_page(page_number)

    # Options cho filter
    distinct_cost_types = (
        TicketCost.objects.values_list("cost_type", flat=True)
        .distinct()
        .order_by("cost_type")
    )
    from django.contrib.auth.models import User
    person_ids = (
        TicketCost.objects.exclude(person__isnull=True)
        .values_list("person_id", flat=True)
        .distinct()
    )
    persons = User.objects.filter(id__in=person_ids).order_by("first_name", "username")

    context = {
        'cost_summary': cost_summary,
        'cost_by_type': cost_by_type,
        'costs': costs_page,
        'page_obj': costs_page,
        'paginator': paginator,
        'filter_payment_from': payment_from,
        'filter_payment_to': payment_to,
        'filter_cost_types': cost_type_filters,
        'filter_person_id': person_id_filter,
        'cost_type_options': distinct_cost_types,
        'person_options': persons,
    }
    return render(request, 'cskh/tickets/cost_overview.html', context)


@group_required("CSKHManager", "CSKHStaff")
def ticket_compensation_overview(request):
    """
    Compensation Tracking – Tổng hợp hàng hỏng vỡ / rà soát lý do hỏng.
    """
    from django.db.models import Count

    damaged_costs = TicketCost.objects.filter(cost_type='Hàng hỏng vỡ')

    damaged_summary = damaged_costs.aggregate(
        total_amount=Sum('amount'),
        total_items=Count('id'),
    )

    # Tổng hợp theo ticket_type để xem loại ticket nào hay phát sinh hỏng vỡ
    damaged_by_ticket_type = (
        damaged_costs
        .values('ticket__ticket_type')
        .annotate(
            total_amount=Sum('amount'),
            count=Count('id'),
        )
        .order_by('-total_amount')
    )

    context = {
        'damaged_summary': damaged_summary,
        'damaged_by_ticket_type': damaged_by_ticket_type,
        'ticket_type_labels': dict(Ticket.TICKET_TYPE_CHOICES),
    }
    return render(request, 'cskh/tickets/compensation_overview.html', context)


@group_required("CSKHManager", "CSKHStaff")
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

    # Cấu hình ticket CSKH/Kho (nguồn lỗi, loại vấn đề, loại lỗi, hướng xử lý, loại chi phí, ...)
    ticket_config = CSKHTicketConfigService.get_config()

    # Loại vấn đề: gộp loại vấn đề CSKH + loại vấn đề kho (nếu có), loại bỏ trùng
    base_issue_types = (ticket_config.get('loai_van_de', []) or []) + (
        ticket_config.get('loai_van_de_kho', []) or []
    )
    issue_type_options = []
    for item in base_issue_types:
        if item and item not in issue_type_options:
            issue_type_options.append(item)

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
                    quantity = float(getattr(item, 'quantity', 0) or 0)
                    line_amount = float(getattr(item, 'line_amount', 0) or 0)
                    # Tính giá 1 sản phẩm = line_amount / quantity (vì có mã giảm giá)
                    unit_price = (line_amount / quantity) if quantity > 0 else 0
                    variants.append({
                        'variant_id': vid,
                        'product_name': item.product_name or '',
                        'variant_name': item.variant_name or '',
                        'sku': item.sku or '',
                        'price': unit_price,  # Giá 1 sản phẩm sau giảm giá
                        'line_amount': line_amount,  # Tổng giá trị dòng item
                        'quantity': quantity,
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
    
    # Nguồn lỗi: gộp nguồn lỗi CSKH + nguồn lỗi kho, loại bỏ trùng
    base_sources = (ticket_config.get('nguon_loi', []) or []) + (
        ticket_config.get('nguon_loi_kho', []) or []
    )
    reason_sources = []
    for item in base_sources:
        if item and item not in reason_sources:
            reason_sources.append(item)

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
        # Lý do, chi phí, hướng xử lý lấy từ cấu hình
        'issue_type_options': issue_type_options,
        'reason_sources': reason_sources,
        'cost_types': ticket_config.get('loai_chi_phi', []),
        'huong_xu_ly_list': ticket_config.get('huong_xu_ly', []),
        'status_choices': Ticket.STATUS_CHOICES,
        'ticket_type_choices': Ticket.TICKET_TYPE_CHOICES,
        'warehouse_name': warehouse_name,
    }
    return render(request, 'cskh/tickets/detail.html', context)


@group_required("CSKHManager", "CSKHStaff")
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
            ticket_type=request.POST.get('ticket_type', ''),
            ticket_status=request.POST.get('ticket_status', 'new'),
            source_ticket=request.POST.get('source_ticket', 'cskh_created'),
            depart=request.POST.get('depart', 'cskh'),
            source_reason=request.POST.get('source_reason', ''),
            reason_type=request.POST.get('reason_type', ''),
            note=note_text,
            images=uploaded_files,
            created_by=request.user,
            created_at=created_at if created_at else timezone.now(),
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
    ticket_config = CSKHTicketConfigService.get_config()

    # Các dropdown lấy trực tiếp từ file config CSKH, không hard-code:
    # - loai_van_de: dùng cho "Loại vấn đề"
    # - nguon_loi: dùng cho "Nguồn lỗi"
    # - loai_chi_phi: dùng cho "Loại chi phí"
    issue_type_options = ticket_config.get('loai_van_de', []) or []
    reason_sources = ticket_config.get('nguon_loi', []) or []
    cost_types = ticket_config.get('loai_chi_phi', []) or []

    context = {
        # Loại vấn đề, nguồn lỗi, loại chi phí lấy từ cấu hình CSKH
        'issue_type_options': issue_type_options,
        'reason_sources': reason_sources,
        'cost_types': cost_types,
        # Các trường khác vẫn dùng choices mặc định của model (nếu cần sau này có thể cấu hình thêm)
        'status_choices': Ticket.STATUS_CHOICES,
        'source_choices': Ticket.SOURCE_CHOICES,
    }
    return render(request, 'cskh/tickets/create.html', context)


# =======================
# WARRANTY VIEWS
# =======================

@group_required("CSKHManager", "CSKHStaff")
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


@group_required("CSKHManager", "CSKHStaff")
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


@group_required("CSKHManager", "CSKHStaff")
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

@group_required("CSKHManager", "CSKHStaff")
def feedback_overview(request):
    """
    Dashboard tổng quan Feedback Center - phân tích reviews, chỉ số đánh giá.
    """
    from core.system_settings import load_shopee_shops_detail
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    
    # Get time filter
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    today = datetime.now(tz_vn).date()
    
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    quick_range = request.GET.get('quick_range', '')
    shop_filter = request.GET.get('shop', '')  # Shop filter (connection_id hoặc 'all')
    
    # Apply quick range if specified
    if quick_range:
        if quick_range == 'today':
            date_from = today.strftime("%Y-%m-%d")
            date_to = today.strftime("%Y-%m-%d")
        elif quick_range == 'yesterday':
            yesterday = today - timedelta(days=1)
            date_from = yesterday.strftime("%Y-%m-%d")
            date_to = yesterday.strftime("%Y-%m-%d")
        elif quick_range == 'last_7d':
            date_from = (today - timedelta(days=7)).strftime("%Y-%m-%d")
            date_to = today.strftime("%Y-%m-%d")
        elif quick_range == 'last_30d':
            date_from = (today - timedelta(days=30)).strftime("%Y-%m-%d")
            date_to = today.strftime("%Y-%m-%d")
    
    # Base queryset with time filter
    base_queryset = Feedback.objects.all()
    if date_from and date_to:
        try:
            start_dt = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=tz_vn)
            end_dt = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=tz_vn)
            start_timestamp = int(start_dt.timestamp())
            end_timestamp = int(end_dt.timestamp())
            base_queryset = base_queryset.filter(create_time__gte=start_timestamp, create_time__lte=end_timestamp)
        except ValueError:
            pass
    
    # Apply shop filter
    if shop_filter and shop_filter != 'all':
        try:
            connection_id = int(shop_filter)
            base_queryset = base_queryset.filter(connection_id=connection_id)
        except ValueError:
            pass
    
    # Get all shops
    shops_detail = load_shopee_shops_detail()
    shop_names = list(shops_detail.keys())
    
    # Build shop filter options
    shop_filter_options = [{'name': 'Tất cả', 'connection_id': 'all', 'selected': shop_filter == '' or shop_filter == 'all'}]
    for shop_name, shop_info in shops_detail.items():
        connection_id = shop_info.get('shop_connect')
        if connection_id:
            shop_filter_options.append({
                'name': shop_name,
                'connection_id': str(connection_id),
                'selected': shop_filter == str(connection_id)
            })
    
    # Statistics
    total_feedbacks = base_queryset.count()
    good_reviews = base_queryset.filter(rating=5).count()
    bad_reviews = base_queryset.filter(rating__lte=4).count()
    unreplied = base_queryset.filter(Q(reply__isnull=True) | Q(reply="")).count()
    replied = base_queryset.exclude(Q(reply__isnull=True) | Q(reply="")).count()
    
    # Average rating
    avg_rating_result = base_queryset.aggregate(avg=Avg('rating'))
    avg_rating = avg_rating_result['avg'] or 0
    
    # Rating breakdown
    rating_breakdown = []
    for stars in [5, 4, 3, 2, 1]:
        count = base_queryset.filter(rating=stars).count()
        percentage = (count / total_feedbacks * 100) if total_feedbacks > 0 else 0
        rating_breakdown.append({
            'stars': stars,
            'count': count,
            'percentage': round(percentage, 1)
        })
    
    # Shop statistics (apply same filters as base_queryset)
    shop_stats = []
    for shop_name, shop_info in shops_detail.items():
        connection_id = shop_info.get('shop_connect')
        if connection_id:
            shop_feedbacks = base_queryset.filter(connection_id=connection_id)
            shop_total = shop_feedbacks.count()
            shop_good = shop_feedbacks.filter(rating=5).count()
            shop_bad = shop_feedbacks.filter(rating__lte=4).count()
            shop_avg_result = shop_feedbacks.aggregate(avg=Avg('rating'))
            shop_avg = shop_avg_result['avg'] or 0
            
            shop_stats.append({
                'name': shop_name,
                'connection_id': connection_id,
                'total': shop_total,
                'good': shop_good,
                'bad': shop_bad,
                'avg_rating': round(shop_avg, 2)
            })
    
    # Top bad products (sản phẩm bị đánh giá xấu nhiều nhất) - Group theo Sapo variants
    bad_feedbacks = base_queryset.filter(rating__lte=4, sapo_variant_id__isnull=False)
    top_bad_products_raw = list(bad_feedbacks.values(
        'sapo_variant_id', 'sapo_product_id', 'product_name'
    ).annotate(
        count=Count('id'),
        avg_rating=Avg('rating')
    ).order_by('-count')[:10])
    
    # Lấy SKU từ variants
    from core.sapo_client import get_sapo_client
    sapo_client = get_sapo_client()
    top_bad_products = []
    for item in top_bad_products_raw:
        variant_sku = ''
        if item['sapo_variant_id']:
            try:
                variant_data = sapo_client.core.get_variant_raw(item['sapo_variant_id'])
                if variant_data and variant_data.get('variant'):
                    variant_sku = variant_data['variant'].get('sku', '')
            except Exception:
                pass
        
        top_bad_products.append({
            'variant_id': item['sapo_variant_id'],
            'product_id': item['sapo_product_id'],
            'product_name': item['product_name'] or '(Chưa có tên)',
            'sku': variant_sku,
            'count': item['count'],
            'avg_rating': round(item['avg_rating'] or 0, 2)
        })
    
    # Product statistics (tất cả sản phẩm với đánh giá trung bình) - Group theo Sapo variants
    product_stats_raw = list(base_queryset.filter(sapo_variant_id__isnull=False).values(
        'sapo_variant_id', 'sapo_product_id', 'product_name'
    ).annotate(
        total_reviews=Count('id'),
        avg_rating=Avg('rating'),
        good_reviews=Count('id', filter=Q(rating=5)),
        bad_reviews=Count('id', filter=Q(rating__lte=4))
    ).order_by('-total_reviews')[:20])  # Top 20 variants có nhiều reviews nhất
    
    # Lấy SKU từ variants
    product_stats = []
    for item in product_stats_raw:
        variant_sku = ''
        if item['sapo_variant_id']:
            try:
                variant_data = sapo_client.core.get_variant_raw(item['sapo_variant_id'])
                if variant_data and variant_data.get('variant'):
                    variant_sku = variant_data['variant'].get('sku', '')
            except Exception:
                pass
        
        product_stats.append({
            'variant_id': item['sapo_variant_id'],
            'product_id': item['sapo_product_id'],
            'product_name': item['product_name'] or '(Chưa có tên)',
            'sku': variant_sku,
            'total_reviews': item['total_reviews'],
            'avg_rating': round(item['avg_rating'] or 0, 2),
            'good_reviews': item['good_reviews'],
            'bad_reviews': item['bad_reviews']
        })
    
    # Calculate percentages
    positive_percentage = (good_reviews / total_feedbacks * 100) if total_feedbacks > 0 else 0
    negative_percentage = (bad_reviews / total_feedbacks * 100) if total_feedbacks > 0 else 0
    replied_percentage = (replied / total_feedbacks * 100) if total_feedbacks > 0 else 0
    unreplied_percentage = (unreplied / total_feedbacks * 100) if total_feedbacks > 0 else 0
    
    context = {
        'metrics': {
            'total_reviews': total_feedbacks,
            'average_rating': round(avg_rating, 2),
            'positive_count': good_reviews,
            'positive_percentage': round(positive_percentage, 1),
            'negative_count': bad_reviews,
            'negative_percentage': round(negative_percentage, 1),
            'pending_response': unreplied,
            'pending_percentage': round(unreplied_percentage, 1),
            'replied': replied,
            'replied_percentage': round(replied_percentage, 1),
        },
        'rating_breakdown': rating_breakdown,
        'shop_stats': shop_stats,
        'top_bad_products': top_bad_products,
        'product_stats': product_stats,
        'shop_filter_options': shop_filter_options,
        'current_shop': shop_filter,
        'date_from': date_from,
        'date_to': date_to,
        'quick_range': quick_range,
    }
    return render(request, 'cskh/feedback/overview.html', context)


@group_required("CSKHManager", "CSKHStaff")
def feedback_list(request):
    """
    Danh sách feedbacks từ database (Feedback model).
    Lấy trực tiếp từ database thay vì từ Sapo API.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    # Get filters from request
    status_filter = request.GET.get('status', '')  # 'all', 'pending', 'replied'
    rating_filters = request.GET.getlist('rating')  # Multiple ratings can be selected
    search_query = request.GET.get('search', '').strip()
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Query feedbacks từ database
    feedbacks_query = Feedback.objects.all()
    
    # Apply filters
    # Search filter
    if search_query:
        feedbacks_query = feedbacks_query.filter(
            Q(channel_order_number__icontains=search_query) |
            Q(buyer_user_name__icontains=search_query) |
            Q(comment__icontains=search_query) |
            Q(product_name__icontains=search_query)
        )
    
    # Time filter
    if date_from and date_to:
        try:
            tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
            start_dt = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=tz_vn)
            end_dt = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=tz_vn)
            start_timestamp = int(start_dt.timestamp())
            end_timestamp = int(end_dt.timestamp())
            feedbacks_query = feedbacks_query.filter(
                create_time__gte=start_timestamp,
                create_time__lte=end_timestamp
            )
        except ValueError:
            pass
    
    # Status filter
    if status_filter == 'pending':
        feedbacks_query = feedbacks_query.filter(Q(reply__isnull=True) | Q(reply=""))
    elif status_filter == 'replied':
        feedbacks_query = feedbacks_query.exclude(Q(reply__isnull=True) | Q(reply=""))
    
    # Rating filter
    if rating_filters and 'all' not in rating_filters:
        try:
            ratings = [int(r) for r in rating_filters if r.isdigit()]
            if ratings:
                feedbacks_query = feedbacks_query.filter(rating__in=ratings)
        except ValueError:
            pass
    
    # Sort by create_time desc
    feedbacks_query = feedbacks_query.order_by('-create_time')
    
    # Get base query for counts (before pagination)
    base_query = Feedback.objects.all()
    if search_query:
        base_query = base_query.filter(
            Q(channel_order_number__icontains=search_query) |
            Q(buyer_user_name__icontains=search_query) |
            Q(comment__icontains=search_query) |
            Q(product_name__icontains=search_query)
        )
    if date_from and date_to:
        try:
            tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
            start_dt = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=tz_vn)
            end_dt = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=tz_vn)
            start_timestamp = int(start_dt.timestamp())
            end_timestamp = int(end_dt.timestamp())
            base_query = base_query.filter(
                create_time__gte=start_timestamp,
                create_time__lte=end_timestamp
            )
        except ValueError:
            pass
    
    # Calculate counts for filters
    all_count = base_query.count()
    pending_count = base_query.filter(Q(reply__isnull=True) | Q(reply="")).count()
    replied_count = base_query.exclude(Q(reply__isnull=True) | Q(reply="")).count()
    
    rating_counts = {}
    for rating in [5, 4, 3, 2, 1]:
        rating_counts[rating] = base_query.filter(rating=rating).count()
    
    # Pagination (50 feedbacks/page)
    DISPLAY_PER_PAGE = 50
    paginator = Paginator(feedbacks_query, DISPLAY_PER_PAGE)
    try:
        feedbacks_page = paginator.get_page(request.GET.get('page', 1))
    except:
        feedbacks_page = paginator.get_page(1)
    
    # Lấy SKU từ variant cho mỗi feedback - Load từ database cache một lần
    # Thu thập tất cả variant_ids cần thiết
    variant_ids = set()
    for feedback in feedbacks_page:
        variant_id = feedback.sapo_variant_id
        if variant_id:
            variant_ids.add(variant_id)
    
    # Load tất cả variants một lần từ database cache
    variant_cache = {}  # variant_id -> {"sku": "...", "name": "..."}
    if variant_ids:
        logger.debug(f"Loading {len(variant_ids)} variants from database cache for feedbacks")
        
        # Load từ database cache (SapoVariantCache)
        from products.models import SapoVariantCache
        cached_variants = SapoVariantCache.objects.filter(variant_id__in=variant_ids)
        
        for cache in cached_variants:
            try:
                variant_data = cache.data  # JSON field chứa variant data
                if variant_data:
                    variant_cache[cache.variant_id] = {
                        "sku": variant_data.get("sku", ""),
                        "name": variant_data.get("name", ""),
                        "opt1": variant_data.get("opt1", ""),
                    }
            except Exception as e:
                logger.debug(f"Error parsing variant cache {cache.variant_id}: {e}")
        
        logger.debug(f"Loaded {len(variant_cache)} variants from database cache")
    
    # Gắn SKU và opt1 vào feedbacks từ cache (sử dụng property hoặc annotation)
    for feedback in feedbacks_page:
        variant_id = feedback.sapo_variant_id
        if variant_id and variant_id in variant_cache:
            # Thêm variant_sku và variant_opt1 vào feedback object (temporary attribute)
            feedback.variant_sku = variant_cache[variant_id].get("sku", "")
            feedback.variant_opt1 = variant_cache[variant_id].get("opt1", "")
        else:
            feedback.variant_sku = ""
            feedback.variant_opt1 = ""
    
    context = {
        'feedbacks': feedbacks_page,  # Sử dụng trực tiếp Feedback objects
        'current_status': status_filter or 'all',
        'current_ratings': rating_filters if rating_filters else ['all'],
        'current_search': search_query,
        'current_date_from': date_from,
        'current_date_to': date_to,
        'total_count': feedbacks_query.count(),
        'filter_counts': {
            'all': all_count,
            'pending': pending_count,
            'replied': replied_count,
            'ratings': rating_counts,
        },
    }
    return render(request, 'cskh/feedback/list.html', context)


@group_required("CSKHManager", "CSKHStaff")
def feedback_sync_status(request):
    """
    Hiển thị trạng thái sync jobs.
    """
    from cskh.models import FeedbackSyncJob
    
    # Lấy các jobs gần nhất
    jobs = FeedbackSyncJob.objects.all()[:20]  # 20 jobs gần nhất
    
    # Thống kê
    stats = {
        'total_jobs': FeedbackSyncJob.objects.count(),
        'running_jobs': FeedbackSyncJob.objects.filter(status='running').count(),
        'completed_jobs': FeedbackSyncJob.objects.filter(status='completed').count(),
        'failed_jobs': FeedbackSyncJob.objects.filter(status='failed').count(),
        'pending_jobs': FeedbackSyncJob.objects.filter(status='pending').count(),
    }
    
    context = {
        'jobs': jobs,
        'stats': stats,
    }
    
    return render(request, 'cskh/feedback/sync_status.html', context)


# =======================
# ORDERS & PRODUCTS LOOKUP
# =======================

@group_required("CSKHManager", "CSKHStaff")
def orders_view(request):
    """Tra cứu đơn hàng"""
    context = {
        'search_placeholder': 'Nhập mã đơn hàng, SĐT, hoặc tên khách hàng...',
    }
    return render(request, 'cskh/lookup/orders.html', context)


@group_required("CSKHManager", "CSKHStaff")
def products_view(request):
    """Tra cứu sản phẩm"""
    context = {
        'search_placeholder': 'Nhập tên sản phẩm hoặc SKU...',
    }
    return render(request, 'cskh/lookup/products.html', context)

def order_list(request):
    return render(request, "kho/order_list.html")


@group_required("Admin")
def ticket_config(request):
    """
    Cấu hình các list cho hệ thống ticket CSKH:
    - Nguồn lỗi
    - Loại vấn đề
    - Loại lỗi
    - Trạng thái
    - Hướng xử lý
    - Loại chi phí
    Chỉ dành cho Admin.
    """
    config = CSKHTicketConfigService.get_config()

    if request.method == "POST":
        def parse_lines(name: str):
            raw = request.POST.get(name, "") or ""
            return [line.strip() for line in raw.splitlines() if line.strip()]

        new_config = {
            "nguon_loi": parse_lines("nguon_loi"),
            "loai_van_de": parse_lines("loai_van_de"),
            "loai_loi": parse_lines("loai_loi"),
            "trang_thai": parse_lines("trang_thai"),
            "huong_xu_ly": parse_lines("huong_xu_ly"),
            "loai_chi_phi": parse_lines("loai_chi_phi"),
            # Cấu hình riêng cho ticket kho
            "nguon_loi_kho": parse_lines("nguon_loi_kho"),
            "loai_loi_kho": parse_lines("loai_loi_kho"),
            "huong_xu_ly_kho": parse_lines("huong_xu_ly_kho"),
        }

        try:
            CSKHTicketConfigService.save_config(new_config)
            messages.success(request, "Đã lưu cấu hình ticket CSKH.")
            config = CSKHTicketConfigService.get_config()
        except Exception as e:
            messages.error(request, f"Lỗi khi lưu cấu hình: {e}")

    context = {
        "config": config,
        "nguon_loi_text": "\n".join(config.get("nguon_loi", [])),
        "loai_van_de_text": "\n".join(config.get("loai_van_de", [])),
        "loai_loi_text": "\n".join(config.get("loai_loi", [])),
        "trang_thai_text": "\n".join(config.get("trang_thai", [])),
        "huong_xu_ly_text": "\n".join(config.get("huong_xu_ly", [])),
        "loai_chi_phi_text": "\n".join(config.get("loai_chi_phi", [])),
        # Text cho cấu hình ticket kho
        "nguon_loi_kho_text": "\n".join(config.get("nguon_loi_kho", [])),
        "loai_loi_kho_text": "\n".join(config.get("loai_loi_kho", [])),
        "huong_xu_ly_kho_text": "\n".join(config.get("huong_xu_ly_kho", [])),
    }
    return render(request, "cskh/tickets/config.html", context)


# =======================
# TRAINING DOCUMENTS
# =======================


@group_required("CSKHManager", "CSKHStaff")
def training_list(request):
    """
    Danh sách tài liệu training nội bộ.
    - Toàn bộ CSKH (Staff + Manager + Admin) đều có quyền xem.
    - Chỉ Admin & CSKHManager mới được upload / reupload / delete.
    """
    from pathlib import Path
    from django.utils.text import slugify
    from datetime import datetime

    docs_qs = TrainingDocument.objects.all().order_by("title")

    # Quyền quản lý: Admin hoặc thuộc group CSKHManager
    can_manage = request.user.is_superuser or request.user.groups.filter(
        name__in=["Admin", "CSKHManager"]
    ).exists()

    if request.method == "POST" and can_manage:
        action = request.POST.get("action") or "create"
        title = (request.POST.get("title") or "").strip()
        doc_id = request.POST.get("doc_id")
        file_obj = request.FILES.get("file")

        # Thư mục lưu file markdown
        base_dir = Path("settings/logs/train_cskh")
        base_dir.mkdir(parents=True, exist_ok=True)

        if action == "delete" and doc_id:
            doc = get_object_or_404(TrainingDocument, id=doc_id)
            file_path = base_dir / doc.filename
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception as e:
                    logger.warning(f"Could not delete training file {file_path}: {e}")
            doc.delete()
            messages.success(request, "Đã xoá tài liệu training.")
            return redirect("cskh:training_list")

        if not title or not file_obj:
            messages.error(request, "Vui lòng nhập tên tài liệu và chọn file Markdown.")
            return redirect("cskh:training_list")

        # Re-upload: giữ lại record, chỉ thay file & metadata
        if action == "reupload" and doc_id:
            doc = get_object_or_404(TrainingDocument, id=doc_id)
            # Xoá file cũ nếu có
            old_path = base_dir / doc.filename
            if old_path.exists():
                try:
                    old_path.unlink()
                except Exception as e:
                    logger.warning(f"Could not delete old training file {old_path}: {e}")
            safe_slug = slugify(title) or "training-doc"
            ext = ".md"
            original_name = file_obj.name or ""
            if "." in original_name:
                ext = "." + original_name.split(".")[-1].lower()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_slug}_{timestamp}{ext}"
            new_path = base_dir / filename
            with open(new_path, "wb") as f:
                for chunk in file_obj.chunks():
                    f.write(chunk)
            doc.title = title
            doc.filename = filename
            doc.uploaded_by = request.user
            doc.uploaded_at = timezone.now()
            doc.save()
            messages.success(request, "Đã cập nhật (reupload) tài liệu training.")
            return redirect("cskh:training_list")

        # Tạo mới
        safe_slug = slugify(title) or "training-doc"
        ext = ".md"
        original_name = file_obj.name or ""
        if "." in original_name:
            ext = "." + original_name.split(".")[-1].lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_slug}_{timestamp}{ext}"
        file_path = base_dir / filename
        with open(file_path, "wb") as f:
            for chunk in file_obj.chunks():
                f.write(chunk)

        TrainingDocument.objects.create(
            title=title,
            filename=filename,
            uploaded_by=request.user,
            uploaded_at=timezone.now(),
        )
        messages.success(request, "Đã thêm tài liệu training mới.")
        return redirect("cskh:training_list")

    # Chuẩn hoá dữ liệu hiển thị: tách thư mục (category) và tên tài liệu bằng dấu "###"
    def build_doc_meta(doc: TrainingDocument):
        raw_title = (doc.title or "").strip()
        category = ""
        display_title = raw_title or "(Không có tiêu đề)"

        if "###" in raw_title:
            cat, name = raw_title.split("###", 1)
            category = cat.strip()
            display_title = (name or "").strip() or category or display_title

        # Gán màu theo category (cùng category => cùng màu)
        cat_upper = category.upper()
        if cat_upper.startswith("QUY ĐỊNH"):
            color_classes = "bg-red-100 text-red-800 border-red-200"
        elif cat_upper.startswith("QUY TRÌNH"):
            color_classes = "bg-blue-100 text-blue-800 border-blue-200"
        elif cat_upper.startswith("HƯỚNG DẪN"):
            color_classes = "bg-emerald-100 text-emerald-800 border-emerald-200"
        else:
            color_classes = "bg-slate-100 text-slate-700 border-slate-200"

        return {
            "id": doc.id,
            "category": category,
            "display_title": display_title,
            "uploaded_by": doc.uploaded_by,
            "uploaded_at": doc.uploaded_at,
            "category_color_classes": color_classes,
        }

    docs_meta = [build_doc_meta(d) for d in docs_qs]

    # Sort để cùng category đứng gần nhau, sau đó sort theo tên hiển thị
    docs_meta.sort(
        key=lambda d: (
            (d["category"] or "ZZZ").upper(),
            d["display_title"].upper(),
        )
    )

    context = {
        "documents": docs_meta,
        "can_manage": can_manage,
    }
    return render(request, "cskh/train/training_list.html", context)


@group_required("CSKHManager", "CSKHStaff")
def training_detail(request, doc_id: int):
    """
    Xem nội dung tài liệu training dưới dạng HTML.
    """
    from pathlib import Path

    doc = get_object_or_404(TrainingDocument, id=doc_id)
    base_dir = Path("settings/logs/train_cskh")
    file_path = base_dir / doc.filename

    if not file_path.exists():
        raise Http404("Tài liệu không tồn tại trên hệ thống.")

    try:
        raw_content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not read training file {file_path}: {e}")
        raise Http404("Không thể đọc nội dung tài liệu.")

    # Render Markdown -> HTML
    from django.utils.html import escape

    html_content = None
    try:
        import markdown  # type: ignore
    except ImportError:
        # Fallback đơn giản: convert xuống HTML cơ bản (không cần thư viện ngoài)
        paragraphs = []
        for block in raw_content.split("\n\n"):
            if not block.strip():
                continue
            # Giữ xuống dòng trong cùng block
            escaped = escape(block).replace("\n", "<br>")
            paragraphs.append(f"<p>{escaped}</p>")
        html_content = "\n".join(paragraphs) or "<p></p>"
    else:
        # Dùng thư viện markdown nếu có
        html_content = markdown.markdown(
            raw_content,
            extensions=["fenced_code", "tables"],
            output_format="html5",
        )

    context = {
        "document": doc,
        "content_html": html_content,
    }
    return render(request, "cskh/train/training_detail.html", context)


# =======================
# VALUE CENTER - CUSTOMERS
# =======================

@group_required("CSKHManager", "CSKHStaff")
def customer_l1_list(request):
    """
    VALUE CENTER – Khách hàng L1

    Yêu cầu:
    - Mỗi trang UI: 20 khách hàng (page=1: 1–20, page=2: 21–40, ...)
    - Server fetch theo block 100 khách thỏa điều kiện:
        + Lần đầu (page 1): tìm 100 khách phù hợp rồi cache.
        + Khi user sang page 11 (khách 201–220): nếu cache < 220, tìm tiếp 100 khách tiếp theo và append vào cache.
    - Cache lưu ở: settings/logs/l1_customer.json
        {
          "meta": {
             "last_sapo_page": int,
             "total_customers_api": int,
             "total_api_pages": int
          },
          "customers": [ ... khách đã lọc ... ]
        }
    """
    from pathlib import Path
    from django.core.paginator import Paginator
    from django.utils.text import slugify
    from core.sapo_client import get_sapo_client
    from core.sapo_client.client import debug_print
    from django.utils import timezone
    from datetime import datetime
    from math import ceil

    # 1. Đọc page từ request (UI)
    page_str = request.GET.get("page", "1")
    try:
        page_number = int(page_str)
    except (ValueError, TypeError):
        page_number = 1
    if page_number < 1:
        page_number = 1

    DISPLAY_PER_PAGE = 20  # 20 khách / trang UI
    # Kể từ REPORT_KHO.md: khi lọc theo quận phải luôn chạy full toàn bộ dữ liệu của quận đó (không dùng page_now nữa)
    MAX_SAPO_PAGE = 400    # Giới hạn tối đa request tới Sapo API

    # City filter gửi trực tiếp lên Sapo API (filterType=advanced)
    SAPO_CITY_FILTER = "TP Hồ Chí Minh,TP. Hồ Chí Minh"

    # Danh sách quận/huyện có thể chọn (theo URL advanced filter của Sapo)
    DISTRICT_CHOICES = [
        "Quận 1", "Quận 2", "Quận 3", "Quận 4", "Quận 5", "Quận 6", "Quận 7", "Quận 8", "Quận 9",
        "Quận 10", "Quận 11", "Quận 12", "Quận Gò Vấp", "Quận Tân Bình", "Quận Tân Phú",
        "Quận Bình Thạnh", "Quận Phú Nhuận", "Quận Thủ Đức", "Quận Bình Tân",
        "Huyện Củ Chi", "Huyện Hóc Môn", "Huyện Bình Chánh", "Huyện Nhà Bè", "Huyện Cần Giờ",
        "Thành phố Thủ Đức",
    ]
    DEFAULT_DISTRICT = "Quận 12"

    # 2. Đọc district từ request (mặc định Quận 12) và chuẩn hóa
    district = request.GET.get("district") or DEFAULT_DISTRICT
    if district not in DISTRICT_CHOICES:
        district = DEFAULT_DISTRICT

    # 3. Đường dẫn file cache DUY NHẤT cho toàn bộ khách L1 (mọi quận)
    #    Bên trong JSON sẽ phân biệt meta theo từng quận bằng key slug (vd: quan-1, quan-12, ...)
    cache_path = Path("settings/logs/l1_customer.json")
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    # File log tổng – lưu tất cả customers đã request (mọi quận) vào một file duy nhất
    log_dir = Path("settings/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "l1_customer_log.jsonl"

    # 4. Load cache nếu có
    cache_data = {"meta": {}, "customers": []}
    if cache_path.exists():
        try:
            raw_text = cache_path.read_text(encoding="utf-8")
            if raw_text.strip():
                cache_data = json.loads(raw_text)
        except Exception as e:
            logger.warning(f"[Customer L1] Could not read cache file: {e}")
            cache_data = {"meta": {}, "customers": []}

    # meta_all: chứa cấu trúc meta cho tất cả quận
    # meta_all = {
    #   "districts": {
    #       "quan-1": { ... meta riêng cho Quận 1 ... },
    #       "quan-12": { ... meta riêng cho Quận 12 ... },
    #       ...
    #   }
    # }
    cache_slug = slugify(district) or "all"
    meta_all = cache_data.get("meta") or {}
    districts_meta = meta_all.get("districts") or {}
    meta = districts_meta.get(cache_slug) or {}
    cached_customers = cache_data.get("customers") or []

    last_sapo_page = int(meta.get("last_sapo_page") or 0)
    total_customers_api = meta.get("total_customers_api")
    total_api_pages = meta.get("total_api_pages")

    # Lọc lại cached_customers theo district đang chọn (an toàn nếu file cache cũ có lẫn dữ liệu)
    def customer_match_district(cust: dict, district_name: str) -> bool:
        addresses = cust.get("addresses") or []
        if not addresses:
            return False
        for address in addresses:
            city = (address.get("city") or "").strip()
            d_name = (address.get("district") or "").strip()
            if ("Hồ Chí Minh" in city or "TP. Hồ Chí Minh" in city) and d_name == district_name:
                return True
        return False

    filtered_cached_customers = [
        c for c in cached_customers if customer_match_district(c, district)
    ]

    debug_print(
        f"[Customer L1] UI page={page_number}, cached_raw={len(cached_customers)}, "
        f"cached_filtered={len(filtered_cached_customers)}, last_sapo_page={last_sapo_page}"
    )

    # 5. Hàm filter & build khách từ raw Sapo JSON
    def build_customer_from_raw(customer: dict):
        """Trả về dict customer đã lọc theo điều kiện, hoặc None nếu không đạt."""
        # Điều kiện name: phải có, KHÔNG chứa '*'
        raw_name = customer.get("name", "")
        name = raw_name.strip() if raw_name else ""
        if not name or "*" in name:
            return None

        # phone_number bắt buộc
        phone_number = customer.get("phone_number", "") or ""
        phone_number = phone_number.strip()
        if not phone_number:
            return None

        # Địa chỉ: city phải là HCM và quận/huyện trùng với district đang chọn
        addresses = customer.get("addresses") or []
        if not addresses:
            return None

        has_valid_address = False
        for address in addresses:
            city = (address.get("city") or "").strip()
            district_name = (address.get("district") or "").strip()

            # City phải là HCM
            if "Hồ Chí Minh" not in city and "TP. Hồ Chí Minh" not in city:
                continue
            # Quận/huyện phải trùng đúng với district đang chọn trên UI
            if district_name != district:
                continue

            has_valid_address = True
            break
        if not has_valid_address:
            return None

        # Xử lý sale_order (nếu có)
        raw_sale_order = customer.get("sale_order") or {}
        sale_order = None
        if isinstance(raw_sale_order, dict) and raw_sale_order:
            total_sales = raw_sale_order.get("total_sales") or 0
            order_purchases = raw_sale_order.get("order_purchases") or 0
            last_order_on = raw_sale_order.get("last_order_on")
            days_ago = None
            if last_order_on:
                try:
                    ts = last_order_on
                    if isinstance(ts, str):
                        if ts.endswith("Z"):
                            ts = ts.replace("Z", "+00:00")
                        dt = datetime.fromisoformat(ts)
                    else:
                        dt = ts
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt)
                    days_ago = (timezone.now().date() - dt.date()).days
                except Exception:
                    days_ago = None
            sale_order = {
                "total_sales": total_sales,
                "order_purchases": order_purchases,
                "last_order_days": days_ago,
            }

        return {
            "id": customer.get("id"),
            "code": customer.get("code", ""),
            "name": name,
            "phone_number": phone_number,
            "email": customer.get("email", "") or "",
            "addresses": addresses,
            "sale_order": sale_order,
            "customer_group": customer.get("customer_group", {}),
            "status": customer.get("status", ""),
        }

    # 6. Nếu cache chưa full cho quận hiện tại thì fetch FULL tất cả pages từ Sapo
    try:
        sapo_client = None

        # Kể từ REPORT_KHO.md: nếu cache chưa được đánh dấu full thì bỏ cache cũ và fetch toàn bộ pages cho quận hiện tại
        is_full = bool(meta.get("is_full"))
        if not cached_customers or not is_full:
            debug_print(f"[Customer L1] Cache for district '{district}' is not full. Fetching ALL pages from Sapo...")

            # Reset meta cũ của QUẬN HIỆN TẠI; danh sách customers dùng chung cho mọi quận
            last_sapo_page = 0
            total_customers_api = None
            total_api_pages = None

            if sapo_client is None:
                sapo_client = get_sapo_client()

            # Mở file log tổng (nếu lỗi thì chỉ log warning, không chặn luồng chính)
            log_handle = None
            try:
                log_handle = open(log_file, "a", encoding="utf-8")
            except Exception as e:
                logger.warning(f"[Customer L1] Could not open log file {log_file}: {e}")

            def append_to_log(customers_block):
                if not log_handle:
                    return
                for cust in customers_block:
                    try:
                        log_handle.write(json.dumps(cust, ensure_ascii=False) + "\n")
                    except Exception:
                        # Không để lỗi ghi log ảnh hưởng tới request chính
                        continue

            # --- Fetch page 1 để lấy metadata.total (sử dụng customers/doSearch.json + condition_type=must) ---
            try:
                raw_page1 = sapo_client.core.search_customers_do_search_raw(
                    page=1,
                    limit=250,
                    **{
                        "city.in": SAPO_CITY_FILTER,
                        "district.in": district,
                        "filterType": "advanced",
                        "condition_type": "must",
                    },
                )
            except Exception as ex:
                if log_handle:
                    log_handle.close()
                raise

            customers_page1 = raw_page1.get("customers") or []
            md = raw_page1.get("metadata") or {}
            total_customers_api = md.get("total") or 0

            if total_customers_api:
                total_api_pages = min(ceil(int(total_customers_api) / 250), MAX_SAPO_PAGE)
            else:
                total_api_pages = 1

            debug_print(
                f"[Customer L1] District={district} total_customers_api={total_customers_api}, "
                f"total_api_pages={total_api_pages}"
            )

            new_block_page1: list[dict] = []
            for cust in customers_page1:
                built = build_customer_from_raw(cust)
                if built:
                    new_block_page1.append(built)

            # Thêm vào cache chung, tránh trùng theo ID
            existing_ids = {c.get("id") for c in cached_customers}
            for c in new_block_page1:
                if c.get("id") not in existing_ids:
                    cached_customers.append(c)
                    existing_ids.add(c.get("id"))
            last_sapo_page = 1
            append_to_log(new_block_page1)

            # --- Fetch các page còn lại (2..total_api_pages) song song ---
            if total_api_pages and total_api_pages > 1:
                from threading import Thread, Lock
                results_lock = Lock()
                page_results: dict[int, list[dict]] = {}

                def fetch_page(p: int):
                    try:
                        client = get_sapo_client()
                        raw = client.core.search_customers_do_search_raw(
                            page=p,
                            limit=250,
                            **{
                                "city.in": SAPO_CITY_FILTER,
                                "district.in": district,
                                "filterType": "advanced",
                                "condition_type": "must",
                            },
                        )
                        raw_customers = raw.get("customers") or []

                        new_block: list[dict] = []
                        for cust in raw_customers:
                            built = build_customer_from_raw(cust)
                            if built:
                                new_block.append(built)

                        debug_print(
                            f"[Customer L1] Sapo page {p}: {len(raw_customers)} customers, "
                            f"{len(new_block)} matched (district={district})"
                        )

                        with results_lock:
                            page_results[p] = new_block
                    except Exception as ex:
                        logger.error(f"[Customer L1] Error fetching Sapo page {p}: {ex}", exc_info=True)

                pages_to_fetch = list(range(2, int(total_api_pages) + 1))
                threads = []
                for p in pages_to_fetch:
                    t = Thread(target=fetch_page, args=(p,))
                    t.daemon = True
                    t.start()
                    threads.append(t)

                for t in threads:
                    t.join(timeout=60)

                # Append kết quả theo thứ tự page, tránh trùng ID trong cache chung
                existing_ids = {c.get("id") for c in cached_customers}
                for p in sorted(page_results.keys()):
                    block = page_results[p]
                    for c in block:
                        if c.get("id") not in existing_ids:
                            cached_customers.append(c)
                            existing_ids.add(c.get("id"))
                    append_to_log(block)
                    last_sapo_page = max(last_sapo_page, p)

            # Đóng file log nếu đang mở
            if log_handle:
                try:
                    log_handle.close()
                except Exception:
                    pass

            # Sau khi fetch full, cập nhật lại meta cho QUẬN HIỆN TẠI & filtered_cached_customers
            meta = {
                "last_sapo_page": last_sapo_page,
                "total_customers_api": total_customers_api,
                "total_api_pages": total_api_pages,
                "total_customers_filtered": len(cached_customers),
                "is_full": True,
            }
            districts_meta[cache_slug] = meta
            meta_all["districts"] = districts_meta
            cache_data = {
                "meta": meta_all,
                "customers": cached_customers,
            }
            try:
                cache_path.write_text(json.dumps(cache_data, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                logger.warning(f"[Customer L1] Could not write cache file: {e}")

            # Rebuild filtered list theo quận từ cache mới
            filtered_cached_customers = [
                c for c in cached_customers if customer_match_district(c, district)
            ]

        # 7. Phân trang trên danh sách cached_customers đã lọc theo district
        paginator = Paginator(filtered_cached_customers, DISPLAY_PER_PAGE)
        try:
            page_obj = paginator.get_page(page_number)
        except Exception:
            page_obj = paginator.get_page(1)
            page_number = 1

        context = {
            "customers": page_obj,
            "page_obj": page_obj,
            "total_count": len(filtered_cached_customers),
            "total_api": total_customers_api,
            "current_page": page_number,
            "total_pages": paginator.num_pages,
            "has_previous": page_obj.has_previous(),
            "has_next": page_obj.has_next(),
            "previous_page_number": page_obj.previous_page_number() if page_obj.has_previous() else None,
            "next_page_number": page_obj.next_page_number() if page_obj.has_next() else None,
            "current_district": district,
            "district_choices": DISTRICT_CHOICES,
        }
        return render(request, "cskh/customers/l1_list.html", context)

    except Exception as e:
        logger.error(f"[Customer L1] Error loading customers L1: {e}", exc_info=True)
        messages.error(request, f"Lỗi khi tải danh sách khách hàng: {str(e)}")

        # Fallback: trả về trang rỗng nhưng không crash
        paginator = Paginator([], DISPLAY_PER_PAGE)
        page_obj = paginator.get_page(1)

        context = {
            "customers": page_obj,
            "page_obj": page_obj,
            "total_count": 0,
            "total_api": 0,
            "current_page": 1,
            "total_pages": 1,
            "has_previous": False,
            "has_next": False,
            "previous_page_number": None,
            "next_page_number": None,
            "current_district": DEFAULT_DISTRICT,
            "district_choices": DISTRICT_CHOICES,
            "error": str(e),
        }
        return render(request, "cskh/customers/l1_list.html", context)
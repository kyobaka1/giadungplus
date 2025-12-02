# cskh/views.py
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from cskh.utils import group_required
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q, Count, Sum, Avg, F, ExpressionWrapper, DurationField
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.urls import reverse

from .models import Ticket, TicketCost, TicketEvent, TicketView, Feedback, FeedbackLog
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
    
    # Bộ lọc lồng nhau (AND): loại ticket, bộ phận xử lý, trạng thái
    ticket_type_filter = request.GET.get('ticket_type', '')
    depart_filter = request.GET.get('depart', '')
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

    # Cấu hình ticket CSKH (nguồn lỗi, hướng xử lý, loại chi phí, ...)
    ticket_config = CSKHTicketConfigService.get_config()

    # Các dropdown lấy từ config
    issue_type_options = ticket_config.get('loai_van_de', []) or []

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
        'sugget_process': sugget_process,
        # Lý do, chi phí, hướng xử lý lấy từ cấu hình CSKH
        'issue_type_options': issue_type_options,
        'reason_sources': ticket_config.get('nguon_loi', []),
        'cost_types': ticket_config.get('loai_chi_phi', []),
        'huong_xu_ly_list': ticket_config.get('huong_xu_ly', []),
        'status_choices': Ticket.STATUS_CHOICES,
        'ticket_type_choices': Ticket.TICKET_TYPE_CHOICES,
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
    Danh sách feedbacks với filters: status, rating, search, time range.
    Pagination: 100 items/page.
    """
    from core.system_settings import load_shopee_shops_detail
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    
    # Get filters from request
    status_filter = request.GET.get('status', '')  # 'all', 'pending', 'replied'
    rating_filters = request.GET.getlist('rating')  # Multiple ratings can be selected
    search_query = request.GET.get('search', '').strip()
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    page_num = request.GET.get('page', 1)
    
    # Base queryset
    base_queryset = Feedback.objects.all()
    
    # Apply search filter
    if search_query:
        base_queryset = base_queryset.filter(
            Q(product_name__icontains=search_query) |
            Q(channel_order_number__icontains=search_query) |
            Q(buyer_user_name__icontains=search_query) |
            Q(comment__icontains=search_query)
        )
    
    # Apply time filter
    if date_from and date_to:
        try:
            tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
            start_dt = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=tz_vn)
            end_dt = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=tz_vn)
            start_timestamp = int(start_dt.timestamp())
            end_timestamp = int(end_dt.timestamp())
            base_queryset = base_queryset.filter(create_time__gte=start_timestamp, create_time__lte=end_timestamp)
        except ValueError:
            pass
    
    # Apply status filter
    filtered_queryset = base_queryset
    if status_filter == 'pending':
        filtered_queryset = filtered_queryset.filter(Q(reply__isnull=True) | Q(reply=""))
    elif status_filter == 'replied':
        filtered_queryset = filtered_queryset.exclude(Q(reply__isnull=True) | Q(reply=""))
    
    # Apply rating filters (multiple can be selected)
    if rating_filters and 'all' not in rating_filters:
        try:
            ratings = [int(r) for r in rating_filters if r.isdigit()]
            if ratings:
                filtered_queryset = filtered_queryset.filter(rating__in=ratings)
        except ValueError:
            pass
    
    # Calculate counts for filters (before applying rating filter for display)
    all_count = base_queryset.count()
    pending_count = base_queryset.filter(Q(reply__isnull=True) | Q(reply="")).count()
    replied_count = base_queryset.exclude(Q(reply__isnull=True) | Q(reply="")).count()
    
    rating_counts = {}
    for rating in [5, 4, 3, 2, 1]:
        rating_counts[rating] = base_queryset.filter(rating=rating).count()
    
    # Order by create_time desc
    filtered_queryset = filtered_queryset.order_by('-create_time')
    
    # Pagination - giảm số items/page để hiển thị trong 1 màn hình
    paginator = Paginator(filtered_queryset, 20)  # Giảm từ 100 xuống 20
    try:
        page = paginator.get_page(page_num)
    except:
        page = paginator.get_page(1)
    
    # Lấy SKU từ variant cho mỗi feedback và gán vào feedback object
    from core.sapo_client import get_sapo_client
    sapo_client = get_sapo_client()
    
    for feedback in page:
        feedback.variant_sku = ''
        if feedback.sapo_variant_id:
            try:
                variant_data = sapo_client.core.get_variant_raw(feedback.sapo_variant_id)
                if variant_data and variant_data.get('variant'):
                    feedback.variant_sku = variant_data['variant'].get('sku', '')
            except Exception as e:
                logger.debug(f"Error getting variant SKU for feedback {feedback.id}: {e}")
    
    context = {
        'feedbacks': page,
        'current_status': status_filter or 'all',
        'current_ratings': rating_filters if rating_filters else ['all'],
        'current_search': search_query,
        'current_date_from': date_from,
        'current_date_to': date_to,
        'total_count': paginator.count,
        'filter_counts': {
            'all': all_count,
            'pending': pending_count,
            'replied': replied_count,
            'ratings': rating_counts,
        },
    }
    return render(request, 'cskh/feedback/list.html', context)


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
    }
    return render(request, "cskh/tickets/config.html", context)

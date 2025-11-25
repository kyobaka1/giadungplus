# kho/views.py
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

# =======================
# DASHBOARD
# =======================

@login_required
def dashboard(request):
    """Dashboard tổng quan CSKH"""
    context = {
        'ticket_stats': {
            'new': 12,
            'processing': 8,
            'overdue': 3,
            'total': 23,
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
    context = {
        'metrics': {
            'unprocessed': 12,
            'overdue_sla': 3,
            'processing': 8,
            'completed_today': 15,
        },
        'category_breakdown': [
            {'name': 'Đổi trả hàng', 'count': 45, 'percentage': 35},
            {'name': 'Khiếu nại chất lượng', 'count': 30, 'percentage': 23},
            {'name': 'Hỗ trợ kỹ thuật', 'count': 25, 'percentage': 19},
            {'name': 'Bảo hành', 'count': 20, 'percentage': 15},
            {'name': 'Khác', 'count': 10, 'percentage': 8},
        ]
    }
    return render(request, 'cskh/tickets/overview.html', context)


@login_required
def ticket_list(request):
    """Danh sách tickets"""
    # Mock data
    tickets = [
        {
            'id': 1,
            'code': 'TK001',
            'category': 'Đổi trả hàng',
            'order_code': 'GDP001234',
            'title': 'Yêu cầu đổi sản phẩm bị lỗi',
            'customer_name': 'Nguyễn Văn A',
            'priority': 'high',
            'status': 'new',
            'assignee': 'Trần Thị B',
            'created_at': '2025-11-24 10:30',
        },
        {
            'id': 2,
            'code': 'TK002',
            'category': 'Hỗ trợ kỹ thuật',
            'order_code': 'GDP001235',
            'title': 'Hướng dẫn sử dụng nồi chiên',
            'customer_name': 'Lê Thị C',
            'priority': 'medium',
            'status': 'processing',
            'assignee': 'Phạm Văn D',
            'created_at': '2025-11-24 09:15',
        },
        {
            'id': 3,
            'code': 'TK003',
            'category': 'Khiếu nại chất lượng',
            'order_code': 'GDP001236',
            'title': 'Sản phẩm không đúng mô tả',
            'customer_name': 'Hoàng Văn E',
            'priority': 'high',
            'status': 'overdue',
            'assignee': 'Trần Thị B',
            'created_at': '2025-11-23 14:20',
        },
    ]
    
    context = {
        'tickets': tickets,
        'total_count': len(tickets),
    }
    return render(request, 'cskh/tickets/list.html', context)


@login_required
def ticket_detail(request, ticket_id):
    """Chi tiết ticket"""
    # Mock data
    ticket = {
        'id': ticket_id,
        'code': f'TK{ticket_id:03d}',
        'category': 'Đổi trả hàng',
        'order_code': 'GDP001234',
        'title': 'Yêu cầu đổi sản phẩm bị lỗi',
        'description': 'Khách hàng nhận được sản phẩm bị trầy xước, yêu cầu đổi mới.',
        'customer_name': 'Nguyễn Văn A',
        'customer_phone': '0901234567',
        'customer_email': 'nguyenvana@email.com',
        'priority': 'high',
        'status': 'new',
        'assignee': 'Trần Thị B',
        'created_at': '2025-11-24 10:30',
        'updated_at': '2025-11-24 10:30',
        'attachments': [],
        'comments': [
            {
                'user': 'Trần Thị B',
                'content': 'Đã liên hệ khách hàng, đang chờ xác nhận.',
                'created_at': '2025-11-24 11:00',
            }
        ]
    }
    
    context = {'ticket': ticket}
    return render(request, 'cskh/tickets/detail.html', context)


@login_required
def ticket_create(request):
    """Tạo ticket mới"""
    if request.method == 'POST':
        # TODO: Xử lý tạo ticket
        return redirect('cskh:ticket_list')
    
    context = {
        'categories': ['Đổi trả hàng', 'Khiếu nại chất lượng', 'Hỗ trợ kỹ thuật', 'Bảo hành', 'Khác'],
        'priorities': ['low', 'medium', 'high', 'urgent'],
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

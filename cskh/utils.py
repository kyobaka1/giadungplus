# cskh/utils.py
"""
Utilities cho app CSKH, bao gồm decorators phân quyền và logging.
"""

import json
import logging
from django.shortcuts import redirect
from functools import wraps
from django.utils import timezone

logger = logging.getLogger(__name__)

def is_admin_or_group(user, *group_names):
    """
    Kiểm tra user có phải là Admin (superuser hoặc group Admin) hoặc thuộc một trong các groups.
    """
    if not user.is_authenticated:
        return False
    # Admin = superuser hoặc có group "Admin"
    if user.is_superuser or user.groups.filter(name="Admin").exists():
        return True
    # Kiểm tra các groups khác
    if group_names:
        return user.groups.filter(name__in=group_names).exists()
    return False

def group_required(*group_names):
    """
    Decorator yêu cầu user phải là Admin hoặc thuộc một trong các groups được chỉ định.
    Nếu không có quyền, redirect về trang thông báo.
    
    Lưu ý: WarehouseManager luôn có quyền với ticket vì kho cũng phải làm việc với ticket.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            # WarehouseManager luôn có quyền với ticket
            allowed_groups = list(group_names) + ["WarehouseManager"]
            if is_admin_or_group(request.user, *allowed_groups):
                return view_func(request, *args, **kwargs)
            else:
                # Redirect về trang thông báo không có quyền
                return redirect('permission_denied')
        return wrapped_view
    return decorator

def log_ticket_action(ticket_number, username, action, data=None):
    """
    Ghi log một hành động liên quan đến ticket.
    
    Args:
        ticket_number: Mã ticket
        username: Tên người dùng thực hiện hành động
        action: Loại hành động (created, updated, etc.)
        data: Dữ liệu bổ sung (dict)
    """
    log_entry = {
        'ticket_number': ticket_number,
        'username': username,
        'action': action,
        'data': data or {},
        'timestamp': timezone.now().isoformat(),
    }
    logger.info(f"Ticket Action: {json.dumps(log_entry, ensure_ascii=False)}")

def get_ticket_logs(ticket_number):
    """
    Lấy danh sách logs của ticket.
    Hiện tại trả về danh sách rỗng vì logs được lưu trong TicketEvent model.
    Có thể mở rộng sau để đọc từ file log hoặc database.
    
    Args:
        ticket_number: Mã ticket
        
    Returns:
        List các log entries
    """
    # Hiện tại trả về danh sách rỗng
    # Có thể mở rộng sau để đọc từ TicketEvent hoặc file log
    return []

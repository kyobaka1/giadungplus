# cskh/utils.py
"""
Utilities cho app CSKH, bao gồm decorators phân quyền và logging.
"""

import json
import logging
from django.shortcuts import redirect
from functools import wraps
from django.utils import timezone
from pathlib import Path

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
        'user': username,  # Thêm field 'user' để tương thích với get_ticket_logs
        'action': action,
        'data': data or {},
        'details': data or {},  # Thêm field 'details' để tương thích
        'timestamp': timezone.now().isoformat(),
    }
    
    # Ghi vào logger
    logger.info(f"Ticket Action: {json.dumps(log_entry, ensure_ascii=False)}")
    
    # Ghi trực tiếp vào file log
    try:
        logs_dir = Path('settings/logs/ticket_actions')
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / f"{ticket_number}.log"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.warning(f"Could not write ticket log to file for {ticket_number}: {e}")

def get_ticket_logs(ticket_number):
    """
    Lấy danh sách logs của ticket.
    Đọc từ file log JSON line-based trong thư mục settings/logs/ticket_actions.
    
    Args:
        ticket_number: Mã ticket
        
    Returns:
        List các log entries
    """
    logs_dir = Path('settings/logs/ticket_actions')
    log_file = logs_dir / f"{ticket_number}.log"

    if not log_file.exists():
        return []

    entries = []

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except Exception:
                    continue

                # Chuẩn hoá các field cơ bản
                timestamp = raw.get('timestamp') or raw.get('time') or ''
                user = raw.get('user') or raw.get('username') or 'System'
                action = raw.get('action') or ''

                # Chi tiết có thể nằm trong "details" hoặc "data"
                raw_details = raw.get('details')
                if raw_details is None:
                    raw_details = raw.get('data', {})

                details_str = ''
                if isinstance(raw_details, dict):
                    # Trường hợp đặc biệt: chỉ có old/new -> hiển thị tóm tắt thay đổi
                    if set(raw_details.keys()) == {'old', 'new'}:
                        old_val = raw_details.get('old')
                        new_val = raw_details.get('new')
                        details_str = f"{old_val} → {new_val}"
                    else:
                        # Lấy các cặp key=value đơn giản (bỏ qua dict/list lồng nhau)
                        parts = []
                        for k, v in raw_details.items():
                            if isinstance(v, (dict, list)):
                                continue
                            parts.append(f"{k}: {v}")
                        details_str = ', '.join(parts)
                elif raw_details is not None:
                    details_str = str(raw_details)

                # Format time để hiển thị đẹp trong template
                formatted_time = ''
                if timestamp:
                    try:
                        ts_str = timestamp
                        if ts_str.endswith('Z'):
                            ts_str = ts_str.replace('Z', '+00:00')
                        from datetime import datetime
                        dt = datetime.fromisoformat(ts_str)
                        formatted_time = dt.strftime('%d/%m/%Y %H:%M')
                    except Exception:
                        formatted_time = timestamp

                entries.append({
                    'user': user,
                    'timestamp': timestamp,
                    'formatted_time': formatted_time,
                    'action': action,
                    'details': details_str,
                })
    except Exception as e:
        logger.warning(f"Could not read ticket logs for {ticket_number}: {e}")

    return entries

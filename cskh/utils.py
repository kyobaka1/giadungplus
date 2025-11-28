"""
Utils cho CSKH - log system cho ticket actions
"""
import os
import json
from datetime import datetime
from pathlib import Path
from django.conf import settings

# Thư mục log cho ticket actions
TICKET_LOG_DIR = Path(settings.BASE_DIR) / "settings" / "logs" / "ticket_actions"


def log_ticket_action(ticket_number: str, user: str, action: str, details: dict = None):
    """
    Log ticket action vào file
    
    Args:
        ticket_number: Mã ticket (vd: TK0001)
        user: Username hoặc tên người dùng
        action: Hành động (vd: "created", "updated_status", "added_cost", "updated_reason")
        details: Dict chứa thông tin chi tiết
    """
    # Đảm bảo thư mục tồn tại
    TICKET_LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # File log cho ticket này
    log_file = TICKET_LOG_DIR / f"{ticket_number}.log"
    
    # Format log entry
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'user': user,
        'action': action,
        'details': details or {},
    }
    
    # Append vào file
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')


def get_ticket_logs(ticket_number: str) -> list:
    """
    Đọc log của ticket
    
    Returns:
        List các log entries (sắp xếp theo thời gian mới nhất trước)
    """
    log_file = TICKET_LOG_DIR / f"{ticket_number}.log"
    
    if not log_file.exists():
        return []
    
    logs = []
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    log_entry = json.loads(line)
                    # Parse timestamp để sort
                    try:
                        log_entry['timestamp_dt'] = datetime.fromisoformat(log_entry['timestamp'])
                    except:
                        pass
                    logs.append(log_entry)
                except:
                    pass
    
    # Sort theo thời gian mới nhất trước
    logs.sort(key=lambda x: x.get('timestamp_dt', datetime.min), reverse=True)
    
    return logs


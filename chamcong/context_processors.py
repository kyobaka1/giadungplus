from django.utils import timezone
from .models import AttendanceRecord


def attendance_reminder(request):
    """
    Context processor để kiểm tra trạng thái check-in của user.
    Trả về thông tin để hiển thị thông báo nhắc nhở check-in.
    """
    if not request.user.is_authenticated:
        return {"show_attendance_reminder": False}

    now = timezone.localtime()
    today = timezone.localdate()
    
    # Xác định ca hiện tại
    current_hour = now.hour
    if current_hour < 12:
        current_shift = "morning"
        shift_name = "Ca sáng"
    elif current_hour < 18:
        current_shift = "afternoon"
        shift_name = "Ca chiều"
    else:
        current_shift = "evening"
        shift_name = "Ca tối"
    
    # Kiểm tra xem user đã check-in trong ca này chưa
    # Tìm tất cả record của ngày hôm nay
    records_today = AttendanceRecord.objects.filter(
        user=request.user,
        work_date=today,
    )
    
    # Kiểm tra xem có record nào có check-in trong ca hiện tại không
    has_checked_in = False
    for record in records_today:
        if not record.check_in_time:
            continue
        
        # Nếu record có shift trùng với ca hiện tại
        if record.shift == current_shift:
            has_checked_in = True
            break
        
        # Nếu record chưa có shift, kiểm tra xem check-in_time có trong ca hiện tại không
        if not record.shift:
            check_in_hour = record.check_in_time.hour
            if current_shift == "morning" and check_in_hour < 12:
                has_checked_in = True
                break
            elif current_shift == "afternoon" and 12 <= check_in_hour < 18:
                has_checked_in = True
                break
            elif current_shift == "evening" and check_in_hour >= 18:
                has_checked_in = True
                break
    
    # Kiểm tra xem user đã dismiss thông báo cho ca này chưa
    session_key = f"dismissed_attendance_{today.strftime('%Y-%m-%d')}_{current_shift}"
    is_dismissed = request.session.get(session_key, False)
    
    # Hiển thị thông báo nếu:
    # - Chưa check-in
    # - Chưa dismiss
    show_reminder = not has_checked_in and not is_dismissed
    
    return {
        "show_attendance_reminder": show_reminder,
        "current_shift": current_shift,
        "current_shift_name": shift_name,
        "checkin_url": "/chamcong/",
    }


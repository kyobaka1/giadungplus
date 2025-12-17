from datetime import date, timedelta
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Sum, Count, Q, Avg
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cskh.utils import is_admin_or_group

from .models import AttendanceRecord

User = get_user_model()


@login_required
def overview_view(request: HttpRequest) -> HttpResponse:
    """
    Overview tổng quát: Xem tổng quát các bộ phận / tình hình chấm công trong tháng hoặc tháng trước.
    Xem các chỉ số phân tích về giờ làm và chấm công của cả công ty.
    
    Chỉ Admin và Manager mới có quyền truy cập.
    """
    user = request.user
    
    # Kiểm tra quyền
    is_admin = is_admin_or_group(user)
    is_manager = (
        is_admin_or_group(user, "WarehouseManager") or
        is_admin_or_group(user, "CSKHManager") or
        is_admin_or_group(user, "MarketingManager")
    )
    
    if not (is_admin or is_manager):
        return redirect("permission_denied")
    
    # Xử lý tham số tháng
    month_param = request.GET.get("month")
    today = timezone.localdate()
    
    if month_param:
        try:
            year, month = map(int, month_param.split("-"))
            target_date = date(year, month, 1)
        except Exception:
            target_date = today.replace(day=1)
    else:
        target_date = today.replace(day=1)
    
    # Tính ngày đầu và cuối tháng
    if target_date.month == 12:
        next_month = date(target_date.year + 1, 1, 1)
    else:
        next_month = date(target_date.year, target_date.month + 1, 1)
    
    # Tính tháng trước và sau cho navigation
    if target_date.month == 1:
        prev_month = date(target_date.year - 1, 12, 1)
    else:
        prev_month = date(target_date.year, target_date.month - 1, 1)
    
    if target_date.month == 12:
        next_month_nav = date(target_date.year + 1, 1, 1)
    else:
        next_month_nav = date(target_date.year, target_date.month + 1, 1)
    
    # Lọc theo quyền: Manager chỉ xem bộ phận của mình
    qs = AttendanceRecord.objects.filter(
        work_date__gte=target_date,
        work_date__lt=next_month
    )
    
    if not is_admin:
        # Manager chỉ xem bộ phận của mình
        user_department = user.last_name or ""
        if user_department:
            qs = qs.filter(department__iexact=user_department)
        else:
            qs = qs.none()
    
    # Thống kê theo bộ phận
    dept_stats = qs.values("department").annotate(
        total_records=Count("id"),
        total_minutes_sum=Sum("total_minutes"),
        overtime_minutes_sum=Sum("overtime_minutes"),
        approved_count=Count("id", filter=Q(approval_status="approved")),
        pending_count=Count("id", filter=Q(approval_status="pending")),
        rejected_count=Count("id", filter=Q(approval_status="rejected")),
        unique_users=Count("user", distinct=True),
    ).order_by("department")
    
    # Tính toán thêm cho từng bộ phận
    dept_data = []
    for stat in dept_stats:
        total_hours = (stat["total_minutes_sum"] or 0) // 60
        total_remaining_minutes = (stat["total_minutes_sum"] or 0) % 60
        overtime_hours = (stat["overtime_minutes_sum"] or 0) // 60
        overtime_remaining_minutes = (stat["overtime_minutes_sum"] or 0) % 60
        
        # Tính trung bình giờ làm mỗi người
        avg_hours = 0
        if stat["unique_users"] > 0:
            avg_minutes = (stat["total_minutes_sum"] or 0) / stat["unique_users"]
            avg_hours = avg_minutes / 60
        
        dept_data.append({
            "department": stat["department"],
            "total_records": stat["total_records"],
            "unique_users": stat["unique_users"],
            "total_hours": total_hours,
            "total_remaining_minutes": total_remaining_minutes,
            "overtime_hours": overtime_hours,
            "overtime_remaining_minutes": overtime_remaining_minutes,
            "avg_hours": round(avg_hours, 1),
            "approved_count": stat["approved_count"],
            "pending_count": stat["pending_count"],
            "rejected_count": stat["rejected_count"],
        })
    
    # Tổng hợp toàn công ty
    total_stats = qs.aggregate(
        total_records=Count("id"),
        total_minutes_sum=Sum("total_minutes"),
        overtime_minutes_sum=Sum("overtime_minutes"),
        unique_users=Count("user", distinct=True),
        approved_count=Count("id", filter=Q(approval_status="approved")),
        pending_count=Count("id", filter=Q(approval_status="pending")),
        rejected_count=Count("id", filter=Q(approval_status="rejected")),
    )
    
    total_hours = (total_stats["total_minutes_sum"] or 0) // 60
    total_remaining_minutes = (total_stats["total_minutes_sum"] or 0) % 60
    overtime_hours = (total_stats["overtime_minutes_sum"] or 0) // 60
    overtime_remaining_minutes = (total_stats["overtime_minutes_sum"] or 0) % 60
    
    # Thống kê theo ngày trong tháng (cho biểu đồ)
    daily_stats = qs.values("work_date").annotate(
        total_minutes_sum=Sum("total_minutes"),
        record_count=Count("id"),
        unique_users=Count("user", distinct=True),
    ).order_by("work_date")
    
    daily_data = []
    chart_height_px = 256  # h-64 = 256px
    
    # Tìm max hours thực tế trong dữ liệu để scale biểu đồ
    max_hours = 0
    for stat in daily_stats:
        daily_hours = (stat["total_minutes_sum"] or 0) / 60
        if daily_hours > max_hours:
            max_hours = daily_hours
    
    # Nếu không có dữ liệu hoặc max_hours = 0, set default
    if max_hours == 0:
        max_hours = 1  # Tránh chia cho 0
    
    # Tính lại chiều cao cho từng ngày
    for stat in daily_stats:
        daily_hours = (stat["total_minutes_sum"] or 0) / 60
        # Tính chiều cao bằng pixel dựa trên max thực tế
        height_px = round((daily_hours / max_hours) * chart_height_px, 1)
        
        daily_data.append({
            "date": stat["work_date"],
            "hours": round(daily_hours, 1),
            "height_px": height_px,  # Chiều cao bằng pixel
            "records": stat["record_count"],
            "users": stat["unique_users"],
        })
    
    # Thống kê theo ca làm việc
    shift_stats = qs.values("shift").annotate(
        total_minutes_sum=Sum("total_minutes"),
        record_count=Count("id"),
    ).order_by("shift")
    
    shift_data = []
    for stat in shift_stats:
        shift_hours = (stat["total_minutes_sum"] or 0) / 60
        shift_data.append({
            "shift": stat["shift"] or "N/A",
            "shift_display": dict(AttendanceRecord.SHIFT_CHOICES).get(stat["shift"], "N/A") if stat["shift"] else "N/A",
            "hours": round(shift_hours, 1),
            "records": stat["record_count"],
        })
    
    # Thống kê theo từng nhân sự
    user_stats = qs.values("user__id", "user__first_name", "user__username", "user__last_name", "department").annotate(
        total_minutes_sum=Sum("total_minutes"),
        overtime_minutes_sum=Sum("overtime_minutes"),
        record_count=Count("id"),
        approved_count=Count("id", filter=Q(approval_status="approved")),
        pending_count=Count("id", filter=Q(approval_status="pending")),
        rejected_count=Count("id", filter=Q(approval_status="rejected")),
    ).order_by("user__last_name", "user__first_name", "user__username")
    
    user_data = []
    for stat in user_stats:
        total_hours_user = (stat["total_minutes_sum"] or 0) // 60
        total_remaining_minutes_user = (stat["total_minutes_sum"] or 0) % 60
        overtime_hours_user = (stat["overtime_minutes_sum"] or 0) // 60
        overtime_remaining_minutes_user = (stat["overtime_minutes_sum"] or 0) % 60
        
        user_data.append({
            "user_id": stat["user__id"],
            "first_name": stat["user__first_name"] or stat["user__username"],
            "username": stat["user__username"],
            "last_name": stat["user__last_name"] or "",
            "department": stat["department"],
            "total_hours": total_hours_user,
            "total_remaining_minutes": total_remaining_minutes_user,
            "overtime_hours": overtime_hours_user,
            "overtime_remaining_minutes": overtime_remaining_minutes_user,
            "record_count": stat["record_count"],
            "approved_count": stat["approved_count"],
            "pending_count": stat["pending_count"],
            "rejected_count": stat["rejected_count"],
        })
    
    context = {
        "target_date": target_date,
        "prev_month": prev_month,
        "next_month": next_month_nav,
        "today": today,
        "dept_data": dept_data,
        "total_stats": {
            "total_records": total_stats["total_records"] or 0,
            "unique_users": total_stats["unique_users"] or 0,
            "total_hours": total_hours,
            "total_remaining_minutes": total_remaining_minutes,
            "overtime_hours": overtime_hours,
            "overtime_remaining_minutes": overtime_remaining_minutes,
            "approved_count": total_stats["approved_count"] or 0,
            "pending_count": total_stats["pending_count"] or 0,
            "rejected_count": total_stats["rejected_count"] or 0,
        },
        "daily_data": daily_data,
        "shift_data": shift_data,
        "user_data": user_data,
        "is_admin": is_admin,
    }
    
    return render(request, "chamcong/overview.html", context)


@login_required
def overview_staff_view(request: HttpRequest, user_id: int = None) -> HttpResponse:
    """
    Overview nhân sự: Xem tổng quát chấm công của nhân sự theo tháng / biểu đồ thời gian làm việc,
    lịch sử làm việc của nhân sự đó trong tháng.
    
    Chỉ Admin và Manager mới có quyền truy cập.
    Manager chỉ xem được nhân viên trong quyền quản lý của mình.
    """
    current_user = request.user
    is_admin = is_admin_or_group(current_user)
    is_warehouse_manager = is_admin_or_group(current_user, "WarehouseManager")
    is_cskh_manager = is_admin_or_group(current_user, "CSKHManager")
    is_marketing_manager = is_admin_or_group(current_user, "MarketingManager")
    is_manager = is_warehouse_manager or is_cskh_manager or is_marketing_manager
    
    # Chỉ Admin và Manager mới có quyền
    if not (is_admin or is_manager):
        return redirect("permission_denied")
    
    # Lấy danh sách nhân viên theo quyền
    if is_admin:
        # Admin xem được tất cả nhân viên
        available_users = User.objects.filter(is_active=True).order_by("last_name", "first_name", "username")
    elif is_warehouse_manager:
        # WarehouseManager chỉ xem được nhân viên cùng department
        user_department = current_user.last_name or ""
        if not user_department:
            return redirect("permission_denied")
        available_users = User.objects.filter(
            last_name__iexact=user_department,
            is_active=True
        ).exclude(
            groups__name__in=["WarehouseManager", "CSKHManager", "MarketingManager"]
        ).order_by("first_name", "username")
    elif is_cskh_manager:
        # CSKHManager chỉ xem được CSKHStaff
        available_users = User.objects.filter(
            groups__name="CSKHStaff",
            is_active=True
        ).order_by("first_name", "username")
    elif is_marketing_manager:
        # MarketingManager chỉ xem được MarketingStaff và MarketingIntern
        available_users = User.objects.filter(
            groups__name__in=["MarketingStaff", "MarketingIntern"],
            is_active=True
        ).order_by("first_name", "username")
    else:
        available_users = User.objects.none()
    
    # Xác định user cần xem
    if user_id:
        target_user = get_object_or_404(User, id=user_id, is_active=True)
        
        # Kiểm tra quyền: user phải nằm trong danh sách available_users
        if target_user not in available_users:
            return redirect("permission_denied")
    else:
        # Nếu không có user_id, chọn nhân viên đầu tiên trong danh sách và redirect
        if available_users.exists():
            first_user = available_users.first()
            month_param = request.GET.get("month", "")
            if month_param:
                return redirect(f"/chamcong/overview/staff/{first_user.id}/?month={month_param}")
            else:
                return redirect(f"/chamcong/overview/staff/{first_user.id}/")
        else:
            # Không có nhân viên nào -> hiển thị thông báo
            target_user = None
    
    # Xử lý tham số tháng
    month_param = request.GET.get("month")
    today = timezone.localdate()
    
    if month_param:
        try:
            year, month = map(int, month_param.split("-"))
            target_date = date(year, month, 1)
        except Exception:
            target_date = today.replace(day=1)
    else:
        target_date = today.replace(day=1)
    
    # Tính ngày đầu và cuối tháng
    if target_date.month == 12:
        next_month = date(target_date.year + 1, 1, 1)
    else:
        next_month = date(target_date.year, target_date.month + 1, 1)
    
    # Tính tháng trước và sau cho navigation
    if target_date.month == 1:
        prev_month = date(target_date.year - 1, 12, 1)
    else:
        prev_month = date(target_date.year, target_date.month - 1, 1)
    
    if target_date.month == 12:
        next_month_nav = date(target_date.year + 1, 1, 1)
    else:
        next_month_nav = date(target_date.year, target_date.month + 1, 1)
    
    # Nếu không có target_user, trả về context với danh sách nhân viên
    if not target_user:
        context = {
            "target_user": None,
            "available_users": available_users,
            "target_date": target_date,
            "prev_month": prev_month,
            "next_month": next_month_nav,
            "today": today,
            "is_admin": is_admin,
            "is_manager": is_manager,
        }
        return render(request, "chamcong/overview_staff.html", context)
    
    # Lấy tất cả records của user trong tháng
    records = AttendanceRecord.objects.filter(
        user=target_user,
        work_date__gte=target_date,
        work_date__lt=next_month
    ).order_by("work_date", "check_in_time")
    
    # Thống kê tổng hợp
    stats = records.aggregate(
        total_records=Count("id"),
        total_minutes_sum=Sum("total_minutes"),
        overtime_minutes_sum=Sum("overtime_minutes"),
        approved_count=Count("id", filter=Q(approval_status="approved")),
        pending_count=Count("id", filter=Q(approval_status="pending")),
        rejected_count=Count("id", filter=Q(approval_status="rejected")),
    )
    
    total_hours = (stats["total_minutes_sum"] or 0) // 60
    total_remaining_minutes = (stats["total_minutes_sum"] or 0) % 60
    overtime_hours = (stats["overtime_minutes_sum"] or 0) // 60
    overtime_remaining_minutes = (stats["overtime_minutes_sum"] or 0) % 60
    
    # Thống kê theo ngày (cho biểu đồ)
    daily_stats = records.values("work_date").annotate(
        total_minutes_sum=Sum("total_minutes"),
        record_count=Count("id"),
    ).order_by("work_date")
    
    daily_data = []
    max_hours = 15  # Max height của biểu đồ
    chart_height_px = 256  # h-64 = 256px
    for stat in daily_stats:
        daily_hours = (stat["total_minutes_sum"] or 0) / 60
        # Tính chiều cao bằng pixel (max 15h = 256px)
        if daily_hours > max_hours:
            height_px = chart_height_px
        else:
            height_px = round((daily_hours / max_hours) * chart_height_px, 1)
        
        daily_data.append({
            "date": stat["work_date"],
            "hours": round(daily_hours, 1),
            "height_px": height_px,  # Chiều cao bằng pixel
            "records": stat["record_count"],
        })
    
    # Thống kê theo ca
    shift_stats = records.values("shift").annotate(
        total_minutes_sum=Sum("total_minutes"),
        record_count=Count("id"),
    ).order_by("shift")
    
    shift_data = []
    for stat in shift_stats:
        shift_hours = (stat["total_minutes_sum"] or 0) / 60
        shift_data.append({
            "shift": stat["shift"] or "N/A",
            "shift_display": dict(AttendanceRecord.SHIFT_CHOICES).get(stat["shift"], "N/A") if stat["shift"] else "N/A",
            "hours": round(shift_hours, 1),
            "records": stat["record_count"],
        })
    
    # Chuẩn bị dữ liệu records với thông tin chi tiết
    records_data = []
    for record in records:
        record_hours = record.total_minutes // 60 if record.total_minutes else 0
        record_remaining_minutes = record.total_minutes % 60 if record.total_minutes else 0
        overtime_record_hours = record.overtime_minutes // 60 if record.overtime_minutes else 0
        overtime_record_remaining_minutes = record.overtime_minutes % 60 if record.overtime_minutes else 0
        
        records_data.append({
            "record": record,
            "total_hours": record_hours,
            "total_remaining_minutes": record_remaining_minutes,
            "overtime_hours": overtime_record_hours,
            "overtime_remaining_minutes": overtime_record_remaining_minutes,
        })
    
    context = {
        "target_user": target_user,
        "available_users": available_users,
        "target_date": target_date,
        "prev_month": prev_month,
        "next_month": next_month_nav,
        "today": today,
        "stats": {
            "total_records": stats["total_records"] or 0,
            "total_hours": total_hours,
            "total_remaining_minutes": total_remaining_minutes,
            "overtime_hours": overtime_hours,
            "overtime_remaining_minutes": overtime_remaining_minutes,
            "approved_count": stats["approved_count"] or 0,
            "pending_count": stats["pending_count"] or 0,
            "rejected_count": stats["rejected_count"] or 0,
        },
        "daily_data": daily_data,
        "shift_data": shift_data,
        "records_data": records_data,
        "is_admin": is_admin,
        "is_manager": is_manager,
    }
    
    return render(request, "chamcong/overview_staff.html", context)


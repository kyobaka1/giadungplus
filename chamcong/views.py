import math
from datetime import date, datetime, time as dt_time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Sum, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cskh.utils import is_admin_or_group

from .models import AttendanceRecord, WorkLocation

User = get_user_model()


def _get_user_primary_group_name(user) -> str:
    """
    Lấy tên group chính của user (nếu có), otherwise trả về chuỗi rỗng.
    """
    first_group = user.groups.first()
    return first_group.name if first_group else ""


def _calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Tính khoảng cách giữa 2 điểm GPS (km) dùng công thức Haversine.
    """
    R = 6371  # Bán kính Trái Đất (km)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def _check_location_valid(latitude: float, longitude: float, department: str) -> tuple[bool, str]:
    """
    Kiểm tra vị trí GPS có hợp lệ không (trong bán kính cho phép của WorkLocation).
    
    Returns:
        (is_valid, location_name): (True/False, tên vị trí hoặc "Vị trí chưa xác định")
    """
    if not latitude or not longitude:
        return False, "Vị trí chưa xác định"
    
    # Tìm các địa điểm hợp lệ
    base_qs = WorkLocation.objects.filter(is_active=True)

    # Ưu tiên lọc theo bộ phận nếu mapping khớp
    if department:
        dept_qs = base_qs.filter(department__iexact=department)
        # Nếu không tìm thấy theo bộ phận (do last_name không trùng code),
        # fallback sang toàn bộ địa điểm đang active
        locations = dept_qs if dept_qs.exists() else base_qs
    else:
        locations = base_qs
    
    for loc in locations:
        distance_km = _calculate_distance_km(
            latitude, longitude,
            loc.latitude, loc.longitude
        )
        distance_m = distance_km * 1000  # Chuyển sang mét
        
        if distance_m <= loc.radius_m:
            return True, loc.name
    
    return False, "Vị trí chưa xác định"


@login_required
def checkin_view(request: HttpRequest) -> HttpResponse:
    """
    View 1: Màn hình chấm công (check-in + check-out cho ngày hôm nay).

    - Frontend sẽ dùng HTML5 Geolocation + upload selfie.
    - Tại backend: lưu record cho hôm nay, không xử lý GPS phức tạp (để tính sau).
    """

    user = request.user
    # Sử dụng localdate theo TIME_ZONE (GMT+7 nếu settings đã chỉnh)
    today = timezone.localdate()

    record, _ = AttendanceRecord.objects.get_or_create(
        user=user,
        work_date=today,
        defaults={
            "department": user.last_name or "",
            "group_name": _get_user_primary_group_name(user),
        },
    )

    if request.method == "POST":
        # Kiểm tra nếu đã duyệt hoặc từ chối thì không cho phép chỉnh sửa
        if record.approval_status in ("approved", "rejected"):
            messages.error(
                request,
                "Không thể chỉnh sửa chấm công đã được duyệt hoặc từ chối.",
            )
            return redirect("chamcong:checkin")

        action = request.POST.get("action")  # "checkin" hoặc "checkout"
        latitude = request.POST.get("latitude")
        longitude = request.POST.get("longitude")
        address = request.POST.get("address") or ""
        photo = request.FILES.get("photo")

        now = timezone.localtime()

        # Xác định ca làm theo giờ hiện tại
        current_hour = now.hour
        if current_hour < 12:
            shift = "morning"
        elif current_hour < 18:
            shift = "afternoon"
        else:
            shift = "evening"

        # GPS & ảnh là bắt buộc cho cả check-in và check-out
        if action in ("checkin", "checkout") and (
            not latitude or not longitude or not photo
        ):
            messages.error(
                request,
                "Vui lòng bật GPS và chụp ảnh selfie trước khi chấm công.",
            )
            return redirect("chamcong:checkin")

        if action == "checkin" and record.check_in_time is None:
            record.check_in_time = now
            record.shift = shift
            if latitude and longitude:
                record.check_in_latitude = float(latitude)
                record.check_in_longitude = float(longitude)
            record.check_in_address = address
            if photo:
                record.check_in_photo = photo

        elif action == "checkout":
            record.check_out_time = now
            if latitude and longitude:
                record.check_out_latitude = float(latitude)
                record.check_out_longitude = float(longitude)
            record.check_out_address = address
            if photo:
                record.check_out_photo = photo

            # Tạm thời: tính total_minutes đơn giản = chênh lệch check_in/check_out
            if record.check_in_time and record.check_out_time:
                delta = record.check_out_time - record.check_in_time
                record.total_minutes = max(int(delta.total_seconds() // 60), 0)

        record.save()
        return redirect("chamcong:checkin")

    # Lịch sử chấm công hôm nay theo ca
    today_records = (
        AttendanceRecord.objects.filter(user=user, work_date=today)
        .order_by("check_in_time")
        .all()
    )

    # Xác định ca hiện tại (để biết cần show lịch sử ca nào)
    now = timezone.localtime()
    current_hour = now.hour
    if current_hour < 12:
        current_shift = "morning"
    elif current_hour < 18:
        current_shift = "afternoon"
    else:
        current_shift = "evening"

    context = {
        "record": record,
        "today": today,
        "today_records": today_records,
        "current_shift": current_shift,
    }
    return render(request, "chamcong/checkin.html", context)


@login_required
def my_attendance_view(request: HttpRequest) -> HttpResponse:
    """
    View 2: Trang xem bảng công của bản thân.

    - Mặc định: tháng hiện tại.
    - Cho phép xem tháng trước (query param ?month=YYYY-MM).
    """

    user = request.user
    today = timezone.localdate()

    month_param = request.GET.get("month")
    if month_param:
        try:
            year, month = map(int, month_param.split("-"))
            start_date = date(year, month, 1)
        except Exception:
            start_date = today.replace(day=1)
    else:
        start_date = today.replace(day=1)

    # Ngày đầu tháng kế tiếp để filter < next_month
    if start_date.month == 12:
        next_month = date(start_date.year + 1, 1, 1)
    else:
        next_month = date(start_date.year, start_date.month + 1, 1)

    records = (
        AttendanceRecord.objects.filter(
            user=user, work_date__gte=start_date, work_date__lt=next_month
        )
        .order_by("work_date")
        .all()
    )

    totals = records.aggregate(
        total_minutes_sum=Sum("total_minutes"),
        overtime_minutes_sum=Sum("overtime_minutes"),
    )

    total_minutes_sum = totals.get("total_minutes_sum") or 0
    total_hours = total_minutes_sum // 60
    remaining_minutes = total_minutes_sum % 60
    
    overtime_minutes_sum = totals.get("overtime_minutes_sum") or 0
    overtime_hours = overtime_minutes_sum // 60
    overtime_remaining_minutes = overtime_minutes_sum % 60
    
    # Tính toán hours và minutes cho từng record
    records_with_hours = []
    for record in records:
        total_hours_record = record.total_minutes // 60 if record.total_minutes else 0
        total_remaining_minutes_record = record.total_minutes % 60 if record.total_minutes else 0
        
        overtime_hours_record = record.overtime_minutes // 60 if record.overtime_minutes else 0
        overtime_remaining_minutes_record = record.overtime_minutes % 60 if record.overtime_minutes else 0
        
        records_with_hours.append({
            "record": record,
            "total_hours": total_hours_record,
            "total_remaining_minutes": total_remaining_minutes_record,
            "overtime_hours": overtime_hours_record,
            "overtime_remaining_minutes": overtime_remaining_minutes_record,
        })

    context = {
        "records_with_hours": records_with_hours,
        "start_date": start_date,
        "today": today,
        "total_minutes_sum": total_minutes_sum,
        "total_hours": total_hours,
        "remaining_minutes": remaining_minutes,
        "overtime_minutes_sum": overtime_minutes_sum,
        "overtime_hours": overtime_hours,
        "overtime_remaining_minutes": overtime_remaining_minutes,
    }
    return render(request, "chamcong/my_attendance.html", context)


@login_required
def approve_attendance_view(request: HttpRequest) -> HttpResponse:
    """
    View 3: Màn hình duyệt giờ làm cho quản lý.

    Quyền:
    - Admin: duyệt tất cả (bao gồm cả chấm công của manager).
    - WarehouseManager: duyệt nhân sự Warehouse cùng department (last_name).
                      Ví dụ: KHO_HCM chỉ duyệt được KHO_HCM, KHO_HN chỉ duyệt được KHO_HN.
                      Không thể duyệt chấm công của manager.
    - CSKHManager: duyệt nhân sự CSKHStaff. Không thể duyệt chấm công của manager.
    - MarketingManager: duyệt MarketingStaff & MarketingIntern. Không thể duyệt chấm công của manager.
    
    Lưu ý: Chấm công của các Manager (WarehouseManager, MarketingManager, CSKHManager)
           chỉ có Admin mới có quyền duyệt.
    """

    user = request.user

    # Xác định quyền quản lý
    is_admin = is_admin_or_group(user)
    is_warehouse_manager = is_admin_or_group(user, "WarehouseManager")
    is_cskh_manager = is_admin_or_group(user, "CSKHManager")
    is_marketing_manager = is_admin_or_group(user, "MarketingManager")

    # Danh sách các group manager - chỉ Admin mới duyệt được chấm công của manager
    manager_groups = ["WarehouseManager", "MarketingManager", "CSKHManager"]

    qs = AttendanceRecord.objects.all().select_related("user")

    if not is_admin:
        # Nếu không phải admin, loại bỏ các chấm công của manager
        qs = qs.exclude(group_name__in=manager_groups)
        
        if is_warehouse_manager:
            # WarehouseManager chỉ duyệt được nhân viên cùng department (last_name)
            # Ví dụ: KHO_HCM chỉ duyệt được KHO_HCM, KHO_HN chỉ duyệt được KHO_HN
            user_department = user.last_name or ""
            if user_department:
                qs = qs.filter(department__iexact=user_department)
            else:
                # Nếu manager không có last_name thì không có quyền
                return redirect("permission_denied")
        elif is_cskh_manager:
            qs = qs.filter(group_name__in=["CSKHStaff"])
        elif is_marketing_manager:
            qs = qs.filter(group_name__in=["MarketingStaff", "MarketingIntern"])
        else:
            # Không có quyền -> quay về trang báo lỗi chung
            return redirect("permission_denied")

    # Chỉ hiển thị những chấm công đã check-out (có check_out_time)
    qs = qs.filter(check_out_time__isnull=False)

    # Xử lý action duyệt / từ chối
    if request.method == "POST":
        record_id = request.POST.get("record_id")
        action = request.POST.get("action")  # "approve" hoặc "reject"
        note = request.POST.get("note") or ""

        record = get_object_or_404(qs, id=record_id)
        
        # Kiểm tra: Nếu không phải admin, không cho phép duyệt chấm công của manager
        if not is_admin and record.group_name in manager_groups:
            messages.error(
                request,
                "Chỉ Admin mới có quyền duyệt chấm công của Manager.",
            )
            return redirect("chamcong:approve_attendance")
        
        # Kiểm tra nếu đã duyệt hoặc từ chối thì không cho phép thay đổi
        if record.approval_status in ("approved", "rejected"):
            messages.error(
                request,
                f"Không thể thay đổi chấm công đã {'duyệt' if record.approval_status == 'approved' else 'từ chối'}.",
            )
            return redirect("chamcong:approve_attendance")
        
        if action == "approve":
            record.approval_status = "approved"
            record.approved_by = user
            record.approved_at = timezone.now()
            record.approval_note = note
            record.save()
        elif action == "reject":
            record.approval_status = "rejected"
            record.approved_by = user
            record.approved_at = timezone.now()
            record.approval_note = note
            record.save()
        elif action == "delete":
            # Kiểm tra trước khi xóa
            if record.approval_status in ("approved", "rejected"):
                messages.error(
                    request,
                    "Không thể xóa chấm công đã được duyệt hoặc từ chối.",
                )
                return redirect("chamcong:approve_attendance")
            # Xoá bản ghi chấm công (debug)
            record.delete()

        return redirect("chamcong:approve_attendance")

    records = qs.order_by("-work_date", "-created_at")[:200]
    
    # Kiểm tra vị trí hợp lệ cho mỗi record
    records_with_location = []
    for record in records:
        location_valid = False
        location_name = "Vị trí chưa xác định"
        
        if record.check_in_latitude and record.check_in_longitude:
            location_valid, location_name = _check_location_valid(
                record.check_in_latitude,
                record.check_in_longitude,
                record.department
            )
        
        # Tính giờ và phút từ total_minutes
        total_hours = record.total_minutes // 60 if record.total_minutes else 0
        total_remaining_minutes = record.total_minutes % 60 if record.total_minutes else 0
        
        # Tính giờ và phút từ overtime_minutes
        overtime_hours = record.overtime_minutes // 60 if record.overtime_minutes else 0
        overtime_remaining_minutes = record.overtime_minutes % 60 if record.overtime_minutes else 0
        
        records_with_location.append({
            "record": record,
            "location_valid": location_valid,
            "location_name": location_name,
            "total_hours": total_hours,
            "total_remaining_minutes": total_remaining_minutes,
            "overtime_hours": overtime_hours,
            "overtime_remaining_minutes": overtime_remaining_minutes,
        })

    context = {
        "records_with_location": records_with_location,
        "is_admin": is_admin,
        "is_warehouse_manager": is_warehouse_manager,
        "is_cskh_manager": is_cskh_manager,
        "is_marketing_manager": is_marketing_manager,
    }
    return render(request, "chamcong/approve_attendance.html", context)


@login_required
def dismiss_attendance_reminder_view(request: HttpRequest) -> HttpResponse:
    """
    View để dismiss thông báo nhắc nhở check-in (không đi làm).
    Lưu vào session để không hiển thị lại trong ca/ngày đó.
    """
    from django.utils import timezone
    from django.http import JsonResponse
    
    now = timezone.localtime()
    today = timezone.localdate()
    
    # Xác định ca hiện tại
    current_hour = now.hour
    if current_hour < 12:
        current_shift = "morning"
    elif current_hour < 18:
        current_shift = "afternoon"
    else:
        current_shift = "evening"
    
    # Lưu vào session
    session_key = f"dismissed_attendance_{today.strftime('%Y-%m-%d')}_{current_shift}"
    request.session[session_key] = True
    request.session.modified = True
    
    return JsonResponse({"status": "success"})


@login_required
def make_up_attendance_view(request: HttpRequest) -> HttpResponse:
    """
    View: Chấm công bù cho nhân viên (chỉ Admin).
    
    Cho phép Admin chấm công bù cho nhiều nhân viên:
    - Chọn bộ phận (last_name)
    - Chọn nhân viên (nhiều người)
    - Chọn ngày làm việc
    - Chọn ca (sáng/chiều/tối)
    - Nhập giờ check-in và check-out
    - Bỏ qua ảnh và vị trí
    """
    user = request.user
    
    # Chỉ Admin mới có quyền
    if not is_admin_or_group(user):
        return redirect("permission_denied")
    
    # Xử lý AJAX: Lấy danh sách nhân viên theo bộ phận
    if request.method == "GET" and request.GET.get("action") == "get_users":
        department = request.GET.get("department")
        if department:
            users = User.objects.filter(
                last_name__iexact=department,
                is_active=True
            ).order_by("first_name", "username")
            
            users_data = []
            for u in users:
                # Lấy ảnh nhân viên
                photo_url = f"/static/nhanvien/{u.username}.png"
                users_data.append({
                    "id": u.id,
                    "username": u.username,
                    "first_name": u.first_name or u.username,
                    "photo_url": photo_url,
                })
            
            return JsonResponse({"users": users_data})
        return JsonResponse({"users": []})
    
    # Xử lý POST: Lưu chấm công bù
    if request.method == "POST":
        try:
            # Lấy dữ liệu từ form
            work_date_str = request.POST.get("work_date")
            shift = request.POST.get("shift")
            check_in_time_str = request.POST.get("check_in_time")
            check_out_time_str = request.POST.get("check_out_time")
            user_ids = request.POST.getlist("user_ids")  # Danh sách ID nhân viên
            
            # Validate dữ liệu
            if not all([work_date_str, shift, check_in_time_str, check_out_time_str, user_ids]):
                messages.error(request, "Vui lòng điền đầy đủ thông tin.")
                return redirect("chamcong:make_up_attendance")
            
            # Parse ngày
            work_date = datetime.strptime(work_date_str, "%Y-%m-%d").date()
            
            # Parse giờ check-in và check-out
            check_in_time_obj = datetime.strptime(check_in_time_str, "%H:%M").time()
            check_out_time_obj = datetime.strptime(check_out_time_str, "%H:%M").time()
            
            # Tạo datetime từ date + time
            check_in_datetime = timezone.make_aware(
                datetime.combine(work_date, check_in_time_obj)
            )
            check_out_datetime = timezone.make_aware(
                datetime.combine(work_date, check_out_time_obj)
            )
            
            # Tính total_minutes
            delta = check_out_datetime - check_in_datetime
            total_minutes = max(int(delta.total_seconds() // 60), 0)
            
            # Lưu chấm công cho từng nhân viên
            success_count = 0
            for user_id in user_ids:
                try:
                    target_user = User.objects.get(id=int(user_id))
                    
                    # Lấy group_name của user
                    group_name = _get_user_primary_group_name(target_user)
                    
                    # Tạo hoặc cập nhật AttendanceRecord
                    record, created = AttendanceRecord.objects.get_or_create(
                        user=target_user,
                        work_date=work_date,
                        shift=shift,
                        defaults={
                            "department": target_user.last_name or "",
                            "group_name": group_name,
                            "check_in_time": check_in_datetime,
                            "check_out_time": check_out_datetime,
                            "total_minutes": total_minutes,
                            "approval_status": "pending",
                            # Bỏ qua ảnh và vị trí (để null)
                        }
                    )
                    
                    # Nếu record đã tồn tại, cập nhật
                    if not created:
                        record.check_in_time = check_in_datetime
                        record.check_out_time = check_out_datetime
                        record.total_minutes = total_minutes
                        record.save()
                    
                    success_count += 1
                except User.DoesNotExist:
                    continue
                except Exception as e:
                    messages.warning(request, f"Lỗi khi chấm công cho user ID {user_id}: {e}")
                    continue
            
            if success_count > 0:
                messages.success(request, f"Đã chấm công bù cho {success_count} nhân viên.")
            else:
                messages.error(request, "Không thể chấm công cho bất kỳ nhân viên nào.")
            
            return redirect("chamcong:make_up_attendance")
            
        except ValueError as e:
            messages.error(request, f"Dữ liệu không hợp lệ: {e}")
            return redirect("chamcong:make_up_attendance")
        except Exception as e:
            messages.error(request, f"Lỗi: {e}")
            return redirect("chamcong:make_up_attendance")
    
    # GET: Hiển thị form
    # Lấy danh sách bộ phận (last_name) từ users
    departments = User.objects.filter(
        is_active=True,
        last_name__isnull=False
    ).exclude(
        last_name=""
    ).values_list("last_name", flat=True).distinct().order_by("last_name")
    
    # Ngày mặc định là hôm nay
    today = timezone.localdate()
    
    context = {
        "departments": departments,
        "default_date": today.strftime("%Y-%m-%d"),
    }
    return render(request, "chamcong/make_up_attendance.html", context)



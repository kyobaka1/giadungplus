from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages

from cskh.utils import is_admin_or_group

from .models import WorkLocation, WorkRule


@login_required
def settings_view(request: HttpRequest) -> HttpResponse:
    """
    Màn hình settings: quản lý vị trí chấm công hợp lệ và giờ làm.
    
    Chỉ Admin mới có quyền truy cập.
    """
    user = request.user
    
    if not is_admin_or_group(user):
        return redirect("permission_denied")
    
    # Xử lý POST: thêm/sửa/xoá WorkLocation hoặc WorkRule
    if request.method == "POST":
        action = request.POST.get("action")
        
        if action == "add_location":
            name = request.POST.get("name")
            department = request.POST.get("department")
            latitude = request.POST.get("latitude")
            longitude = request.POST.get("longitude")
            radius_m = request.POST.get("radius_m", 150)
            
            if name and department and latitude and longitude:
                WorkLocation.objects.create(
                    name=name,
                    department=department,
                    latitude=float(latitude),
                    longitude=float(longitude),
                    radius_m=int(radius_m),
                )
                messages.success(request, f"Đã thêm vị trí chấm công: {name}")
        
        elif action == "edit_location":
            loc_id = request.POST.get("location_id")
            location = get_object_or_404(WorkLocation, id=loc_id)
            location.name = request.POST.get("name", location.name)
            location.department = request.POST.get("department", location.department)
            if request.POST.get("latitude"):
                location.latitude = float(request.POST.get("latitude"))
            if request.POST.get("longitude"):
                location.longitude = float(request.POST.get("longitude"))
            if request.POST.get("radius_m"):
                location.radius_m = int(request.POST.get("radius_m"))
            location.is_active = request.POST.get("is_active") == "on"
            location.save()
            messages.success(request, f"Đã cập nhật vị trí: {location.name}")
        
        elif action == "delete_location":
            loc_id = request.POST.get("location_id")
            location = get_object_or_404(WorkLocation, id=loc_id)
            location.delete()
            messages.success(request, f"Đã xoá vị trí: {location.name}")
        
        elif action == "add_work_rule":
            department = request.POST.get("department")
            group_name = request.POST.get("group_name")
            start_time = request.POST.get("start_time")
            end_time = request.POST.get("end_time")
            allow_overtime = request.POST.get("allow_overtime") == "on"
            
            if department and group_name and start_time and end_time:
                WorkRule.objects.create(
                    department=department,
                    group_name=group_name,
                    start_time=start_time,
                    end_time=end_time,
                    allow_overtime=allow_overtime,
                )
                messages.success(request, f"Đã thêm quy định giờ làm: {department} / {group_name}")
        
        elif action == "edit_work_rule":
            rule_id = request.POST.get("rule_id")
            rule = get_object_or_404(WorkRule, id=rule_id)
            rule.department = request.POST.get("department", rule.department)
            rule.group_name = request.POST.get("group_name", rule.group_name)
            if request.POST.get("start_time"):
                rule.start_time = request.POST.get("start_time")
            if request.POST.get("end_time"):
                rule.end_time = request.POST.get("end_time")
            rule.allow_overtime = request.POST.get("allow_overtime") == "on"
            rule.is_active = request.POST.get("is_active") == "on"
            rule.save()
            messages.success(request, f"Đã cập nhật quy định giờ làm: {rule.department} / {rule.group_name}")
        
        elif action == "delete_work_rule":
            rule_id = request.POST.get("rule_id")
            rule = get_object_or_404(WorkRule, id=rule_id)
            rule.delete()
            messages.success(request, f"Đã xoá quy định giờ làm: {rule.department} / {rule.group_name}")
        
        return redirect("chamcong:settings")
    
    # GET: hiển thị danh sách
    locations = WorkLocation.objects.all().order_by("department", "name")
    work_rules = WorkRule.objects.all().order_by("department", "group_name")
    
    context = {
        "locations": locations,
        "work_rules": work_rules,
    }
    return render(request, "chamcong/settings.html", context)


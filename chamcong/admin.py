from django.contrib import admin

from .models import AttendanceRecord, WorkLocation, WorkRule


@admin.register(WorkLocation)
class WorkLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "latitude", "longitude", "radius_m", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(WorkRule)
class WorkRuleAdmin(admin.ModelAdmin):
    list_display = ("department", "group_name", "shift", "start_time", "end_time", "allow_overtime", "is_active")
    list_filter = ("department", "shift", "is_active", "allow_overtime")
    search_fields = ("department", "group_name")
    ordering = ("department", "group_name", "shift")


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "work_date",
        "shift",
        "check_in_time",
        "check_out_time",
        "total_minutes",
        "approval_status",
    )
    list_filter = ("work_date", "shift", "approval_status", "department")
    search_fields = ("user__username", "user__first_name", "department")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "work_date"
    ordering = ("-work_date", "-created_at")


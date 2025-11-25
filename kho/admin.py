from django.contrib import admin
from .models import Warehouse, UserProfile, Ticket, TicketComment

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("code", "name")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name")
    filter_horizontal = ("warehouses",)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "order_code", "title", "status", "error_type", "created_at", "created_by")
    list_filter = ("status", "error_type", "created_at")
    search_fields = ("order_code", "title", "description")
    readonly_fields = ("created_at", "updated_at", "resolved_at")


@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket", "user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("content",)
    readonly_fields = ("created_at",)

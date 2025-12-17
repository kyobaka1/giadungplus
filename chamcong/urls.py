from django.urls import path
from . import views
from . import views_settings

app_name = "chamcong"

urlpatterns = [
    path("", views.checkin_view, name="checkin"),
    path("me/", views.my_attendance_view, name="my_attendance"),
    path("approve/", views.approve_attendance_view, name="approve_attendance"),
    path("settings/", views_settings.settings_view, name="settings"),
    path("dismiss-reminder/", views.dismiss_attendance_reminder_view, name="dismiss_reminder"),
    path("make-up/", views.make_up_attendance_view, name="make_up_attendance"),
]



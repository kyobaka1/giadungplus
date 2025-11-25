# kho/middleware.py
from datetime import timedelta, datetime
from django.utils import timezone

class KhoSwitcherMiddleware:
    """
    Middleware:
    - Đọc query ?kho=...
    - Nếu hợp lệ thì set vào session: request.session["current_kho"]
    - Có thể set default nếu chưa có.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        kho = request.GET.get("kho")

        # Chỉ cho phép 2 giá trị hợp lệ
        if kho in ["geleximco", "toky"]:
            request.session["current_kho"] = kho

        # Nếu chưa có thì cho default luôn (tuỳ anh muốn HN hay SG)
        if "current_kho" not in request.session:
            request.session["current_kho"] = "geleximco"

        response = self.get_response(request)
        return response

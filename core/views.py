# core/views.py
"""
Core app views.
"""

import logging
import os
import subprocess
import shlex
from typing import Any, Dict

from django.conf import settings
from django.shortcuts import render, redirect
from django.http import (
    JsonResponse,
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
)
from django.core.cache import cache
from django.contrib.auth import logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from core.sapo_client.client import SELENIUM_LOCK_KEY
from .models import WebPushSubscription, NotificationDelivery
from .serializers import WebPushSubscriptionSerializer

logger = logging.getLogger(__name__)


def custom_logout_view(request):
    """
    Custom logout view để xử lý cả GET và POST requests.
    """
    logout(request)
    return redirect('/login/')


class CustomLoginView(LoginView):
    """
    Custom login view để redirect về dashboard nếu user đã authenticated.
    """
    template_name = "auth/login.html"
    
    def dispatch(self, request, *args, **kwargs):
        # Nếu user đã đăng nhập, redirect về dashboard
        if request.user.is_authenticated:
            return redirect('/')
        # Gọi super để handle GET/POST requests bình thường
        return super().dispatch(request, *args, **kwargs)
    
    def get_success_url(self):
        # Sau khi login thành công, redirect về dashboard hoặc next parameter
        next_url = self.request.GET.get('next') or self.request.POST.get('next')
        if next_url:
            return next_url
        return '/'


@login_required
def dashboard_home(request):
    """
    Trang dashboard điều hướng sau khi login.
    Hiển thị grid các menu chính: Kho Hàng, CSKH, Quản trị, Cấu hình
    """
    if request.method != "GET":
        from django.http import HttpResponseNotAllowed

        return HttpResponseNotAllowed(["GET"])

    # WebPush debug: hiển thị subscription hiện tại của user ngay trên trang chủ
    webpush_subs = (
        WebPushSubscription.objects.filter(user=request.user, is_active=True)
        .order_by("-created_at")[:10]
    )

    context = {
        "title": "Dashboard - Gia Dụng Plus",
        "webpush_subscriptions": webpush_subs,
    }
    return render(request, "core/dashboard.html", context)


def selenium_loading_view(request):
    """
    Loading page hiển thị khi Selenium đang login.
    
    Page này sẽ polling status API và auto-redirect về URL gốc
    khi login hoàn tất.
    """
    logger.info("[SeleniumLoadingView] User waiting for Selenium login")
    
    # Lấy redirect URL từ session (đã được lưu bởi middleware)
    redirect_url = request.session.get('selenium_redirect_url', '/kho/')
    
    context = {
        'redirect_url': redirect_url,
    }
    
    return render(request, 'core/selenium_loading.html', context)


def permission_denied(request):
    """
    Trang thông báo không có quyền truy cập.
    """
    context = {
        'title': 'Không có quyền truy cập - Gia Dụng Plus',
    }
    return render(request, 'core/permission_denied.html', context)


def selenium_login_status_api(request):
    """
    API endpoint để check status của Selenium login.
    
    Returns:
        JSON: {
            "is_locked": true/false,
            "message": "..."
        }
    """
    is_locked = cache.get(SELENIUM_LOCK_KEY) is not None
    
    response_data = {
        'is_locked': is_locked,
        'message': 'Login in progress' if is_locked else 'Login completed'
    }
    
    logger.debug(f"[SeleniumStatusAPI] Lock status: {is_locked}")
    
    return JsonResponse(response_data)


# ==================== SERVER LOGS (ADMIN ONLY) ====================


def _tail_file(path: str, num_lines: int = 200) -> str:
    """
    Đọc num_lines dòng cuối cùng của file log.

    Ưu tiên an toàn / đơn giản vì file log thường không quá lớn.
    Nếu file rất lớn, có thể tối ưu sau.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return ""
    except OSError as exc:  # Các lỗi IO khác
        logger.error("Không thể đọc log file %s: %s", path, exc)
        return ""

    if num_lines <= 0:
        return "".join(lines)

    return "".join(lines[-num_lines:])


@login_required
def server_logs_api(request: HttpRequest) -> JsonResponse:
    """
    API endpoint: /core/api/server-logs/

    Đọc log server (tail N dòng cuối) để sử dụng cho UI realtime (JS polling).

    Query params:
        - file: django | gunicorn-error | gunicorn-access | supervisor | supervisor-error
        - lines: số dòng cuối muốn lấy (mặc định: 200)
    """
    if not request.user.is_superuser:
        return JsonResponse({"detail": "Bạn không có quyền xem logs."}, status=403)

    file_key = request.GET.get("file", "django").strip() or "django"
    try:
        num_lines = int(request.GET.get("lines", "200"))
    except ValueError:
        num_lines = 200

    # Chỉ cho phép map tới một số file log cố định, tránh path traversal
    logs_dir = os.path.join(settings.BASE_DIR, "logs")
    file_map = {
        "django": os.path.join(logs_dir, "django.log"),
        "gunicorn-error": os.path.join(logs_dir, "gunicorn-error.log"),
        "gunicorn-access": os.path.join(logs_dir, "gunicorn-access.log"),
        "supervisor": os.path.join(logs_dir, "gunicorn-supervisor.log"),
        "supervisor-error": os.path.join(logs_dir, "gunicorn-supervisor-error.log"),
    }

    path = file_map.get(file_key)
    if not path:
        return JsonResponse({"detail": "Loại file log không hợp lệ."}, status=400)

    content = _tail_file(path, num_lines=num_lines)

    return JsonResponse(
        {
            "file": file_key,
            "path": path,
            "lines": num_lines,
            "content": content,
        }
    )


@login_required
def server_logs_view(request: HttpRequest) -> HttpResponse:
    """
    Trang HTML đơn giản để xem log server theo thời gian thực (JS auto refresh).

    Chỉ cho phép superuser truy cập.
    """
    if not request.user.is_superuser:
        return HttpResponseForbidden("Bạn không có quyền xem logs.")

    default_file = request.GET.get("file", "django").strip() or "django"

    available_logs = [
        {"id": "django", "label": "Django (django.log)"},
        {"id": "gunicorn-error", "label": "Gunicorn Error (gunicorn-error.log)"},
        {"id": "gunicorn-access", "label": "Gunicorn Access (gunicorn-access.log)"},
        {"id": "supervisor", "label": "Supervisor (gunicorn-supervisor.log)"},
        {"id": "supervisor-error", "label": "Supervisor Error (gunicorn-supervisor-error.log)"},
    ]

    context = {
        "title": "Server Logs - Gia Dụng Plus",
        "available_logs": available_logs,
        "default_file": default_file,
    }
    return render(request, "core/server_logs.html", context)


@login_required
def server_logs_execute_cmd_api(request: HttpRequest) -> JsonResponse:
    """
    API endpoint: /core/api/server-logs/execute-cmd/
    
    Thực thi lệnh CMD từ xa (chỉ superuser).
    
    POST data:
        - command: str (lệnh cần thực thi)
        - timeout: int (thời gian timeout, mặc định: 30 giây)
    
    Returns:
        JSON: {
            "success": bool,
            "output": str,
            "error": str,
            "exit_code": int,
            "execution_time": float
        }
    """
    if not request.user.is_superuser:
        return JsonResponse(
            {"success": False, "error": "Bạn không có quyền thực thi lệnh."},
            status=403
        )
    
    import json
    import time
    
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        command = data.get('command', '').strip()
        timeout = int(data.get('timeout', 30))
        
        if not command:
            return JsonResponse(
                {"success": False, "error": "Lệnh không được để trống."},
                status=400
            )
        
        # Tự động loại bỏ 'sudo' khỏi lệnh vì user đã là superuser
        # (không cần sudo nữa, và có thể gây lỗi nếu sudo không có trong PATH)
        original_command = command
        if command.startswith('sudo '):
            command = command[5:].strip()  # Loại bỏ 'sudo ' ở đầu
            logger.info(
                "[ServerLogsExecuteCmd] Tự động loại bỏ 'sudo' khỏi lệnh (user đã là superuser): %s -> %s",
                original_command[:100],
                command[:100]
            )
        
        # Tự động thêm prefix: cd vào thư mục project và activate virtualenv
        # Trừ khi lệnh đã có prefix này hoặc là lệnh cd vào thư mục khác
        project_prefix = "cd /var/www/giadungplus && source venv/bin/activate && "
        
        # Kiểm tra xem lệnh đã có prefix chưa
        has_project_prefix = command.startswith("cd /var/www/giadungplus") and "source venv/bin/activate" in command
        
        # Kiểm tra xem có phải lệnh cd vào thư mục khác không
        is_cd_other_dir = command.startswith("cd ") and "/var/www/giadungplus" not in command
        
        # Chỉ thêm prefix nếu chưa có và không phải lệnh cd vào thư mục khác
        if not has_project_prefix and not is_cd_other_dir:
            command = project_prefix + command
            logger.info(
                "[ServerLogsExecuteCmd] Tự động thêm prefix project: %s",
                command[:200]
            )
        
        # Tự động sửa lệnh chạy script .sh để dùng /bin/bash trực tiếp
        # Tránh lỗi shebang #!/usr/bin/env bash không tìm thấy bash
        if '.sh' in command and not command.strip().startswith('bash ') and not command.strip().startswith('/bin/bash '):
            # Tìm script path trong lệnh
            import re
            # Tìm pattern ./script.sh hoặc script.sh hoặc /path/to/script.sh
            script_pattern = r'\.?/?([^\s&|;]+\.sh)'
            match = re.search(script_pattern, command)
            if match:
                script_path = match.group(1)
                # Thay thế script.sh bằng bash script.sh hoặc /bin/bash script.sh
                # Giữ nguyên các phần khác của lệnh (cd, source, &&, etc.)
                if script_path.startswith('./'):
                    # ./script.sh -> bash ./script.sh
                    command = command.replace(script_path, f'bash {script_path}', 1)
                elif script_path.startswith('/'):
                    # /path/to/script.sh -> /bin/bash /path/to/script.sh
                    command = command.replace(script_path, f'/bin/bash {script_path}', 1)
                else:
                    # script.sh -> bash ./script.sh (giả định trong thư mục hiện tại)
                    command = command.replace(script_path, f'bash ./{script_path}', 1)
                
                logger.info(
                    "[ServerLogsExecuteCmd] Tự động sửa lệnh chạy script: %s",
                    command[:200]
                )
        
        # Giới hạn timeout tối đa 300 giây (5 phút) để tránh lệnh chạy quá lâu
        timeout = min(timeout, 300)
        
        # Log lệnh được thực thi (bảo mật)
        logger.warning(
            "[ServerLogsExecuteCmd] User %s thực thi lệnh: %s",
            request.user.username,
            command[:200]  # Chỉ log 200 ký tự đầu
        )
        
        # Thực thi lệnh
        start_time = time.time()
        
        # Dùng shell=True cho cả Windows và Linux để có thể chạy các lệnh shell built-in
        # (cd, ls, pipe, redirect, etc.)
        # Vì chỉ superuser mới có quyền, nên security risk được chấp nhận
        is_windows = os.name == 'nt'
        
        if is_windows:
            # Windows: dùng cmd.exe với shell=True
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
        else:
            # Linux/Mac: dùng /bin/bash -c để chạy lệnh shell
            # Điều này cho phép chạy các lệnh built-in như cd, ls, và các lệnh có pipe/redirect
            # Nếu lệnh có chạy script (.sh), đảm bảo dùng /bin/bash để tránh lỗi shebang
            # Đặt PATH để đảm bảo tìm thấy các lệnh cơ bản
            env = os.environ.copy()
            # Đảm bảo /bin và /usr/bin có trong PATH
            current_path = env.get('PATH', '')
            if '/bin' not in current_path:
                env['PATH'] = f"/bin:/usr/bin:/usr/local/bin:{current_path}"
            
            process = subprocess.Popen(
                ['/bin/bash', '-c', command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=env
            )
        
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            execution_time = time.time() - start_time
            return JsonResponse({
                "success": False,
                "error": f"Lệnh đã vượt quá thời gian timeout ({timeout} giây).",
                "output": "",
                "exit_code": -1,
                "execution_time": round(execution_time, 2)
            })
        
        execution_time = time.time() - start_time
        
        # Kết hợp stdout và stderr
        output = stdout
        if stderr:
            output += f"\n[STDERR]\n{stderr}"
        
        # Cải thiện thông báo lỗi cho một số trường hợp phổ biến
        error_message = stderr if exit_code != 0 else ""
        if exit_code == 127 and "command not found" in error_message.lower():
            # Lệnh không tìm thấy - có thể là script cần đường dẫn đầy đủ
            suggested_fix = ""
            if ".sh" in command or ".py" in command:
                suggested_fix = "\n💡 Gợi ý: Nếu đây là script, hãy dùng đường dẫn đầy đủ hoặc ./script.sh (ví dụ: ./update-git.sh hoặc /var/www/giadungplus/update-git.sh)"
            elif "cd" in command and "&&" in command:
                suggested_fix = "\n💡 Gợi ý: Với lệnh có cd &&, hãy đảm bảo script có đường dẫn đầy đủ hoặc ./script.sh"
            
            if suggested_fix:
                error_message += suggested_fix
        
        # Giới hạn độ dài output (tránh response quá lớn)
        max_output_length = 100000  # 100KB
        if len(output) > max_output_length:
            output = output[:max_output_length] + f"\n\n... (đã cắt bớt, tổng cộng {len(output)} ký tự)"
        
        return JsonResponse({
            "success": exit_code == 0,
            "output": output,
            "error": error_message,
            "exit_code": exit_code,
            "execution_time": round(execution_time, 2)
        })
        
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Dữ liệu JSON không hợp lệ."},
            status=400
        )
    except Exception as e:
        logger.exception("[ServerLogsExecuteCmd] Lỗi khi thực thi lệnh: %s", e)
        return JsonResponse(
            {"success": False, "error": f"Lỗi không mong đợi: {str(e)}"},
            status=500
        )


@api_view(["POST"])
@authentication_classes([])  # Tắt SessionAuthentication để DRF không bắt CSRF
@permission_classes([AllowAny])
@csrf_exempt  # Bỏ kiểm tra CSRF ở middleware mức Django
def register_webpush_subscription(request: HttpRequest):
    """
    API endpoint: /api/push/register/

    Nhận thông tin subscription/token từ frontend và lưu vào DB.
    - Nếu endpoint đã tồn tại → update.
    - Nếu fcm_token trùng → update.
    - Ngược lại → tạo mới.

    Payload ví dụ:
    {
        "device_type": "android_web" | "ios_web" | "unknown",
        "endpoint": "...",
        "keys": {
            "p256dh": "...",
            "auth": "..."
        },
        "fcm_token": "..."
    }
    """

    # Debug nhanh: log payload thô (limit độ dài để tránh spam log)
    try:
        logger.info(
            "[WebPushRegister] New request: path=%s, method=%s, user=%s, data=%s",
            request.path,
            request.method,
            getattr(request.user, "username", None),
            dict(request.data) if hasattr(request, "data") else request.body[:500],
        )

        serializer = WebPushSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data: Dict[str, Any] = serializer.validated_data

        # Ưu tiên user đang đăng nhập (nếu có session)
        user = request.user if request.user.is_authenticated else None

        # Cho phép client gửi thêm username để map sang user_id (trong trường hợp không có session)
        username = (data.pop("username", "") or "").strip()
        if not user and username:
            User = get_user_model()
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                logger.warning(
                    "register_webpush_subscription: không tìm thấy user với username=%s",
                    username,
                )

        endpoint = data.get("endpoint") or ""
        fcm_token = data.get("fcm_token") or ""

        # Chuẩn hoá device_type tốt hơn (tránh toàn bộ là "unknown")
        # Ưu tiên theo endpoint + User-Agent, sau đó mới fallback device_type client gửi lên.
        raw_device_type = data.get("device_type") or WebPushSubscription.DEVICE_UNKNOWN
        ua = request.META.get("HTTP_USER_AGENT", "") or ""

        device_type = raw_device_type
        if "web.push.apple.com" in endpoint:
            # Safari iOS Web Push (PWA / Safari 16.4+)
            device_type = WebPushSubscription.DEVICE_IOS_WEB
        elif "Android" in ua and "Chrome" in ua:
            # Chrome trên Android (dùng FCM)
            device_type = WebPushSubscription.DEVICE_ANDROID_WEB
        else:
            # Giữ nguyên device_type client gửi, hoặc UNKNOWN nếu không hợp lệ
            device_type = raw_device_type

        # Ưu tiên match theo endpoint + auth (Web Push thuần) hoặc fcm_token (Android Chrome).
        # YÊU CẦU:
        #   - Nếu login bằng device khác, endpoint khác, auth khác → tạo dòng mới trong DB
        #     (có thể cùng user_id / username).
        subscription = None
        created = False

        if endpoint:
            # Tìm subscription hiện có cho cùng user + endpoint (+ auth nếu có).
            qs = WebPushSubscription.objects.filter(endpoint=endpoint)
            if user is not None:
                qs = qs.filter(user=user)
            auth = data.get("auth")
            if auth:
                qs = qs.filter(auth=auth)
            subscription = qs.first()

            if subscription:
                # Cập nhật subscription hiện có
                subscription.user = user or subscription.user
                subscription.device_type = device_type
                subscription.p256dh = data.get("p256dh")
                subscription.auth = data.get("auth")
                subscription.fcm_token = fcm_token or subscription.fcm_token
                subscription.is_active = True
                subscription.save(
                    update_fields=["user", "device_type", "p256dh", "auth", "fcm_token", "is_active"]
                )
                created = False
            else:
                # Không tìm thấy subscription phù hợp → tạo bản ghi mới
                subscription = WebPushSubscription.objects.create(
                    user=user,
                    device_type=device_type,
                    endpoint=endpoint,
                    p256dh=data.get("p256dh"),
                    auth=data.get("auth"),
                    fcm_token=fcm_token or "",
                    is_active=True,
                )
                created = True
        elif fcm_token:
            # Với FCM token, cho phép 1 user có nhiều token khác nhau (nhiều device/browser).
            # Chỉ update nếu tìm được bản ghi trùng user + fcm_token, ngược lại tạo mới.
            qs = WebPushSubscription.objects.filter(fcm_token=fcm_token)
            if user is not None:
                qs = qs.filter(user=user)
            subscription = qs.first()

            if subscription:
                subscription.user = user or subscription.user
                subscription.device_type = device_type
                subscription.p256dh = data.get("p256dh")
                subscription.auth = data.get("auth")
                subscription.endpoint = endpoint or subscription.endpoint
                subscription.is_active = True
                subscription.save(
                    update_fields=["user", "device_type", "p256dh", "auth", "endpoint", "is_active"]
                )
                created = False
            else:
                subscription = WebPushSubscription.objects.create(
                    user=user,
                    device_type=device_type,
                    endpoint=endpoint or "",
                    p256dh=data.get("p256dh"),
                    auth=data.get("auth"),
                    fcm_token=fcm_token,
                    is_active=True,
                )
                created = True

        if not subscription:
            return Response(
                {"detail": "Thiếu endpoint hoặc fcm_token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        out = WebPushSubscriptionSerializer(subscription)
        logger.info(
            "[WebPushRegister] Saved subscription id=%s user_id=%s device_type=%s endpoint_prefix=%s",
            subscription.id,
            getattr(subscription.user, "id", None),
            subscription.device_type,
            (subscription.endpoint or "")[:50],
        )
        return Response(
            {"created": created, "subscription": out.data},
            status=status.HTTP_200_OK,
        )
    except Exception as exc:
        # Log chi tiết để debug nhanh khi client báo 500
        logger.exception("Lỗi không mong đợi trong register_webpush_subscription: %s", exc)
        return Response(
            {
                "detail": "Internal Server Error in register_webpush_subscription",
                "error": str(exc),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ==================== NOTIFICATION APIs ====================

@api_view(["GET"])
@login_required
def list_notifications(request: HttpRequest):
    """
    API endpoint: /api/notifications/

    Lấy danh sách notifications của user hiện tại.

    Query params:
        - limit: Số lượng (mặc định: 50)
        - offset: Offset (mặc định: 0)
        - unread_only: Chỉ lấy chưa đọc (true/false, mặc định: false)
    """
    from django.core.paginator import Paginator

    limit = int(request.GET.get("limit", 50))
    offset = int(request.GET.get("offset", 0))
    unread_only = request.GET.get("unread_only", "false").lower() == "true"

    qs = NotificationDelivery.objects.filter(
        user=request.user,
        channel=NotificationDelivery.CHANNEL_IN_APP,
        status=NotificationDelivery.STATUS_SENT,
    ).select_related("notification").order_by("-created_at")

    if unread_only:
        qs = qs.filter(is_read=False)

    # Pagination
    paginator = Paginator(qs, limit)
    page = (offset // limit) + 1
    deliveries = paginator.get_page(page)

    results = []
    for delivery in deliveries:
        notification = delivery.notification
        results.append({
            "id": delivery.id,
            "notification_id": notification.id,
            "title": notification.title,
            "body": notification.body,
            "link": notification.link or "",
            "action": notification.action,
            "sound": notification.sound or "",
            "count": notification.count,
            "tag": notification.tag or "",
            "event_type": notification.event_type or "",
            "context": notification.context,
            "is_read": delivery.is_read,
            "read_at": delivery.read_at.isoformat() if delivery.read_at else None,
            "created_at": delivery.created_at.isoformat(),
        })

    return Response({
        "count": paginator.count,
        "next": deliveries.has_next(),
        "previous": deliveries.has_previous(),
        "results": results,
    })


@api_view(["GET"])
@login_required
def unread_notifications_count(request: HttpRequest):
    """
    API endpoint: /api/notifications/unread-count/

    Lấy số lượng notifications chưa đọc của user hiện tại.
    """
    count = NotificationDelivery.objects.filter(
        user=request.user,
        channel=NotificationDelivery.CHANNEL_IN_APP,
        status=NotificationDelivery.STATUS_SENT,
        is_read=False,
    ).count()

    return Response({"count": count})


@api_view(["POST"])
@login_required
def mark_notification_read(request: HttpRequest, delivery_id: int):
    """
    API endpoint: /api/notifications/<delivery_id>/mark-read/

    Đánh dấu 1 notification đã đọc.
    """
    from django.utils import timezone

    try:
        delivery = NotificationDelivery.objects.get(
            id=delivery_id,
            user=request.user,
            channel=NotificationDelivery.CHANNEL_IN_APP,
        )
    except NotificationDelivery.DoesNotExist:
        return Response(
            {"detail": "Notification không tồn tại."},
            status=status.HTTP_404_NOT_FOUND,
        )

    delivery.is_read = True
    delivery.read_at = timezone.now()
    delivery.save(update_fields=["is_read", "read_at"])

    return Response({"success": True})


@api_view(["POST"])
@login_required
def mark_all_notifications_read(request: HttpRequest):
    """
    API endpoint: /api/notifications/mark-all-read/

    Đánh dấu tất cả notifications của user hiện tại là đã đọc.
    """
    from django.utils import timezone

    updated = NotificationDelivery.objects.filter(
        user=request.user,
        channel=NotificationDelivery.CHANNEL_IN_APP,
        status=NotificationDelivery.STATUS_SENT,
        is_read=False,
    ).update(is_read=True, read_at=timezone.now())

    return Response({"success": True, "updated": updated})


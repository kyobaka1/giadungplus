# kho/views/management.py
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
from kho.utils import group_required
from kho.models import WarehousePackingSetting
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@group_required("WarehouseManager")
def stats(request):
    """
    Thống kê kho:
    - Số đơn/ngày
    - Số đơn/nhân viên
    - Tỷ lệ lỗi kho...
    """
    # Get date range from request or default to today
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    today = datetime.now(tz_vn).date()
    
    date_from = request.GET.get("date_from", today.strftime("%Y-%m-%d"))
    date_to = request.GET.get("date_to", today.strftime("%Y-%m-%d"))
    
    # TODO: Query database for statistics
    # - Total orders packed
    # - Orders per employee
    # - Error rate
    # - Average packing time
    # - Top performing employees
    
    stats_data = {
        "total_orders": 0,
        "packed_orders": 0,
        "error_orders": 0,
        "error_rate": 0.0,
        "avg_packing_time": 0,
        "orders_by_employee": [],
        "orders_by_hour": [],
        "top_performers": [],
    }
    
    context = {
        "title": "Thống Kê Kho - GIA DỤNG PLUS",
        "current_kho": request.session.get("current_kho", "geleximco"),
        "date_from": date_from,
        "date_to": date_to,
        "stats": stats_data,
    }
    return render(request, "kho/management/stats.html", context)


@group_required("WarehouseManager")
@require_http_methods(["GET"])
def get_packing_settings(request):
    """
    GET /kho/management/packing_settings/
    Lấy cài đặt bật/tắt packing cho cả 2 kho
    """
    settings = WarehousePackingSetting.objects.all()
    settings_data = {}
    
    for setting in settings:
        settings_data[setting.warehouse_code] = {
            'warehouse_code': setting.warehouse_code,
            'warehouse_display': setting.get_warehouse_code_display(),
            'is_active': setting.is_active,
            'updated_at': setting.updated_at.isoformat() if setting.updated_at else None,
            'updated_by': setting.updated_by.username if setting.updated_by else None,
        }
    
    # Đảm bảo có cả 2 kho
    if 'KHO_HCM' not in settings_data:
        default_setting = WarehousePackingSetting.get_setting_for_warehouse('KHO_HCM')
        settings_data['KHO_HCM'] = {
            'warehouse_code': 'KHO_HCM',
            'warehouse_display': default_setting.get_warehouse_code_display(),
            'is_active': default_setting.is_active,
            'updated_at': default_setting.updated_at.isoformat() if default_setting.updated_at else None,
            'updated_by': default_setting.updated_by.username if default_setting.updated_by else None,
        }
    
    if 'KHO_HN' not in settings_data:
        default_setting = WarehousePackingSetting.get_setting_for_warehouse('KHO_HN')
        settings_data['KHO_HN'] = {
            'warehouse_code': 'KHO_HN',
            'warehouse_display': default_setting.get_warehouse_code_display(),
            'is_active': default_setting.is_active,
            'updated_at': default_setting.updated_at.isoformat() if default_setting.updated_at else None,
            'updated_by': default_setting.updated_by.username if default_setting.updated_by else None,
        }
    
    return JsonResponse({
        'success': True,
        'settings': settings_data
    })


@group_required("WarehouseManager")
@require_http_methods(["POST"])
@csrf_exempt
def toggle_packing_setting(request):
    """
    POST /kho/management/packing_settings/toggle/
    Body: {"warehouse_code": "KHO_HCM" hoặc "KHO_HN", "is_active": true/false}
    Bật/tắt tính năng packing cho một kho
    """
    try:
        data = json.loads(request.body)
        warehouse_code = data.get('warehouse_code')
        is_active = data.get('is_active')
        
        if warehouse_code not in ['KHO_HCM', 'KHO_HN']:
            return JsonResponse({
                'success': False,
                'error': 'warehouse_code phải là KHO_HCM hoặc KHO_HN'
            }, status=400)
        
        if not isinstance(is_active, bool):
            return JsonResponse({
                'success': False,
                'error': 'is_active phải là boolean (true/false)'
            }, status=400)
        
        setting = WarehousePackingSetting.get_setting_for_warehouse(warehouse_code)
        setting.is_active = is_active
        setting.updated_by = request.user
        setting.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Đã {"bật" if is_active else "tắt"} tính năng đóng gói hàng cho {setting.get_warehouse_code_display()}',
            'setting': {
                'warehouse_code': setting.warehouse_code,
                'warehouse_display': setting.get_warehouse_code_display(),
                'is_active': setting.is_active,
                'updated_at': setting.updated_at.isoformat() if setting.updated_at else None,
                'updated_by': setting.updated_by.username if setting.updated_by else None,
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Dữ liệu JSON không hợp lệ'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Lỗi hệ thống: {str(e)}'
        }, status=500)

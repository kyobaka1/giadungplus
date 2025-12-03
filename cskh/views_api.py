"""
API endpoints cho Ticket operations
"""
from django.shortcuts import get_object_or_404
from cskh.utils import group_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
import json
import os
from pathlib import Path
from datetime import datetime

from .models import Ticket, TicketCost, TicketEvent, Feedback, FeedbackLog
from .settings import get_reason_types_by_source, get_cost_types
from .utils import log_ticket_action
from core.sapo_client import get_sapo_client
from .services.ticket_service import TicketService
from django.utils import timezone


@csrf_exempt
@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["POST"])
def api_add_cost(request, ticket_id):
    """API: Thêm chi phí cho ticket"""
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    try:
        data = json.loads(request.body)
        cost_type = (data.get('cost_type') or '').strip()
        note = data.get('note', '') or ''

        # Thông tin sản phẩm (áp dụng khi loại chi phí là "Hàng hỏng vỡ" hoặc liên quan hàng hóa)
        variant_id = data.get('variant_id') or None
        try:
            variant_id = int(variant_id) if variant_id else None
        except (TypeError, ValueError):
            variant_id = None

        product_name = data.get('product_name') or ''
        variant_name = data.get('variant_name') or ''
        sku = data.get('sku') or ''

        quantity_raw = data.get('quantity')
        try:
            quantity = int(quantity_raw) if quantity_raw is not None else None
        except (TypeError, ValueError):
            quantity = None

        unit_price_raw = data.get('unit_price')
        try:
            unit_price = float(unit_price_raw) if unit_price_raw is not None else None
        except (TypeError, ValueError):
            unit_price = None

        amount_raw = data.get('amount', 0)
        try:
            amount = float(amount_raw or 0)
        except (TypeError, ValueError):
            amount = 0.0

        # Ngày thanh toán
        payment_date = None
        payment_date_str = (data.get('payment_date') or '').strip()
        if payment_date_str:
            try:
                # Frontend gửi dạng "YYYY-MM-DD"
                payment_date = datetime.fromisoformat(payment_date_str).date()
            except Exception:
                payment_date = None

        # Ràng buộc: số lượng hỏng vỡ không được vượt quá số lượng trong đơn
        if cost_type == 'Hàng hỏng vỡ' and variant_id and (quantity or 0) > 0 and ticket.order_id:
            max_qty = None
            try:
                ticket_service = TicketService()
                order = ticket_service.order_service.get_order_dto(ticket.order_id)
                if hasattr(order, 'line_items') and order.line_items:
                    for item in order.line_items:
                        if item.variant_id == variant_id:
                            try:
                                max_qty = int(item.quantity or 0)
                            except (TypeError, ValueError):
                                max_qty = None
                            break
            except Exception:
                max_qty = None

            if max_qty is not None and quantity > max_qty:
                return JsonResponse(
                    {
                        'success': False,
                        'error': f'Số lượng hàng hỏng vỡ ({quantity}) không được vượt quá số lượng trong đơn ({max_qty}).'
                    },
                    status=400
                )

        # Auto tính amount cho loại "Hàng hỏng vỡ" nếu có variant + quantity
        if cost_type == 'Hàng hỏng vỡ' and variant_id and (quantity or 0) > 0:
            # Nếu frontend chưa gửi unit_price thì cố gắng lấy từ Sapo
            if unit_price is None:
                try:
                    sapo = get_sapo_client()
                    core_api = sapo.core
                    raw = core_api.get_variant_raw(variant_id)
                    variant_data = raw.get('variant') or {}
                    # Sapo variant.price là giá bán / đơn vị
                    unit_price = float(variant_data.get('price') or 0)
                except Exception:
                    unit_price = None

            if unit_price is not None:
                amount = unit_price * (quantity or 0)

        if not cost_type or amount <= 0:
            return JsonResponse({'success': False, 'error': 'Thiếu thông tin chi phí'}, status=400)

        cost = TicketCost.objects.create(
            ticket=ticket,
            cost_type=cost_type,
            amount=amount,
            note=note,
            variant_id=variant_id,
            product_name=product_name,
            variant_name=variant_name,
            sku=sku,
            quantity=quantity,
            unit_price=unit_price,
            payment_date=payment_date,
            person=request.user,
        )
        
        # Nếu ticket đang ở trạng thái 'new' thì chuyển sang 'processing'
        if ticket.ticket_status == 'new':
            ticket.ticket_status = 'processing'
            ticket.save(update_fields=['ticket_status'])

        # Log action
        log_ticket_action(
            ticket.ticket_number,
            request.user.username,
            'added_cost',
            {'cost_type': cost_type, 'amount': float(amount)}
        )
        
        return JsonResponse({
            'success': True,
            'cost': {
                'id': cost.id,
                'cost_type': cost.cost_type,
                'amount': float(cost.amount),
                'note': cost.note,
                'variant_id': cost.variant_id,
                'product_name': cost.product_name,
                'variant_name': cost.variant_name,
                'sku': cost.sku,
                'quantity': cost.quantity,
                'unit_price': float(cost.unit_price) if cost.unit_price is not None else None,
                'payment_date': cost.payment_date.isoformat() if cost.payment_date else None,
                'created_at': cost.created_at.isoformat(),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["POST"])
def api_update_reason(request, ticket_id):
    """API: Cập nhật reason cho ticket"""
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    try:
        data = json.loads(request.body)
        source_reason = data.get('source_reason', '')
        reason_type = data.get('reason_type', '')
        
        old_source = ticket.source_reason
        old_type = ticket.reason_type
        
        ticket.source_reason = source_reason
        ticket.reason_type = reason_type
        ticket.save()

        # Nếu ticket đang ở trạng thái 'new' thì chuyển sang 'processing'
        if ticket.ticket_status == 'new':
            ticket.ticket_status = 'processing'
            ticket.save(update_fields=['ticket_status'])
        
        # Log action
        log_ticket_action(
            ticket.ticket_number,
            request.user.username,
            'updated_reason',
            {
                'old': {'source': old_source, 'type': old_type},
                'new': {'source': source_reason, 'type': reason_type}
            }
        )
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@group_required("CSKHManager", "CSKHStaff")
@csrf_exempt
@require_http_methods(["POST"])
def api_upload_ticket_files(request, ticket_id):
    """
    API: Upload thêm ảnh/video cho ticket.
    - Nhận multipart/form-data với field 'images'
    - Lưu file vào assets/cskh
    - Append path vào ticket.images
    """
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    if 'images' not in request.FILES:
        return JsonResponse({'success': False, 'error': 'Không có file nào được chọn'}, status=400)
    
    upload_dir = Path('assets/cskh')
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    saved_paths = []
    
    for file in request.FILES.getlist('images'):
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        ext = os.path.splitext(file.name)[1]
        filename = f"{ts}{ext}"
        file_path = upload_dir / filename
        
        with open(file_path, 'wb') as f:
            for chunk in file.chunks():
                f.write(chunk)
        
        rel_path = f"cskh/{filename}"
        saved_paths.append(rel_path)
    
    # Append vào ticket.images
    current = ticket.images or []
    ticket.images = current + saved_paths
    ticket.save()

    # Nếu ticket đang ở trạng thái 'new' thì chuyển sang 'processing'
    if ticket.ticket_status == 'new':
        ticket.ticket_status = 'processing'
        ticket.save(update_fields=['ticket_status'])
    
    # Log action
    log_ticket_action(
        ticket.ticket_number,
        request.user.username,
        'uploaded_files',
        {'files': saved_paths},
    )
    
    return JsonResponse({'success': True, 'files': saved_paths})


@csrf_exempt
@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["PUT", "POST"])
def api_update_cost(request, ticket_id, cost_id):
    """API: Cập nhật chi phí cho ticket"""
    ticket = get_object_or_404(Ticket, id=ticket_id)
    cost = get_object_or_404(TicketCost, id=cost_id, ticket=ticket)
    
    try:
        data = json.loads(request.body)
        cost_type = (data.get('cost_type') or '').strip()
        note = data.get('note', '') or ''

        # Thông tin sản phẩm
        variant_id = data.get('variant_id') or None
        try:
            variant_id = int(variant_id) if variant_id else None
        except (TypeError, ValueError):
            variant_id = None

        product_name = data.get('product_name') or ''
        variant_name = data.get('variant_name') or ''
        sku = data.get('sku') or ''

        quantity_raw = data.get('quantity')
        try:
            quantity = int(quantity_raw) if quantity_raw is not None else None
        except (TypeError, ValueError):
            quantity = None

        unit_price_raw = data.get('unit_price')
        try:
            unit_price = float(unit_price_raw) if unit_price_raw is not None else None
        except (TypeError, ValueError):
            unit_price = None

        amount_raw = data.get('amount', 0)
        try:
            amount = float(amount_raw or 0)
        except (TypeError, ValueError):
            amount = 0.0

        # Ngày thanh toán
        payment_date = None
        payment_date_str = (data.get('payment_date') or '').strip()
        if payment_date_str:
            try:
                payment_date = datetime.fromisoformat(payment_date_str).date()
            except Exception:
                payment_date = None

        # Ràng buộc: số lượng hỏng vỡ không được vượt quá số lượng trong đơn
        if cost_type == 'Hàng hỏng vỡ' and variant_id and (quantity or 0) > 0 and ticket.order_id:
            max_qty = None
            try:
                ticket_service = TicketService()
                order = ticket_service.order_service.get_order_dto(ticket.order_id)
                if hasattr(order, 'line_items') and order.line_items:
                    for item in order.line_items:
                        if item.variant_id == variant_id:
                            try:
                                max_qty = int(item.quantity or 0)
                            except (TypeError, ValueError):
                                max_qty = None
                            break
            except Exception:
                max_qty = None

            if max_qty is not None and quantity > max_qty:
                return JsonResponse(
                    {
                        'success': False,
                        'error': f'Số lượng hàng hỏng vỡ ({quantity}) không được vượt quá số lượng trong đơn ({max_qty}).'
                    },
                    status=400
                )

        # Auto tính amount cho loại "Hàng hỏng vỡ" nếu có variant + quantity
        if cost_type == 'Hàng hỏng vỡ' and variant_id and (quantity or 0) > 0:
            if unit_price is None:
                try:
                    sapo = get_sapo_client()
                    core_api = sapo.core
                    raw = core_api.get_variant_raw(variant_id)
                    variant_data = raw.get('variant') or {}
                    unit_price = float(variant_data.get('price') or 0)
                except Exception:
                    unit_price = None

            if unit_price is not None:
                amount = unit_price * (quantity or 0)

        if not cost_type or amount <= 0:
            return JsonResponse({'success': False, 'error': 'Thiếu thông tin chi phí'}, status=400)

        # Cập nhật cost
        cost.cost_type = cost_type
        cost.amount = amount
        cost.note = note
        cost.variant_id = variant_id
        cost.product_name = product_name
        cost.variant_name = variant_name
        cost.sku = sku
        cost.quantity = quantity
        cost.unit_price = unit_price
        cost.payment_date = payment_date
        cost.save()
        
        # Log action
        log_ticket_action(
            ticket.ticket_number,
            request.user.username,
            'updated_cost',
            {'cost_id': cost.id, 'cost_type': cost_type, 'amount': float(amount)}
        )
        
        return JsonResponse({
            'success': True,
            'cost': {
                'id': cost.id,
                'cost_type': cost.cost_type,
                'amount': float(cost.amount),
                'note': cost.note,
                'variant_id': cost.variant_id,
                'product_name': cost.product_name,
                'variant_name': cost.variant_name,
                'sku': cost.sku,
                'quantity': cost.quantity,
                'unit_price': float(cost.unit_price) if cost.unit_price is not None else None,
                'payment_date': cost.payment_date.isoformat() if cost.payment_date else None,
                'created_at': cost.created_at.isoformat(),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["DELETE", "POST"])
def api_delete_cost(request, ticket_id, cost_id):
    """API: Xóa chi phí cho ticket"""
    ticket = get_object_or_404(Ticket, id=ticket_id)
    cost = get_object_or_404(TicketCost, id=cost_id, ticket=ticket)
    
    try:
        cost_id_save = cost.id
        cost_type_save = cost.cost_type
        amount_save = float(cost.amount)
        
        cost.delete()
        
        # Log action
        log_ticket_action(
            ticket.ticket_number,
            request.user.username,
            'deleted_cost',
            {'cost_id': cost_id_save, 'cost_type': cost_type_save, 'amount': amount_save}
        )
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@group_required("CSKHManager", "CSKHStaff")
@csrf_exempt
@require_http_methods(["POST"])
def api_upload_cost_files(request, ticket_id, cost_id):
    """
    API: Upload ảnh chứng từ cho một khoản chi phí (TicketCost).
    - Nhận multipart/form-data với field 'images'
    - Lưu file vào assets/billhoantien
    - Append path vào TicketCost.images
    """
    ticket = get_object_or_404(Ticket, id=ticket_id)
    cost = get_object_or_404(TicketCost, id=cost_id, ticket=ticket)

    if 'images' not in request.FILES:
        return JsonResponse({'success': False, 'error': 'Không có file nào được chọn'}, status=400)

    upload_dir = Path('assets/billhoantien')
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []

    for file in request.FILES.getlist('images'):
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        ext = os.path.splitext(file.name)[1]
        filename = f"{ts}{ext}"
        file_path = upload_dir / filename

        with open(file_path, 'wb') as f:
            for chunk in file.chunks():
                f.write(chunk)

        # Lưu path relative từ thư mục static
        rel_path = f"billhoantien/{filename}"
        saved_paths.append(rel_path)

    current = cost.images or []
    cost.images = current + saved_paths
    cost.save()

    # Nếu ticket đang ở trạng thái 'new' thì chuyển sang 'processing'
    if ticket.ticket_status == 'new':
        ticket.ticket_status = 'processing'
        ticket.save(update_fields=['ticket_status'])

    # Log action
    log_ticket_action(
        ticket.ticket_number,
        request.user.username,
        'uploaded_cost_files',
        {'cost_id': cost.id, 'files': saved_paths},
    )

    return JsonResponse({'success': True, 'files': saved_paths})


@group_required("CSKHManager", "CSKHStaff")
@csrf_exempt
@require_http_methods(["POST"])
def api_add_event(request, ticket_id):
    """
    API: Thêm Trouble & Event cho ticket.
    Body JSON:
        {
            "content": str,
            "tags": str (optional, comma separated)
        }
    """
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    try:
        data = json.loads(request.body)
        content = (data.get("content") or "").strip()
        tags = (data.get("tags") or "").strip()
        
        if not content:
            return JsonResponse({'success': False, 'error': 'Nội dung event không được để trống'}, status=400)
        
        event = TicketEvent.objects.create(
            ticket=ticket,
            content=content,
            tags=tags,
            created_by=request.user,
        )

        # Nếu ticket đang ở trạng thái 'new' thì chuyển sang 'processing'
        if ticket.ticket_status == 'new':
            ticket.ticket_status = 'processing'
            ticket.save(update_fields=['ticket_status'])

        # Nếu tags chứa "CHUYỂN BỘ PHẬN: KHO" và bộ phận hiện tại là CSKH -> chuyển sang KHO
        tag_list = [t.strip() for t in tags.split(',')] if tags else []
        if 'CHUYỂN BỘ PHẬN: KHO' in tag_list and ticket.depart == 'cskh':
            from_depart = ticket.depart
            ticket.depart = 'warehouse'
            ticket.save(update_fields=['depart'])

            log_ticket_action(
                ticket.ticket_number,
                request.user.username,
                'transferred_department',
                {
                    'from': from_depart,
                    'to': ticket.depart,
                    'reason': 'CHUYỂN BỘ PHẬN: KHO qua Trouble & Event',
                    'event_id': event.id,
                }
            )
        else:
            # Log action bình thường
            log_ticket_action(
                ticket.ticket_number,
                request.user.username,
                'added_event',
                {'event_id': event.id, 'tags': tags},
            )
        
        return JsonResponse({
            'success': True,
            'event': {
                'id': event.id,
                'content': event.content,
                'tags': event.tags,
                'created_by': (event.created_by.first_name or event.created_by.username) if event.created_by else '',
                'created_at': event.created_at.isoformat(),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["POST"])
def api_update_sugget_process(request, ticket_id):
    """
    API: Cập nhật / thêm hướng xử lý (sugget_process) cho ticket.
    Body JSON:
        {
            "sugget_main": str,           # Hướng xử lý chính
            "description": str (optional) # Giải thích ngắn gọn
        }
    Hệ thống tự ghi nhận:
        - user_id, user_name từ request.user
        - time: thời điểm cập nhật (ISO)
    """
    ticket = get_object_or_404(Ticket, id=ticket_id)

    try:
        data = json.loads(request.body)
        sugget_main = (data.get('sugget_main') or '').strip()
        description = (data.get('description') or '').strip()

        if not sugget_main:
            return JsonResponse({'success': False, 'error': 'Vui lòng chọn hướng xử lý chính'}, status=400)

        user = request.user
        now = timezone.now()

        old_sugget = ticket.sugget_process or {}

        # Lấy chức vụ/bộ phận từ last_name (ví dụ: QUẢN TRỊ VIÊN, CSKH, KHO_HN, ...)
        department = (getattr(user, "last_name", "") or "").strip()

        new_sugget = {
            'user_id': user.id,
            'user_name': user.first_name or user.username,
            'department': department,
            'sugget_main': sugget_main,
            'description': description,
            'time': now.isoformat(),
        }

        ticket.sugget_process = new_sugget
        ticket.save(update_fields=['sugget_process', 'updated_at'])

        # Nếu ticket đang ở trạng thái 'new' thì chuyển sang 'processing'
        if ticket.ticket_status == 'new':
            ticket.ticket_status = 'processing'
            ticket.save(update_fields=['ticket_status'])

        # Log action
        log_ticket_action(
            ticket.ticket_number,
            user.username,
            'updated_sugget_process',
            {
                'old': old_sugget,
                'new': new_sugget,
            }
        )

        return JsonResponse({'success': True, 'sugget_process': new_sugget})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["POST"])
def api_update_status(request, ticket_id):
    """API: Cập nhật status cho ticket"""
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    try:
        data = json.loads(request.body)
        new_status = data.get('status', '').strip()

        valid_status = dict(Ticket.STATUS_CHOICES).keys()
        if new_status not in valid_status:
            return JsonResponse({'success': False, 'error': 'Status không hợp lệ'}, status=400)

        # Không cho phép đặt lại về 'new' qua API (trạng thái khởi tạo)
        if new_status == 'new' and ticket.ticket_status != 'new':
            return JsonResponse({'success': False, 'error': 'Không thể chuyển trạng thái về Mới'}, status=400)

        old_status = ticket.ticket_status
        ticket.ticket_status = new_status
        
        # Cập nhật resolved_at nếu status = resolved
        if new_status == 'resolved' and not ticket.resolved_at:
            from django.utils import timezone
            ticket.resolved_at = timezone.now()
        
        # Cập nhật closed_at nếu status = closed
        if new_status == 'closed' and not ticket.closed_at:
            from django.utils import timezone
            ticket.closed_at = timezone.now()
        
        ticket.save()
        
        # Log action
        log_ticket_action(
            ticket.ticket_number,
            request.user.username,
            'updated_status',
            {'old': old_status, 'new': new_status}
        )
        
        return JsonResponse({'success': True, 'status': new_status})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["GET"])
def api_get_reason_types(request):
    """API: Lấy danh sách reason types theo source"""
    source_reason = request.GET.get('source_reason', '')
    
    if not source_reason:
        return JsonResponse({'success': False, 'error': 'Thiếu source_reason'}, status=400)

    # Ưu tiên đọc mapping từ file config CSKH (cấu hình Admin)
    try:
        from settings.services.cskh_ticket_config_service import CSKHTicketConfigService

        config = CSKHTicketConfigService.get_config()
        raw_types = config.get("loai_loi", []) or []

        # Định dạng mới: "Nguồn lỗi: Loại lỗi"
        # Ví dụ: "Lỗi kho: Gửi thiếu" → source = "Lỗi kho", type = "Gửi thiếu"
        mapped_types = []
        for item in raw_types:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if not text:
                continue
            if ":" in text:
                src, typ = [p.strip() for p in text.split(":", 1)]
                if src == source_reason and typ:
                    mapped_types.append(typ)

        # Nếu config đã trả được danh sách theo source → dùng luôn
        if mapped_types:
            return JsonResponse({'success': True, 'types': mapped_types})

        # Fallback: nếu chưa có mapping theo source, dùng toàn bộ loai_loi (bỏ phần "Nguồn lỗi:" nếu có)
        fallback_types = []
        for item in raw_types:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if not text:
                continue
            if ":" in text:
                _, typ = [p.strip() for p in text.split(":", 1)]
                if typ:
                    fallback_types.append(typ)
            else:
                fallback_types.append(text)

        if fallback_types:
            return JsonResponse({'success': True, 'types': fallback_types})

    except Exception:
        # Nếu có lỗi khi đọc config, fallback về settings cũ
        pass

    # Fallback cuối: logic cũ trong cskh/settings.py
    types = get_reason_types_by_source(source_reason)
    return JsonResponse({'success': True, 'types': types})


@csrf_exempt
@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["POST"])
def api_update_process_order(request, ticket_id):
    """
    API: Gắn/cập nhật đơn xử lý (order_process) cho ticket.
    Body JSON:
        {
            "order_id": int,
            "order_code": str,
            "reference_number": str
        }
    """
    ticket = get_object_or_404(Ticket, id=ticket_id)

    try:
        data = json.loads(request.body)
        order_id_raw = data.get('order_id')
        order_code = (data.get('order_code') or '').strip()
        reference_number = (data.get('reference_number') or '').strip()

        try:
            order_id = int(order_id_raw)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'order_id không hợp lệ'}, status=400)

        # Xác thực order tồn tại (dùng TicketService, không gọi API lạ)
        ticket_service = TicketService()
        try:
            order = ticket_service.order_service.get_order_dto(order_id)
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Không tìm thấy đơn xử lý: {e}'}, status=400)

        # Dùng extract_order_info để đảm bảo code/reference_number chuẩn
        order_info = ticket_service.extract_order_info(order)

        # Kiểm tra xem đã có ticket nào khác đang dùng đơn này hay chưa
        # - order_id (thông tin đơn hàng)
        # - hoặc process_order_id (thông tin đơn xử lý)
        process_order_id = order_info.get('order_id')
        
        existing_ticket = None
        if process_order_id:
            existing_ticket = Ticket.objects.filter(
                Q(order_id=process_order_id) | Q(process_order_id=process_order_id)
            ).exclude(id=ticket.id).first()
        
        if existing_ticket:
            return JsonResponse({
                'success': False, 
                'error': f'Đơn xử lý này đã được liên kết với ticket khác: {existing_ticket.ticket_number}'
            }, status=400)

        old_values = {
            'process_order_id': ticket.process_order_id,
            'process_order_code': ticket.process_order_code,
            'process_reference_number': ticket.process_reference_number,
        }

        ticket.process_order_id = order_info['order_id']
        ticket.process_order_code = order_info['order_code']
        ticket.process_reference_number = order_info['reference_number']
        ticket.save()

        # Log action
        log_ticket_action(
            ticket.ticket_number,
            request.user.username,
            'updated_process_order',
            {
                'old': old_values,
                'new': {
                    'process_order_id': ticket.process_order_id,
                    'process_order_code': ticket.process_order_code,
                    'process_reference_number': ticket.process_reference_number,
                }
            }
        )

        return JsonResponse({'success': True, 'order': order_info})
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["POST"])
def api_update_responsible(request, ticket_id):
    """
    API: Cập nhật thông tin người chịu trách nhiệm cho ticket.
    Body JSON:
        {
            "responsible_user_id": int (optional),
            "responsible_department": str (optional),
            "responsible_note": str (optional)
        }
    """
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    try:
        data = json.loads(request.body)
        responsible_user_id = data.get('responsible_user_id')
        responsible_department = (data.get('responsible_department') or '').strip()
        responsible_note = (data.get('responsible_note') or '').strip()
        
        # Xử lý responsible_user_id
        if responsible_user_id:
            try:
                responsible_user_id = int(responsible_user_id)
                from django.contrib.auth.models import User
                responsible_user = User.objects.get(id=responsible_user_id)
                ticket.responsible_user = responsible_user
            except (TypeError, ValueError, User.DoesNotExist):
                ticket.responsible_user = None
        else:
            ticket.responsible_user = None
        
        ticket.responsible_department = responsible_department
        ticket.responsible_note = responsible_note
        ticket.save()
        
        # Log action
        log_ticket_action(
            ticket.ticket_number,
            request.user.username,
            'updated_responsible',
            {
                'responsible_user_id': responsible_user_id,
                'responsible_department': responsible_department,
                'responsible_note': responsible_note[:100] if responsible_note else '',  # Chỉ log 100 ký tự đầu
            }
        )
        
        return JsonResponse({
            'success': True,
            'responsible_user': {
                'id': ticket.responsible_user.id if ticket.responsible_user else None,
                'name': (ticket.responsible_user.first_name or ticket.responsible_user.username) if ticket.responsible_user else None,
            } if ticket.responsible_user else None,
            'responsible_department': ticket.responsible_department,
            'responsible_note': ticket.responsible_note,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["GET"])
def api_search_order(request):
    """API: Tìm order theo search key"""
    from .services.ticket_service import TicketService
    from django.urls import reverse
    
    search_key = request.GET.get('q', '').strip()
    
    if not search_key:
        return JsonResponse({'success': False, 'error': 'Thiếu search key'}, status=400)
    
    # Endpoint cũ: vẫn giữ behavior tìm 1 đơn để dùng cho các màn chi tiết / đơn xử lý
    ticket_service = TicketService()
    order = ticket_service.find_order(search_key)

    if not order:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy đơn hàng'}, status=404)

    order_info = ticket_service.extract_order_info(order)
    
    # Kiểm tra xem đơn hàng này đã có ticket chưa
    # Chỉ tính là trùng khi order_id đã được gắn vào:
    # - Thông tin đơn hàng (order_id)
    # - Hoặc thông tin đơn xử lý (process_order_id)
    final_order_id = order_info.get('order_id')
    
    existing_ticket = None
    if final_order_id:
        existing_ticket = Ticket.objects.filter(
            Q(order_id=final_order_id) | Q(process_order_id=final_order_id)
        ).first()
    
    if existing_ticket:
        ticket_url = reverse('cskh:ticket_detail', args=[existing_ticket.id])
        return JsonResponse({
            'success': False, 
            'error': f'Đơn hàng này đã có ticket: {existing_ticket.ticket_number}',
            'existing_ticket': {
                'id': existing_ticket.id,
                'ticket_number': existing_ticket.ticket_number,
                'url': ticket_url
            }
        }, status=400)
    
    # Lấy thông tin variants từ order (bao gồm giá bán & số lượng để phục vụ tính thiệt hại)
    variants = []
    variant_ids = set()
    if hasattr(order, 'line_items') and order.line_items:
        for item in order.line_items:
            vid = item.variant_id
            variants.append({
                'variant_id': vid,
                'product_name': item.product_name or '',
                'variant_name': item.variant_name or '',
                'sku': item.sku or '',
                'price': float(getattr(item, 'price', 0) or 0),
                'quantity': float(getattr(item, 'quantity', 0) or 0),
            })
            if vid:
                variant_ids.add(vid)

    # Gọi Sapo để lấy image_url cho từng variant
    image_map = {}
    if variant_ids:
        sapo = get_sapo_client()
        core_api = sapo.core
        for vid in variant_ids:
            try:
                raw = core_api.get_variant_raw(vid)
                variant_data = raw.get("variant") or {}
                images = variant_data.get("images") or []
                if images:
                    url = images[0].get("full_path")
                    if url:
                        image_map[vid] = url
            except Exception:
                continue

    # Gắn image_url vào variants
    for v in variants:
        vid = v.get("variant_id")
        v["image_url"] = image_map.get(vid, "")
    
    return JsonResponse({
        'success': True,
        'order': order_info,
        'variants': variants
    })


@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["GET"])
def api_search_order_multi(request):
    """
    API: Tìm nhiều orders theo search key (dùng cho màn tạo ticket).
    Trả về danh sách đơn đơn giản để người dùng chọn:
        [
            {
                "order_id": ...,
                "order_code": ...,
                "reference_number": ...,
                "warehouse": ...,
                "channel": ...,
                "order_status": ...,
                "order_status_label": ...,
                "total_to_pay": float,
            },
            ...
        ]
    """
    from .services.ticket_service import TicketService

    search_key = request.GET.get('q', '').strip()
    if not search_key:
        return JsonResponse({'success': False, 'error': 'Thiếu search key'}, status=400)

    ticket_service = TicketService()
    orders = ticket_service.search_orders_for_ticket(search_key, limit=10)

    if not orders:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy đơn hàng'}, status=404)

    items = []
    for order in orders:
        try:
            info = ticket_service.extract_order_info(order)
            items.append({
                'order_id': info.get('order_id'),
                'order_code': info.get('order_code') or '',
                'reference_number': info.get('reference_number') or '',
                'warehouse': info.get('warehouse') or '',
                'channel': info.get('channel') or '',
                'order_status': info.get('order_status') or '',
                'order_status_label': info.get('order_status_label') or info.get('order_status') or '',
                # Khách phải trả – dùng tổng đơn hàng (có thể tinh chỉnh sau nếu cần)
                'total_to_pay': float(getattr(order, 'total', 0) or 0),
            })
        except Exception as e:
            # Bỏ qua đơn lỗi, tiếp tục với đơn khác
            continue

    return JsonResponse({'success': True, 'orders': items})


@group_required("CSKHManager", "CSKHStaff")
@csrf_exempt
@require_http_methods(["POST"])
def api_update_note(request, ticket_id):
    """(Legacy) API: Cập nhật ghi chú cho ticket - không còn dùng cho UI mới (Trouble & Event)."""
    return JsonResponse({'success': False, 'error': 'deprecated'}, status=400)


@csrf_exempt
@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["POST"])
def api_delete_ticket(request, ticket_id):
    """
    API: Xóa ticket.
    
    POST /cskh/api/tickets/<ticket_id>/delete/
    """
    try:
        ticket = get_object_or_404(Ticket, id=ticket_id)
        
        # Lưu thông tin ticket trước khi xóa để log
        ticket_number = ticket.ticket_number
        order_code = ticket.order_code
        
        # Xóa ticket (cascade sẽ xóa các related objects như costs, events)
        ticket.delete()
        
        # Log action
        log_ticket_action(
            ticket_number,
            request.user.username,
            'deleted',
            {'order_code': order_code}
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Ticket {ticket_number} đã được xóa thành công'
        })
        
    except Exception as e:
        logger.error(f"Error deleting ticket {ticket_id}: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@group_required("CSKHManager", "CSKHStaff")
@csrf_exempt
@require_http_methods(["POST"])
def api_save_ticket(request, ticket_id):
    """
    API: Lưu toàn bộ thông tin ticket (reason, status, note, variants_issue, etc.)
    Nhận JSON:
        {
            "ticket_type": str,
            "source_reason": str,
            "reason_type": str,
            "ticket_status": str,
            "note": str,
            "variants_issue": [int, ...]  # List of variant_id
        }
    """
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    try:
        data = json.loads(request.body)
        
        old_values = {
            "ticket_type": ticket.ticket_type,
            "source_reason": ticket.source_reason,
            "reason_type": ticket.reason_type,
            "ticket_status": ticket.ticket_status,
            "note": ticket.note,
            "variants_issue": ticket.variants_issue or [],
        }
        
        # Cập nhật các trường
        if "ticket_type" in data:
            ticket.ticket_type = data.get("ticket_type", ticket.ticket_type)
        if "source_reason" in data:
            ticket.source_reason = data.get("source_reason", ticket.source_reason)
        if "reason_type" in data:
            ticket.reason_type = data.get("reason_type", ticket.reason_type)
        
        new_status = data.get("ticket_status", ticket.ticket_status)
        if new_status in dict(Ticket.STATUS_CHOICES).keys():
            ticket.ticket_status = new_status
            # Cập nhật resolved_at nếu status = resolved
            if new_status == 'resolved' and not ticket.resolved_at:
                from django.utils import timezone
                ticket.resolved_at = timezone.now()
            # Cập nhật closed_at nếu status = closed
            if new_status == 'closed' and not ticket.closed_at:
                from django.utils import timezone
                ticket.closed_at = timezone.now()
        
        if "note" in data:
            ticket.note = data.get("note", ticket.note)
        
        # Cập nhật variants_issue
        if "variants_issue" in data:
            variants_issue = data.get("variants_issue", [])
            # Đảm bảo là list of integers
            if isinstance(variants_issue, list):
                ticket.variants_issue = [int(v) for v in variants_issue if v]
            else:
                ticket.variants_issue = []
        
        ticket.save()
        
        new_values = {
            "ticket_type": ticket.ticket_type,
            "source_reason": ticket.source_reason,
            "reason_type": ticket.reason_type,
            "ticket_status": ticket.ticket_status,
            "note": ticket.note,
            "variants_issue": ticket.variants_issue or [],
        }
        
        # Log action
        log_ticket_action(
            ticket.ticket_number,
            request.user.username,
            "saved_ticket",
            {"old": old_values, "new": new_values},
        )
        
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


# ========================
# FEEDBACK API ENDPOINTS
# ========================

@csrf_exempt
@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["POST"])
def api_sync_feedbacks(request):
    """
    API: Sync feedbacks từ Shopee API vào database.
    Lấy đánh giá 7 ngày gần nhất của tất cả các shop.
    
    POST /cskh/api/feedback/sync/
    Body: {
        "days": 7 (optional, default: 7),
        "page_size": 50 (optional, default: 50)
    }
    
    Hoặc để tương thích với code cũ, vẫn hỗ trợ:
    {
        "tenant_id": 1262,
        "connection_ids": "10925,134366,..." (optional),
        "rating": "1,2,3,4,5" (optional)
    }
    """
    try:
        from .services.feedback_service import FeedbackService
        from core.sapo_client import get_sapo_client
        
        data = json.loads(request.body)
        
        # Kiểm tra xem có dùng Shopee API hay Sapo MP (tương thích ngược)
        use_shopee_api = data.get("use_shopee_api", True)  # Mặc định dùng Shopee API
        tenant_id = data.get("tenant_id")
        
        if use_shopee_api and not tenant_id:
            # Dùng Shopee API mới
            days = data.get("days", 3)  # Mặc định 3 ngày
            page_size = data.get("page_size", 50)  # Mặc định 50 items/page
            
            # Initialize service
            sapo_client = get_sapo_client()
            feedback_service = FeedbackService(sapo_client)
            
            # Sync feedbacks từ Shopee API
            result = feedback_service.sync_feedbacks_from_shopee(
                days=days,
                page_size=page_size
            )
            
            return JsonResponse(result)
        else:
            # Dùng Sapo MP (tương thích ngược)
            if not tenant_id:
                return JsonResponse({
                    "success": False,
                    "error": "tenant_id is required for Sapo MP sync"
                }, status=400)
            
            connection_ids = data.get("connection_ids")
            rating = data.get("rating", "1,2,3,4,5")
            max_feedbacks = data.get("max_feedbacks", 5000)
            num_threads = data.get("num_threads", 25)
            
            # Initialize service
            sapo_client = get_sapo_client()
            feedback_service = FeedbackService(sapo_client)
            
            # Sync feedbacks với multi-threading
            result = feedback_service.sync_feedbacks(
                tenant_id=tenant_id,
                connection_ids=connection_ids,
                rating=rating,
                max_feedbacks=max_feedbacks,
                num_threads=num_threads
            )
            
            return JsonResponse(result)
        
    except json.JSONDecodeError:
        return JsonResponse({
            "success": False,
            "error": "Invalid JSON in request body"
        }, status=400)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in api_sync_feedbacks: {e}", exc_info=True)
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@csrf_exempt
@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["POST"])
def api_reply_feedback(request, feedback_id):
    """
    API: Gửi phản hồi cho feedback.
    
    POST /cskh/api/feedback/<feedback_id>/reply/
    Body: {
        "reply_content": "...",
        "tenant_id": 1262
    }
    """
    try:
        from .services.feedback_service import FeedbackService
        from core.sapo_client import get_sapo_client
        
        feedback = get_object_or_404(Feedback, id=feedback_id)
        
        data = json.loads(request.body)
        reply_content = data.get("reply_content", "").strip()
        tenant_id = data.get("tenant_id")
        
        if not reply_content:
            return JsonResponse({
                "success": False,
                "error": "reply_content is required"
            }, status=400)
        
        if not tenant_id:
            return JsonResponse({
                "success": False,
                "error": "tenant_id is required"
            }, status=400)
        
        # Initialize service
        sapo_client = get_sapo_client()
        feedback_service = FeedbackService(sapo_client)
        
        # Reply feedback
        result = feedback_service.reply_feedback(
            feedback_id=feedback_id,
            reply_content=reply_content,
            tenant_id=tenant_id,
            user=request.user
        )
        
        return JsonResponse(result)
        
    except json.JSONDecodeError:
        return JsonResponse({
            "success": False,
            "error": "Invalid JSON in request body"
        }, status=400)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in api_reply_feedback: {e}", exc_info=True)
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@csrf_exempt
@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["POST"])
def api_create_ticket_from_feedback(request, feedback_id):
    """
    API: Tạo ticket từ bad review.
    
    POST /cskh/api/feedback/<feedback_id>/create-ticket/
    """
    try:
        from .services.feedback_service import FeedbackService
        from core.sapo_client import get_sapo_client
        
        feedback = get_object_or_404(Feedback, id=feedback_id)
        
        if feedback.ticket:
            return JsonResponse({
                "success": False,
                "error": "Feedback đã có ticket rồi",
                "ticket_id": feedback.ticket.id,
                "ticket_number": feedback.ticket.ticket_number
            }, status=400)
        
        # Initialize service
        sapo_client = get_sapo_client()
        feedback_service = FeedbackService(sapo_client)
        
        # Create ticket
        result = feedback_service.create_ticket_from_bad_review(
            feedback_id=feedback_id,
            user=request.user
        )
        
        return JsonResponse(result)
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in api_create_ticket_from_feedback: {e}", exc_info=True)
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@csrf_exempt
@group_required("CSKHManager", "CSKHStaff")
@require_http_methods(["POST"])
def api_ai_suggest_reply(request, feedback_id):
    """
    API: AI suggest reply cho feedback (placeholder - sẽ implement sau).
    
    POST /cskh/api/feedback/<feedback_id>/ai-suggest/
    Body: {
        "step": "name" | "reply"  # Bước xử lý: name (tên, giới tính) hoặc reply (gợi ý phản hồi)
    }
    """
    try:
        feedback = get_object_or_404(Feedback, id=feedback_id)
        
        data = json.loads(request.body)
        step = data.get("step", "reply")
        
        # TODO: Implement AI processing
        # Bước 1: Xử lý tên, giới tính
        # Bước 2: Gợi ý phản hồi
        
        if step == "name":
            # Placeholder: AI xử lý tên và giới tính
            return JsonResponse({
                "success": True,
                "suggested_name": feedback.buyer_user_name,
                "suggested_gender": "unknown",  # male, female, unknown
                "message": "AI processing name and gender (placeholder)"
            })
        elif step == "reply":
            # Placeholder: AI gợi ý phản hồi
            if feedback.rating == 5:
                suggested_reply = f"Cảm ơn bạn {feedback.buyer_user_name} đã đánh giá tốt về sản phẩm! Chúng tôi rất vui khi được phục vụ bạn."
            else:
                suggested_reply = f"Xin chào {feedback.buyer_user_name}, chúng tôi rất tiếc về trải nghiệm của bạn. Vui lòng liên hệ CSKH để được hỗ trợ tốt hơn."
            
            return JsonResponse({
                "success": True,
                "suggested_reply": suggested_reply,
                "message": "AI suggested reply (placeholder)"
            })
        else:
            return JsonResponse({
                "success": False,
                "error": "Invalid step. Use 'name' or 'reply'"
            }, status=400)
        
    except json.JSONDecodeError:
        return JsonResponse({
            "success": False,
            "error": "Invalid JSON in request body"
        }, status=400)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in api_ai_suggest_reply: {e}", exc_info=True)
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


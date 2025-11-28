"""
API endpoints cho Ticket operations
"""
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
import os
from pathlib import Path
from datetime import datetime

from .models import Ticket, TicketCost, TicketEvent
from .settings import get_reason_types_by_source, get_cost_types
from .utils import log_ticket_action
from core.sapo_client import get_sapo_client
from .services.ticket_service import TicketService


@csrf_exempt
@login_required
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
@login_required
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


@login_required
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


@login_required
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


@login_required
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
                'created_by': event.created_by.get_full_name() or event.created_by.username if event.created_by else '',
                'created_at': event.created_at.isoformat(),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@login_required
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


@login_required
@require_http_methods(["GET"])
def api_get_reason_types(request):
    """API: Lấy danh sách reason types theo source"""
    source_reason = request.GET.get('source_reason', '')
    
    if not source_reason:
        return JsonResponse({'success': False, 'error': 'Thiếu source_reason'}, status=400)
    
    types = get_reason_types_by_source(source_reason)
    return JsonResponse({'success': True, 'types': types})


@csrf_exempt
@login_required
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

        # Kiểm tra xem đã có ticket nào khác với cùng process_order_code hoặc process_reference_number chưa
        process_order_code = order_info.get('order_code', '')
        process_reference_number = order_info.get('reference_number', '')
        
        existing_ticket = None
        if process_order_code:
            existing_ticket = Ticket.objects.filter(
                process_order_code=process_order_code
            ).exclude(id=ticket.id).first()
        if not existing_ticket and process_reference_number:
            existing_ticket = Ticket.objects.filter(
                process_reference_number=process_reference_number
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
@login_required
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
                'name': ticket.responsible_user.get_full_name() if ticket.responsible_user else None,
            } if ticket.responsible_user else None,
            'responsible_department': ticket.responsible_department,
            'responsible_note': ticket.responsible_note,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET"])
def api_search_order(request):
    """API: Tìm order theo search key"""
    from .services.ticket_service import TicketService
    from django.urls import reverse
    
    search_key = request.GET.get('q', '').strip()
    
    if not search_key:
        return JsonResponse({'success': False, 'error': 'Thiếu search key'}, status=400)
    
    ticket_service = TicketService()
    order = ticket_service.find_order(search_key)
    
    if not order:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy đơn hàng'}, status=404)
    
    order_info = ticket_service.extract_order_info(order)
    
    # Kiểm tra xem đơn hàng này đã có ticket chưa
    final_order_code = order_info.get('order_code', '')
    final_reference_number = order_info.get('reference_number', '')
    
    existing_ticket = None
    if final_order_code:
        existing_ticket = Ticket.objects.filter(order_code=final_order_code).first()
    if not existing_ticket and final_reference_number:
        existing_ticket = Ticket.objects.filter(reference_number=final_reference_number).first()
    
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


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_update_note(request, ticket_id):
    """(Legacy) API: Cập nhật ghi chú cho ticket - không còn dùng cho UI mới (Trouble & Event)."""
    return JsonResponse({'success': False, 'error': 'deprecated'}, status=400)


@login_required
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


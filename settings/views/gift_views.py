# settings/views/gift_views.py
"""
Views for Gift Rule management
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import user_passes_test
from ..services.gift_service import GiftRuleService
from ..models import GiftRule


def is_admin(user):
    return user.is_active and user.is_superuser


@user_passes_test(is_admin)
def gift_list(request):
    """
    Danh sách tất cả Gift Rules với filtering
    """
    # Get filter parameters
    active_filter = request.GET.get('active', 'all')
    scope_filter = request.GET.get('scope', 'all')
    
    # Build queryset
    rules = GiftRule.objects.prefetch_related('gifts').all()
    
    if active_filter == 'active':
        rules = rules.filter(is_active=True)
    elif active_filter == 'inactive':
        rules = rules.filter(is_active=False)
    
    if scope_filter in ['order', 'line']:
        rules = rules.filter(scope=scope_filter)
    
    # Count statistics
    total_count = GiftRule.objects.count()
    active_count = GiftRule.objects.filter(is_active=True).count()
    
    context = {
        'rules': rules,
        'total_count': total_count,
        'active_count': active_count,
        'active_filter': active_filter,
        'scope_filter': scope_filter,
    }
    
    return render(request, 'settings/gift_list.html', context)


@user_passes_test(is_admin)
@require_http_methods(["GET", "POST"])
def gift_create(request):
    """
    Tạo Gift Rule mới
    """
    if request.method == "POST":
        # Parse form data
        data = {
            'name': request.POST.get('name'),
            'scope': request.POST.get('scope'),
            'shop_code': request.POST.get('shop_code') or None,
            'priority': int(request.POST.get('priority', 0)),
            'is_active': request.POST.get('is_active') == 'on',
            'stop_further': request.POST.get('stop_further') == 'on',
        }
        
        # Parse scope-specific fields
        if data['scope'] == 'order':
            min_total = request.POST.get('min_order_total')
            max_total = request.POST.get('max_order_total')
            data['min_order_total'] = int(min_total) if min_total else None
            data['max_order_total'] = int(max_total) if max_total else None
            data['required_variant_ids'] = []
            data['required_min_qty'] = None
            data['required_max_qty'] = None
        else:  # line
            # Parse variant IDs from textarea (one per line)
            variant_ids_text = request.POST.get('required_variant_ids', '')
            variant_ids = []
            if variant_ids_text:
                for line in variant_ids_text.strip().split('\n'):
                    line = line.strip()
                    if line and line.isdigit():
                        variant_ids.append(int(line))
            data['required_variant_ids'] = variant_ids
            
            min_qty = request.POST.get('required_min_qty')
            max_qty = request.POST.get('required_max_qty')
            data['required_min_qty'] = int(min_qty) if min_qty else None
            data['required_max_qty'] = int(max_qty) if max_qty else None
            data['min_order_total'] = None
            data['max_order_total'] = None
        
        # Parse datetime fields
        start_at = request.POST.get('start_at')
        end_at = request.POST.get('end_at')
        data['start_at'] = start_at if start_at else None
        data['end_at'] = end_at if end_at else None
        
        # Parse gifts
        gift_variant_ids = request.POST.getlist('gift_variant_id[]')
        gift_qtys = request.POST.getlist('gift_qty[]')
        match_quantities = request.POST.getlist('match_quantity[]')
        
        gifts = []
        if not match_quantities:
            match_quantities = ['0'] * len(gift_variant_ids)

        for variant_id, qty, match_qty in zip(gift_variant_ids, gift_qtys, match_quantities):
            if variant_id and qty:
                gifts.append({
                    'gift_variant_id': int(variant_id),
                    'gift_qty': int(qty),
                    'match_quantity': match_qty == '1'
                })
        data['gifts'] = gifts
        
        # Validate
        errors = GiftRuleService.validate_rule_data(data)
        if errors:
            for field, error in errors.items():
                messages.error(request, f"{field}: {error}")
            return render(request, 'settings/gift_form.html', {
                'form_data': data,
                'is_edit': False
            })
        
        # Create rule
        try:
            rule = GiftRuleService.create_rule(data)
            messages.success(request, f"Đã tạo gift rule '{rule.name}' thành công!")
            return redirect('gift_list')
        except Exception as e:
            messages.error(request, f"Lỗi khi tạo rule: {str(e)}")
            return render(request, 'settings/gift_form.html', {
                'form_data': data,
                'is_edit': False
            })
    
    # GET: Show form
    return render(request, 'settings/gift_form.html', {'is_edit': False})


@user_passes_test(is_admin)
@require_http_methods(["GET", "POST"])
def gift_edit(request, rule_id):
    """
    Chỉnh sửa Gift Rule
    """
    rule = get_object_or_404(GiftRule.objects.prefetch_related('gifts'), id=rule_id)
    
    if request.method == "POST":
        # Parse form data (same as create)
        data = {
            'name': request.POST.get('name'),
            'scope': request.POST.get('scope'),
            'shop_code': request.POST.get('shop_code') or None,
            'priority': int(request.POST.get('priority', 0)),
            'is_active': request.POST.get('is_active') == 'on',
            'stop_further': request.POST.get('stop_further') == 'on',
        }
        
        # Parse scope-specific fields
        if data['scope'] == 'order':
            min_total = request.POST.get('min_order_total')
            max_total = request.POST.get('max_order_total')
            data['min_order_total'] = int(min_total) if min_total else None
            data['max_order_total'] = int(max_total) if max_total else None
            data['required_variant_ids'] = []
            data['required_min_qty'] = None
            data['required_max_qty'] = None
        else:  # line
            # Parse variant IDs from textarea (one per line)
            variant_ids_text = request.POST.get('required_variant_ids', '')
            variant_ids = []
            if variant_ids_text:
                for line in variant_ids_text.strip().split('\n'):
                    line = line.strip()
                    if line and line.isdigit():
                        variant_ids.append(int(line))
            data['required_variant_ids'] = variant_ids
            
            min_qty = request.POST.get('required_min_qty')
            max_qty = request.POST.get('required_max_qty')
            data['required_min_qty'] = int(min_qty) if min_qty else None
            data['required_max_qty'] = int(max_qty) if max_qty else None
            data['min_order_total'] = None
            data['max_order_total'] = None
        
        # Parse datetime fields
        start_at = request.POST.get('start_at')
        end_at = request.POST.get('end_at')
        data['start_at'] = start_at if start_at else None
        data['end_at'] = end_at if end_at else None
        
        # Parse gifts
        gift_variant_ids = request.POST.getlist('gift_variant_id[]')
        gift_qtys = request.POST.getlist('gift_qty[]')
        
        gifts = []
        for variant_id, qty in zip(gift_variant_ids, gift_qtys):
            if variant_id and qty:
                gifts.append({
                    'gift_variant_id': int(variant_id),
                    'gift_qty': int(qty)
                })
        data['gifts'] = gifts
        
        # Validate
        errors = GiftRuleService.validate_rule_data(data)
        if errors:
            for field, error in errors.items():
                messages.error(request, f"{field}: {error}")
            return render(request, 'settings/gift_form.html', {
                'rule': rule,
                'form_data': data,
                'is_edit': True
            })
        
        # Update rule
        try:
            updated_rule = GiftRuleService.update_rule(rule_id, data)
            messages.success(request, f"Đã cập nhật gift rule '{updated_rule.name}' thành công!")
            return redirect('gift_list')
        except Exception as e:
            messages.error(request, f"Lỗi khi cập nhật rule: {str(e)}")
            return render(request, 'settings/gift_form.html', {
                'rule': rule,
                'form_data': data,
                'is_edit': True
            })
    
    # GET: Show form with existing data
    return render(request, 'settings/gift_form.html', {
        'rule': rule,
        'is_edit': True
    })


@user_passes_test(is_admin)
@require_http_methods(["POST"])
def gift_delete(request, rule_id):
    """
    Xóa Gift Rule
    """
    rule = get_object_or_404(GiftRule, id=rule_id)
    rule_name = rule.name
    
    if GiftRuleService.delete_rule(rule_id):
        messages.success(request, f"Đã xóa gift rule '{rule_name}' thành công!")
    else:
        messages.error(request, "Không thể xóa gift rule!")
    
    return redirect('gift_list')

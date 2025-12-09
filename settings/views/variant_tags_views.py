# settings/views/variant_tags_views.py
"""
Views để quản lý Variant Tags (plan_tags).
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q

from kho.utils import admin_only
from ..models import VariantTag


@admin_only
def variant_tags_list(request):
    """
    Danh sách tất cả variant tags.
    """
    tags = VariantTag.objects.all().order_by('tags_name')
    
    return render(request, 'settings/variant_tags_list.html', {
        'tags': tags,
        'title': 'Quản lý Variant Tags'
    })


@admin_only
@require_http_methods(["GET", "POST"])
def variant_tag_create(request):
    """
    Tạo tag mới.
    """
    if request.method == "POST":
        tags_name = request.POST.get("tags_name", "").strip()
        color = request.POST.get("color", "blue").strip()
        
        if not tags_name:
            messages.error(request, "Tên tag không được để trống.")
            return redirect('variant_tags_list')
        
        # Kiểm tra trùng tên
        if VariantTag.objects.filter(tags_name=tags_name).exists():
            messages.error(request, f"Tag '{tags_name}' đã tồn tại.")
            return redirect('variant_tags_list')
        
        # Tạo tag mới
        tag = VariantTag.objects.create(tags_name=tags_name, color=color)
        messages.success(request, f"Đã tạo tag '{tags_name}' thành công.")
        return redirect('variant_tags_list')
    
    # GET: Hiển thị form (nếu cần)
    return redirect('variant_tags_list')


@admin_only
@require_http_methods(["GET", "POST"])
def variant_tag_edit(request, tag_id):
    """
    Sửa tag.
    """
    tag = get_object_or_404(VariantTag, id=tag_id)
    
    if request.method == "POST":
        tags_name = request.POST.get("tags_name", "").strip()
        color = request.POST.get("color", "blue").strip()
        
        if not tags_name:
            messages.error(request, "Tên tag không được để trống.")
            return redirect('variant_tags_list')
        
        # Kiểm tra trùng tên (trừ chính nó)
        if VariantTag.objects.filter(tags_name=tags_name).exclude(id=tag_id).exists():
            messages.error(request, f"Tag '{tags_name}' đã tồn tại.")
            return redirect('variant_tags_list')
        
        # Cập nhật
        tag.tags_name = tags_name
        tag.color = color
        tag.save()
        messages.success(request, f"Đã cập nhật tag thành công.")
        return redirect('variant_tags_list')
    
    # GET: Trả về JSON để edit inline (hoặc redirect)
    return JsonResponse({
        'id': tag.id,
        'tags_name': tag.tags_name,
        'color': tag.color
    })


@admin_only
@require_http_methods(["POST"])
@csrf_exempt
def variant_tag_delete(request, tag_id):
    """
    Xóa tag.
    """
    tag = get_object_or_404(VariantTag, id=tag_id)
    tag_name = tag.tags_name
    tag.delete()
    
    messages.success(request, f"Đã xóa tag '{tag_name}' thành công.")
    
    if request.headers.get('Content-Type') == 'application/json':
        return JsonResponse({
            'status': 'success',
            'message': f"Đã xóa tag '{tag_name}' thành công."
        })
    
    return redirect('variant_tags_list')


@admin_only
@csrf_exempt
def variant_tags_api_list(request):
    """
    API endpoint để lấy danh sách tags (JSON).
    Dùng cho dropdown/select trong variant edit form.
    """
    tags = VariantTag.objects.all().order_by('tags_name')
    
    return JsonResponse({
        'status': 'success',
        'tags': [
            {
                'id': tag.id,
                'tags_name': tag.tags_name,
                'color': tag.color
            }
            for tag in tags
        ]
    })


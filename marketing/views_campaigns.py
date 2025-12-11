# marketing/views_campaigns.py
"""
Campaigns Module - Views
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, Http404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, Prefetch
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal
import json
import csv
import io
from datetime import datetime

from marketing.models import (
    Campaign, CampaignProduct, CampaignCreator,
    Brand, Product, Creator
)
from marketing.utils import marketing_permission_required
from marketing.forms_campaigns import (
    CampaignForm, CampaignProductForm, CampaignCreatorForm,
    BulkAddProductsForm, BulkAddCreatorsForm
)
from marketing.services.campaign_metrics_service import CampaignMetricsService


# ==================== PERMISSIONS HELPERS ====================

def can_edit_campaign(user, campaign=None):
    """Admin và MarketingManager/Staff có thể edit campaigns"""
    if user.is_superuser or user.groups.filter(name="Admin").exists():
        return True
    if user.groups.filter(name__in=["MarketingManager", "MarketingStaff"]).exists():
        return True
    return False

def can_finish_cancel_campaign(user):
    """Chỉ Admin và MarketingManager có thể finish/cancel"""
    return (user.is_superuser or 
            user.groups.filter(name__in=["Admin", "MarketingManager"]).exists())

def can_delete_campaign(user):
    """Chỉ Admin có thể delete (soft delete)"""
    return user.is_superuser or user.groups.filter(name="Admin").exists()


# ==================== CAMPAIGN LIST ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
def campaign_list(request):
    """
    Campaign List Screen với filters và search.
    """
    # Get filter parameters
    search = request.GET.get('search', '').strip()
    brand_id = request.GET.get('brand', '')
    channel_filter = request.GET.get('channel', '')
    objective_filter = request.GET.get('objective', '')
    status_filter = request.GET.get('status', '')
    owner_id = request.GET.get('owner', '')
    has_creators = request.GET.get('has_creators', '')
    has_products = request.GET.get('has_products', '')
    
    # Date range
    start_date_from = request.GET.get('start_date_from', '')
    start_date_to = request.GET.get('start_date_to', '')
    end_date_from = request.GET.get('end_date_from', '')
    end_date_to = request.GET.get('end_date_to', '')
    
    # Sorting
    sort_by = request.GET.get('sort', '-start_date')
    sort_order = request.GET.get('order', 'desc')
    
    # Build queryset
    queryset = Campaign.objects.filter(is_active=True, deleted_at__isnull=True)
    
    # Search filter (code, name)
    if search:
        queryset = queryset.filter(
            Q(code__icontains=search) |
            Q(name__icontains=search)
        )
    
    # Brand filter
    if brand_id:
        queryset = queryset.filter(brand_id=brand_id)
    
    # Channel filter
    if channel_filter:
        queryset = queryset.filter(channel=channel_filter)
    
    # Objective filter
    if objective_filter:
        queryset = queryset.filter(objective=objective_filter)
    
    # Status filter
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    
    # Owner filter
    if owner_id:
        queryset = queryset.filter(owner_id=owner_id)
    
    # Has creators/products filters
    if has_creators == 'yes':
        queryset = queryset.annotate(
            creators_count=Count('campaign_creators', filter=Q(campaign_creators__is_active=True))
        ).filter(creators_count__gt=0)
    elif has_creators == 'no':
        queryset = queryset.annotate(
            creators_count=Count('campaign_creators', filter=Q(campaign_creators__is_active=True))
        ).filter(creators_count=0)
    
    if has_products == 'yes':
        queryset = queryset.annotate(
            products_count=Count('campaign_products', filter=Q(campaign_products__is_active=True))
        ).filter(products_count__gt=0)
    elif has_products == 'no':
        queryset = queryset.annotate(
            products_count=Count('campaign_products', filter=Q(campaign_products__is_active=True))
        ).filter(products_count=0)
    
    # Date range filters
    if start_date_from:
        queryset = queryset.filter(start_date__gte=start_date_from)
    if start_date_to:
        queryset = queryset.filter(start_date__lte=start_date_to)
    if end_date_from:
        queryset = queryset.filter(end_date__gte=end_date_from)
    if end_date_to:
        queryset = queryset.filter(end_date__lte=end_date_to)
    
    # Sorting
    if sort_order == 'asc':
        sort_by = sort_by.lstrip('-')
    queryset = queryset.order_by(sort_by)
    
    # Prefetch related
    queryset = queryset.select_related('brand', 'owner').prefetch_related(
        'campaign_creators__creator',
        'campaign_products__product'
    )
    
    # Pagination
    paginator = Paginator(queryset, 50)
    page_number = request.GET.get('page', 1)
    campaigns = paginator.get_page(page_number)
    
    # Get metrics và health flags cho mỗi campaign
    for campaign in campaigns:
        campaign.metrics = CampaignMetricsService.get_campaign_metrics(campaign)
        campaign.health_flags = CampaignMetricsService.get_health_flags(campaign)
        campaign.creators_count = campaign.metrics['creators_count']
        campaign.products_count = campaign.metrics['products_count']
    
    # Filter options
    brands = Brand.objects.filter(is_active=True).order_by('name')
    from django.contrib.auth.models import User
    owners = User.objects.filter(
        is_active=True,
        owned_campaigns__isnull=False
    ).distinct().order_by('username')
    
    context = {
        'title': 'Campaigns - Danh sách',
        'campaigns': campaigns,
        'brands': brands,
        'owners': owners,
        'filters': {
            'search': search,
            'brand_id': brand_id,
            'channel': channel_filter,
            'objective': objective_filter,
            'status': status_filter,
            'owner_id': owner_id,
            'has_creators': has_creators,
            'has_products': has_products,
            'start_date_from': start_date_from,
            'start_date_to': start_date_to,
            'end_date_from': end_date_from,
            'end_date_to': end_date_to,
            'sort': sort_by,
            'order': sort_order,
        },
        'can_edit': can_edit_campaign(request.user),
        'can_delete': can_delete_campaign(request.user),
    }
    
    return render(request, 'marketing/campaigns/campaign_list.html', context)


# ==================== CAMPAIGN CREATE/EDIT ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
def campaign_create(request):
    """Create new campaign."""
    if not can_edit_campaign(request.user):
        messages.error(request, 'Bạn không có quyền tạo campaign')
        return redirect('marketing:campaign_list')
    
    if request.method == 'POST':
        form = CampaignForm(request.POST)
        if form.is_valid():
            campaign = form.save(commit=False)
            if not campaign.owner:
                campaign.owner = request.user
            # Handle save_as_draft vs save_and_plan
            if 'save_and_plan' in request.POST:
                campaign.status = 'planned'
            elif 'save_as_draft' in request.POST:
                campaign.status = 'draft'
            campaign.save()
            messages.success(request, f'Đã tạo campaign {campaign.code} thành công')
            return redirect('marketing:campaign_detail', campaign_id=campaign.id)
    else:
        form = CampaignForm()
    
    context = {
        'title': 'Tạo Campaign mới',
        'form': form,
        'action': 'create',
    }
    return render(request, 'marketing/campaigns/campaign_form.html', context)


@marketing_permission_required("MarketingManager", "MarketingStaff")
def campaign_edit(request, campaign_id):
    """Edit campaign."""
    campaign = get_object_or_404(Campaign, id=campaign_id, is_active=True)
    
    if not can_edit_campaign(request.user, campaign):
        messages.error(request, 'Bạn không có quyền chỉnh sửa campaign này')
        return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    # Check if can edit (finished/canceled are limited)
    if campaign.status in ['finished', 'canceled']:
        messages.warning(request, 'Campaign đã kết thúc/hủy, chỉ có thể xem')
        return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    if request.method == 'POST':
        form = CampaignForm(request.POST, instance=campaign)
        if form.is_valid():
            form.save()
            messages.success(request, f'Đã cập nhật campaign {campaign.code}')
            return redirect('marketing:campaign_detail', campaign_id=campaign.id)
    else:
        form = CampaignForm(instance=campaign)
    
    context = {
        'title': f'Chỉnh sửa Campaign: {campaign.code}',
        'form': form,
        'campaign': campaign,
        'action': 'edit',
    }
    return render(request, 'marketing/campaigns/campaign_form.html', context)


# ==================== CAMPAIGN DETAIL ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
def campaign_detail(request, campaign_id):
    """
    Campaign Detail Screen - Command center với tabs.
    """
    campaign = get_object_or_404(
        Campaign.objects.select_related('brand', 'owner').prefetch_related(
            'campaign_creators__creator',
            'campaign_products__product'
        ),
        id=campaign_id,
        is_active=True
    )
    
    # Get metrics và health flags
    metrics = CampaignMetricsService.get_campaign_metrics(campaign)
    health_flags = CampaignMetricsService.get_health_flags(campaign)
    
    # Get creators và products
    creators = campaign.campaign_creators.filter(is_active=True).select_related('creator')
    products = campaign.campaign_products.filter(is_active=True).select_related('product').order_by('priority', 'product__name')
    
    # Get available products/creators for modals
    from marketing.models import Product, Creator
    available_products = Product.objects.filter(
        brand=campaign.brand,
        is_active=True
    ).exclude(
        id__in=campaign.campaign_products.filter(is_active=True).values_list('product_id', flat=True)
    ).order_by('name')
    
    available_creators = Creator.objects.filter(
        is_active=True
    ).exclude(
        id__in=campaign.campaign_creators.filter(is_active=True).values_list('creator_id', flat=True)
    ).order_by('name')
    
    # Extract postmortem section
    postmortem_content = None
    if campaign.description and '## Postmortem' in campaign.description:
        parts = campaign.description.split('## Postmortem')
        if len(parts) > 1:
            postmortem_content = parts[1].strip()
    
    # Tab
    tab = request.GET.get('tab', 'overview')
    
    context = {
        'title': f'Campaign: {campaign.code}',
        'campaign': campaign,
        'metrics': metrics,
        'health_flags': health_flags,
        'creators': creators,
        'products': products,
        'available_products': available_products,
        'available_creators': available_creators,
        'postmortem_content': postmortem_content,
        'tab': tab,
        'can_edit': can_edit_campaign(request.user, campaign),
        'can_finish_cancel': can_finish_cancel_campaign(request.user),
        'can_delete': can_delete_campaign(request.user),
    }
    
    return render(request, 'marketing/campaigns/campaign_detail.html', context)


# ==================== CAMPAIGN STATUS CHANGE ====================

@require_http_methods(["POST"])
@marketing_permission_required("MarketingManager", "MarketingStaff")
def campaign_change_status(request, campaign_id):
    """Change campaign status với validation."""
    campaign = get_object_or_404(Campaign, id=campaign_id, is_active=True)
    
    new_status = request.POST.get('status', '').strip()
    if not new_status:
        messages.error(request, 'Status không hợp lệ')
        return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    # Validate status transition
    old_status = campaign.status
    valid_transitions = {
        'draft': ['planned', 'canceled'],
        'planned': ['running', 'paused', 'canceled'],
        'running': ['paused', 'finished', 'canceled'],
        'paused': ['running', 'canceled'],
        'finished': [],  # Terminal
        'canceled': [],  # Terminal
    }
    
    if new_status not in valid_transitions.get(old_status, []):
        messages.error(request, f'Không thể chuyển từ {campaign.get_status_display()} sang {dict(Campaign.STATUS_CHOICES).get(new_status, new_status)}')
        return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    # Check permissions for finish/cancel
    if new_status in ['finished', 'canceled']:
        if not can_finish_cancel_campaign(request.user):
            messages.error(request, 'Bạn không có quyền finish/cancel campaign')
            return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    # Validate requirements
    if new_status in ['planned', 'running']:
        if not campaign.start_date or not campaign.end_date:
            messages.error(request, 'Campaign phải có ngày bắt đầu và kết thúc')
            return redirect('marketing:campaign_detail', campaign_id=campaign_id)
        
        creators_count = campaign.campaign_creators.filter(is_active=True).count()
        if creators_count == 0:
            messages.error(request, 'Campaign phải có ít nhất 1 creator')
            return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    # Check postmortem requirement for finished
    if new_status == 'finished':
        # Check if description contains postmortem section
        if campaign.description and '## Postmortem' not in campaign.description:
            messages.warning(request, 'Vui lòng thêm phần Postmortem vào Brief trước khi finish campaign')
            return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    campaign.status = new_status
    campaign.save()
    
    messages.success(request, f'Đã chuyển status sang {campaign.get_status_display()}')
    return redirect('marketing:campaign_detail', campaign_id=campaign_id)


# ==================== CAMPAIGN PRODUCTS ====================

@require_http_methods(["POST"])
@marketing_permission_required("MarketingManager", "MarketingStaff")
def campaign_product_add(request, campaign_id):
    """Add product to campaign."""
    campaign = get_object_or_404(Campaign, id=campaign_id, is_active=True)
    
    if not can_edit_campaign(request.user, campaign):
        messages.error(request, 'Bạn không có quyền chỉnh sửa campaign này')
        return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    form = CampaignProductForm(request.POST, campaign=campaign)
    if form.is_valid():
        form.save()
        messages.success(request, 'Đã thêm sản phẩm vào campaign')
    else:
        for error in form.non_field_errors():
            messages.error(request, error)
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{field}: {error}')
    
    return redirect('marketing:campaign_detail', campaign_id=campaign_id, tab='products')


@require_http_methods(["POST"])
@marketing_permission_required("MarketingManager", "MarketingStaff")
def campaign_product_bulk_add(request, campaign_id):
    """Bulk add products to campaign."""
    campaign = get_object_or_404(Campaign, id=campaign_id, is_active=True)
    
    if not can_edit_campaign(request.user, campaign):
        messages.error(request, 'Bạn không có quyền chỉnh sửa campaign này')
        return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    form = BulkAddProductsForm(request.POST, campaign=campaign)
    if form.is_valid():
        products = form.cleaned_data['products']
        priority = form.cleaned_data['priority']
        note = form.cleaned_data['note']
        
        created_count = 0
        for product in products:
            cp, created = CampaignProduct.objects.get_or_create(
                campaign=campaign,
                product=product,
                defaults={'priority': priority, 'note': note}
            )
            if created:
                created_count += 1
        
        messages.success(request, f'Đã thêm {created_count} sản phẩm vào campaign')
    else:
        for error in form.non_field_errors():
            messages.error(request, error)
    
    return redirect('marketing:campaign_detail', campaign_id=campaign_id, tab='products')


@require_http_methods(["POST"])
@marketing_permission_required("MarketingManager", "MarketingStaff")
def campaign_product_remove(request, campaign_id, product_id):
    """Remove product from campaign (soft delete)."""
    campaign = get_object_or_404(Campaign, id=campaign_id, is_active=True)
    
    if not can_edit_campaign(request.user, campaign):
        messages.error(request, 'Bạn không có quyền chỉnh sửa campaign này')
        return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    cp = get_object_or_404(
        CampaignProduct,
        campaign=campaign,
        product_id=product_id,
        is_active=True
    )
    cp.is_active = False
    cp.deleted_at = timezone.now()
    cp.save()
    
    messages.success(request, 'Đã xóa sản phẩm khỏi campaign')
    return redirect('marketing:campaign_detail', campaign_id=campaign_id, tab='products')


# ==================== CAMPAIGN CREATORS ====================

@require_http_methods(["POST"])
@marketing_permission_required("MarketingManager", "MarketingStaff")
def campaign_creator_add(request, campaign_id):
    """Add creator to campaign."""
    campaign = get_object_or_404(Campaign, id=campaign_id, is_active=True)
    
    if not can_edit_campaign(request.user, campaign):
        messages.error(request, 'Bạn không có quyền chỉnh sửa campaign này')
        return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    form = CampaignCreatorForm(request.POST, campaign=campaign)
    if form.is_valid():
        form.save()
        messages.success(request, 'Đã thêm creator vào campaign')
    else:
        for error in form.non_field_errors():
            messages.error(request, error)
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{field}: {error}')
    
    return redirect('marketing:campaign_detail', campaign_id=campaign_id, tab='creators')


@require_http_methods(["POST"])
@marketing_permission_required("MarketingManager", "MarketingStaff")
def campaign_creator_bulk_add(request, campaign_id):
    """Bulk add creators to campaign."""
    campaign = get_object_or_404(Campaign, id=campaign_id, is_active=True)
    
    if not can_edit_campaign(request.user, campaign):
        messages.error(request, 'Bạn không có quyền chỉnh sửa campaign này')
        return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    form = BulkAddCreatorsForm(request.POST, campaign=campaign)
    if form.is_valid():
        creators = form.cleaned_data['creators']
        role = form.cleaned_data['role']
        note = form.cleaned_data['note']
        
        created_count = 0
        for creator in creators:
            cc, created = CampaignCreator.objects.get_or_create(
                campaign=campaign,
                creator=creator,
                defaults={'role': role, 'note': note}
            )
            if created:
                created_count += 1
        
        messages.success(request, f'Đã thêm {created_count} creator vào campaign')
    else:
        for error in form.non_field_errors():
            messages.error(request, error)
    
    return redirect('marketing:campaign_detail', campaign_id=campaign_id, tab='creators')


@require_http_methods(["POST"])
@marketing_permission_required("MarketingManager", "MarketingStaff")
def campaign_creator_remove(request, campaign_id, creator_id):
    """Remove creator from campaign (soft delete)."""
    campaign = get_object_or_404(Campaign, id=campaign_id, is_active=True)
    
    if not can_edit_campaign(request.user, campaign):
        messages.error(request, 'Bạn không có quyền chỉnh sửa campaign này')
        return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    cc = get_object_or_404(
        CampaignCreator,
        campaign=campaign,
        creator_id=creator_id,
        is_active=True
    )
    cc.is_active = False
    cc.deleted_at = timezone.now()
    cc.save()
    
    messages.success(request, 'Đã xóa creator khỏi campaign')
    return redirect('marketing:campaign_detail', campaign_id=campaign_id, tab='creators')


# ==================== CAMPAIGN DUPLICATE ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
def campaign_duplicate(request, campaign_id):
    """Duplicate campaign với reset dates và status."""
    campaign = get_object_or_404(Campaign, id=campaign_id, is_active=True)
    
    if not can_edit_campaign(request.user):
        messages.error(request, 'Bạn không có quyền tạo campaign')
        return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    with transaction.atomic():
        # Create new campaign
        new_code = f"{campaign.code}-COPY"
        counter = 1
        while Campaign.objects.filter(code=new_code, is_active=True).exists():
            new_code = f"{campaign.code}-COPY-{counter}"
            counter += 1
        
        new_campaign = Campaign.objects.create(
            code=new_code,
            name=f"{campaign.name} (Copy)",
            brand=campaign.brand,
            channel=campaign.channel,
            objective=campaign.objective,
            description=campaign.description,
            start_date=None,  # Reset dates
            end_date=None,
            budget_planned=campaign.budget_planned,
            kpi_view=campaign.kpi_view,
            kpi_order=campaign.kpi_order,
            kpi_revenue=campaign.kpi_revenue,
            status='draft',  # Reset status
            owner=request.user,
        )
        
        # Copy products
        for cp in campaign.campaign_products.filter(is_active=True):
            CampaignProduct.objects.create(
                campaign=new_campaign,
                product=cp.product,
                priority=cp.priority,
                note=cp.note,
            )
        
        # Copy creators
        for cc in campaign.campaign_creators.filter(is_active=True):
            CampaignCreator.objects.create(
                campaign=new_campaign,
                creator=cc.creator,
                role=cc.role,
                note=cc.note,
            )
    
    messages.success(request, f'Đã tạo campaign copy: {new_campaign.code}')
    return redirect('marketing:campaign_detail', campaign_id=new_campaign.id)


# ==================== CAMPAIGN DELETE ====================

@require_http_methods(["POST"])
@marketing_permission_required("MarketingManager", "MarketingStaff")
def campaign_delete(request, campaign_id):
    """Soft delete campaign."""
    campaign = get_object_or_404(Campaign, id=campaign_id, is_active=True)
    
    if not can_delete_campaign(request.user):
        messages.error(request, 'Bạn không có quyền xóa campaign')
        return redirect('marketing:campaign_detail', campaign_id=campaign_id)
    
    campaign.is_active = False
    campaign.deleted_at = timezone.now()
    campaign.save()
    
    messages.success(request, f'Đã xóa campaign {campaign.code}')
    return redirect('marketing:campaign_list')


# ==================== CAMPAIGN EXPORT ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
def campaign_export(request, campaign_id=None):
    """
    Export campaigns to CSV/XLSX.
    Nếu campaign_id được cung cấp, export detail của campaign đó.
    Nếu không, export list với filters hiện tại.
    """
    if campaign_id:
        # Export single campaign detail
        campaign = get_object_or_404(Campaign, id=campaign_id, is_active=True)
        
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="campaign_{campaign.code}_detail.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Campaign Detail Export'])
        writer.writerow(['Code', campaign.code])
        writer.writerow(['Name', campaign.name])
        writer.writerow(['Brand', campaign.brand.name])
        writer.writerow(['Channel', campaign.get_channel_display()])
        writer.writerow(['Objective', campaign.get_objective_display()])
        writer.writerow(['Status', campaign.get_status_display()])
        writer.writerow(['Start Date', campaign.start_date or ''])
        writer.writerow(['End Date', campaign.end_date or ''])
        writer.writerow(['Budget Planned', campaign.budget_planned])
        writer.writerow([''])
        writer.writerow(['Products'])
        writer.writerow(['Product Code', 'Product Name', 'Priority', 'Note'])
        
        for cp in campaign.campaign_products.filter(is_active=True).select_related('product'):
            writer.writerow([
                cp.product.code,
                cp.product.name,
                cp.priority,
                cp.note or ''
            ])
        
        writer.writerow([''])
        writer.writerow(['Creators'])
        writer.writerow(['Creator Name', 'Role', 'Status', 'Note'])
        
        for cc in campaign.campaign_creators.filter(is_active=True).select_related('creator'):
            writer.writerow([
                cc.creator.name,
                cc.get_role_display(),
                cc.creator.get_status_display(),
                cc.note or ''
            ])
        
        return response
    else:
        # Export list với filters
        # Reuse filter logic from campaign_list
        search = request.GET.get('search', '').strip()
        brand_id = request.GET.get('brand', '')
        channel_filter = request.GET.get('channel', '')
        objective_filter = request.GET.get('objective', '')
        status_filter = request.GET.getlist('status', [])
        
        queryset = Campaign.objects.filter(is_active=True, deleted_at__isnull=True)
        
        if search:
            queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))
        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)
        if channel_filter:
            queryset = queryset.filter(channel=channel_filter)
        if objective_filter:
            queryset = queryset.filter(objective=objective_filter)
        if status_filter:
            queryset = queryset.filter(status__in=status_filter)
        
        queryset = queryset.select_related('brand', 'owner').order_by('-start_date', 'name')
        
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="campaigns_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Code', 'Name', 'Brand', 'Channel', 'Objective', 'Status',
            'Start Date', 'End Date', 'Budget Planned', 'Budget Actual',
            'KPI View', 'KPI Order', 'KPI Revenue', 'Owner'
        ])
        
        for campaign in queryset:
            metrics = CampaignMetricsService.get_campaign_metrics(campaign)
            writer.writerow([
                campaign.code,
                campaign.name,
                campaign.brand.name if campaign.brand else '',
                campaign.get_channel_display(),
                campaign.get_objective_display(),
                campaign.get_status_display(),
                campaign.start_date or '',
                campaign.end_date or '',
                campaign.budget_planned,
                metrics['budget_actual_paid'],
                campaign.kpi_view,
                campaign.kpi_order,
                campaign.kpi_revenue,
                campaign.owner.username if campaign.owner else '',
            ])
        
        return response


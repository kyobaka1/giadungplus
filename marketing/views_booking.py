# marketing/views_booking.py
"""
KOC/KOL Database - Booking Center Views
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, Http404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Max, Prefetch
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal, InvalidOperation
import json
import csv
import io
from datetime import datetime

from marketing.models import (
    Creator, CreatorChannel, CreatorContact, CreatorTag, 
    CreatorTagMap, CreatorNote, CreatorRateCard
)
from marketing.utils import marketing_permission_required
from marketing.services.booking_import_export import (
    import_creators_csv, import_channels_csv, import_contacts_csv,
    export_creators_csv, export_creators_xlsx
)


# ==================== PERMISSIONS HELPERS ====================

def can_manage_tags(user):
    """Admin can manage tags"""
    return user.is_superuser or user.groups.filter(name="Admin").exists()

def can_blacklist(user):
    """Admin can blacklist"""
    return user.is_superuser or user.groups.filter(name="Admin").exists()

def can_import_export(user):
    """Admin and MarketingManager can import/export"""
    return (user.is_superuser or 
            user.groups.filter(name__in=["Admin", "MarketingManager"]).exists())


# ==================== CREATOR LIST (DASHBOARD) ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
def booking_creator_list(request):
    """
    Creator List Screen - KOC Dashboard
    Filters: search, status, platform, tags, location, niche, follower range, avg_view range, priority_score
    """
    # Get filter parameters
    search = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')
    platform_filter = request.GET.get('platform', '')
    tag_ids = request.GET.getlist('tags', [])
    location_filter = request.GET.get('location', '').strip()
    niche_filter = request.GET.get('niche', '').strip()
    
    # Range filters
    follower_min = request.GET.get('follower_min', '')
    follower_max = request.GET.get('follower_max', '')
    avg_view_min = request.GET.get('avg_view_min', '')
    avg_view_max = request.GET.get('avg_view_max', '')
    priority_min = request.GET.get('priority_min', '')
    priority_max = request.GET.get('priority_max', '')
    
    # Sorting
    sort_by = request.GET.get('sort', 'priority_score')
    sort_order = request.GET.get('order', 'desc')
    
    # Build queryset
    queryset = Creator.objects.filter(is_active=True, deleted_at__isnull=True)
    
    # Search filter (name, alias, handle, phone, email)
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) |
            Q(alias__icontains=search) |
            Q(channels__handle__icontains=search) |
            Q(contacts__phone__icontains=search) |
            Q(contacts__email__icontains=search)
        ).distinct()
    
    # Status filter
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    
    # Platform filter
    if platform_filter:
        queryset = queryset.filter(channels__platform=platform_filter).distinct()
    
    # Tag filter
    if tag_ids:
        queryset = queryset.filter(tag_maps__tag_id__in=tag_ids).distinct()
    
    # Location filter
    if location_filter:
        queryset = queryset.filter(location__icontains=location_filter)
    
    # Niche filter
    if niche_filter:
        queryset = queryset.filter(niche__icontains=niche_filter)
    
    # Follower range filter
    if follower_min or follower_max:
        channel_filter = Q()
        if follower_min:
            try:
                channel_filter &= Q(channels__follower_count__gte=int(follower_min))
            except ValueError:
                pass
        if follower_max:
            try:
                channel_filter &= Q(channels__follower_count__lte=int(follower_max))
            except ValueError:
                pass
        if channel_filter:
            queryset = queryset.filter(channel_filter).distinct()
    
    # Avg view range filter
    if avg_view_min or avg_view_max:
        channel_filter = Q()
        if avg_view_min:
            try:
                channel_filter &= Q(channels__avg_view_10__gte=int(avg_view_min))
            except ValueError:
                pass
        if avg_view_max:
            try:
                channel_filter &= Q(channels__avg_view_10__lte=int(avg_view_max))
            except ValueError:
                pass
        if channel_filter:
            queryset = queryset.filter(channel_filter).distinct()
    
    # Priority score range
    if priority_min:
        try:
            queryset = queryset.filter(priority_score__gte=int(priority_min))
        except ValueError:
            pass
    if priority_max:
        try:
            queryset = queryset.filter(priority_score__lte=int(priority_max))
        except ValueError:
            pass
    
    # Annotate with latest note
    queryset = queryset.annotate(
        latest_note_date=Max('notes__created_at')
    ).prefetch_related(
        Prefetch('channels', queryset=CreatorChannel.objects.filter(is_active=True, deleted_at__isnull=True).order_by('-follower_count')),
        Prefetch('tag_maps', queryset=CreatorTagMap.objects.select_related('tag')),
        Prefetch('contacts', queryset=CreatorContact.objects.filter(is_active=True, deleted_at__isnull=True, is_primary=True)),
    )
    
    # Sorting
    if sort_by == 'priority_score':
        queryset = queryset.order_by('-priority_score' if sort_order == 'desc' else 'priority_score', 'name')
    elif sort_by == 'followers':
        queryset = queryset.order_by('-channels__follower_count' if sort_order == 'desc' else 'channels__follower_count', 'name')
    elif sort_by == 'avg_view':
        queryset = queryset.order_by('-channels__avg_view_10' if sort_order == 'desc' else 'channels__avg_view_10', 'name')
    elif sort_by == 'last_interaction':
        queryset = queryset.order_by('-latest_note_date' if sort_order == 'desc' else 'latest_note_date', 'name')
    else:
        queryset = queryset.order_by('-priority_score', 'name')
    
    # Pagination
    paginator = Paginator(queryset, 50)
    page = request.GET.get('page', 1)
    creators = paginator.get_page(page)
    
    # Get filter options
    all_tags = CreatorTag.objects.filter(is_active=True, deleted_at__isnull=True).annotate(
        usage_count=Count('creator_maps')
    ).order_by('name')
    
    platforms = CreatorChannel.objects.filter(is_active=True, deleted_at__isnull=True).values_list(
        'platform', flat=True
    ).distinct()
    
    locations = Creator.objects.filter(is_active=True, deleted_at__isnull=True).exclude(
        location__isnull=True
    ).values_list('location', flat=True).distinct()[:50]
    
    niches = Creator.objects.filter(is_active=True, deleted_at__isnull=True).exclude(
        niche__isnull=True
    ).values_list('niche', flat=True).distinct()
    
    context = {
        'title': 'KOC/KOL Database - Creator List',
        'creators': creators,
        'all_tags': all_tags,
        'platforms': platforms,
        'locations': locations,
        'niches': niches,
        'filters': {
            'search': search,
            'status': status_filter,
            'platform': platform_filter,
            'tags': [int(t) for t in tag_ids if t.isdigit()],
            'location': location_filter,
            'niche': niche_filter,
            'follower_min': follower_min,
            'follower_max': follower_max,
            'avg_view_min': avg_view_min,
            'avg_view_max': avg_view_max,
            'priority_min': priority_min,
            'priority_max': priority_max,
            'sort': sort_by,
            'order': sort_order,
        },
        'can_manage_tags': can_manage_tags(request.user),
        'can_blacklist': can_blacklist(request.user),
    }
    
    return render(request, 'marketing/booking/creator_list.html', context)


# ==================== CREATOR DETAIL ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
def booking_creator_detail(request, creator_id):
    """
    Creator Detail Screen - Profile 360
    Tabs: Overview, Channels, Contacts, Rate Card, Notes/Timeline
    """
    creator = get_object_or_404(Creator, id=creator_id, is_active=True, deleted_at__isnull=True)
    
    # Get active tab
    tab = request.GET.get('tab', 'overview')
    
    # Get related data
    channels = creator.channels.filter(is_active=True, deleted_at__isnull=True).order_by('-follower_count')
    contacts = creator.contacts.filter(is_active=True, deleted_at__isnull=True).order_by('-is_primary', 'contact_type')
    tags = creator.tag_maps.select_related('tag').filter(tag__is_active=True, tag__deleted_at__isnull=True)
    rate_cards = creator.rate_cards.filter(is_active=True, deleted_at__isnull=True).order_by('-valid_from')
    notes = creator.notes.filter(is_active=True, deleted_at__isnull=True).select_related('user').order_by('-created_at')
    
    # Get all tags for assignment
    all_tags = CreatorTag.objects.filter(is_active=True, deleted_at__isnull=True).order_by('name')
    
    # Get primary contact
    primary_contact = contacts.filter(is_primary=True).first()
    
    # Get primary TikTok channel (most common)
    primary_tiktok = channels.filter(platform='tiktok').first()
    
    # Get current tag IDs
    current_tag_ids = list(tags.values_list('tag_id', flat=True))
    
    context = {
        'title': f'Creator: {creator.name}',
        'creator': creator,
        'channels': channels,
        'contacts': contacts,
        'tags': tags,
        'all_tags': all_tags,
        'current_tag_ids': current_tag_ids,
        'rate_cards': rate_cards,
        'notes': notes,
        'primary_contact': primary_contact,
        'primary_tiktok': primary_tiktok,
        'active_tab': tab,
        'can_manage_tags': can_manage_tags(request.user),
        'can_blacklist': can_blacklist(request.user),
    }
    
    return render(request, 'marketing/booking/creator_detail.html', context)


# ==================== CREATOR CREATE/EDIT ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
def booking_creator_create(request):
    """Create new creator"""
    if request.method == 'POST':
        try:
            with transaction.atomic():
                creator = Creator.objects.create(
                    name=request.POST.get('name', '').strip(),
                    alias=request.POST.get('alias', '').strip() or None,
                    gender=request.POST.get('gender') or None,
                    dob=request.POST.get('dob') or None,
                    location=request.POST.get('location', '').strip() or None,
                    niche=request.POST.get('niche', '').strip() or None,
                    note_internal=request.POST.get('note_internal', '').strip() or None,
                    priority_score=int(request.POST.get('priority_score', 5)),
                    status=request.POST.get('status', 'active'),
                )
                
                # Validate priority_score
                if creator.priority_score < 1 or creator.priority_score > 10:
                    creator.priority_score = 5
                    creator.save()
                
                messages.success(request, f'Creator "{creator.name}" đã được tạo thành công.')
                return redirect('marketing:booking_creator_detail', creator_id=creator.id)
        except Exception as e:
            messages.error(request, f'Lỗi khi tạo creator: {str(e)}')
    
    context = {
        'title': 'Tạo Creator mới',
        'creator': None,
    }
    return render(request, 'marketing/booking/creator_form.html', context)


@marketing_permission_required("MarketingManager", "MarketingStaff")
def booking_creator_edit(request, creator_id):
    """Edit creator"""
    creator = get_object_or_404(Creator, id=creator_id, is_active=True, deleted_at__isnull=True)
    
    # Check blacklist restriction
    if creator.status == 'blacklist' and not can_blacklist(request.user):
        messages.warning(request, 'Bạn không có quyền chỉnh sửa creator đã bị blacklist.')
        return redirect('marketing:booking_creator_detail', creator_id=creator.id)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                creator.name = request.POST.get('name', '').strip()
                creator.alias = request.POST.get('alias', '').strip() or None
                creator.gender = request.POST.get('gender') or None
                creator.dob = request.POST.get('dob') or None
                creator.location = request.POST.get('location', '').strip() or None
                creator.niche = request.POST.get('niche', '').strip() or None
                creator.note_internal = request.POST.get('note_internal', '').strip() or None
                
                priority_score = int(request.POST.get('priority_score', 5))
                if 1 <= priority_score <= 10:
                    creator.priority_score = priority_score
                
                # Only admin can set blacklist
                new_status = request.POST.get('status', creator.status)
                if new_status == 'blacklist' and not can_blacklist(request.user):
                    messages.warning(request, 'Bạn không có quyền đặt status blacklist.')
                else:
                    creator.status = new_status
                
                creator.save()
                messages.success(request, f'Creator "{creator.name}" đã được cập nhật.')
                return redirect('marketing:booking_creator_detail', creator_id=creator.id)
        except Exception as e:
            messages.error(request, f'Lỗi khi cập nhật creator: {str(e)}')
    
    context = {
        'title': f'Chỉnh sửa: {creator.name}',
        'creator': creator,
    }
    return render(request, 'marketing/booking/creator_form.html', context)


@marketing_permission_required("MarketingManager", "MarketingStaff")
@require_http_methods(["POST"])
def booking_creator_delete(request, creator_id):
    """Soft delete creator"""
    creator = get_object_or_404(Creator, id=creator_id, is_active=True, deleted_at__isnull=True)
    
    if request.method == 'POST':
        creator.is_active = False
        creator.deleted_at = timezone.now()
        creator.save()
        messages.success(request, f'Creator "{creator.name}" đã được xóa.')
        return redirect('marketing:booking_creator_list')
    
    return redirect('marketing:booking_creator_detail', creator_id=creator.id)


# ==================== CHANNEL MANAGEMENT ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
@require_http_methods(["POST"])
def booking_channel_create(request, creator_id):
    """Create channel for creator"""
    creator = get_object_or_404(Creator, id=creator_id, is_active=True, deleted_at__isnull=True)
    
    try:
        platform = request.POST.get('platform', '').strip()
        handle = request.POST.get('handle', '').strip()
        
        if not platform or not handle:
            messages.error(request, 'Platform và handle là bắt buộc.')
            return redirect('marketing:booking_creator_detail', creator_id=creator.id)
        
        # Check duplicate
        existing = CreatorChannel.objects.filter(
            platform=platform, 
            handle=handle,
            is_active=True,
            deleted_at__isnull=True
        ).exclude(creator=creator).first()
        
        if existing:
            messages.error(request, f'Channel {platform}/{handle} đã tồn tại cho creator khác.')
            return redirect('marketing:booking_creator_detail', creator_id=creator.id)
        
        channel = CreatorChannel.objects.create(
            creator=creator,
            platform=platform,
            handle=handle,
            profile_url=request.POST.get('profile_url', '').strip() or None,
            external_id=request.POST.get('external_id', '').strip() or None,
            follower_count=int(request.POST.get('follower_count', 0) or 0),
            avg_view_10=int(request.POST.get('avg_view_10', 0) or 0),
            avg_engagement_rate=Decimal(request.POST.get('avg_engagement_rate', 0) or 0),
        )
        
        messages.success(request, f'Channel {platform}/{handle} đã được thêm.')
    except Exception as e:
        messages.error(request, f'Lỗi khi tạo channel: {str(e)}')
    
    return redirect('marketing:booking_creator_detail', creator_id=creator.id)


@marketing_permission_required("MarketingManager", "MarketingStaff")
@require_http_methods(["POST"])
def booking_channel_delete(request, creator_id, channel_id):
    """Soft delete channel"""
    creator = get_object_or_404(Creator, id=creator_id, is_active=True, deleted_at__isnull=True)
    channel = get_object_or_404(CreatorChannel, id=channel_id, creator=creator, is_active=True, deleted_at__isnull=True)
    
    channel.is_active = False
    channel.deleted_at = timezone.now()
    channel.save()
    
    messages.success(request, f'Channel đã được xóa.')
    return redirect('marketing:booking_creator_detail', creator_id=creator.id)


# ==================== CONTACT MANAGEMENT ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
@require_http_methods(["POST"])
def booking_contact_create(request, creator_id):
    """Create contact for creator"""
    creator = get_object_or_404(Creator, id=creator_id, is_active=True, deleted_at__isnull=True)
    
    try:
        is_primary = request.POST.get('is_primary') == 'on'
        
        # If setting as primary, unset others
        if is_primary:
            CreatorContact.objects.filter(
                creator=creator,
                is_active=True,
                deleted_at__isnull=True
            ).update(is_primary=False)
        
        contact = CreatorContact.objects.create(
            creator=creator,
            contact_type=request.POST.get('contact_type', 'owner'),
            name=request.POST.get('name', '').strip(),
            phone=request.POST.get('phone', '').strip() or None,
            zalo=request.POST.get('zalo', '').strip() or None,
            email=request.POST.get('email', '').strip() or None,
            wechat=request.POST.get('wechat', '').strip() or None,
            note=request.POST.get('note', '').strip() or None,
            is_primary=is_primary,
        )
        
        messages.success(request, f'Contact "{contact.name}" đã được thêm.')
    except Exception as e:
        messages.error(request, f'Lỗi khi tạo contact: {str(e)}')
    
    return redirect('marketing:booking_creator_detail', creator_id=creator.id)


@marketing_permission_required("MarketingManager", "MarketingStaff")
@require_http_methods(["POST"])
def booking_contact_set_primary(request, creator_id, contact_id):
    """Set contact as primary"""
    creator = get_object_or_404(Creator, id=creator_id, is_active=True, deleted_at__isnull=True)
    contact = get_object_or_404(CreatorContact, id=contact_id, creator=creator, is_active=True, deleted_at__isnull=True)
    
    # Unset all others
    CreatorContact.objects.filter(
        creator=creator,
        is_active=True,
        deleted_at__isnull=True
    ).update(is_primary=False)
    
    # Set this one
    contact.is_primary = True
    contact.save()
    
    messages.success(request, f'Contact "{contact.name}" đã được đặt làm primary.')
    return redirect('marketing:booking_creator_detail', creator_id=creator.id)


@marketing_permission_required("MarketingManager", "MarketingStaff")
@require_http_methods(["POST"])
def booking_contact_delete(request, creator_id, contact_id):
    """Soft delete contact"""
    creator = get_object_or_404(Creator, id=creator_id, is_active=True, deleted_at__isnull=True)
    contact = get_object_or_404(CreatorContact, id=contact_id, creator=creator, is_active=True, deleted_at__isnull=True)
    
    contact.is_active = False
    contact.deleted_at = timezone.now()
    contact.save()
    
    messages.success(request, f'Contact đã được xóa.')
    return redirect('marketing:booking_creator_detail', creator_id=creator.id)


# ==================== TAG MANAGEMENT ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
def booking_tag_list(request):
    """Tag management screen"""
    tags = CreatorTag.objects.filter(is_active=True, deleted_at__isnull=True).annotate(
        usage_count=Count('creator_maps')
    ).order_by('name')
    
    context = {
        'title': 'Tag Management',
        'tags': tags,
        'can_manage_tags': can_manage_tags(request.user),
    }
    return render(request, 'marketing/booking/tag_list.html', context)


@marketing_permission_required("MarketingManager", "MarketingStaff")
@require_http_methods(["POST"])
def booking_tag_create(request):
    """Create tag (admin only for delete, but marketing can create)"""
    name = request.POST.get('name', '').strip()
    
    if not name:
        messages.error(request, 'Tên tag là bắt buộc.')
        return redirect('booking_tag_list')
    
    # Check duplicate (case-insensitive)
    existing = CreatorTag.objects.filter(
        name__iexact=name,
        is_active=True,
        deleted_at__isnull=True
    ).first()
    
    if existing:
        messages.warning(request, f'Tag "{name}" đã tồn tại (tương tự: {existing.name}).')
        return redirect('booking_tag_list')
    
    tag = CreatorTag.objects.create(
        name=name,
        description=request.POST.get('description', '').strip() or None,
    )
    
    messages.success(request, f'Tag "{tag.name}" đã được tạo.')
    return redirect('booking_tag_list')


@marketing_permission_required("MarketingManager", "MarketingStaff")
@require_http_methods(["POST"])
def booking_tag_delete(request, tag_id):
    """Delete tag (admin only)"""
    if not can_manage_tags(request.user):
        messages.error(request, 'Bạn không có quyền xóa tag.')
        return redirect('booking_tag_list')
    
    tag = get_object_or_404(CreatorTag, id=tag_id, is_active=True, deleted_at__isnull=True)
    
    usage_count = tag.creator_maps.count()
    if usage_count > 0:
        messages.warning(request, f'Tag "{tag.name}" đang được sử dụng bởi {usage_count} creator. Không thể xóa.')
        return redirect('booking_tag_list')
    
    tag.is_active = False
    tag.deleted_at = timezone.now()
    tag.save()
    
    messages.success(request, f'Tag "{tag.name}" đã được xóa.')
    return redirect('booking_tag_list')


@marketing_permission_required("MarketingManager", "MarketingStaff")
@require_http_methods(["POST"])
def booking_tag_assign(request, creator_id):
    """Assign/unassign tags to creator"""
    creator = get_object_or_404(Creator, id=creator_id, is_active=True, deleted_at__isnull=True)
    
    tag_ids = request.POST.getlist('tags', [])
    tag_ids = [int(t) for t in tag_ids if t.isdigit()]
    
    # Remove all existing
    CreatorTagMap.objects.filter(creator=creator).delete()
    
    # Add new ones
    for tag_id in tag_ids:
        tag = CreatorTag.objects.filter(id=tag_id, is_active=True, deleted_at__isnull=True).first()
        if tag:
            CreatorTagMap.objects.get_or_create(creator=creator, tag=tag)
    
    messages.success(request, 'Tags đã được cập nhật.')
    return redirect('marketing:booking_creator_detail', creator_id=creator.id)


# ==================== NOTE MANAGEMENT ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
@require_http_methods(["POST"])
def booking_note_create(request, creator_id):
    """Create note for creator"""
    creator = get_object_or_404(Creator, id=creator_id, is_active=True, deleted_at__isnull=True)
    
    note = CreatorNote.objects.create(
        creator=creator,
        user=request.user,
        title=request.POST.get('title', '').strip(),
        content=request.POST.get('content', '').strip(),
        note_type=request.POST.get('note_type', 'other'),
    )
    
    messages.success(request, 'Note đã được thêm.')
    return redirect('marketing:booking_creator_detail', creator_id=creator.id)


@marketing_permission_required("MarketingManager", "MarketingStaff")
@require_http_methods(["POST"])
def booking_note_delete(request, creator_id, note_id):
    """Soft delete note"""
    creator = get_object_or_404(Creator, id=creator_id, is_active=True, deleted_at__isnull=True)
    note = get_object_or_404(CreatorNote, id=note_id, creator=creator, is_active=True, deleted_at__isnull=True)
    
    note.is_active = False
    note.deleted_at = timezone.now()
    note.save()
    
    messages.success(request, 'Note đã được xóa.')
    return redirect('marketing:booking_creator_detail', creator_id=creator.id)


# ==================== RATE CARD MANAGEMENT ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
@require_http_methods(["POST"])
def booking_ratecard_create(request, creator_id):
    """Create rate card for creator"""
    creator = get_object_or_404(Creator, id=creator_id, is_active=True, deleted_at__isnull=True)
    
    try:
        channel_id = request.POST.get('channel_id') or None
        channel = None
        if channel_id:
            channel = CreatorChannel.objects.filter(
                id=channel_id, creator=creator, is_active=True, deleted_at__isnull=True
            ).first()
        
        rate_card = CreatorRateCard.objects.create(
            creator=creator,
            channel=channel,
            deliverable_type=request.POST.get('deliverable_type', 'video_single'),
            description=request.POST.get('description', '').strip() or None,
            price=Decimal(request.POST.get('price', 0) or 0),
            currency=request.POST.get('currency', 'VND'),
            valid_from=request.POST.get('valid_from') or None,
            valid_to=request.POST.get('valid_to') or None,
        )
        
        messages.success(request, 'Rate card đã được thêm.')
    except Exception as e:
        messages.error(request, f'Lỗi khi tạo rate card: {str(e)}')
    
    return redirect('marketing:booking_creator_detail', creator_id=creator.id)


@marketing_permission_required("MarketingManager", "MarketingStaff")
@require_http_methods(["POST"])
def booking_ratecard_delete(request, creator_id, ratecard_id):
    """Soft delete rate card"""
    creator = get_object_or_404(Creator, id=creator_id, is_active=True, deleted_at__isnull=True)
    rate_card = get_object_or_404(CreatorRateCard, id=ratecard_id, creator=creator, is_active=True, deleted_at__isnull=True)
    
    rate_card.is_active = False
    rate_card.deleted_at = timezone.now()
    rate_card.save()
    
    messages.success(request, 'Rate card đã được xóa.')
    return redirect('marketing:booking_creator_detail', creator_id=creator.id)


# ==================== IMPORT/EXPORT CENTER ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
def booking_import_export(request):
    """Import/Export center"""
    if not can_import_export(request.user):
        messages.error(request, 'Bạn không có quyền import/export.')
        return redirect('marketing:booking_creator_list')
    
    context = {
        'title': 'Import/Export Center',
        'can_import_export': True,
    }
    return render(request, 'marketing/booking/import_export.html', context)


@marketing_permission_required("MarketingManager", "MarketingStaff")
@require_http_methods(["POST"])
def booking_import_process(request):
    """Process import file"""
    if not can_import_export(request.user):
        return JsonResponse({'error': 'Không có quyền import'}, status=403)
    
    import_type = request.POST.get('import_type', 'creators')
    dry_run = request.POST.get('dry_run') == 'true'
    
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Không có file'}, status=400)
    
    file = request.FILES['file']
    
    try:
        if import_type == 'creators':
            result = import_creators_csv(file, dry_run=dry_run)
        elif import_type == 'channels':
            result = import_channels_csv(file, dry_run=dry_run)
        elif import_type == 'contacts':
            result = import_contacts_csv(file, dry_run=dry_run)
        else:
            return JsonResponse({'error': 'Loại import không hợp lệ'}, status=400)
        
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@marketing_permission_required("MarketingManager", "MarketingStaff")
def booking_export(request):
    """Export creators with current filters"""
    if not can_import_export(request.user):
        messages.error(request, 'Bạn không có quyền export.')
        return redirect('marketing:booking_creator_list')
    
    format_type = request.GET.get('format', 'csv')
    
    # Get same filters as list view
    search = request.GET.get('search', '').strip()
    status_filter = request.GET.getlist('status', [])
    platform_filter = request.GET.get('platform', '')
    tag_ids = request.GET.getlist('tags', [])
    
    # Build queryset (same as list view)
    queryset = Creator.objects.filter(is_active=True, deleted_at__isnull=True)
    
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) |
            Q(alias__icontains=search) |
            Q(channels__handle__icontains=search) |
            Q(contacts__phone__icontains=search) |
            Q(contacts__email__icontains=search)
        ).distinct()
    
    if status_filter:
        queryset = queryset.filter(status__in=status_filter)
    
    if platform_filter:
        queryset = queryset.filter(channels__platform=platform_filter).distinct()
    
    if tag_ids:
        queryset = queryset.filter(tag_maps__tag_id__in=tag_ids).distinct()
    
    if format_type == 'csv':
        return export_creators_csv(queryset)
    else:
        return export_creators_xlsx(queryset)


@marketing_permission_required("MarketingManager", "MarketingStaff")
def booking_export_template(request):
    """Download import template"""
    import_type = request.GET.get('type', 'creators')
    
    if import_type == 'creators':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="template_creators.csv"'
        writer = csv.writer(response)
        writer.writerow(['creator_key', 'name', 'alias', 'gender', 'dob', 'location', 'niche', 'priority_score', 'status', 'note_internal'])
        writer.writerow(['EXAMPLE_001', 'Nguyễn Văn A', 'Creator A', 'male', '1990-01-01', 'Hà Nội', 'beauty', '7', 'active', 'Ghi chú nội bộ'])
    elif import_type == 'channels':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="template_channels.csv"'
        writer = csv.writer(response)
        writer.writerow(['creator_key', 'platform', 'handle', 'profile_url', 'external_id', 'follower_count', 'avg_view_10', 'avg_engagement_rate'])
        writer.writerow(['EXAMPLE_001', 'tiktok', '@example', 'https://tiktok.com/@example', '123456', '100000', '50000', '5.5'])
    elif import_type == 'contacts':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="template_contacts.csv"'
        writer = csv.writer(response)
        writer.writerow(['creator_key', 'contact_type', 'name', 'phone', 'zalo', 'email', 'wechat', 'note', 'is_primary'])
        writer.writerow(['EXAMPLE_001', 'owner', 'Nguyễn Văn A', '0901234567', '0901234567', 'example@email.com', '', 'Liên hệ chính', 'true'])
    else:
        return HttpResponse('Invalid type', status=400)
    
    return response


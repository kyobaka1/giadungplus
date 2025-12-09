# marketing/views.py
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import logging

# Setup logger for debugging
logger = logging.getLogger(__name__)
from marketing.utils import marketing_permission_required
from marketing.services.image_extractor import (
    extract_images_from_html,
    normalize_image_url,
    filter_images,
    get_image_info
)
import json
import requests
import zipfile
import io
import os
import re
import codecs
from pathlib import Path
from urllib.parse import urlparse, unquote
from PIL import Image

# ==================== SHOPEE SHOP MANAGER ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
def shopee_overview(request):
    """Shopee Shop Manager - Overview"""
    context = {
        "title": "Shopee Shop Manager - Overview",
    }
    return render(request, "marketing/shopee/overview.html", context)

@marketing_permission_required("MarketingManager", "MarketingStaff")
def shopee_product(request):
    """Shopee Shop Manager - Product"""
    context = {
        "title": "Shopee Shop Manager - Product",
    }
    return render(request, "marketing/shopee/product.html", context)

@marketing_permission_required("MarketingManager", "MarketingStaff")
def shopee_roas_manager(request):
    """Shopee Shop Manager - ROAS Manager"""
    context = {
        "title": "Shopee Shop Manager - ROAS Manager",
    }
    return render(request, "marketing/shopee/roas_manager.html", context)

@marketing_permission_required("MarketingManager", "MarketingStaff")
def shopee_flash_sale(request):
    """Shopee Shop Manager - Flash Sale"""
    context = {
        "title": "Shopee Shop Manager - Flash Sale",
    }
    return render(request, "marketing/shopee/flash_sale.html", context)

# ==================== TIKTOK BOOKING ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
def tiktok_overview(request):
    """Tiktok Booking - Overview"""
    context = {
        "title": "Tiktok Booking - Overview",
    }
    return render(request, "marketing/tiktok/overview.html", context)

@marketing_permission_required("MarketingManager", "MarketingStaff")
def tiktok_koc_kol_list(request):
    """Tiktok Booking - KOC/KOL List"""
    context = {
        "title": "Tiktok Booking - KOC/KOL List",
    }
    return render(request, "marketing/tiktok/koc_kol_list.html", context)

@marketing_permission_required("MarketingManager", "MarketingStaff")
def tiktok_booking_contact(request):
    """Tiktok Booking - Booking Contact"""
    context = {
        "title": "Tiktok Booking - Booking Contact",
    }
    return render(request, "marketing/tiktok/booking_contact.html", context)

@marketing_permission_required("MarketingManager", "MarketingStaff")
def tiktok_booking_manager(request):
    """Tiktok Booking - Booking Manager"""
    context = {
        "title": "Tiktok Booking - Booking Manager",
    }
    return render(request, "marketing/tiktok/booking_manager.html", context)

@marketing_permission_required("MarketingManager", "MarketingStaff")
def tiktok_tracking_video_booking(request):
    """Tiktok Booking - Tracking Video Booking"""
    context = {
        "title": "Tiktok Booking - Tracking Video Booking",
    }
    return render(request, "marketing/tiktok/tracking_video_booking.html", context)

# ==================== TOOLS ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
def tools_copy_images(request):
    """Tools - Copy Images"""
    context = {
        "title": "Tools - Copy Images",
        "images": [],
    }
    
    if request.method == 'POST':
        html_content = request.POST.get('html_content', '')
        
        # Extract images (không filter ngay, filter sẽ làm ở client-side)
        images = extract_images_from_html(html_content)
        
        context.update({
            'images': images,
            'html_content': html_content,
        })
    
    return render(request, "marketing/tools/copy_images.html", context)

@csrf_exempt
@marketing_permission_required("MarketingManager", "MarketingStaff")
def tools_copy_images_api(request):
    """API endpoint để extract images từ HTML"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        html_content = data.get('html_content', '')
        
        if not html_content:
            return JsonResponse({'error': 'HTML content is required'}, status=400)
        
        images = extract_images_from_html(html_content)
        
        return JsonResponse({
            'success': True,
            'images': images,
            'count': len(images)
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@marketing_permission_required("MarketingManager", "MarketingStaff")
def tools_copy_images_download(request):
    """Download tất cả images dưới dạng ZIP với convert format"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        images = data.get('images', [])
        base_name = data.get('base_name', 'images')
        target_format = data.get('format', 'original')  # jpg, png, webp, original
        
        if not images:
            return JsonResponse({'error': 'No images to download'}, status=400)
        
        # Debug: log số lượng images
        print(f"[DEBUG] Download request: {len(images)} images, format: {target_format}")
        
        # Map format
        format_map = {
            'jpg': 'JPEG',
            'jpeg': 'JPEG',
            'png': 'PNG',
            'webp': 'WEBP',
        }
        
        # Tạo ZIP file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            success_count = 0
            for idx, img_data in enumerate(images, start=1):
                url = img_data.get('normalized_url') or img_data.get('original_url')
                if not url:
                    print(f"[DEBUG] Image {idx}: No URL found")
                    continue
                
                # Fix unicode escapes (e.g., \u002D -> -)
                # URL có thể bị escape từ JavaScript JSON.stringify
                # Replace unicode escapes: \u002D -> -
                url = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), url)
                # Replace other common escapes
                url = url.replace('\\/', '/').replace('\\"', '"').replace("\\'", "'")
                # Remove any remaining backslashes before special chars
                url = url.replace('\\-', '-').replace('\\_', '_')
                
                print(f"[DEBUG] Fixed URL {idx}: {url[:80]}...")
                
                try:
                    print(f"[DEBUG] Downloading image {idx}: {url[:80]}...")
                    response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
                    if response.status_code == 200:
                        image_content = response.content
                        if not image_content:
                            print(f"[DEBUG] Image {idx}: Empty content")
                            continue
                        
                        # Convert format nếu cần
                        if target_format != 'original':
                            try:
                                # Mở ảnh với PIL
                                img = Image.open(io.BytesIO(image_content))
                                
                                # Convert RGBA sang RGB nếu cần (cho JPG)
                                if target_format.lower() in ['jpg', 'jpeg'] and img.mode in ('RGBA', 'LA', 'P'):
                                    # Tạo background trắng
                                    background = Image.new('RGB', img.size, (255, 255, 255))
                                    if img.mode == 'P':
                                        img = img.convert('RGBA')
                                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                                    img = background
                                elif img.mode == 'P':
                                    img = img.convert('RGB')
                                
                                # Convert sang format mới
                                pil_format = format_map.get(target_format.lower(), 'JPEG')
                                output_buffer = io.BytesIO()
                                img.save(output_buffer, format=pil_format, quality=95)
                                image_content = output_buffer.getvalue()
                                ext = target_format.lower()
                            except Exception as e:
                                # Nếu convert lỗi, dùng ảnh gốc
                                parsed_url = urlparse(url)
                                path = parsed_url.path
                                ext = os.path.splitext(path)[1] or '.jpg'
                                if ext.startswith('.'):
                                    ext = ext[1:]
                        else:
                            # Giữ nguyên format gốc
                            parsed_url = urlparse(url)
                            path = parsed_url.path
                            ext = os.path.splitext(path)[1] or '.jpg'
                            if ext.startswith('.'):
                                ext = ext[1:]
                        
                        # Tên file: base_name_001, base_name_002, ...
                        filename = f"{base_name}_{idx:03d}.{ext}"
                        zip_file.writestr(filename, image_content)
                        success_count += 1
                        print(f"[DEBUG] Image {idx}: Successfully added to ZIP")
                    else:
                        print(f"[DEBUG] Image {idx}: HTTP {response.status_code}")
                except Exception as e:
                    # Bỏ qua lỗi download từng ảnh
                    print(f"[DEBUG] Image {idx}: Error - {str(e)}")
                    continue
            
            print(f"[DEBUG] Total success: {success_count}/{len(images)}")
        
        zip_buffer.seek(0)
        zip_size = len(zip_buffer.getvalue())
        print(f"[DEBUG] ZIP file size: {zip_size} bytes")
        
        if zip_size == 0:
            return JsonResponse({'error': 'ZIP file is empty. No images were downloaded successfully.'}, status=400)
        
        response = HttpResponse(zip_buffer.read(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{base_name}.zip"'
        return response
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@marketing_permission_required("MarketingManager", "MarketingStaff")
def tools_get_videos(request):
    """Tools - Get Videos - Hiển thị danh sách video đã được track"""
    from marketing.models import MediaTrack
    from marketing.services.video_thumbnail import generate_thumbnail_from_video_url
    import threading
    
    # Chỉ hiển thị video của user đang login
    current_username = request.user.username
    media_tracks = MediaTrack.objects.filter(user_name=current_username)
    
    # Tự động generate thumbnail cho video không có thumbnail (chạy background)
    def generate_missing_thumbnails():
        """Background task để generate thumbnail cho video không có thumbnail"""
        try:
            # Lấy các video không có thumbnail và có extension là mp4 hoặc mov (chỉ của user hiện tại)
            videos_without_thumbnail = MediaTrack.objects.filter(
                user_name=current_username,
                thumbnail_url__isnull=True,
                file_extension__in=['mp4', 'mov']
            ).exclude(media_url__startswith='blob:').exclude(media_url__startswith='data:')[:10]  # Giới hạn 10 video mỗi lần
            
            for track in videos_without_thumbnail:
                try:
                    print(f"[GDP Media Tracker] Generating thumbnail for video ID {track.id}: {track.media_url[:100]}")
                    thumbnail_url = generate_thumbnail_from_video_url(track.media_url)
                    if thumbnail_url:
                        track.thumbnail_url = thumbnail_url
                        track.save(update_fields=['thumbnail_url'])
                        print(f"[GDP Media Tracker] ✅ Thumbnail generated for video ID {track.id}: {thumbnail_url}")
                    else:
                        print(f"[GDP Media Tracker] ⚠️ Failed to generate thumbnail for video ID {track.id}")
                except Exception as e:
                    print(f"[GDP Media Tracker] ❌ Error generating thumbnail for video ID {track.id}: {e}")
                    continue
        except Exception as e:
            print(f"[GDP Media Tracker] ❌ Error in generate_missing_thumbnails: {e}")
    
    # Chạy background task (không block request)
    if request.GET.get('generate_thumbnails') == '1':
        # Chạy trong thread riêng để không block response
        thread = threading.Thread(target=generate_missing_thumbnails, daemon=True)
        thread.start()
    
    context = {
        "title": "Tools - Get Videos",
        "media_tracks": media_tracks[:100],  # Giới hạn 100 items mới nhất
        "total_count": media_tracks.count(),
        "current_username": current_username,
    }
    return render(request, "marketing/tools/get_videos.html", context)

@csrf_exempt
def tools_get_videos_api(request):
    """
    API endpoint để nhận dữ liệu từ Chrome Extension
    POST /marketing/tools/get-videos/api/
    
    Expected JSON payload:
    {
        "user_name": "username",
        "page_url": "https://...",
        "page_title": "Page Title",
        "media_url": "https://...",
        "file_extension": "mp4",
        "mime_type": "video/mp4",
        "source_type": "video_tag",
        "tab_id": 123,
        "thumbnail_url": "https://..." (optional)
    }
    """
    # Add CORS headers for Chrome Extension
    response_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
    }
    
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print(f"[GDP Media Tracker API] OPTIONS preflight request from: {request.META.get('HTTP_ORIGIN', 'unknown')}")
        response = HttpResponse()
        for key, value in response_headers.items():
            response[key] = value
        return response
    
    if request.method != 'POST':
        print(f"[GDP Media Tracker API] Wrong method: {request.method} (expected POST)")
        response = JsonResponse({'error': 'Method not allowed'}, status=405)
        for key, value in response_headers.items():
            response[key] = value
        return response
    
    # Log request info
    print(f"[GDP Media Tracker API] ========== NEW REQUEST ==========")
    print(f"[GDP Media Tracker API] Method: {request.method}")
    print(f"[GDP Media Tracker API] Path: {request.path}")
    print(f"[GDP Media Tracker API] Full URL: {request.build_absolute_uri()}")
    print(f"[GDP Media Tracker API] Origin: {request.META.get('HTTP_ORIGIN', 'none')}")
    print(f"[GDP Media Tracker API] Referer: {request.META.get('HTTP_REFERER', 'none')}")
    print(f"[GDP Media Tracker API] Content-Type: {request.META.get('CONTENT_TYPE', 'none')}")
    print(f"[GDP Media Tracker API] Body length: {len(request.body)} bytes")
    if request.body:
        try:
            print(f"[GDP Media Tracker API] Body preview: {request.body.decode('utf-8')[:500]}")
        except:
            print(f"[GDP Media Tracker API] Body (raw): {request.body[:200]}")
    else:
        print(f"[GDP Media Tracker API] Body is empty!")
    
    try:
        data = json.loads(request.body)
        
        # Log incoming request for debugging
        print(f"[GDP Media Tracker API] ✅ JSON parsed successfully")
        print(f"[GDP Media Tracker API] User: {data.get('user_name')}")
        print(f"[GDP Media Tracker API] Page URL: {data.get('page_url', '')[:100]}")
        print(f"[GDP Media Tracker API] Media URL: {data.get('media_url', '')[:200]}")
        print(f"[GDP Media Tracker API] File extension: {data.get('file_extension')}")
        print(f"[GDP Media Tracker API] Source type: {data.get('source_type')}")
        
        # Validate required fields
        required_fields = ['user_name', 'page_url', 'media_url', 'file_extension']
        for field in required_fields:
            if not data.get(field):
                response = JsonResponse({'error': f'Missing required field: {field}'}, status=400)
                for key, value in response_headers.items():
                    response[key] = value
                return response
        
        # Validate file extension
        allowed_extensions = ['mp3', 'mp4', 'mov']
        file_ext = data.get('file_extension', '').lower().strip('.')
        if file_ext not in allowed_extensions:
            response = JsonResponse({'error': f'Invalid file extension. Allowed: {", ".join(allowed_extensions)}'}, status=400)
            for key, value in response_headers.items():
                response[key] = value
            return response
        
        # Check if this media_url already exists (avoid duplicates - không phân biệt user)
        from marketing.models import MediaTrack
        existing = MediaTrack.objects.filter(
            media_url=data['media_url']
        ).first()
        
        if existing:
            result = JsonResponse({
                'success': True,
                'message': 'Media already tracked',
                'id': existing.id,
                'created_at': existing.created_at.isoformat()
            })
            for key, value in response_headers.items():
                result[key] = value
            return result
        
        # Try to find thumbnail if not provided
        thumbnail_url = data.get('thumbnail_url', '')
        if not thumbnail_url and file_ext in ['mp4', 'mov']:
            # Try to find thumbnail URL pattern
            from marketing.services.video_thumbnail import find_thumbnail_url_pattern, check_url_exists
            potential_thumbnail = find_thumbnail_url_pattern(data['media_url'])
            if potential_thumbnail and check_url_exists(potential_thumbnail):
                thumbnail_url = potential_thumbnail
                print(f"[GDP Media Tracker API] Found thumbnail URL: {thumbnail_url[:200]}")
        
        # Create new MediaTrack
        media_track = MediaTrack.objects.create(
            user_name=data['user_name'],
            page_url=data['page_url'],
            page_title=data.get('page_title', '')[:500],
            media_url=data['media_url'],
            file_extension=file_ext,
            mime_type=data.get('mime_type', '')[:100],
            source_type=data.get('source_type', 'video_tag'),
            tab_id=data.get('tab_id'),
            thumbnail_url=thumbnail_url
        )
        
        print(f"[GDP Media Tracker API] Successfully saved: ID={media_track.id}, URL={media_track.media_url[:100]}")
        
        result = JsonResponse({
            'success': True,
            'message': 'Media tracked successfully',
            'id': media_track.id,
            'created_at': media_track.created_at.isoformat()
        })
        # Add CORS headers
        for key, value in response_headers.items():
            result[key] = value
        return result
        
    except json.JSONDecodeError as e:
        print(f"[GDP Media Tracker API] JSON decode error: {str(e)}")
        response = JsonResponse({'error': 'Invalid JSON'}, status=400)
        for key, value in response_headers.items():
            response[key] = value
        return response
    except Exception as e:
        import traceback
        print(f"[GDP Media Tracker API] Error: {str(e)}")
        print(traceback.format_exc())
        response = JsonResponse({'error': str(e)}, status=500)
        for key, value in response_headers.items():
            response[key] = value
        return response

# ==================== DASHBOARD ====================

@marketing_permission_required("MarketingManager", "MarketingStaff")
def dashboard(request):
    """Marketing Dashboard - Trang chủ"""
    context = {
        "title": "Marketing - Dashboard",
    }
    return render(request, "marketing/dashboard.html", context)

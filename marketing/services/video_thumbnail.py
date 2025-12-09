"""
Service để tạo thumbnail từ video URL
"""
import requests
import os
from urllib.parse import urlparse
from PIL import Image
import io
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("[Video Thumbnail] Warning: opencv-python not installed. Thumbnail generation will be disabled.")

import numpy as np
from django.conf import settings
import hashlib
from pathlib import Path

def generate_thumbnail_from_video_url(video_url, output_dir=None):
    """
    Tạo thumbnail từ video URL bằng cách download video và extract frame đầu tiên.
    
    Args:
        video_url: URL của video
        output_dir: Thư mục để lưu thumbnail (default: assets/Images_thumb_video_mkt/)
    
    Returns:
        Đường dẫn static URL của thumbnail (ví dụ: /static/Images_thumb_video_mkt/xxx.jpg)
        hoặc None nếu không thể tạo
    """
    if not CV2_AVAILABLE:
        print("[Video Thumbnail] ❌ OpenCV not available. Please install: pip install opencv-python-headless")
        return None
    
    if output_dir is None:
        output_dir = os.path.join(settings.BASE_DIR, 'assets', 'Images_thumb_video_mkt')
    
    # Tạo thư mục nếu chưa có
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Tạo tên file từ hash của URL
        url_hash = hashlib.md5(video_url.encode()).hexdigest()
        thumbnail_filename = f"{url_hash}.jpg"
        thumbnail_path = os.path.join(output_dir, thumbnail_filename)
        
        # Nếu đã có thumbnail rồi, return luôn
        if os.path.exists(thumbnail_path):
            static_url = f"/static/Images_thumb_video_mkt/{thumbnail_filename}"
            print(f"[Video Thumbnail] Thumbnail already exists: {static_url}")
            return static_url
        
        print(f"[Video Thumbnail] Downloading video from: {video_url[:100]}...")
        
        # Download video (chỉ một phần đầu để tiết kiệm bandwidth)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Range': 'bytes=0-10485760',  # Chỉ download 10MB đầu tiên
            'Referer': video_url  # Một số site cần referer
        }
        
        try:
            response = requests.get(video_url, headers=headers, stream=True, timeout=30, allow_redirects=True)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"[Video Thumbnail] ❌ Error downloading video: {e}")
            return None
        
        # Lưu video tạm thời
        temp_video_path = os.path.join(output_dir, f"temp_{url_hash}.mp4")
        
        try:
            with open(temp_video_path, 'wb') as f:
                downloaded = 0
                max_size = 10 * 1024 * 1024  # 10MB
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        # Giới hạn 10MB
                        if downloaded > max_size:
                            print(f"[Video Thumbnail] Reached 10MB limit, stopping download")
                            break
        except Exception as e:
            print(f"[Video Thumbnail] ❌ Error writing video file: {e}")
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            return None
        
        file_size = os.path.getsize(temp_video_path)
        print(f"[Video Thumbnail] Video downloaded ({file_size} bytes), extracting frame...")
        
        if file_size < 1024:  # File quá nhỏ, có thể không phải video hợp lệ
            print(f"[Video Thumbnail] ⚠️ Video file too small ({file_size} bytes), may not be valid")
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            return None
        
        # Extract frame đầu tiên bằng OpenCV
        try:
            cap = cv2.VideoCapture(temp_video_path)
            
            if not cap.isOpened():
                print(f"[Video Thumbnail] ❌ Error: Cannot open video file with OpenCV")
                if os.path.exists(temp_video_path):
                    os.remove(temp_video_path)
                return None
            
            # Đọc frame đầu tiên
            ret, frame = cap.read()
            cap.release()
            
            # Xóa file video tạm ngay sau khi đọc xong
            try:
                if os.path.exists(temp_video_path):
                    os.remove(temp_video_path)
            except:
                pass
            
            if not ret or frame is None:
                print(f"[Video Thumbnail] ❌ Error: Cannot read frame from video (ret={ret}, frame is None={frame is None})")
                return None
        except Exception as e:
            print(f"[Video Thumbnail] ❌ Error with OpenCV: {e}")
            import traceback
            traceback.print_exc()
            if os.path.exists(temp_video_path):
                try:
                    os.remove(temp_video_path)
                except:
                    pass
            return None
        
        # Resize frame nếu quá lớn (max 1280x720)
        height, width = frame.shape[:2]
        print(f"[Video Thumbnail] Frame size: {width}x{height}")
        
        if width > 1280 or height > 720:
            scale = min(1280 / width, 720 / height)
            new_width = int(width * scale)
            new_height = int(height * scale)
            print(f"[Video Thumbnail] Resizing to: {new_width}x{new_height}")
            frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
        
        # Convert BGR to RGB (OpenCV uses BGR, PIL uses RGB)
        try:
            if len(frame.shape) == 3:
                if frame.shape[2] == 3:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                elif frame.shape[2] == 4:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
                else:
                    print(f"[Video Thumbnail] ⚠️ Unexpected frame shape: {frame.shape}")
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                # Grayscale, convert to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
        except Exception as e:
            print(f"[Video Thumbnail] ❌ Error converting color: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        # Save as JPEG
        try:
            img = Image.fromarray(frame_rgb)
            img.save(thumbnail_path, 'JPEG', quality=85, optimize=True)
            print(f"[Video Thumbnail] ✅ Thumbnail saved to: {thumbnail_path}")
        except Exception as e:
            print(f"[Video Thumbnail] ❌ Error saving image: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        # Verify file was created
        if not os.path.exists(thumbnail_path):
            print(f"[Video Thumbnail] ❌ Thumbnail file was not created!")
            return None
        
        file_size = os.path.getsize(thumbnail_path)
        print(f"[Video Thumbnail] Thumbnail file size: {file_size} bytes")
        
        if file_size == 0:
            print(f"[Video Thumbnail] ❌ Thumbnail file is empty!")
            os.remove(thumbnail_path)
            return None
        
        static_url = f"/static/Images_thumb_video_mkt/{thumbnail_filename}"
        print(f"[Video Thumbnail] ✅ Thumbnail created successfully: {static_url}")
        
        return static_url
        
    except requests.RequestException as e:
        print(f"[Video Thumbnail] ❌ Error downloading video: {e}")
        return None
    except Exception as e:
        print(f"[Video Thumbnail] ❌ Error generating thumbnail: {e}")
        import traceback
        traceback.print_exc()
        return None

def find_thumbnail_url_pattern(video_url):
    """
    Tìm thumbnail URL dựa trên pattern phổ biến.
    """
    if not video_url:
        return None
    
    try:
        parsed = urlparse(video_url)
        path = parsed.path
        
        # Pattern 1: Thay .mp4 thành .jpg/.png
        patterns = [
            video_url.replace('.mp4', '.jpg'),
            video_url.replace('.mp4', '.png'),
            video_url.replace('.mp4', '.webp'),
            video_url.replace('.mov', '.jpg'),
            video_url.replace('.mov', '.png'),
        ]
        
        # Pattern 2: Thêm _thumb hoặc _thumbnail
        if path.endswith('.mp4') or path.endswith('.mov'):
            base_path = path.rsplit('.', 1)[0]
            ext = path.rsplit('.', 1)[1]
            patterns.extend([
                f"{parsed.scheme}://{parsed.netloc}{base_path}_thumb.jpg",
                f"{parsed.scheme}://{parsed.netloc}{base_path}_thumbnail.jpg",
                f"{parsed.scheme}://{parsed.netloc}{base_path}_thumb.png",
                f"{parsed.scheme}://{parsed.netloc}{base_path}_thumbnail.png",
            ])
        
        # Pattern 3: Thay stream/ thành thumbnail/
        if '/stream/' in path:
            patterns.append(video_url.replace('/stream/', '/thumbnail/').replace('.mp4', '.jpg'))
        
        # Trả về pattern đầu tiên (sẽ check sau)
        return patterns[0] if patterns else None
    except Exception as e:
        print(f"[Video Thumbnail] Error finding pattern: {e}")
        return None

def check_url_exists(url):
    """
    Kiểm tra xem URL có tồn tại không (HEAD request).
    """
    try:
        response = requests.head(url, timeout=5, allow_redirects=True)
        return response.status_code == 200
    except:
        return False


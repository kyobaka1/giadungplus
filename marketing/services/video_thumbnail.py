"""
Service để tạo thumbnail từ video URL
"""
import requests
import os
from urllib.parse import urlparse
from PIL import Image
import io

def generate_thumbnail_from_url(video_url, output_path=None):
    """
    Tạo thumbnail từ video URL.
    
    Args:
        video_url: URL của video
        output_path: Đường dẫn để lưu thumbnail (optional)
    
    Returns:
        URL hoặc path của thumbnail, hoặc None nếu không thể tạo
    """
    try:
        # Method 1: Thử tìm thumbnail URL pattern
        thumbnail_url = find_thumbnail_url_pattern(video_url)
        if thumbnail_url and check_url_exists(thumbnail_url):
            return thumbnail_url
        
        # Method 2: Nếu có ffmpeg, có thể extract frame từ video
        # Nhưng cần download video trước, tốn thời gian và bandwidth
        # Tạm thời skip method này
        
        return None
    except Exception as e:
        print(f"[Video Thumbnail] Error generating thumbnail: {e}")
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


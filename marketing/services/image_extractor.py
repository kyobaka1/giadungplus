# marketing/services/image_extractor.py
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import requests
from typing import List, Dict, Optional

def normalize_image_url(url: str) -> str:
    """
    Chuẩn hóa URL hình ảnh theo các quy tắc:
    - TMALL: bỏ _.webp để lấy .jpg
    - Bỏ _q50.jpg_.webp
    - Shopee: bỏ @resize_w48_nl.webp hoặc _tn
    - Bỏ resize nếu có
    - Ưu tiên .jpg .png trước webp
    """
    if not url:
        return url
    
    original_url = url
    
    # 1. Xử lý TMALL / Alibaba (alicdn.com)
    if 'alicdn.com' in url:
        # 1.1. Các pattern kiểu: .jpg_b.jpg, .jpg_sum.jpg -> .jpg
        # Ví dụ:
        #   https://cbu01.alicdn.com/..._cib.jpg_b.jpg  -> ..._cib.jpg
        #   https://cbu01.alicdn.com/..._cib.jpg_sum.jpg -> ..._cib.jpg
        url = re.sub(r'\.jpg_(?:b|sum)\.jpg$', '.jpg', url, flags=re.IGNORECASE)

        # 1.2. Bỏ _.webp ở cuối nếu có
        url = re.sub(r'\.jpg_\.webp$', '.jpg', url, flags=re.IGNORECASE)
        url = re.sub(r'\.png_\.webp$', '.png', url, flags=re.IGNORECASE)
        
        # 1.3. Bỏ _q50.jpg_.webp hoặc các pattern tương tự
        url = re.sub(r'_q\d+\.jpg_\.webp$', '.jpg', url, flags=re.IGNORECASE)
        url = re.sub(r'_q\d+\.png_\.webp$', '.png', url, flags=re.IGNORECASE)
    
    # 2. Xử lý Shopee: bỏ @resize_w48_nl.webp hoặc _tn
    if 'susercontent.com' in url or 'shopee' in url.lower():
        # Bỏ @resize_* pattern
        url = re.sub(r'@resize_[^\.]+\.webp$', '', url, flags=re.IGNORECASE)
        url = re.sub(r'@resize_[^\.]+$', '', url, flags=re.IGNORECASE)
        
        # Bỏ _tn ở cuối
        url = re.sub(r'_tn\.(jpg|png|webp)$', r'.\1', url, flags=re.IGNORECASE)
        url = re.sub(r'_tn$', '', url, flags=re.IGNORECASE)
    
    # 3. Bỏ resize pattern chung (nếu có)
    url = re.sub(r'@resize_[^\.\s]+', '', url, flags=re.IGNORECASE)
    
    # 4. Ưu tiên .jpg .png trước webp
    # Nếu có .webp, thử chuyển về .jpg hoặc .png nếu có thể
    if url.endswith('.webp'):
        # Thử tìm pattern .jpg hoặc .png trước .webp
        jpg_match = re.search(r'\.jpg', url, re.IGNORECASE)
        png_match = re.search(r'\.png', url, re.IGNORECASE)
        
        if jpg_match:
            url = url[:jpg_match.end()]
        elif png_match:
            url = url[:png_match.end()]
        else:
            # Nếu không có, giữ nguyên .webp
            pass
    
    # 5. Loại bỏ các query parameters không cần thiết (giữ lại nếu cần)
    # url = url.split('?')[0]  # Uncomment nếu muốn bỏ query params
    
    return url

def extract_images_from_html(html_content: str) -> List[Dict[str, any]]:
    """
    Extract tất cả hình ảnh từ HTML:
    - Từ thẻ <img src="...">
    - Từ background-image trong style
    - Từ data-src, data-lazy-src (lazy loading)
    """
    if not html_content:
        return []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    images = []
    seen_urls = set()
    
    # 1. Extract từ thẻ <img>
    img_tags = soup.find_all('img')
    for img in img_tags:
        # Thử các attribute: src, data-src, data-lazy-src, data-original
        for attr in ['src', 'data-src', 'data-lazy-src', 'data-original', 'data-url']:
            url = img.get(attr)
            if url:
                # Xử lý relative URL
                if url.startswith('//'):
                    url = 'https:' + url
                elif url.startswith('/'):
                    # Cần base URL để resolve, tạm thời bỏ qua
                    pass
                
                # Bỏ qua SVG
                if url.lower().endswith('.svg'):
                    continue
                
                normalized_url = normalize_image_url(url)
                
                if normalized_url and normalized_url not in seen_urls:
                    seen_urls.add(normalized_url)
                    images.append({
                        'original_url': url,
                        'normalized_url': normalized_url,
                        'source': 'img_tag',
                        'width': img.get('width'),
                        'height': img.get('height'),
                    })
    
    # 2. Extract từ background-image trong style
    elements_with_style = soup.find_all(style=re.compile(r'background-image', re.I))
    for element in elements_with_style:
        style = element.get('style', '')
        # Tìm url(...) trong background-image
        bg_matches = re.findall(r'background-image\s*:\s*url\(["\']?([^"\'()]+)["\']?\)', style, re.I)
        for bg_url in bg_matches:
            if bg_url.startswith('//'):
                bg_url = 'https:' + bg_url
            
            if bg_url.lower().endswith('.svg'):
                continue
            
            normalized_url = normalize_image_url(bg_url)
            
            if normalized_url and normalized_url not in seen_urls:
                seen_urls.add(normalized_url)
                images.append({
                    'original_url': bg_url,
                    'normalized_url': normalized_url,
                    'source': 'background_image',
                })
    
    # 3. Extract từ CSS trong <style> tags
    style_tags = soup.find_all('style')
    for style_tag in style_tags:
        css_content = style_tag.string or ''
        # Tìm url(...) trong CSS
        css_urls = re.findall(r'url\(["\']?([^"\'()]+)["\']?\)', css_content, re.I)
        for css_url in css_urls:
            if css_url.startswith('//'):
                css_url = 'https:' + css_url
            
            if css_url.lower().endswith('.svg'):
                continue
            
            normalized_url = normalize_image_url(css_url)
            
            if normalized_url and normalized_url not in seen_urls:
                seen_urls.add(normalized_url)
                images.append({
                    'original_url': css_url,
                    'normalized_url': normalized_url,
                    'source': 'css',
                })
    
    return images

def get_image_info(url: str) -> Optional[Dict]:
    """
    Lấy thông tin về hình ảnh (width, height, format) bằng cách HEAD request
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
        
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            content_length = response.headers.get('Content-Length')
            
            # Thử lấy dimensions từ PIL nếu có thể
            # Tạm thời trả về basic info
            return {
                'content_type': content_type,
                'content_length': content_length,
                'status_code': response.status_code,
            }
    except Exception as e:
        pass
    
    return None

def filter_images(images: List[Dict], min_width: Optional[int] = None, 
                 max_width: Optional[int] = None, 
                 formats: Optional[List[str]] = None) -> List[Dict]:
    """
    Lọc hình ảnh theo width và format
    """
    filtered = []
    
    for img in images:
        url = img.get('normalized_url', '')
        
        # Filter theo format
        if formats:
            url_lower = url.lower()
            matches_format = any(url_lower.endswith(f'.{fmt}') for fmt in formats)
            if not matches_format:
                continue
        
        # Filter theo width (cần fetch image để biết width thực tế)
        # Tạm thời bỏ qua filter width vì cần download image
        # Có thể implement sau nếu cần
        
        filtered.append(img)
    
    return filtered


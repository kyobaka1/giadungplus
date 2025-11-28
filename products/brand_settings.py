"""
Cài đặt nhãn hiệu - Quản lý nhãn hiệu được sử dụng (bật/tắt).

File này đọc danh sách nhãn hiệu bị TẮT từ brand_settings.json.
Nếu nhãn hiệu không có trong danh sách này -> nhãn hiệu đó BẬT (enabled).
"""

import json
from pathlib import Path

# Đường dẫn đến file settings
SETTINGS_FILE = Path(__file__).parent / "brand_settings.json"


def _load_settings():
    """Load settings từ JSON file."""
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data.get('disabled_brands', []))
        return set()
    except Exception:
        return set()


def _save_settings(disabled_brands: set):
    """Lưu settings vào JSON file."""
    try:
        data = {
            'disabled_brands': sorted(list(disabled_brands))
        }
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# Danh sách nhãn hiệu bị TẮT (load từ file)
DISABLED_BRANDS = _load_settings()


def is_brand_enabled(brand_name: str) -> bool:
    """
    Kiểm tra nhãn hiệu có được bật hay không.
    
    Args:
        brand_name: Tên nhãn hiệu cần kiểm tra
        
    Returns:
        True nếu nhãn hiệu được bật, False nếu bị tắt
    """
    if not brand_name:
        return True  # Nhãn hiệu rỗng luôn được bật
    
    return brand_name not in DISABLED_BRANDS


def get_enabled_brands(all_brands: list) -> list:
    """
    Lọc danh sách nhãn hiệu, chỉ trả về các nhãn hiệu được bật.
    
    Args:
        all_brands: Danh sách tất cả nhãn hiệu
        
    Returns:
        Danh sách nhãn hiệu được bật
    """
    return [brand for brand in all_brands if is_brand_enabled(brand)]


def get_disabled_brands() -> set:
    """
    Lấy danh sách nhãn hiệu bị tắt.
    
    Returns:
        Set các nhãn hiệu bị tắt
    """
    return DISABLED_BRANDS.copy()


def set_brand_enabled(brand_name: str, enabled: bool) -> bool:
    """
    Bật/tắt nhãn hiệu và lưu vào file.
    
    Args:
        brand_name: Tên nhãn hiệu
        enabled: True để bật, False để tắt
        
    Returns:
        True nếu lưu thành công, False nếu có lỗi
    """
    if not brand_name:
        return False
    
    global DISABLED_BRANDS
    
    if enabled:
        DISABLED_BRANDS.discard(brand_name)
    else:
        DISABLED_BRANDS.add(brand_name)
    
    return _save_settings(DISABLED_BRANDS)


def reload_settings():
    """Reload settings từ file (khi file được cập nhật từ bên ngoài)."""
    global DISABLED_BRANDS
    DISABLED_BRANDS = _load_settings()


def sync_brands_from_api(api_brands: list) -> int:
    """
    Đồng bộ brands từ API vào settings.
    Nếu có brand mới trong API mà chưa có trong settings -> tự động thêm vào (enabled).
    
    Args:
        api_brands: Danh sách brands từ API (list of dict với key 'name')
        
    Returns:
        Số lượng brands mới được thêm vào
    """
    global DISABLED_BRANDS
    
    # Lấy danh sách brand names từ API
    api_brand_names = set()
    for brand in api_brands:
        brand_name = brand.get("name") if isinstance(brand, dict) else str(brand)
        if brand_name:
            api_brand_names.add(brand_name)
    
    # Brands mới = có trong API nhưng chưa có trong settings (cả enabled và disabled)
    # Vì settings chỉ lưu disabled_brands, nên brands mới sẽ tự động enabled
    # Không cần làm gì thêm vì mặc định brand không có trong disabled_brands = enabled
    
    # Reload settings để đảm bảo có dữ liệu mới nhất
    reload_settings()
    
    # Đếm số brands mới (có trong API nhưng chưa từng được quản lý)
    # Vì chúng ta không lưu danh sách tất cả brands, nên không thể biết chính xác
    # Nhưng có thể kiểm tra xem có brand nào trong API mà không có trong disabled_brands
    # -> đó là brands mới (hoặc đã được enable)
    
    # Trả về 0 vì logic hiện tại: brand không có trong disabled_brands = enabled
    # Nên không cần "thêm" brands mới, chúng tự động enabled
    return 0

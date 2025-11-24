# kho/services/delivery_provider_service.py
"""
Delivery Provider Service - Lấy và cache thông tin delivery service providers từ Sapo API.
Mapping delivery_service_provider_id -> provider_name để hiển thị trong đơn hàng.
"""

from typing import Dict, Optional
import logging

from core.sapo_client import get_sapo_client

logger = logging.getLogger(__name__)

# Cache mapping delivery_service_provider_id -> provider_name
_provider_name_cache: Dict[int, str] = {}
_providers_loaded: bool = False


def get_provider_name(provider_id: Optional[int]) -> str:
    """
    Lấy tên của delivery service provider từ provider_id.
    
    Args:
        provider_id: Delivery service provider ID
        
    Returns:
        Provider name hoặc empty string nếu không tìm thấy
        
    Note:
        - Nếu chưa có trong cache, sẽ gọi API để lấy
        - Cache trong memory cho request hiện tại
    """
    if not provider_id:
        return ""
    
    # Nếu đã có trong cache, trả về ngay
    if provider_id in _provider_name_cache:
        return _provider_name_cache[provider_id]
    
    # Nếu chưa có, gọi API để lấy
    try:
        sapo = get_sapo_client()
        core_repo = sapo.core
        
        logger.debug(f"[DeliveryProviderService] Fetching provider: {provider_id}")
        
        response = core_repo.get_delivery_service_provider_raw(provider_id)
        provider_data = response.get("delivery_service_provider", {})
        
        provider_name = provider_data.get("name", "")
        
        # Cache kết quả
        if provider_name:
            _provider_name_cache[provider_id] = provider_name
            logger.debug(f"[DeliveryProviderService] Cached provider {provider_id}: {provider_name}")
        
        return provider_name
        
    except Exception as e:
        logger.warning(f"[DeliveryProviderService] Error fetching provider {provider_id}: {e}")
        return ""


def load_all_providers(force_reload: bool = False) -> Dict[int, str]:
    """
    Lấy toàn bộ delivery service providers từ Sapo API và cache mapping.
    
    Args:
        force_reload: Nếu True, reload lại cache dù đã load rồi
        
    Returns:
        Dict mapping {provider_id: provider_name}
        
    Note:
        - Pagination với limit=250 (max)
        - Cache trong memory cho request hiện tại
    """
    global _provider_name_cache, _providers_loaded
    
    # Nếu đã load và không force reload, trả về cache
    if _providers_loaded and not force_reload:
        return _provider_name_cache
    
    logger.info("[DeliveryProviderService] Loading all delivery service providers from Sapo API...")
    
    sapo = get_sapo_client()
    core_repo = sapo.core
    
    # Clear cache nếu force reload
    if force_reload:
        _provider_name_cache.clear()
    
    provider_name_map: Dict[int, str] = {}
    page = 1
    limit = 250  # Max limit theo Sapo API
    max_pages = 10  # Giới hạn an toàn (2500 providers - đủ cho hầu hết trường hợp)
    
    total_providers = 0
    
    while page <= max_pages:
        try:
            # Lấy providers với pagination
            response = core_repo.list_delivery_service_providers_raw(
                page=page,
                limit=limit,
                status="active"  # Chỉ lấy providers active
            )
            
            providers = response.get("delivery_service_providers", [])
            
            if not providers:
                break
            
            # Process từng provider
            for provider in providers:
                provider_id = provider.get("id")
                provider_name = provider.get("name")
                
                if provider_id and provider_name:
                    provider_name_map[provider_id] = provider_name
                    total_providers += 1
            
            logger.debug(f"[DeliveryProviderService] Loaded page {page}: {len(providers)} providers, total: {len(provider_name_map)}")
            
            # Check nếu hết providers (ít hơn limit)
            if len(providers) < limit:
                break
            
            page += 1
            
        except Exception as e:
            logger.error(f"[DeliveryProviderService] Error loading providers page {page}: {e}", exc_info=True)
            break
    
    # Update cache
    _provider_name_cache.update(provider_name_map)
    _providers_loaded = True
    
    logger.info(f"[DeliveryProviderService] Loaded {total_providers} delivery service providers")
    
    return _provider_name_cache


def clear_cache():
    """Xóa cache (dùng khi cần reload providers)"""
    global _provider_name_cache, _providers_loaded
    _provider_name_cache.clear()
    _providers_loaded = False


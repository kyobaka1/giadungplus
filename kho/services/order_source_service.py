# kho/services/order_source_service.py
"""
Order Source Service - Lấy và cache thông tin order sources từ Sapo API.
Mapping source_id -> source_name để hiển thị trong đơn hàng.
"""

from typing import Dict, Optional
import logging

from core.sapo_client import get_sapo_client

logger = logging.getLogger(__name__)

# Cache mapping source_id -> source_name
_source_name_cache: Dict[int, str] = {}
_sources_loaded: bool = False


def load_all_order_sources(force_reload: bool = False) -> Dict[int, str]:
    """
    Lấy toàn bộ order sources từ Sapo API và cache mapping source_id -> source_name.
    
    Args:
        force_reload: Nếu True, reload lại cache dù đã load rồi
        
    Returns:
        Dict mapping {source_id: source_name}
        
    Note:
        - Pagination với limit=250 (max)
        - Cache trong memory cho request hiện tại
    """
    global _source_name_cache, _sources_loaded
    
    # Nếu đã load và không force reload, trả về cache
    if _sources_loaded and not force_reload:
        return _source_name_cache
    
    logger.info("[OrderSourceService] Loading all order sources from Sapo API...")
    
    sapo = get_sapo_client()
    core_repo = sapo.core
    
    # Clear cache nếu force reload
    if force_reload:
        _source_name_cache.clear()
    
    source_name_map: Dict[int, str] = {}
    page = 1
    limit = 250  # Max limit theo Sapo API
    max_pages = 10  # Giới hạn an toàn (2500 sources - đủ cho hầu hết trường hợp)
    
    total_sources = 0
    
    while page <= max_pages:
        try:
            # Lấy order sources với pagination
            response = core_repo.list_order_sources_raw(
                page=page,
                limit=limit,
                query=""  # Empty query để lấy tất cả
            )
            
            order_sources = response.get("order_sources", [])
            
            if not order_sources:
                break
            
            # Process từng source
            for source in order_sources:
                source_id = source.get("id")
                source_name = source.get("name")
                
                if source_id and source_name:
                    source_name_map[source_id] = source_name
                    total_sources += 1
            
            logger.debug(f"[OrderSourceService] Loaded page {page}: {len(order_sources)} sources, total: {len(source_name_map)}")
            
            # Check nếu hết sources (ít hơn limit)
            if len(order_sources) < limit:
                break
            
            page += 1
            
        except Exception as e:
            logger.error(f"[OrderSourceService] Error loading order sources page {page}: {e}", exc_info=True)
            break
    
    # Update cache
    _source_name_cache.update(source_name_map)
    _sources_loaded = True
    
    logger.info(f"[OrderSourceService] Loaded {total_sources} order sources")
    
    return _source_name_cache


def get_source_name(source_id: Optional[int]) -> str:
    """
    Lấy tên của order source từ source_id.
    
    Args:
        source_id: Source ID
        
    Returns:
        Source name hoặc empty string nếu không tìm thấy
    """
    if not source_id:
        return ""
    
    # Ensure sources are loaded
    if not _sources_loaded:
        load_all_order_sources()
    
    return _source_name_cache.get(source_id, "")


def clear_cache():
    """Xóa cache (dùng khi cần reload sources)"""
    global _source_name_cache, _sources_loaded
    _source_name_cache.clear()
    _sources_loaded = False


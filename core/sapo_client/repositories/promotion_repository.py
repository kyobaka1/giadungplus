# core/sapo_client/repositories/promotion_repository.py
"""
Repository cho Sapo Promotion API.
Handles promotion programs, conditions, and gift configurations.
"""

from typing import Dict, Any
import logging

from core.base.repository import BaseRepository

logger = logging.getLogger(__name__)


class SapoPromotionRepository(BaseRepository):
    """
    Repository cho Sapo Promotion V2 API.
    Base URL: https://sisapsan.mysapogo.com/admin
    
    Endpoints:
    - /promotion_programs_v2/list.json - List promotion programs
    - /promotion_programs_v2/{id}/conditions.json - Get promotion conditions
    """
    
    def list_programs(
        self, 
        statuses: str = "active",
        page: int = 1,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Lấy danh sách promotion programs.
        
        Args:
            statuses: Trạng thái (active, inactive, all)
            page: Trang số
            limit: Số lượng/trang (max 100)
            
        Returns:
            {
                "metadata": {
                    "total": int,
                    "page": int,
                    "limit": int
                },
                "promotion_list": [...]
            }
            
        Example:
            GET /admin/promotion_programs_v2/list.json?page=1&limit=20&statuses=active
        """
        logger.debug(
            f"[SapoPromotionRepo] list_programs: statuses={statuses}, page={page}, limit={limit}"
        )
        
        return self.get("promotion_programs_v2/list.json", params={
            "page": page,
            "limit": limit,
            "statuses": statuses
        })
    
    def get_conditions(self, promotion_id: int) -> Dict[str, Any]:
        """
        Lấy conditions (điều kiện và quà tặng) của promotion program.
        
        Args:
            promotion_id: ID của promotion program
            
        Returns:
            {
                "metadata": {...},
                "condition_items": [
                    {
                        "id": int,
                        "conditions": [...],
                        "items": [...],  # Gifts
                        "multiple": bool,
                        ...
                    }
                ]
            }
            
        Example:
            GET /admin/promotion_programs_v2/256528/conditions.json
        """
        logger.debug(f"[SapoPromotionRepo] get_conditions: promotion_id={promotion_id}")
        
        return self.get(f"promotion_programs_v2/{promotion_id}/conditions.json")
    
    def get_program_detail(self, promotion_id: int) -> Dict[str, Any]:
        """
        Lấy chi tiết promotion program (nếu cần).
        
        Args:
            promotion_id: ID của promotion program
            
        Returns:
            {
                "promotion_program": {...}
            }
            
        Note: API này có thể không tồn tại, cần verify.
        Hiện tại có thể dùng list_programs với filter nếu cần.
        """
        logger.debug(f"[SapoPromotionRepo] get_program_detail: promotion_id={promotion_id}")
        
        return self.get(f"promotion_programs_v2/{promotion_id}.json")

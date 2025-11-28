# core/sapo_client/repositories/__init__.py
"""
Sapo API Repositories.
"""

from .core_repository import SapoCoreRepository
from .marketplace_repository import SapoMarketplaceRepository
from .promotion_repository import SapoPromotionRepository

__all__ = ['SapoCoreRepository', 'SapoMarketplaceRepository', 'SapoPromotionRepository']

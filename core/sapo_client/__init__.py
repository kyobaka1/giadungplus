# core/sapo_client/__init__.py
"""
Sapo Client package.
Provides SapoClient for accessing Sapo Core and Marketplace APIs.
"""

from typing import Optional
from .client import SapoClient
from .filters import BaseFilter
from .repositories import SapoCoreRepository, SapoMarketplaceRepository

# Singleton instance
_sapo_client: Optional[SapoClient] = None


def get_sapo_client() -> SapoClient:
    """
    Get singleton SapoClient instance (dùng chung toàn project).
    
    Returns:
        SapoClient instance
    """
    global _sapo_client
    if _sapo_client is None:
        _sapo_client = SapoClient()
    return _sapo_client


__all__ = [
    "SapoClient",
    "BaseFilter",
    "SapoCoreRepository",
    "SapoMarketplaceRepository",
    "get_sapo_client",
]

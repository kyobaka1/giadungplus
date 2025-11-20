# core/sapo_client/__init__.py
from typing import Optional
from .client import SapoClient
from .filters import BaseFilter
from .core_api import SapoCoreAPI
from .marketplace_api import SapoMarketplaceAPI

_sapo_client: Optional[SapoClient] = None


def get_sapo_client() -> SapoClient:
    """
    Singleton SapoClient dùng chung toàn project.
    """
    global _sapo_client
    if _sapo_client is None:
        _sapo_client = SapoClient()
    return _sapo_client


__all__ = [
    "SapoClient",
    "BaseFilter",
    "SapoCoreAPI",
    "SapoMarketplaceAPI",
    "get_sapo_client",
]

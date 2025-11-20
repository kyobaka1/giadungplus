"""
Base infrastructure package for core functionality.
Contains base classes for DTOs, repositories, and services.
"""

from .dto_base import BaseDTO
from .repository import BaseRepository

__all__ = ['BaseDTO', 'BaseRepository']

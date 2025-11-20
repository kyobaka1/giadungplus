# core/base/dto_base.py
"""
Base DTO class using Pydantic for all data transfer objects.
Provides automatic validation, JSON serialization, and type safety.
"""

from pydantic import BaseModel, ConfigDict
from typing import Dict, Any, Optional
import json


class BaseDTO(BaseModel):
    """
    Base class cho tất cả DTOs trong hệ thống.
    
    Features:
    - Automatic validation qua Pydantic
    - JSON serialization/deserialization
    - Type safety với Python type hints
    - Snake_case field names (giống Sapo API)
    
    Usage:
        class MyDTO(BaseDTO):
            id: int
            name: str
            created_on: Optional[datetime] = None
        
        # From dict
        dto = MyDTO.from_dict({"id": 1, "name": "Test"})
        
        # To dict
        data = dto.to_dict()
        
        # To JSON string
        json_str = dto.to_json_str()
    """
    
    model_config = ConfigDict(
        # Allow creation from ORM models (if needed)
        from_attributes=True,
        
        # Allow field population by name or alias
        populate_by_name=True,
        
        # Use enum values instead of enum objects
        use_enum_values=True,
        
        # Validate on assignment (not just on init)
        validate_assignment=True,
        
        # Allow arbitrary types (for complex nested objects)
        arbitrary_types_allowed=True,
    )
    
    def to_dict(self, exclude_none: bool = True) -> Dict[str, Any]:
        """
        Convert DTO to dictionary (snake_case).
        
        Args:
            exclude_none: If True, không include fields có giá trị None
            
        Returns:
            Dict với tất cả fields
        """
        return self.model_dump(
            by_alias=False,
            exclude_none=exclude_none,
            mode='python'
        )
    
    def to_json_str(self, exclude_none: bool = True, indent: Optional[int] = None) -> str:
        """
        Convert DTO to JSON string.
        
        Args:
            exclude_none: If True, không include fields có giá trị None
            indent: Số spaces để indent (None = compact)
            
        Returns:
            JSON string
        """
        return self.model_dump_json(
            by_alias=False,
            exclude_none=exclude_none,
            indent=indent
        )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """
        Create DTO from dictionary.
        
        Args:
            data: Dictionary chứa data
            
        Returns:
            Instance của DTO class
            
        Raises:
            ValidationError: Nếu data không hợp lệ
        """
        if not data:
            return None
        return cls.model_validate(data)
    
    @classmethod
    def from_json_str(cls, json_str: str):
        """
        Create DTO from JSON string.
        
        Args:
            json_str: JSON string
            
        Returns:
            Instance của DTO class
        """
        return cls.model_validate_json(json_str)
    
    def update_from_dict(self, data: Dict[str, Any]):
        """
        Update DTO fields từ dictionary.
        
        Args:
            data: Dictionary chứa fields cần update
        """
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

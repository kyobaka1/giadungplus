# core/sapo_client/filters.py
from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class BaseFilter:
    """
    Filter cơ bản – chỉ là cái dict param.
    Sau này nếu cần type-safe hơn thì mở rộng thêm.
    """
    params: Dict[str, Any] = field(default_factory=dict)

    def to_params(self) -> Dict[str, Any]:
        return self.params

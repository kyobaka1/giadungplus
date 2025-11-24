# customers/services/__init__.py
"""
Customer services package.

Public API:
- CustomerDTO, CustomerAddressDTO, CustomerGroupDTO, CustomerNoteDTO
- CustomerService
- CustomerDTOFactory
"""

from .dto import (
    CustomerDTO,
    CustomerAddressDTO,
    CustomerGroupDTO,
    CustomerNoteDTO,
    CustomerSaleOrderStatsDTO,
)
from .customer_service import CustomerService
from .customer_builder import CustomerDTOFactory

__all__ = [
    # DTOs
    'CustomerDTO',
    'CustomerAddressDTO',
    'CustomerGroupDTO',
    'CustomerNoteDTO',
    'CustomerSaleOrderStatsDTO',
    
    # Services
    'CustomerService',
    'CustomerDTOFactory',
]


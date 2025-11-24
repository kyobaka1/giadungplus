# customers/services/customer_builder.py
"""
CustomerDTOFactory - Factory để convert raw Sapo JSON sang CustomerDTO.
"""

from typing import Dict, Any, List, Optional
import logging

from .dto import (
    CustomerDTO, CustomerAddressDTO, CustomerGroupDTO, 
    CustomerNoteDTO, CustomerSaleOrderStatsDTO
)

logger = logging.getLogger(__name__)


class CustomerDTOFactory:
    """
    Factory để convert raw JSON từ Sapo API sang CustomerDTO.
    
    Usage:
        factory = CustomerDTOFactory()
        customer = factory.from_sapo_json(raw_customer_dict)
    """
    
    def from_sapo_json(self, payload: Dict[str, Any]) -> Optional[CustomerDTO]:
        """
        Convert JSON từ Sapo API sang CustomerDTO.
        
        Args:
            payload: Raw JSON từ /admin/customers/{id}.json
                    Có thể có key "customer" bao ngoài hoặc không
                    
        Returns:
            CustomerDTO instance với full validation
        """
        if not payload:
            return None
        
        # Unwrap "customer" key nếu có
        raw_customer = payload.get("customer", payload)
        
        if not raw_customer:
            logger.warning("Empty customer data")
            return None
        
        try:
            # Build nested objects
            addresses = self._build_addresses(raw_customer.get("addresses", []))
            customer_group = self._build_customer_group(raw_customer.get("customer_group"))
            sale_stats = self._build_sale_stats(raw_customer.get("sale_order"))
            
            # Build main CustomerDTO
            customer_data = {
                # Core fields
                "id": raw_customer.get("id"),
                "tenant_id": raw_customer.get("tenant_id"),
                "default_location_id": raw_customer.get("default_location_id"),
                "created_on": raw_customer.get("created_on"),
                "modified_on": raw_customer.get("modified_on"),
                "code": raw_customer.get("code"),
                "name": raw_customer.get("name"),
                "dob": raw_customer.get("dob"),
                "sex": raw_customer.get("sex"),
                "description": raw_customer.get("description"),
                "email": raw_customer.get("email"),
                "fax": raw_customer.get("fax"),
                "phone_number": raw_customer.get("phone_number"),
                
                # Mapped fields
                "tax_number": raw_customer.get("tax_number"),  # processing_status
                "website": raw_customer.get("website"),        # short_name
                
                # Group and assignment
                "customer_group_id": raw_customer.get("customer_group_id"),
                "group_id": raw_customer.get("group_id"),
                "group_ids": raw_customer.get("group_ids", []),
                "group_name": raw_customer.get("group_name"),
                "assignee_id": raw_customer.get("assignee_id"),
                
                # Payment and pricing
                "default_payment_term_id": raw_customer.get("default_payment_term_id"),
                "default_payment_method_id": raw_customer.get("default_payment_method_id"),
                "default_tax_type_id": raw_customer.get("default_tax_type_id"),
                "default_discount_rate": raw_customer.get("default_discount_rate"),
                "default_price_list_id": raw_customer.get("default_price_list_id"),
                
                # Tags and addresses
                "tags": raw_customer.get("tags", []),
                "addresses": addresses,
                
                # Nested objects
                "customer_group": customer_group,
                "sale_stats": sale_stats,
                
                # Status and financials
                "status": raw_customer.get("status"),
                "is_default": raw_customer.get("is_default", False),
                "debt": raw_customer.get("debt", 0.0),
                "apply_incentives": raw_customer.get("apply_incentives"),
                "total_expense": raw_customer.get("total_expense"),
            }
            
            return CustomerDTO.from_dict(customer_data)
            
        except Exception as e:
            logger.error(f"Error building CustomerDTO: {e}", exc_info=True)
            logger.error(f"Raw data: {raw_customer}")
            raise
    
    def _build_addresses(self, data_list: List[Dict[str, Any]]) -> List[CustomerAddressDTO]:
        """Build list of CustomerAddressDTO."""
        if not data_list:
            return []
        
        addresses = []
        for addr_data in data_list:
            try:
                addr = CustomerAddressDTO.from_dict(addr_data)
                addresses.append(addr)
            except Exception as e:
                logger.warning(f"Failed to build address: {e}")
                continue
        
        return addresses
    
    def _build_customer_group(self, data: Optional[Dict[str, Any]]) -> Optional[CustomerGroupDTO]:
        """Build CustomerGroupDTO từ raw data."""
        if not data:
            return None
        
        try:
            return CustomerGroupDTO.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to build customer group: {e}")
            return None
    
    def _build_sale_stats(self, data: Optional[Dict[str, Any]]) -> Optional[CustomerSaleOrderStatsDTO]:
        """Build CustomerSaleOrderStatsDTO từ raw data."""
        if not data:
            return None
        
        try:
            return CustomerSaleOrderStatsDTO.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to build sale stats: {e}")
            return None
    
    def from_note_json(self, payload: Dict[str, Any]) -> Optional[CustomerNoteDTO]:
        """
        Convert note JSON từ Sapo API sang CustomerNoteDTO.
        
        Args:
            payload: Raw JSON từ /admin/customers/{id}/notes.json
                    hoặc từ response của POST note
                    
        Returns:
            CustomerNoteDTO instance
        """
        if not payload:
            return None
        
        # Unwrap "note" key nếu có
        raw_note = payload.get("note", payload)
        
        if not raw_note:
            return None
        
        try:
            return CustomerNoteDTO.from_dict(raw_note)
        except Exception as e:
            logger.error(f"Error building CustomerNoteDTO: {e}")
            return None
    
    def from_notes_list_json(self, payload: Dict[str, Any]) -> List[CustomerNoteDTO]:
        """
        Convert list of notes JSON sang list of CustomerNoteDTO.
        
        Args:
            payload: Raw JSON từ GET /admin/customers/{id}/notes.json
                    Format: {"notes": [...], "metadata": {...}}
                    
        Returns:
            List of CustomerNoteDTO
        """
        if not payload:
            return []
        
        raw_notes = payload.get("notes", [])
        
        notes = []
        for note_data in raw_notes:
            try:
                note = CustomerNoteDTO.from_dict(note_data)
                notes.append(note)
            except Exception as e:
                logger.warning(f"Failed to build note: {e}")
                continue
        
        return notes


# Backward compatibility: Keep simple function name
def build_customer_from_sapo(payload: Dict[str, Any]) -> Optional[CustomerDTO]:
    """
    Deprecated: Use CustomerDTOFactory instead.
    Kept for backward compatibility.
    """
    factory = CustomerDTOFactory()
    return factory.from_sapo_json(payload)

# customers/services/customer_service.py
"""
Customer Service - Business logic layer cho customers từ Sapo.
Convert raw JSON responses sang CustomerDTO.
"""

from typing import List, Dict, Any, Optional
import logging

from core.sapo_client.client import SapoClient
from .dto import CustomerDTO, CustomerNoteDTO
from .customer_builder import CustomerDTOFactory

logger = logging.getLogger(__name__)


class CustomerService:
    """
    Service layer để làm việc với Sapo customers.
    
    Chức năng:
    - Lấy customers từ Sapo Core API
    - Convert raw JSON → CustomerDTO
    - Business logic xử lý customer data
    - Update customer info với field mapping conventions
    
    Usage:
        sapo_client = SapoClient()
        service = CustomerService(sapo_client)
        
        # Get customer
        customer = service.get_customer(846791668)
        print(customer.name, customer.short_name)
        
        # Update customer
        updated = service.update_customer_info(
            customer_id=846791668,
            email="new@email.com",
            short_name="Nguyễn A"
        )
    """
    
    def __init__(self, sapo_client: SapoClient):
        """
        Args:
            sapo_client: SapoClient instance
        """
        self._sapo = sapo_client
        self._factory = CustomerDTOFactory()
    
    @staticmethod
    def from_json(customer_json: Dict[str, Any]) -> Optional[CustomerDTO]:
        """
        Khởi tạo CustomerDTO từ JSON có sẵn (không gọi API).
        
        Sử dụng khi đã có customer data từ nguồn khác (vd: order['customer']).
        
        Args:
            customer_json: Dict chứa customer data từ Sapo
                          Có thể có key "customer" bao ngoài hoặc không
        
        Returns:
            CustomerDTO instance
            
        Example:
            # Từ order data
            order = {..., "customer": {...}}
            customer = CustomerService.from_json(order['customer'])
            
            # Hoặc từ response API
            response = {"customer": {...}}
            customer = CustomerService.from_json(response)
        """
        factory = CustomerDTOFactory()
        return factory.from_sapo_json(customer_json)
    
    def get_customer(self, customer_id: int) -> Optional[CustomerDTO]:
        """
        Lấy 1 customer theo ID từ Sapo Core API.
        
        Args:
            customer_id: Sapo customer ID
            
        Returns:
            CustomerDTO instance hoặc None nếu không tìm thấy
        """
        logger.info(f"[CustomerService] Getting customer: {customer_id}")
        
        try:
            raw_data = self._sapo.core.get_customer_raw(customer_id)
            customer = self._factory.from_sapo_json(raw_data)
            
            if customer:
                logger.debug(f"Loaded customer: {customer.name}")
            
            return customer
            
        except Exception as e:
            logger.error(f"[CustomerService] Error getting customer: {e}")
            raise
    
    def list_customers(self, **filters) -> List[CustomerDTO]:
        """
        Lấy danh sách customers từ Sapo Core API.
        
        Args:
            **filters:
                - page: int
                - limit: int (max 250)
                - query: str (search term)
                - ids: str (comma-separated IDs)
                - emails: str
                - status: str
                - etc.
                
        Returns:
            List of CustomerDTO
        """
        logger.info(f"[CustomerService] Listing customers with filters: {filters}")
        
        try:
            raw_data = self._sapo.core.list_customers_raw(**filters)
            raw_customers = raw_data.get("customers", [])
            
            customers = []
            for raw_customer in raw_customers:
                try:
                    # Wrap in {"customer": ...} format for factory
                    customer = self._factory.from_sapo_json({"customer": raw_customer})
                    if customer:
                        customers.append(customer)
                except Exception as e:
                    logger.warning(f"Failed to build customer {raw_customer.get('id')}: {e}")
                    continue
            
            logger.info(f"[CustomerService] Loaded {len(customers)} customers")
            return customers
            
        except Exception as e:
            logger.error(f"[CustomerService] Error listing customers: {e}")
            raise
    
    def update_customer_info(
        self, 
        customer_id: int,
        name: Optional[str] = None,
        email: Optional[str] = None,
        short_name: Optional[str] = None,
        sex: Optional[str] = None,
        phone_number: Optional[str] = None,
        processing_status: Optional[str] = None,
        **other_fields
    ) -> CustomerDTO:
        """
        Update thông tin khách hàng trên Sapo.
        
        Args:
            customer_id: Sapo customer ID
            name: Tên đầy đủ
            email: Email
            short_name: Tên rút gọn (sẽ lưu vào website field)
            sex: Giới tính ("female", "male", "other")
            phone_number: SĐT
            processing_status: Trạng thái xử lý ("0", "1") - sẽ lưu vào tax_number
            **other_fields: Các fields khác (tags, customer_group_id, website, etc.)
            
        Returns:
            CustomerDTO updated
        """
        logger.info(f"[CustomerService] Updating customer {customer_id}")
        
        # ⭐ KEY FIX: Get current customer data first
        current_customer = self.get_customer(customer_id)
        
        # Build update payload from CURRENT customer data
        update_data = current_customer.to_sapo_update_dict()
        
        # Now apply changes on top of current data
        if name is not None:
            update_data["name"] = name
        if email is not None:
            update_data["email"] = email
        if sex is not None:
            update_data["sex"] = sex
        if phone_number is not None:
            update_data["phone_number"] = phone_number
        
        # Field mapping conventions
        if short_name is not None:
            update_data["website"] = short_name
            logger.debug(f"Mapping short_name → website: {short_name}")
        
        if processing_status is not None:
            update_data["tax_number"] = processing_status
            logger.debug(f"Mapping processing_status → tax_number: {processing_status}")
        
        # Merge other fields (website can be passed directly)
        update_data.update(other_fields)
        
        # Ensure customer_id is in payload
        update_data["id"] = customer_id
        
        logger.debug(f"Update payload keys: {list(update_data.keys())}")
        
        try:
            raw_data = self._sapo.core.update_customer(customer_id, update_data)
            customer = self._factory.from_sapo_json(raw_data)
            
            logger.info(f"[CustomerService] Customer {customer_id} updated successfully")
            return customer
            
        except Exception as e:
            logger.error(f"[CustomerService] Error updating customer {customer_id}: {e}")
            raise
    
    def update_username(self, customer_id: int, username: str) -> CustomerDTO:
        """
        Update Shopee username to customer.website field (format: short_name/username).
        
        Args:
            customer_id: Sapo customer ID
            username: Shopee username (e.g., "ngocvuongdn95")
            
        Returns:
            Updated CustomerDTO
        """
        customer = self.get_customer(customer_id)
        short_name = customer.short_name or customer.name or ""
        new_website = f"{short_name}/{username}"
        logger.info(f"[CustomerService] Updating username for customer {customer_id}: {username}")
        return self.update_customer_info(customer_id=customer_id, website=new_website)
    
    def update_from_pdf_data(self, customer_id: int, pdf_name: Optional[str] = None, 
                            pdf_address: Optional[str] = None) -> CustomerDTO:
        """
        Update customer name/address from PDF if current data is masked (*****).
        
        Args:
            customer_id: Sapo customer ID
            pdf_name: Name extracted from PDF
            pdf_address: Address extracted from PDF (address1 only)
            
        Returns:
            Updated CustomerDTO (or unchanged if no updates needed)
        """
        customer = self.get_customer(customer_id)
        updates = {}
        
        # 1. Update name if masked
        if pdf_name and '*****' in (customer.name or ''):
            updates["name"] = pdf_name
            logger.info(f"[CustomerService] Updating masked name for customer {customer_id}")
        
        # 2. Update address if masked AND customer has primary address
        if pdf_address and customer.primary_address:
            addr = customer.primary_address
            # Check if address is masked (contains ***** or ****** pattern)
            address1 = addr.address1 or ''
            is_masked = '*****' in address1 or '******' in address1 or address1.startswith('****')
            if is_masked:
                logger.info(f"[CustomerService] Updating masked address for customer {customer_id} (current: {address1[:50]}...)")
                try:
                    # Build full address payload with ALL existing fields
                    address_payload = {
                        "id": addr.id,
                        "full_name": addr.full_name or customer.name,
                        "phone_number": addr.phone_number or "",
                        "email": addr.email or "",
                        "zip_code": addr.zip_code or "",
                        "address1": pdf_address,  # ⭐ Update this field
                        "address2": addr.address2,
                        "country": addr.country or "Việt Nam",
                        "city": addr.city,
                        "district": addr.district,
                        "ward": addr.ward,
                        "first_name": addr.first_name,
                        "last_name": addr.last_name,
                        "label": addr.label,
                        "status": addr.status or "active",
                        "created_on": addr.created_on,
                        "modified_on": addr.modified_on,
                    }
                    
                    # Call Sapo API to update address
                    self._sapo.core.update_customer_address(
                        customer_id=customer_id,
                        address_id=addr.id,
                        address_data=address_payload
                    )
                    logger.info(f"[CustomerService] ✅ Address updated successfully for customer {customer_id}")
                    
                except Exception as e:
                    logger.error(f"[CustomerService] Failed to update address: {e}", exc_info=True)
        
        # 3. Update name via standard method if needed
        if updates:
            return self.update_customer_info(customer_id, **updates)
        
        # Return refreshed customer data
        return self.get_customer(customer_id)
    
    def mark_as_processed(self, customer_id: int) -> bool:
        """
        Đánh dấu customer đã được xử lý bằng tools.
        Set tax_number = "1"
        
        Args:
            customer_id: Sapo customer ID
            
        Returns:
            True nếu thành công
        """
        logger.info(f"[CustomerService] Marking customer {customer_id} as processed")
        
        try:
            self.update_customer_info(customer_id, processing_status="1")
            return True
        except Exception as e:
            logger.error(f"Error marking customer as processed: {e}")
            return False
    
    def add_note(self, customer_id: int, content: str) -> CustomerNoteDTO:
        """
        Thêm ghi chú cho khách hàng.
        
        Args:
            customer_id: Sapo customer ID
            content: Nội dung ghi chú
            
        Returns:
            CustomerNoteDTO của note vừa tạo
        """
        logger.info(f"[CustomerService] Adding note to customer {customer_id}")
        logger.debug(f"Note content: {content}")
        
        try:
            raw_data = self._sapo.core.add_customer_note(customer_id, content)
            note = self._factory.from_note_json(raw_data)
            
            if note:
                logger.info(f"[CustomerService] Note {note.id} added successfully")
            
            return note
            
        except Exception as e:
            logger.error(f"[CustomerService] Error adding note: {e}")
            raise
    
    def get_notes(self, customer_id: int, **filters) -> List[CustomerNoteDTO]:
        """
        Lấy danh sách ghi chú của khách hàng.
        
        Args:
            customer_id: Sapo customer ID
            **filters:
                - page: int
                - limit: int (max 250)
                
        Returns:
            List of CustomerNoteDTO
        """
        logger.info(f"[CustomerService] Getting notes for customer {customer_id}")
        
        try:
            raw_data = self._sapo.core.list_customer_notes(customer_id, **filters)
            notes = self._factory.from_notes_list_json(raw_data)
            
            logger.info(f"[CustomerService] Loaded {len(notes)} notes")
            return notes
            
        except Exception as e:
            logger.error(f"[CustomerService] Error getting notes: {e}")
            raise
    
    def delete_customer(self, customer_id: int) -> bool:
        """
        Xóa khách hàng.
        
        Args:
            customer_id: Sapo customer ID
            
        Returns:
            True nếu thành công
        """
        logger.warning(f"[CustomerService] Deleting customer {customer_id}")
        
        try:
            self._sapo.core.delete_customer(customer_id)
            logger.info(f"[CustomerService] Customer {customer_id} deleted")
            return True
        except Exception as e:
            logger.error(f"[CustomerService] Error deleting customer: {e}")
            return False

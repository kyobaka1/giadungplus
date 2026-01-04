# customers/services/customer_service.py
"""
Customer Service - Business logic layer cho customers từ Sapo.
Convert raw JSON responses sang CustomerDTO.
"""

from typing import List, Dict, Any, Optional
import logging
import json

from core.sapo_client.client import SapoClient
from .dto import CustomerDTO, CustomerNoteDTO
from .customer_builder import CustomerDTOFactory

logger = logging.getLogger(__name__)


# ===================================================================
# HELPER FUNCTIONS: Description JSON Management
# ===================================================================

def parse_customer_description(description: Optional[str]) -> Dict[str, Any]:
    """
    Parse customer.description từ JSON string thành dict.
    
    Args:
        description: JSON string hoặc None
        
    Returns:
        Dict chứa các fields: short_name, user_name, user_portrait, ...
        Nếu description rỗng/invalid, trả về dict rỗng.
    """
    if not description:
        return {}
    
    # Strip whitespace
    description = description.strip()
    if not description:
        return {}
    
    # Nếu là "{}" hoặc empty JSON, trả về dict rỗng
    if description == "{}":
        return {}
    
    try:
        # Try parse as JSON
        data = json.loads(description)
        if isinstance(data, dict):
            return data
        return {}
    except (json.JSONDecodeError, TypeError) as e:
        # Nếu không phải JSON hợp lệ, log warning và trả về dict rỗng
        logger.warning(f"[parse_customer_description] Invalid JSON: {description[:100]}, error: {e}")
        return {}


def merge_customer_description(
    current_description: Optional[str],
    short_name: Optional[str] = None,
    user_name: Optional[str] = None,
    user_portrait: Optional[str] = None,
    **other_fields
) -> str:
    """
    Merge data mới vào customer.description (JSON format).
    
    Args:
        current_description: Description hiện tại (JSON string hoặc None)
        short_name: Tên rút gọn
        user_name: Username (Shopee username)
        user_portrait: Avatar ID từ Shopee (buyer_image)
        **other_fields: Các fields khác cần lưu
        
    Returns:
        JSON string mới để lưu vào description
    """
    # Parse description hiện tại
    data = parse_customer_description(current_description)
    
    # Update các fields mới (chỉ update nếu có giá trị)
    if short_name is not None:
        data["short_name"] = short_name
    if user_name is not None:
        data["user_name"] = user_name
    if user_portrait is not None:
        data["user_portrait"] = user_portrait
    
    # Merge other fields
    data.update(other_fields)
    
    # Convert về JSON string
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


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
    
    def update_customer_description(
        self,
        customer_id: int,
        short_name: Optional[str] = None,
        user_name: Optional[str] = None,
        user_portrait: Optional[str] = None,
        **other_fields
    ) -> CustomerDTO:
        """
        Update customer.description với JSON data (short_name, user_name, user_portrait).
        
        Args:
            customer_id: Sapo customer ID
            short_name: Tên rút gọn
            user_name: Username (Shopee username)
            user_portrait: Avatar ID từ Shopee (buyer_image)
            **other_fields: Các fields khác cần lưu vào description
            
        Returns:
            Updated CustomerDTO
        """
        logger.info(f"[CustomerService] Updating description for customer {customer_id}")
        
        # Get current customer để lấy description hiện tại
        current_customer = self.get_customer(customer_id)
        current_description = current_customer.description
        
        # Merge data mới vào description
        new_description = merge_customer_description(
            current_description=current_description,
            short_name=short_name,
            user_name=user_name,
            user_portrait=user_portrait,
            **other_fields
        )
        
        # Update description
        return self.update_customer_info(
            customer_id=customer_id,
            description=new_description
        )
    
    def get_customer_description_data(self, customer_id: int) -> Dict[str, Any]:
        """
        Lấy data từ customer.description (JSON format).
        
        Args:
            customer_id: Sapo customer ID
            
        Returns:
            Dict chứa các fields: short_name, user_name, user_portrait, ...
        """
        customer = self.get_customer(customer_id)
        return parse_customer_description(customer.description)
    
    def update_customer_info(
        self, 
        customer_id: int,
        name: Optional[str] = None,
        email: Optional[str] = None,
        short_name: Optional[str] = None,
        sex: Optional[str] = None,
        phone_number: Optional[str] = None,
        processing_status: Optional[str] = None,
        description: Optional[str] = None,
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
        
        # Handle description field
        if description is not None:
            update_data["description"] = description
        # ⭐ Nếu không truyền description, preserve description hiện tại (đã có trong to_sapo_update_dict)
        
        # Merge other fields (website can be passed directly)
        update_data.update(other_fields)
        
        # Ensure customer_id is in payload
        update_data["id"] = customer_id
        
        logger.debug(f"Update payload keys: {list(update_data.keys())}")
        if "description" in update_data:
            logger.debug(f"Update payload description: {update_data['description'][:100]}...")
        
        try:
            raw_data = self._sapo.core.update_customer(customer_id, update_data)
            customer = self._factory.from_sapo_json(raw_data)
            
            # ⭐ VERIFY: Kiểm tra description trong response
            response_description = customer.description if customer else None
            if response_description:
                logger.info(f"[CustomerService] Customer {customer_id} updated successfully - Description in response: {response_description[:100]}...")
            else:
                logger.warning(f"[CustomerService] Customer {customer_id} updated but description is empty in response!")
            
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
                            pdf_address: Optional[str] = None, force_update: bool = False) -> CustomerDTO:
        """
        Update customer name/address from PDF.
        
        Args:
            customer_id: Sapo customer ID
            pdf_name: Name extracted from PDF
            pdf_address: Address extracted from PDF (address1 only)
            force_update: If True, update even if not masked. If False, only update if masked.
            
        Returns:
            Updated CustomerDTO (or unchanged if no updates needed)
        """
        customer = self.get_customer(customer_id)
        updates = {}
        
        # 1. Update name if masked OR force_update
        if pdf_name:
            is_masked = '*****' in (customer.name or '')
            if force_update or is_masked:
                updates["name"] = pdf_name
                logger.info(f"[CustomerService] Updating name for customer {customer_id} (force={force_update}, masked={is_masked})")
        
        # 2. Update address if masked OR force_update AND customer has primary address
        if pdf_address and customer.primary_address:
            addr = customer.primary_address
            # Check if address is masked (contains ***** or ****** pattern)
            address1 = addr.address1 or ''
            is_masked = '*****' in address1 or '******' in address1 or address1.startswith('****')
            
            if force_update or is_masked:
                logger.info(f"[CustomerService] Updating address for customer {customer_id} (force={force_update}, masked={is_masked}, current: {address1[:50]}...)")
                try:
                    # Build full address payload with ALL existing fields
                    address_payload = {
                        "id": addr.id,
                        "full_name": pdf_name or addr.full_name or customer.name,
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

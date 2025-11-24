# Customers Module

Module quản lý thông tin khách hàng từ Sapo Core API.

## Features

### Customer Auto-Update from Shopee (NEW)
Tự động cập nhật thông tin khách hàng từ đơn hàng Shopee khi in vận đơn.

**Chức năng:**
- ✅ Tự động lấy Shopee username → lưu vào `customer.website` (format: `"Tên/username"`)
- ✅ Tự động cập nhật tên khách hàng từ PDF nếu data bị mask (`*****`)
- ✅ Non-blocking: Lỗi update không ảnh hưởng đến workflow in đơn
- ✅ Idempotent: Chỉ update khi cần thiết (data bị mask)

**Implementation:**

**1. CustomerDTO Updates** (`services/dto.py`)
```python
class CustomerDTO:
    # Computed fields
    @computed_field
    @property
    def username(self) -> Optional[str]:
        """Extract username from website field (format: short_name/username)"""
        
    @computed_field  
    @property
    def short_name(self) -> Optional[str]:
        """Extract short_name from website field (before /)"""
        
    # Helper methods
    def set_username(self, username: str) -> None:
        """Update website field with new username while preserving short_name"""
```

**2. CustomerService Methods** (`services/customer_service.py`)
```python
class CustomerService:
    def update_username(self, customer_id: int, username: str) -> CustomerDTO:
        """Update Shopee username to customer.website field"""
        
    def update_from_pdf_data(self, customer_id: int, 
                            pdf_name: Optional[str] = None,
                            pdf_address: Optional[str] = None) -> CustomerDTO:
        """Update customer name/address from PDF if masked (*****) """
```

## Data Mapping Conventions

| Sapo Field | Custom Usage | Format |
|------------|--------------|---------|
| `website` | `short_name/username` | "Nguyễn A/ngocvuongdn95" |
| `tax_number` | `processing_status` | "0" (chưa xử lý) / "1" (đã xử lý) |

## Usage Example

```python
from customers.services import CustomerService
from core.sapo_client import get_sapo_client

# Initialize service
sapo = get_sapo_client()
customer_service = CustomerService(sapo)

# Update username from Shopee
customer = customer_service.update_username(
    customer_id=846791668,
    username="ngocvuongdn95"
)

# Update from PDF data (only if masked)
customer = customer_service.update_from_pdf_data(
    customer_id=846791668,
    pdf_name="Nguyễn Văn A",
    pdf_address="123 Nguyễn Huệ"
)
```

## Dependencies

- `core.sapo_client` - Sapo API integration
- `pydantic` - DTO validation và computed fields

# Core Module

Module chứa các integration với external APIs và shared utilities.

## Shopee Client Updates

**File:** `shopee_client/client.py`

### Breaking Change: `get_shopee_order_id()` Return Type

**Old Behavior:**
```python
def get_shopee_order_id(self, order_sn: str) -> int:
    return order_id  # Returns integer
```

**New Behavior:**
```python
def get_shopee_order_id(self, order_sn: str) -> Dict[str, Any]:
    return {
        "order_id": 123456,
        "order_sn": "251121BJXGAP11",
        "buyer_name": "ngocvuongdn95",  # NEW: Shopee username
        "buyer_image": "...",
        # ... other order info
    }
```

**Migration Guide:**

```python
# Before
order_id = client.get_shopee_order_id(order_sn)

# After
order_info = client.get_shopee_order_id(order_sn)
order_id = order_info["order_id"]
username = order_info["buyer_name"]  # Now available!
```

**Affected Files:**
- ✅ `orders/services/shopee_print_service.py` - Updated
- ✅ `kho/views/orders.py` - Updated

## API Integrations

### Shopee KNB API
- Search orders by order_sn
- Get package information
- Generate shipping labels
- **NEW:** Extract buyer username

### Sapo Core API
- Customer CRUD operations
- Order management
- Fulfillment tracking
- **NEW:** Customer auto-update support

## Dependencies

- `requests` - HTTP client
- `typing` - Type hints

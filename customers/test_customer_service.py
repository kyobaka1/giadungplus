# customers/test_customer_service.py
"""
Test script để verify CustomerService functionality.

Usage:
    python manage.py shell
    >>> exec(open('customers/test_customer_service.py').read())
"""

from core.sapo_client.client import SapoClient
from customers.services import CustomerService

print("\n" + "="*60)
print("TESTING CUSTOMER SERVICE")
print("="*60)

# Initialize
print("\n[1] Initializing SapoClient and CustomerService...")
sapo = SapoClient()
service = CustomerService(sapo)
print("✓ Services initialized")

# Test 1: Get customer by ID
print("\n[2] Testing get_customer() - Cách 1: từ customer_id...")
try:
    customer_id = 846791668  # ID từ YEUCAU.md
    customer = service.get_customer(customer_id)
    
    if customer:
        print(f"✓ Customer loaded successfully (from API)")
        print(f"  - ID: {customer.id}")
        print(f"  - Code: {customer.code}")
        print(f"  - Name: {customer.name}")
        print(f"  - Short name: {customer.short_name}")  # từ website field
        print(f"  - Email: {customer.email}")
        print(f"  - Sex: {customer.sex}")
        print(f"  - Phone: {customer.primary_phone}")
        print(f"  - Processing status: {customer.processing_status}")  # từ tax_number
        print(f"  - Is processed: {customer.is_processed}")
        print(f"  - Tags: {customer.tags}")
        print(f"  - Group: {customer.group_name}")
        if customer.primary_address:
            print(f"  - Address: {customer.primary_address.as_line}")
    else:
        print("✗ Customer not found")
        
except Exception as e:
    print(f"✗ Error: {e}")

# Test 1b: Init from JSON (without API call)
print("\n[2b] Testing from_json() - Cách 2: từ JSON có sẵn...")
try:
    # Giả sử đã có customer data từ order hoặc source khác
    if customer:
        # Serialize và deserialize để demo
        customer_json = customer.to_dict()
        
        # Init from JSON (không cần SapoClient, không gọi API)
        customer_from_json = CustomerService.from_json(customer_json)
        
        print(f"✓ Customer initialized from JSON successfully")
        print(f"  - ID: {customer_from_json.id}")
        print(f"  - Name: {customer_from_json.name}")
        print(f"  - Short name: {customer_from_json.short_name}")
        print(f"  ℹ No API call made - data loaded from JSON")
    else:
        print("⚠ Skipped - no customer data available")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 2: List customers
print("\n[3] Testing list_customers()...")
try:
    customers = service.list_customers(page=1, limit=5)
    print(f"✓ Loaded {len(customers)} customers")
    for c in customers[:3]:  # Show first 3
        print(f"  - {c.code}: {c.name} ({c.email or 'no email'})")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 3: Update customer info (commented out by default)
print("\n[4] Testing update_customer_info()...")
print("  ⚠ Skipped - Uncomment to test updates")
# Uncomment để test:
# try:
#     updated = service.update_customer_info(
#         customer_id=846791668,
#         email="test@example.com",
#         short_name="Test Short Name",
#         sex="other"
#     )
#     print(f"✓ Customer updated")
#     print(f"  - Email: {updated.email}")
#     print(f"  - Short name: {updated.short_name}")
#     print(f"  - Sex: {updated.sex}")
# except Exception as e:
#     print(f"✗ Error: {e}")

# Test 4: Get customer notes
print("\n[5] Testing get_notes()...")
try:
    notes = service.get_notes(customer_id=846791668, page=1, limit=10)
    print(f"✓ Loaded {len(notes)} notes")
    for note in notes[:3]:  # Show first 3
        print(f"  - [{note.created_on}] {note.content[:50]}...")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 5: Add note (commented out by default)
print("\n[6] Testing add_note()...")
print("  ⚠ Skipped - Uncomment to test adding notes")
# Uncomment để test:
# try:
#     note = service.add_note(
#         customer_id=846791668,
#         content="Test note từ customer service"
#     )
#     print(f"✓ Note added")
#     print(f"  - ID: {note.id}")
#     print(f"  - Content: {note.content}")
#     print(f"  - Created: {note.created_on}")
# except Exception as e:
#     print(f"✗ Error: {e}")

# Test 6: Mark as processed (commented out by default)
print("\n[7] Testing mark_as_processed()...")
print("  ⚠ Skipped - Uncomment to test marking as processed")
# Uncomment để test:
# try:
#     success = service.mark_as_processed(customer_id=846791668)
#     if success:
#         print("✓ Customer marked as processed (tax_number=1)")
#     else:
#         print("✗ Failed to mark as processed")
# except Exception as e:
#     print(f"✗ Error: {e}")

print("\n" + "="*60)
print("TESTS COMPLETED")
print("="*60 + "\n")

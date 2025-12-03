#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script kiểm tra signature của hàm update_fulfillment_packing_status
Chạy trên server Ubuntu để verify code đã được update đúng chưa
"""

import sys
import inspect
from orders.services.sapo_service import SapoCoreOrderService

def check_function_signature():
    """Kiểm tra signature của hàm update_fulfillment_packing_status"""
    service = SapoCoreOrderService()
    
    # Lấy signature của hàm
    sig = inspect.signature(service.update_fulfillment_packing_status)
    
    print("=" * 60)
    print("Function: SapoCoreOrderService.update_fulfillment_packing_status")
    print("=" * 60)
    print(f"Signature: {sig}")
    print()
    print("Parameters:")
    for param_name, param in sig.parameters.items():
        default = f" = {param.default}" if param.default != inspect.Parameter.empty else ""
        annotation = f": {param.annotation}" if param.annotation != inspect.Parameter.empty else ""
        print(f"  - {param_name}{annotation}{default}")
    print()
    
    # Kiểm tra xem có parameter 'nguoi_goi' không
    params = list(sig.parameters.keys())
    if 'nguoi_goi' in params:
        print("✅ PASS: Parameter 'nguoi_goi' đã có trong signature")
        return True
    else:
        print("❌ FAIL: Parameter 'nguoi_goi' KHÔNG có trong signature")
        print(f"   Các parameters hiện tại: {', '.join(params)}")
        return False

if __name__ == "__main__":
    try:
        success = check_function_signature()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


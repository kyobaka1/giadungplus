#!/usr/bin/env python
"""
Script để migrate variant metadata từ customer notes cũ sang product.description.

Chạy script này để migrate toàn bộ variants từ customer notes (ID: 759999534, 792508285)
sang format mới lưu trong product.description với [GDP_META]...[/GDP_META].

Usage:
    python products/migrate_variants.py
    python products/migrate_variants.py --test-mode
    python products/migrate_variants.py --limit 100
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GIADUNGPLUS.settings')
django.setup()

from products.services.variant_migration import init_variants_from_old_data


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Migrate variant metadata từ customer notes cũ sang product.description'
    )
    parser.add_argument(
        '--test-mode',
        action='store_true',
        help='Chế độ test: chỉ log, không thực sự update'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Giới hạn số lượng variants để migrate (default: None = tất cả)'
    )
    
    args = parser.parse_args()
    
    print('=' * 60)
    print('MIGRATE VARIANTS TỪ CUSTOMER NOTES')
    print('=' * 60)
    print('')
    
    if args.test_mode:
        print('⚠️  CHẾ ĐỘ TEST: Chỉ log, không thực sự update!')
    else:
        print('⚠️  CHẾ ĐỘ THẬT: Sẽ update product.description!')
        confirm = input('Bạn có chắc chắn muốn tiếp tục? (yes/no): ')
        if confirm.lower() != 'yes':
            print('Đã hủy.')
            return
    
    print('')
    if args.limit:
        print(f'Giới hạn: {args.limit} variants')
    else:
        print('Không giới hạn - sẽ migrate tất cả variants')
    
    print('')
    print('Đang tải dữ liệu từ customer notes...')
    print('(Nếu bị treo, có thể đang chờ Sapo login hoặc API timeout)')
    print('')
    
    try:
        # Gọi hàm migration
        result = init_variants_from_old_data(test_mode=args.test_mode, limit=args.limit)
    except KeyboardInterrupt:
        print('')
        print('⚠️  Đã bị ngắt bởi người dùng (Ctrl+C)')
        return
    except Exception as e:
        print('')
        print(f'✗ LỖI: {e}')
        import traceback
        traceback.print_exc()
        return
    
    # Hiển thị kết quả
    print('')
    print('=' * 60)
    print('KẾT QUẢ MIGRATION')
    print('=' * 60)
    print('')
    
    print(f'Tổng số variants trong customer notes: {result["total_old_variants"]}')
    print(f'✓ Đã migrate thành công: {result["migrated"]}')
    print(f'⚠ Đã bỏ qua: {result["skipped"]}')
    print(f'✗ Lỗi: {result["errors"]}')
    
    # Hiển thị chi tiết nếu có
    if result.get("details"):
        print('')
        print('Chi tiết:')
        success_details = [d for d in result["details"] if d.get("status") == "success"]
        error_details = [d for d in result["details"] if d.get("status") == "error"]
        skipped_details = [d for d in result["details"] if d.get("status") == "skipped"]
        
        if success_details:
            print(f'  - Thành công: {len(success_details)} variants')
            # Hiển thị 10 variants đầu tiên
            for detail in success_details[:10]:
                print(f'    ✓ Variant {detail.get("variant_id")} (Product {detail.get("product_id")})')
            if len(success_details) > 10:
                print(f'    ... và {len(success_details) - 10} variants khác')
        
        if error_details:
            print(f'  - Lỗi: {len(error_details)} variants')
            # Hiển thị 5 lỗi đầu tiên
            for detail in error_details[:5]:
                print(f'    ✗ Variant {detail.get("variant_id")}: {detail.get("reason", "Unknown error")}')
            if len(error_details) > 5:
                print(f'    ... và {len(error_details) - 5} lỗi khác')
        
        if skipped_details:
            print(f'  - Bỏ qua: {len(skipped_details)} variants')
            # Hiển thị 5 variants đầu tiên
            for detail in skipped_details[:5]:
                print(f'    ⚠ Variant {detail.get("variant_id")}: {detail.get("reason", "Unknown")}')
            if len(skipped_details) > 5:
                print(f'    ... và {len(skipped_details) - 5} variants khác')
    
    print('')
    print('=' * 60)
    print('✓ HOÀN THÀNH!')
    print('=' * 60)


if __name__ == '__main__':
    main()


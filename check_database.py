#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script để kiểm tra dữ liệu trong database
Hiển thị số lượng records trong các bảng
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GIADUNGPLUS.settings')
django.setup()

from django.db import connection
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.apps import apps

def check_database():
    """Kiểm tra và hiển thị thông tin database"""
    
    print("=" * 60)
    print("KIỂM TRA DỮ LIỆU TRONG DATABASE")
    print("=" * 60)
    print()
    
    # Kiểm tra file database
    db_file = "db.sqlite3"
    if not os.path.exists(db_file):
        print("❌ Không tìm thấy file database: db.sqlite3")
        print("   Database chưa được tạo. Chạy: python manage.py migrate")
        return
    
    file_size = os.path.getsize(db_file) / 1024  # KB
    print(f"📁 File database: {db_file}")
    print(f"   Kích thước: {file_size:.2f} KB")
    print()
    
    # Đếm records trong các bảng
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        print("=" * 60)
        print("SỐ LƯỢNG RECORDS TRONG CÁC BẢNG")
        print("=" * 60)
        print()
        
        total_records = 0
        tables_with_data = []
        
        for table in sorted(tables):
            if table.startswith('sqlite_'):
                continue
            
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                
                if count > 0:
                    tables_with_data.append((table, count))
                    total_records += count
                    status = "✓" if count > 0 else "○"
                    print(f"{status} {table:40} {count:>10,} records")
            except Exception as e:
                print(f"✗ {table:40} ERROR: {e}")
        
        print()
        print("-" * 60)
        print(f"Tổng cộng: {total_records:,} records trong {len(tables_with_data)} bảng")
        print()
        
        if total_records == 0:
            print("⚠ CẢNH BÁO: Database trống!")
            print()
            print("Có thể:")
            print("  1. Chưa import dữ liệu")
            print("  2. Import bị lỗi")
            print("  3. File backup không có dữ liệu")
            print()
            print("Kiểm tra:")
            print("  - Chạy: python import_data.py")
            print("  - Hoặc: python manage.py loaddata <file_backup.json>")
        else:
            print("✓ Database có dữ liệu!")
    
    # Kiểm tra các model quan trọng
    print()
    print("=" * 60)
    print("KIỂM TRA CÁC MODEL QUAN TRỌNG")
    print("=" * 60)
    print()
    
    # User
    try:
        user_count = User.objects.count()
        superuser_count = User.objects.filter(is_superuser=True).count()
        print(f"👤 User:")
        print(f"   Tổng số: {user_count}")
        print(f"   Superuser: {superuser_count}")
        if user_count == 0:
            print("   ⚠ Chưa có user nào!")
    except Exception as e:
        print(f"✗ User: ERROR - {e}")
    
    # Kiểm tra các app models
    apps_to_check = {
        'kho': ['Warehouse', 'UserProfile', 'Ticket'],
        'cskh': [],
        'products': [],
        'orders': [],
        'customers': [],
        'core': [],
        'marketing': [],
        'settings': [],
        'chamcong': [],
    }
    
    print()
    for app_name, model_names in apps_to_check.items():
        try:
            app_config = apps.get_app_config(app_name)
            models = app_config.get_models()
            
            if models:
                print(f"📦 {app_name}:")
                for model in models:
                    try:
                        count = model.objects.count()
                        if count > 0 or model_names:  # Hiển thị cả khi = 0 nếu là model quan trọng
                            status = "✓" if count > 0 else "○"
                            print(f"   {status} {model.__name__}: {count:,}")
                    except Exception as e:
                        print(f"   ✗ {model.__name__}: ERROR - {e}")
        except Exception as e:
            print(f"✗ {app_name}: Không thể kiểm tra - {e}")
    
    print()
    print("=" * 60)
    print("KẾT THÚC KIỂM TRA")
    print("=" * 60)

if __name__ == "__main__":
    check_database()


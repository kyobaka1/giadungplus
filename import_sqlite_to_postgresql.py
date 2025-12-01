#!/usr/bin/env python3
"""
Script import data từ SQLite (export JSON) sang PostgreSQL
Sử dụng trên server Ubuntu với settings_production.py

Cách dùng:
    1. Export data từ SQLite (Windows): python export_sqlite_data.py
    2. Copy file db_backup.json lên server
    3. Chạy script này: python import_sqlite_to_postgresql.py db_backup.json
"""

import os
import sys
import django
import json
import argparse
from pathlib import Path

# Setup Django với settings production
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GIADUNGPLUS.settings_production')

django.setup()

from django.core import serializers
from django.apps import apps
from django.db import transaction
from django.contrib.contenttypes.models import ContentType


def import_data(json_file_path):
    """Import data từ file JSON vào PostgreSQL"""
    
    if not os.path.exists(json_file_path):
        print(f"❌ File không tồn tại: {json_file_path}")
        sys.exit(1)
    
    print(f"📥 Đang import từ: {json_file_path}")
    print(f"📊 Database: {os.environ.get('DJANGO_SETTINGS_MODULE', 'default')}")
    print("")
    
    # Đọc file JSON
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Lỗi parse JSON: {e}")
        sys.exit(1)
    
    # Nếu data là list (format dumpdata chuẩn)
    if isinstance(data, list):
        objects_to_import = data
    else:
        print("❌ Format JSON không đúng. File phải là array của objects.")
        sys.exit(1)
    
    # Nhóm objects theo model
    models_data = {}
    for obj in objects_to_import:
        model_name = obj.get('model', '')
        if model_name:
            if model_name not in models_data:
                models_data[model_name] = []
            models_data[model_name].append(obj)
    
    print(f"📦 Tìm thấy {len(models_data)} models với tổng {len(objects_to_import)} objects")
    print("")
    
    # Import từng model
    total_imported = 0
    total_skipped = 0
    errors = []
    
    # Sắp xếp thứ tự import: ContentType và User trước, sau đó đến các model khác
    priority_models = ['contenttypes.contenttype', 'auth.user', 'auth.group', 'auth.permission']
    sorted_models = sorted(models_data.keys(), key=lambda x: (
        0 if x in priority_models else 1,
        x
    ))
    
    with transaction.atomic():
        for model_name in sorted_models:
            objects = models_data[model_name]
            print(f"📥 Importing {model_name}... ({len(objects)} objects)")
            
            try:
                # Tìm model
                app_label, model_class_name = model_name.split('.')
                model = apps.get_model(app_label, model_class_name)
                
                imported_count = 0
                skipped_count = 0
                
                for obj_data in objects:
                    try:
                        # Deserialize object
                        obj = serializers.deserialize('json', json.dumps([obj_data]))
                        
                        for deserialized_obj in obj:
                            # Kiểm tra xem object đã tồn tại chưa (dựa trên pk)
                            pk = deserialized_obj.object.pk
                            if model.objects.filter(pk=pk).exists():
                                skipped_count += 1
                                continue
                            
                            # Save object
                            deserialized_obj.save()
                            imported_count += 1
                            
                    except Exception as e:
                        error_msg = f"  ⚠️  Lỗi khi import object {obj_data.get('pk', 'unknown')}: {str(e)}"
                        errors.append(error_msg)
                        skipped_count += 1
                
                print(f"  ✅ Imported: {imported_count}, Skipped: {skipped_count}")
                total_imported += imported_count
                total_skipped += skipped_count
                
            except LookupError:
                error_msg = f"  ⚠️  Không tìm thấy model: {model_name}"
                print(error_msg)
                errors.append(error_msg)
                total_skipped += len(objects)
            except Exception as e:
                error_msg = f"  ❌ Lỗi khi import {model_name}: {str(e)}"
                print(error_msg)
                errors.append(error_msg)
                total_skipped += len(objects)
    
    print("")
    print("=" * 60)
    print(f"✅ Import hoàn tất!")
    print(f"   📊 Imported: {total_imported} objects")
    print(f"   ⏭️  Skipped: {total_skipped} objects")
    
    if errors:
        print(f"   ⚠️  Errors: {len(errors)}")
        print("")
        print("Chi tiết lỗi:")
        for error in errors[:10]:  # Chỉ hiển thị 10 lỗi đầu
            print(f"   {error}")
        if len(errors) > 10:
            print(f"   ... và {len(errors) - 10} lỗi khác")


def export_data(output_file='db_backup.json'):
    """Export data từ SQLite (chạy trên Windows với settings.py)"""
    print(f"📤 Exporting data to: {output_file}")
    
    all_objects = []
    
    # Lấy tất cả models
    for app_config in apps.get_app_configs():
        for model in app_config.get_models():
            # Bỏ qua một số models không cần migrate
            if model._meta.app_label in ['sessions', 'admin']:
                continue
            
            try:
                objects = model.objects.all()
                if objects.exists():
                    serialized = serializers.serialize('json', objects, ensure_ascii=False)
                    data = json.loads(serialized)
                    all_objects.extend(data)
                    print(f"✅ Exported {model.__name__}: {objects.count()} objects")
            except Exception as e:
                print(f"⚠️  Warning: Could not export {model.__name__}: {e}")
    
    # Lưu vào file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_objects, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Export completed: {len(all_objects)} objects saved to {output_file}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Import/Export database data')
    parser.add_argument('action', choices=['import', 'export'], help='Action to perform')
    parser.add_argument('file', nargs='?', help='JSON file path (for import) or output file (for export)')
    
    args = parser.parse_args()
    
    if args.action == 'import':
        if not args.file:
            print("❌ Cần chỉ định file JSON để import")
            sys.exit(1)
        import_data(args.file)
    elif args.action == 'export':
        output_file = args.file or 'db_backup.json'
        export_data(output_file)


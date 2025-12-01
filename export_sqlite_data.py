#!/usr/bin/env python3
"""
Script export data từ SQLite (Windows/Dev) ra file JSON
Sử dụng với settings.py (SQLite)

Cách dùng:
    python export_sqlite_data.py [output_file.json]
"""

import os
import sys
import django
import json
from pathlib import Path

# Setup Django với settings dev (SQLite)
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GIADUNGPLUS.settings')

django.setup()

from django.core import serializers
from django.apps import apps

def export_data(output_file='db_backup.json'):
    """Export tất cả data từ SQLite ra JSON"""
    
    print(f"📤 Exporting data from SQLite to: {output_file}")
    print("")
    
    all_objects = []
    
    # Lấy tất cả models
    for app_config in apps.get_app_configs():
        app_name = app_config.name
        print(f"📦 Processing app: {app_name}")
        
        for model in app_config.get_models():
            # Bỏ qua một số models không cần migrate hoặc system models
            skip_models = ['LogEntry', 'Session']  # Django admin logs, sessions
            if model.__name__ in skip_models:
                continue
            
            try:
                objects = model.objects.all()
                if objects.exists():
                    # Serialize với natural keys để tránh lỗi foreign key
                    serialized = serializers.serialize(
                        'json', 
                        objects, 
                        ensure_ascii=False,
                        use_natural_foreign_keys=True,
                        use_natural_primary_keys=False
                    )
                    data = json.loads(serialized)
                    all_objects.extend(data)
                    print(f"  ✅ {model.__name__}: {objects.count()} objects")
                else:
                    print(f"  ⏭️  {model.__name__}: 0 objects (skipped)")
            except Exception as e:
                print(f"  ⚠️  Warning: Could not export {model.__name__}: {e}")
    
    # Lưu vào file
    print("")
    print(f"💾 Saving {len(all_objects)} objects to {output_file}...")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_objects, f, ensure_ascii=False, indent=2)
    
    file_size = os.path.getsize(output_file) / (1024 * 1024)  # MB
    print(f"✅ Export completed!")
    print(f"   📊 Total objects: {len(all_objects)}")
    print(f"   💾 File size: {file_size:.2f} MB")
    print(f"   📁 File location: {os.path.abspath(output_file)}")
    print("")
    print("📋 Next steps:")
    print(f"   1. Copy file to server: scp {output_file} user@server:/tmp/")
    print(f"   2. On server, run: python import_sqlite_to_postgresql.py import /tmp/{output_file}")


if __name__ == '__main__':
    output_file = sys.argv[1] if len(sys.argv) > 1 else 'db_backup.json'
    export_data(output_file)


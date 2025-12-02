#!/usr/bin/env python
"""Script to add comment_id column if it doesn't exist"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GIADUNGPLUS.settings')
django.setup()

from django.db import connection

with connection.cursor() as cursor:
    # Check if column exists
    cursor.execute("PRAGMA table_info(cskh_feedback)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if 'comment_id' not in columns:
        print("Adding comment_id column...")
        cursor.execute("ALTER TABLE cskh_feedback ADD COLUMN comment_id bigint NULL")
        print("Column added successfully!")
    else:
        print("comment_id column already exists")
    
    # Verify
    cursor.execute("PRAGMA table_info(cskh_feedback)")
    columns = {row[1] for row in cursor.fetchall()}
    print(f"comment_id exists: {'comment_id' in columns}")


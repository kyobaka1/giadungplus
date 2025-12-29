#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script import dữ liệu vào SQLite (Test - Windows)
Chạy script này trên Windows để import dữ liệu từ file JSON
"""

import os
import sys
import glob
import shutil
from pathlib import Path
from datetime import datetime

# Màu sắc cho Windows console (nếu hỗ trợ)
try:
    from colorama import init, Fore, Style
    init()
    GREEN = Fore.GREEN
    YELLOW = Fore.YELLOW
    RED = Fore.RED
    RESET = Style.RESET_ALL
except ImportError:
    GREEN = YELLOW = RED = RESET = ""

def print_colored(message, color=""):
    """In message với màu sắc"""
    print(f"{color}{message}{RESET}")

def find_latest_backup(backup_dir="data_backup"):
    """Tìm file backup mới nhất"""
    backup_path = Path(backup_dir)
    
    if not backup_path.exists():
        return None
    
    # Tìm tất cả file .json trong thư mục backup
    json_files = list(backup_path.glob("*.json"))
    
    if not json_files:
        return None
    
    # Sắp xếp theo thời gian modify, lấy file mới nhất
    latest_file = max(json_files, key=lambda f: f.stat().st_mtime)
    return latest_file

def backup_current_db():
    """Backup database hiện tại"""
    db_file = Path("db.sqlite3")
    
    if not db_file.exists():
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = Path(f"db.sqlite3.backup_{timestamp}")
    
    shutil.copy2(db_file, backup_file)
    return backup_file

def main():
    print_colored("=" * 50, GREEN)
    print_colored("Script import dữ liệu vào SQLite (Test)", GREEN)
    print_colored("=" * 50, GREEN)
    print()
    
    # Kiểm tra manage.py
    if not Path("manage.py").exists():
        print_colored("Lỗi: Không tìm thấy manage.py. Vui lòng chạy script trong thư mục gốc của project.", RED)
        input("Nhấn Enter để thoát...")
        sys.exit(1)
    
    # Tìm file backup
    backup_file = find_latest_backup()
    
    if not backup_file:
        print_colored("Không tìm thấy file backup trong thư mục data_backup", YELLOW)
        print()
        print("Vui lòng:")
        print("1. Copy file backup từ server Ubuntu vào thư mục data_backup")
        print("2. Hoặc đặt file backup vào thư mục gốc của project")
        print()
        
        user_input = input("Nhập đường dẫn đến file backup (hoặc Enter để thoát): ").strip().strip('"')
        
        if not user_input:
            print("Đã hủy thao tác.")
            sys.exit(0)
        
        backup_file = Path(user_input)
    
    # Kiểm tra file có tồn tại không
    if not backup_file.exists():
        print_colored(f"Lỗi: File không tồn tại: {backup_file}", RED)
        input("Nhấn Enter để thoát...")
        sys.exit(1)
    
    print()
    print_colored(f"File backup: {backup_file}", GREEN)
    print()
    
    # Xác nhận
    print_colored("CẢNH BÁO: Thao tác này sẽ ghi đè toàn bộ dữ liệu hiện tại trong database!", YELLOW)
    confirm = input("Bạn có chắc chắn muốn tiếp tục? (y/n): ").strip().lower()
    
    if confirm != 'y':
        print("Đã hủy thao tác.")
        sys.exit(0)
    
    print()
    print_colored("Đang backup database hiện tại...", YELLOW)
    backup_db = backup_current_db()
    
    if backup_db:
        print_colored(f"Đã backup database hiện tại thành: {backup_db}", GREEN)
    
    print()
    print_colored("Đang xóa database cũ...", YELLOW)
    db_file = Path("db.sqlite3")
    if db_file.exists():
        db_file.unlink()
    
    print()
    print_colored("Đang tạo database mới...", YELLOW)
    os.system("python manage.py migrate --run-syncdb")
    
    print()
    print_colored("Đang import dữ liệu...", YELLOW)
    result = os.system(f'python manage.py loaddata "{backup_file}"')
    
    if result == 0:
        print()
        print_colored("=" * 50, GREEN)
        print_colored("Import dữ liệu thành công!", GREEN)
        print_colored("=" * 50, GREEN)
        print()
        if backup_db:
            print_colored(f"Database backup cũ: {backup_db}", YELLOW)
        print_colored(f"File đã import: {backup_file}", YELLOW)
    else:
        print()
        print_colored("=" * 50, RED)
        print_colored("Lỗi khi import dữ liệu!", RED)
        print_colored("=" * 50, RED)
        print()
        if backup_db:
            print_colored(f"Nếu cần, bạn có thể restore database cũ từ file: {backup_db}", YELLOW)
    
    print()
    input("Nhấn Enter để thoát...")

if __name__ == "__main__":
    main()


#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script để validate và sửa file JSON backup
Sử dụng khi file backup bị lỗi format
"""

import json
import sys
import os
from pathlib import Path

def validate_json(file_path):
    """Validate file JSON và trả về lỗi nếu có"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return True, None, data
    except json.JSONDecodeError as e:
        return False, str(e), None
    except Exception as e:
        return False, str(e), None

def fix_json_file(file_path):
    """Cố gắng sửa file JSON bằng cách loại bỏ các dòng lỗi"""
    print(f"Đang cố gắng sửa file: {file_path}")
    
    # Đọc file theo dòng
    lines = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Lỗi khi đọc file: {e}")
        return False
    
    # Tìm dòng lỗi (thường là dòng trống hoặc không hợp lệ)
    error_line = None
    try:
        # Thử parse từng phần để tìm dòng lỗi
        for i, line in enumerate(lines, 1):
            # Bỏ qua dòng trống hoặc chỉ có whitespace
            if line.strip() == '':
                continue
            # Thử parse từ đầu đến dòng hiện tại
            partial_content = ''.join(lines[:i])
            try:
                json.loads(partial_content)
            except json.JSONDecodeError as e:
                error_line = i
                print(f"Phát hiện lỗi ở dòng {i}: {e}")
                break
    except Exception:
        pass
    
    # Tạo file backup
    backup_path = f"{file_path}.backup"
    try:
        import shutil
        shutil.copy2(file_path, backup_path)
        print(f"Đã tạo backup: {backup_path}")
    except Exception as e:
        print(f"Không thể tạo backup: {e}")
        return False
    
    # Thử các cách sửa khác nhau
    fixed = False
    
    # Cách 1: Loại bỏ dòng lỗi
    if error_line:
        print(f"Thử loại bỏ dòng {error_line}...")
        fixed_lines = lines[:error_line-1] + lines[error_line:]
        try:
            content = ''.join(fixed_lines)
            json.loads(content)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print("✓ Đã sửa bằng cách loại bỏ dòng lỗi")
            fixed = True
        except:
            pass
    
    # Cách 2: Tìm và sửa các vấn đề phổ biến
    if not fixed:
        print("Thử sửa các vấn đề phổ biến...")
        content = ''.join(lines)
        
        # Sửa các vấn đề phổ biến
        fixes = [
            (',\n]', '\n]'),  # Loại bỏ dấu phẩy thừa trước ]
            (',\n}', '\n}'),  # Loại bỏ dấu phẩy thừa trước }
            ('\n\n\n', '\n\n'),  # Loại bỏ dòng trống thừa
        ]
        
        for old, new in fixes:
            content = content.replace(old, new)
        
        try:
            json.loads(content)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print("✓ Đã sửa bằng cách sửa các vấn đề phổ biến")
            fixed = True
        except:
            pass
    
    # Cách 3: Parse từng object và rebuild
    if not fixed:
        print("Thử parse từng object và rebuild...")
        try:
            all_objects = []
            current_obj = ""
            brace_count = 0
            
            for line in lines:
                current_obj += line
                brace_count += line.count('{') - line.count('}')
                
                if brace_count == 0 and current_obj.strip():
                    # Có thể là một object hoàn chỉnh
                    try:
                        obj = json.loads(current_obj.strip().rstrip(','))
                        if isinstance(obj, list):
                            all_objects.extend(obj)
                        else:
                            all_objects.append(obj)
                        current_obj = ""
                    except:
                        pass
            
            if all_objects:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(all_objects, f, ensure_ascii=False, indent=2)
                print(f"✓ Đã sửa bằng cách rebuild, tìm thấy {len(all_objects)} objects")
                fixed = True
        except Exception as e:
            print(f"Không thể sửa bằng cách rebuild: {e}")
    
    if fixed:
        # Validate lại
        is_valid, error, _ = validate_json(file_path)
        if is_valid:
            print("✓ File đã được sửa và validate thành công!")
            return True
        else:
            print(f"⚠ File đã được sửa nhưng vẫn còn lỗi: {error}")
            return False
    else:
        print("✗ Không thể sửa file tự động")
        print("Vui lòng kiểm tra file backup và export lại từ server")
        return False

def main():
    if len(sys.argv) < 2:
        print("Sử dụng: python fix_json_backup.py <file_backup.json>")
        print("Hoặc: python fix_json_backup.py (sẽ tìm file backup mới nhất)")
        sys.exit(1)
    
    file_path = sys.argv[1] if len(sys.argv) > 1 else None
    
    # Nếu không có file path, tìm file backup mới nhất
    if not file_path or file_path == "auto":
        backup_dir = Path("data_backup")
        if backup_dir.exists():
            json_files = list(backup_dir.glob("*.json"))
            if json_files:
                # Sắp xếp theo thời gian modify, lấy file mới nhất
                file_path = max(json_files, key=lambda f: f.stat().st_mtime)
                print(f"Tìm thấy file backup mới nhất: {file_path}")
            else:
                print("Không tìm thấy file backup nào trong thư mục data_backup")
                sys.exit(1)
        else:
            print("Không tìm thấy thư mục data_backup")
            sys.exit(1)
    
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"File không tồn tại: {file_path}")
        sys.exit(1)
    
    print(f"Đang kiểm tra file: {file_path}")
    print(f"Kích thước: {file_path.stat().st_size / 1024 / 1024:.2f} MB")
    print()
    
    # Validate
    is_valid, error, data = validate_json(file_path)
    
    if is_valid:
        print("✓ File JSON hợp lệ!")
        if data:
            if isinstance(data, list):
                print(f"  Số objects: {len(data)}")
            else:
                print(f"  Type: {type(data).__name__}")
        sys.exit(0)
    else:
        print(f"✗ File JSON không hợp lệ!")
        print(f"  Lỗi: {error}")
        print()
        
        # Hỏi có muốn sửa không
        try:
            confirm = input("Bạn có muốn thử sửa file? (y/n): ").strip().lower()
            if confirm == 'y':
                if fix_json_file(file_path):
                    print("\n✓ Đã sửa file thành công!")
                    print("Bạn có thể thử import lại bằng: python manage.py loaddata <file>")
                else:
                    print("\n✗ Không thể sửa file tự động")
                    print("Vui lòng export lại từ server Ubuntu")
        except KeyboardInterrupt:
            print("\nĐã hủy")
            sys.exit(0)

if __name__ == "__main__":
    main()


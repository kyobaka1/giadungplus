# Generated manually to ensure all Shopee API columns exist in PostgreSQL

from django.db import migrations


def ensure_all_shopee_columns(apps, schema_editor):
    """Đảm bảo tất cả các cột Shopee API đã được thêm vào database"""
    vendor = schema_editor.connection.vendor
    
    # Danh sách tất cả các cột cần có (từ migration 0014)
    columns_to_ensure = {
        "product_id": "bigint NULL",
        "product_cover": "varchar(200) NOT NULL DEFAULT ''",
        "model_id": "bigint NULL",
        "model_name": "varchar(500) NOT NULL DEFAULT ''",
        "order_id": "bigint NULL",
        "user_id": "bigint NULL",
        "user_portrait": "varchar(200) NOT NULL DEFAULT ''",
        "is_hidden": "boolean NOT NULL DEFAULT false",
        "status": "integer NULL",
        "can_follow_up": "boolean NULL",
        "follow_up": "text NULL",
        "submit_time": "bigint NULL",
        "low_rating_reasons": "jsonb NOT NULL DEFAULT '[]'::jsonb",
        "ctime": "bigint NULL",
        "mtime": "bigint NULL",
    }
    
    with schema_editor.connection.cursor() as cursor:
        if vendor == "postgresql":
            # Lấy danh sách cột hiện có
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'cskh_feedback'
                """
            )
            existing_columns = {row[0] for row in cursor.fetchall()}
            
            # Thêm các cột còn thiếu
            for column_name, column_type in columns_to_ensure.items():
                if column_name not in existing_columns:
                    try:
                        cursor.execute(
                            f"ALTER TABLE cskh_feedback ADD COLUMN {column_name} {column_type}"
                        )
                        print(f"Added column: {column_name}")
                    except Exception as e:
                        print(f"Error adding {column_name}: {e}")
                else:
                    print(f"Column {column_name} already exists")
            
            # Tạo index cho các cột quan trọng
            indexes_to_create = [
                ("product_id", "cskh_feedback_product_id_idx"),
                ("order_id", "cskh_feedback_order_id_idx"),
                ("user_id", "cskh_feedback_user_id_idx"),
            ]
            
            cursor.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'cskh_feedback'
                """
            )
            existing_indexes = {row[0] for row in cursor.fetchall()}
            
            for column_name, index_name in indexes_to_create:
                if index_name not in existing_indexes:
                    try:
                        cursor.execute(
                            f"CREATE INDEX IF NOT EXISTS {index_name} "
                            f"ON cskh_feedback ({column_name})"
                        )
                        print(f"Created index: {index_name}")
                    except Exception as e:
                        print(f"Error creating index {index_name}: {e}")
        
        elif vendor == "sqlite":
            # Lấy danh sách cột hiện có
            cursor.execute("PRAGMA table_info(cskh_feedback)")
            existing_columns = {row[1] for row in cursor.fetchall()}
            
            # Thêm các cột còn thiếu
            sqlite_type_map = {
                "product_id": "bigint NULL",
                "product_cover": 'varchar(200) NOT NULL DEFAULT ""',
                "model_id": "bigint NULL",
                "model_name": 'varchar(500) NOT NULL DEFAULT ""',
                "order_id": "bigint NULL",
                "user_id": "bigint NULL",
                "user_portrait": 'varchar(200) NOT NULL DEFAULT ""',
                "is_hidden": "bool NOT NULL DEFAULT 0",
                "status": "integer NULL",
                "can_follow_up": "bool NULL",
                "follow_up": "text NULL",
                "submit_time": "bigint NULL",
                "low_rating_reasons": "text NOT NULL DEFAULT '[]'",
                "ctime": "bigint NULL",
                "mtime": "bigint NULL",
            }
            
            for column_name in columns_to_ensure.keys():
                if column_name not in existing_columns:
                    try:
                        sqlite_type = sqlite_type_map.get(column_name, "text NULL")
                        cursor.execute(
                            f"ALTER TABLE cskh_feedback ADD COLUMN {column_name} {sqlite_type}"
                        )
                        print(f"Added column: {column_name}")
                    except Exception as e:
                        print(f"Error adding {column_name}: {e}")


def reverse_ensure_all_shopee_columns(apps, schema_editor):
    """Rollback: không xóa cột vì có thể mất dữ liệu"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cskh', '0018_ensure_product_id_column'),
    ]

    operations = [
        migrations.RunPython(ensure_all_shopee_columns, reverse_ensure_all_shopee_columns),
    ]


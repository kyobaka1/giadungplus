# Generated manually to fix missing product_id column in PostgreSQL

from django.db import migrations


def ensure_product_id_column(apps, schema_editor):
    """Đảm bảo cột product_id tồn tại trong database"""
    vendor = schema_editor.connection.vendor
    
    with schema_editor.connection.cursor() as cursor:
        if vendor == "postgresql":
            # Kiểm tra xem cột đã tồn tại chưa
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'cskh_feedback' AND column_name = 'product_id'
                """
            )
            exists = cursor.fetchone()
            
            if not exists:
                # Thêm cột product_id nếu chưa có
                try:
                    cursor.execute(
                        "ALTER TABLE cskh_feedback ADD COLUMN product_id bigint NULL"
                    )
                    print("Added product_id column to cskh_feedback")
                except Exception as e:
                    print(f"Error adding product_id column: {e}")
            
            # Tạo index nếu chưa có
            cursor.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'cskh_feedback' AND indexname LIKE '%product_id%'
                """
            )
            index_exists = cursor.fetchone()
            
            if not index_exists:
                try:
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS cskh_feedback_product_id_idx "
                        "ON cskh_feedback (product_id)"
                    )
                    print("Created index on product_id")
                except Exception as e:
                    print(f"Error creating index on product_id: {e}")
        
        elif vendor == "sqlite":
            # Kiểm tra xem cột đã tồn tại chưa
            cursor.execute("PRAGMA table_info(cskh_feedback)")
            columns = {row[1] for row in cursor.fetchall()}
            
            if "product_id" not in columns:
                try:
                    cursor.execute(
                        "ALTER TABLE cskh_feedback ADD COLUMN product_id bigint NULL"
                    )
                    print("Added product_id column to cskh_feedback")
                except Exception as e:
                    print(f"Error adding product_id column: {e}")


def reverse_ensure_product_id_column(apps, schema_editor):
    """Rollback: không xóa cột vì có thể mất dữ liệu"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cskh', '0017_alter_ticket_ticket_status'),
    ]

    operations = [
        migrations.RunPython(ensure_product_id_column, reverse_ensure_product_id_column),
    ]


# Generated manually for Shopee API integration

from django.db import migrations, models


def check_and_add_fields(apps, schema_editor):
    """Kiểm tra và thêm các field còn thiếu"""
    # Chỉ chạy PRAGMA khi dùng SQLite (dev/local).
    # Trên PostgreSQL/MySQL, các field đã/được tạo bằng migrations chuẩn,
    # không cần (và không được) dùng PRAGMA.
    if schema_editor.connection.vendor != "sqlite":
        return

    db_alias = schema_editor.connection.alias
    with schema_editor.connection.cursor() as cursor:
        # Kiểm tra xem các column đã có chưa
        cursor.execute("PRAGMA table_info(cskh_feedback)")
        columns = {row[1] for row in cursor.fetchall()}
        
        # Danh sách các field cần thêm
        fields_to_add = {
            'comment_id': 'bigint NULL',
            'user_portrait': 'varchar(200) NOT NULL DEFAULT ""',
            'product_id': 'bigint NULL',
            'product_cover': 'varchar(200) NOT NULL DEFAULT ""',
            'model_id': 'bigint NULL',
            'model_name': 'varchar(500) NOT NULL DEFAULT ""',
            'order_id': 'bigint NULL',
            'user_id': 'bigint NULL',
            'is_hidden': 'bool NOT NULL DEFAULT 0',
            'status': 'integer NULL',
            'can_follow_up': 'bool NULL',
            'follow_up': 'text NULL',
            'submit_time': 'bigint NULL',
            'low_rating_reasons': 'text NOT NULL DEFAULT \'[]\'',
            'ctime': 'bigint NULL',
            'mtime': 'bigint NULL',
        }
        
        # Thêm các field còn thiếu
        for field_name, field_type in fields_to_add.items():
            if field_name not in columns:
                try:
                    cursor.execute(f"ALTER TABLE cskh_feedback ADD COLUMN {field_name} {field_type}")
                    print(f"Added column: {field_name}")
                except Exception as e:
                    print(f"Error adding {field_name}: {e}")
        
        # Tạo index cho comment_id nếu chưa có
        cursor.execute("PRAGMA index_list(cskh_feedback)")
        indexes = {row[1] for row in cursor.fetchall()}
        if 'cskh_feedback_comment_id_5705455e' not in indexes and 'comment_id' in columns:
            try:
                cursor.execute("CREATE INDEX IF NOT EXISTS cskh_feedback_comment_id_5705455e ON cskh_feedback (comment_id)")
            except Exception:
                pass


def reverse_check_and_add_fields(apps, schema_editor):
    """Rollback: không làm gì vì không thể xóa column an toàn"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cskh', '0013_fix_feedback_user_reply_nullable'),
    ]

    operations = [
        # Kiểm tra và thêm các field còn thiếu (bỏ qua nếu đã có)
        migrations.RunPython(check_and_add_fields, reverse_check_and_add_fields),
        
        # Đổi feedback_id, tenant_id thành nullable (legacy fields)
        migrations.AlterField(
            model_name='feedback',
            name='feedback_id',
            field=models.BigIntegerField(blank=True, db_index=True, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='feedback',
            name='tenant_id',
            field=models.IntegerField(blank=True, db_index=True, null=True),
        ),
    ]

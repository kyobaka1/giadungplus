# Generated manually for Shopee API integration

from django.db import migrations, models


def check_and_add_fields(apps, schema_editor):
    """Kiểm tra và thêm các field còn thiếu"""
    vendor = schema_editor.connection.vendor

    # Danh sách các field cần thêm (mapping chung, type sẽ convert theo DB backend)
    fields_to_add = {
        "comment_id": {"sqlite": "bigint NULL", "postgresql": "bigint NULL"},
        "user_portrait": {
            "sqlite": 'varchar(200) NOT NULL DEFAULT ""',
            "postgresql": 'varchar(200) NOT NULL DEFAULT \'\'',
        },
        "product_id": {"sqlite": "bigint NULL", "postgresql": "bigint NULL"},
        "product_cover": {
            "sqlite": 'varchar(200) NOT NULL DEFAULT ""',
            "postgresql": 'varchar(200) NOT NULL DEFAULT \'\'',
        },
        "model_id": {"sqlite": "bigint NULL", "postgresql": "bigint NULL"},
        "model_name": {
            "sqlite": 'varchar(500) NOT NULL DEFAULT ""',
            "postgresql": 'varchar(500) NOT NULL DEFAULT \'\'',
        },
        "order_id": {"sqlite": "bigint NULL", "postgresql": "bigint NULL"},
        "user_id": {"sqlite": "bigint NULL", "postgresql": "bigint NULL"},
        "is_hidden": {
            "sqlite": "bool NOT NULL DEFAULT 0",
            "postgresql": "boolean NOT NULL DEFAULT false",
        },
        "status": {"sqlite": "integer NULL", "postgresql": "integer NULL"},
        "can_follow_up": {"sqlite": "bool NULL", "postgresql": "boolean NULL"},
        "follow_up": {"sqlite": "text NULL", "postgresql": "text NULL"},
        "submit_time": {"sqlite": "bigint NULL", "postgresql": "bigint NULL"},
        "low_rating_reasons": {
            "sqlite": "text NOT NULL DEFAULT '[]'",
            "postgresql": "jsonb NOT NULL DEFAULT '[]'::jsonb",
        },
        "ctime": {"sqlite": "bigint NULL", "postgresql": "bigint NULL"},
        "mtime": {"sqlite": "bigint NULL", "postgresql": "bigint NULL"},
    }

    with schema_editor.connection.cursor() as cursor:
        if vendor == "sqlite":
            # Kiểm tra xem các column đã có chưa bằng PRAGMA
            cursor.execute("PRAGMA table_info(cskh_feedback)")
            columns = {row[1] for row in cursor.fetchall()}

            # Thêm các field còn thiếu
            for field_name, type_map in fields_to_add.items():
                field_type = type_map["sqlite"]
                if field_name not in columns:
                    try:
                        cursor.execute(
                            f"ALTER TABLE cskh_feedback ADD COLUMN {field_name} {field_type}"
                        )
                        print(f"Added column: {field_name}")
                    except Exception as e:
                        print(f"Error adding {field_name}: {e}")

            # Tạo index cho comment_id nếu chưa có
            cursor.execute("PRAGMA index_list(cskh_feedback)")
            indexes = {row[1] for row in cursor.fetchall()}
            if (
                "cskh_feedback_comment_id_5705455e" not in indexes
                and "comment_id" in columns
            ):
                try:
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS "
                        "cskh_feedback_comment_id_5705455e "
                        "ON cskh_feedback (comment_id)"
                    )
                except Exception:
                    pass

        elif vendor == "postgresql":
            # Lấy danh sách cột hiện có từ information_schema
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'cskh_feedback'
                """
            )
            columns = {row[0] for row in cursor.fetchall()}

            # Thêm các field còn thiếu bằng ALTER TABLE ... ADD COLUMN IF NOT EXISTS
            for field_name, type_map in fields_to_add.items():
                field_type = type_map["postgresql"]
                try:
                    cursor.execute(
                        f"ALTER TABLE cskh_feedback "
                        f"ADD COLUMN IF NOT EXISTS {field_name} {field_type}"
                    )
                except Exception as e:
                    print(f"Error adding {field_name} on PostgreSQL: {e}")

            # Tạo index cho comment_id nếu chưa có
            cursor.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'cskh_feedback'
                """
            )
            indexes = {row[0] for row in cursor.fetchall()}
            if "cskh_feedback_comment_id_5705455e" not in indexes:
                try:
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS "
                        "cskh_feedback_comment_id_5705455e "
                        "ON cskh_feedback (comment_id)"
                    )
                except Exception as e:
                    print(f"Error creating index on PostgreSQL: {e}")

        else:
            # Các backend khác: bỏ qua (không hỗ trợ custom SQL)
            return


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

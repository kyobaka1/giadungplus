from django.db import migrations, models
import django.utils.timezone
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("cskh", "0015_feedback_can_follow_up_feedback_comment_id_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="TrainingDocument",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        max_length=255, help_text="Tên hiển thị của tài liệu"
                    ),
                ),
                (
                    "filename",
                    models.CharField(
                        max_length=255,
                        unique=True,
                        help_text="Tên file .md được lưu trong settings/logs/train_cskh/",
                    ),
                ),
                (
                    "uploaded_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="training_documents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["title"],
            },
        ),
    ]



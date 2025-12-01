from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cskh', '0009_tickettransfer'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='sugget_process',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]



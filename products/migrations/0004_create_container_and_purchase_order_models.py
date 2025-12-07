# Generated migration for Container and Purchase Order models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('products', '0003_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContainerTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, help_text='Mã container (ví dụ: CONT-01)', max_length=50, unique=True)),
                ('name', models.CharField(blank=True, help_text='Tên container (tùy chọn)', max_length=200)),
                ('container_type', models.CharField(choices=[('40ft', '40 feet'), ('20ft', '20 feet')], default='40ft', help_text='Loại container', max_length=20)),
                ('volume_cbm', models.FloatField(default=65.0, help_text='Mét khối (mặc định 65 CBM cho 40ft)')),
                ('default_supplier_id', models.BigIntegerField(blank=True, help_text='Sapo supplier_id', null=True)),
                ('default_supplier_code', models.CharField(blank=True, help_text='Mã NSX (ví dụ: ShuangQing)', max_length=100)),
                ('default_supplier_name', models.CharField(blank=True, help_text='Tên NSX', max_length=200)),
                ('ship_time_avg_hn', models.IntegerField(default=0, help_text='TQ -> Hà Nội (ngày)')),
                ('ship_time_avg_hcm', models.IntegerField(default=0, help_text='TQ -> Hồ Chí Minh (ngày)')),
                ('departure_port', models.CharField(blank=True, help_text='Ningbo, Shanghai...', max_length=100)),
                ('avg_import_cycle_days', models.IntegerField(blank=True, help_text='Ngày/1 lần nhập (tính toán tự động)', null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Container Template',
                'verbose_name_plural': 'Container Templates',
                'db_table': 'products_container_template',
            },
        ),
        migrations.CreateModel(
            name='SumPurchaseOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, help_text='SPO-2025-001', max_length=50, unique=True)),
                ('name', models.CharField(blank=True, help_text='Tên đợt nhập (tùy chọn)', max_length=200)),
                ('status', models.CharField(choices=[('draft', 'Nháp'), ('created', 'Đã tạo SPO'), ('supplier_confirmed', 'NSX xác nhận PO'), ('producing', 'Đang sản xuất'), ('waiting_packing', 'Đợi đóng container'), ('packed', 'Đóng xong container'), ('departed_cn', 'Rời cảng Trung Quốc'), ('arrived_vn', 'Về cảng Việt Nam'), ('customs_cleared', 'Thông quan'), ('arrived_warehouse_hn', 'Về kho Hà Nội'), ('arrived_warehouse_hcm', 'Về kho Hồ Chí Minh'), ('completed', 'Hoàn thành'), ('cancelled', 'Đã hủy')], default='draft', max_length=50)),
                ('timeline', models.JSONField(blank=True, default=list)),
                ('shipping_cn_vn', models.DecimalField(decimal_places=2, default=0, help_text='Vận chuyển TQ-VN', max_digits=15)),
                ('customs_processing_vn', models.DecimalField(decimal_places=2, default=0, help_text='Xử lý Hải Quan VN', max_digits=15)),
                ('other_costs', models.DecimalField(decimal_places=2, default=0, help_text='Phí phát sinh', max_digits=15)),
                ('port_to_warehouse', models.DecimalField(decimal_places=2, default=0, help_text='Cảng -> kho', max_digits=15)),
                ('loading_unloading', models.DecimalField(decimal_places=2, default=0, help_text='Bốc xếp', max_digits=15)),
                ('total_cbm', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('tags', models.JSONField(blank=True, default=list, help_text="Tags từ Sapo PO (ví dụ: ['TEMP_HCM'])")),
                ('note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('container_template', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sum_purchase_orders', to='products.containertemplate')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Sum Purchase Order',
                'verbose_name_plural': 'Sum Purchase Orders',
                'db_table': 'products_sum_purchase_order',
            },
        ),
        migrations.CreateModel(
            name='PurchaseOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sapo_order_supplier_id', models.BigIntegerField(db_index=True, help_text='Sapo order_supplier.id', unique=True)),
                ('sapo_code', models.CharField(db_index=True, help_text='CN-2025-S87', max_length=100)),
                ('supplier_id', models.BigIntegerField(db_index=True)),
                ('supplier_code', models.CharField(max_length=100)),
                ('supplier_name', models.CharField(max_length=200)),
                ('domestic_shipping_cn', models.DecimalField(decimal_places=2, default=0, help_text='Vận chuyển nội địa TQ', max_digits=15)),
                ('packing_fee', models.DecimalField(decimal_places=2, default=0, help_text='Phí đóng hàng', max_digits=15)),
                ('total_cbm', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('tags', models.JSONField(blank=True, default=list, help_text="['CN', 'TEMP_HCM']")),
                ('status', models.CharField(blank=True, help_text='pending, completed...', max_length=50)),
                ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('total_quantity', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('synced_at', models.DateTimeField(blank=True, help_text='Lần sync cuối từ Sapo', null=True)),
                ('sum_purchase_order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchase_orders', to='products.sumpurchaseorder')),
            ],
            options={
                'verbose_name': 'Purchase Order',
                'verbose_name_plural': 'Purchase Orders',
                'db_table': 'products_purchase_order',
            },
        ),
        migrations.CreateModel(
            name='ContainerTemplateSupplier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('supplier_id', models.BigIntegerField(db_index=True, help_text='Sapo supplier_id')),
                ('supplier_code', models.CharField(max_length=100)),
                ('supplier_name', models.CharField(max_length=200)),
                ('supplier_logo_path', models.CharField(blank=True, help_text='Logo URL', max_length=500)),
                ('priority', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('container_template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='suppliers', to='products.containertemplate')),
            ],
            options={
                'verbose_name': 'Container Template Supplier',
                'verbose_name_plural': 'Container Template Suppliers',
                'db_table': 'products_container_template_supplier',
            },
        ),
        migrations.CreateModel(
            name='PurchaseOrderLineItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sapo_line_item_id', models.BigIntegerField(db_index=True)),
                ('product_id', models.BigIntegerField()),
                ('variant_id', models.BigIntegerField()),
                ('sku', models.CharField(db_index=True, max_length=100)),
                ('product_name', models.CharField(max_length=500)),
                ('variant_name', models.CharField(max_length=500)),
                ('quantity', models.IntegerField()),
                ('price', models.DecimalField(decimal_places=2, max_digits=15)),
                ('total_amount', models.DecimalField(decimal_places=2, max_digits=15)),
                ('domestic_shipping_cn', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('packing_fee', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('shipping_cn_vn_allocated', models.DecimalField(decimal_places=2, default=0, help_text='Phân bổ từ SPO', max_digits=15)),
                ('customs_processing_allocated', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('other_costs_allocated', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('port_to_warehouse_allocated', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('loading_unloading_allocated', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('vat', models.DecimalField(decimal_places=2, default=0, help_text='VAT', max_digits=15)),
                ('import_tax', models.DecimalField(decimal_places=2, default=0, help_text='Thuế nhập khẩu', max_digits=15)),
                ('cbm', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('unit', models.CharField(blank=True, max_length=50)),
                ('variant_options', models.CharField(blank=True, max_length=200)),
                ('purchase_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='line_items', to='products.purchaseorder')),
            ],
            options={
                'verbose_name': 'Purchase Order Line Item',
                'verbose_name_plural': 'Purchase Order Line Items',
                'db_table': 'products_purchase_order_line_item',
            },
        ),
        migrations.AddIndex(
            model_name='sumpurchaseorder',
            index=models.Index(fields=['code'], name='products_su_code_idx'),
        ),
        migrations.AddIndex(
            model_name='sumpurchaseorder',
            index=models.Index(fields=['status'], name='products_su_status_idx'),
        ),
        migrations.AddIndex(
            model_name='sumpurchaseorder',
            index=models.Index(fields=['container_template'], name='products_su_contain_idx'),
        ),
        migrations.AddIndex(
            model_name='sumpurchaseorder',
            index=models.Index(fields=['-created_at'], name='products_su_created_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['sapo_order_supplier_id'], name='products_pu_sapo_or_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['sapo_code'], name='products_pu_sapo_co_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['supplier_id'], name='products_pu_supplie_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['sum_purchase_order'], name='products_pu_sum_pur_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['status'], name='products_pu_status_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorderlineitem',
            index=models.Index(fields=['purchase_order', 'variant_id'], name='products_pu_purchas_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorderlineitem',
            index=models.Index(fields=['sku'], name='products_pu_sku_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorderlineitem',
            index=models.Index(fields=['variant_id'], name='products_pu_variant_idx'),
        ),
        migrations.AddIndex(
            model_name='containertemplate',
            index=models.Index(fields=['code'], name='products_co_code_idx'),
        ),
        migrations.AddIndex(
            model_name='containertemplate',
            index=models.Index(fields=['is_active'], name='products_co_is_acti_idx'),
        ),
        migrations.AddIndex(
            model_name='containertemplatesupplier',
            index=models.Index(fields=['container_template', 'supplier_id'], name='products_co_contain_idx'),
        ),
        migrations.AddIndex(
            model_name='containertemplatesupplier',
            index=models.Index(fields=['supplier_id'], name='products_co_supplie_idx'),
        ),
        migrations.AddConstraint(
            model_name='containertemplatesupplier',
            constraint=models.UniqueConstraint(fields=['container_template', 'supplier_id'], name='products_containertemplatesupplier_unique'),
        ),
    ]

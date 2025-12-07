# Generated migration to refactor SPO-PO relationship

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0006_sumpurchaseorder_destination_port_and_more'),
    ]

    operations = [
        # Tạo model mới SPOPurchaseOrder
        migrations.CreateModel(
            name='SPOPurchaseOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sapo_order_supplier_id', models.BigIntegerField(db_index=True, help_text='Sapo order_supplier.id')),
                ('domestic_shipping_cn', models.DecimalField(decimal_places=2, default=0, help_text='Vận chuyển nội địa TQ (ship nội địa của PO)', max_digits=15)),
                ('expected_production_date', models.DateField(blank=True, help_text='Thời gian dự kiến PO sản xuất xong', null=True)),
                ('expected_delivery_date', models.DateField(blank=True, help_text='Thời gian dự kiến ship đến nơi nhận', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('sum_purchase_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='spo_purchase_orders', to='products.sumpurchaseorder')),
            ],
            options={
                'verbose_name': 'SPO Purchase Order',
                'verbose_name_plural': 'SPO Purchase Orders',
                'db_table': 'products_spo_purchase_order',
            },
        ),
        migrations.AddIndex(
            model_name='spopurchaseorder',
            index=models.Index(fields=['sum_purchase_order', 'sapo_order_supplier_id'], name='products_sp_sum_pu_sapo_o_idx'),
        ),
        migrations.AddIndex(
            model_name='spopurchaseorder',
            index=models.Index(fields=['sapo_order_supplier_id'], name='products_sp_sapo_or_idx'),
        ),
        migrations.AddConstraint(
            model_name='spopurchaseorder',
            constraint=models.UniqueConstraint(fields=('sum_purchase_order', 'sapo_order_supplier_id'), name='products_spo_purchase_order_unique'),
        ),
        # Xóa models cũ PurchaseOrder và PurchaseOrderLineItem
        # Note: Cần backup data trước khi chạy migration này
        migrations.DeleteModel(
            name='PurchaseOrderLineItem',
        ),
        migrations.DeleteModel(
            name='PurchaseOrder',
        ),
    ]

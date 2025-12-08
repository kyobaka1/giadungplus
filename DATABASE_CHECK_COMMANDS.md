# Lệnh kiểm tra và điều chỉnh Database

## 1. Kiểm tra cấu trúc bảng SPOPurchaseOrder

```sql
-- Xem cấu trúc bảng SPOPurchaseOrder
\d products_spo_purchase_order;

-- Hoặc với MySQL/PostgreSQL
DESCRIBE products_spo_purchase_order;
-- hoặc
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'products_spo_purchase_order';
```

## 2. Kiểm tra các trường có trong bảng

```sql
-- PostgreSQL
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'products_spo_purchase_order'
ORDER BY ordinal_position;

-- MySQL
SHOW COLUMNS FROM products_spo_purchase_order;
```

## 3. Kiểm tra dữ liệu hiện tại

```sql
-- Xem các SPOPurchaseOrder hiện có
SELECT 
    id,
    sum_purchase_order_id,
    purchase_order_id,
    created_at,
    updated_at
FROM products_spo_purchase_order
LIMIT 10;

-- Kiểm tra xem có record nào có purchase_order_id = NULL không
SELECT COUNT(*) 
FROM products_spo_purchase_order 
WHERE purchase_order_id IS NULL;
```

## 4. Kiểm tra bảng PurchaseOrder

```sql
-- Xem cấu trúc bảng PurchaseOrder
\d products_purchase_order;

-- Xem các PurchaseOrder hiện có
SELECT 
    id,
    sapo_order_supplier_id,
    sapo_code,
    supplier_id,
    supplier_name,
    delivery_status
FROM products_purchase_order
LIMIT 10;
```

## 5. Kiểm tra quan hệ giữa SPOPurchaseOrder và PurchaseOrder

```sql
-- Xem các SPOPurchaseOrder có purchase_order_id hợp lệ
SELECT 
    spo_po.id as spo_po_id,
    spo_po.sum_purchase_order_id,
    spo_po.purchase_order_id,
    po.id as po_id,
    po.sapo_order_supplier_id,
    po.sapo_code
FROM products_spo_purchase_order spo_po
LEFT JOIN products_purchase_order po ON spo_po.purchase_order_id = po.id
LIMIT 20;
```

## 6. Kiểm tra các SPOPurchaseOrder có purchase_order_id = NULL (nếu có)

```sql
-- Tìm các SPOPurchaseOrder chưa có purchase_order
SELECT 
    spo_po.id,
    spo_po.sum_purchase_order_id,
    spo_po.created_at
FROM products_spo_purchase_order spo_po
WHERE spo_po.purchase_order_id IS NULL;
```

## 7. Kiểm tra migration đã chạy chưa

```sql
-- PostgreSQL
SELECT * FROM django_migrations 
WHERE app = 'products' 
ORDER BY applied DESC 
LIMIT 10;

-- MySQL
SELECT * FROM django_migrations 
WHERE app = 'products' 
ORDER BY applied DESC 
LIMIT 10;
```

## 8. Kiểm tra trường created_date trong SumPurchaseOrder

```sql
-- Xem cấu trúc bảng SumPurchaseOrder
\d products_sum_purchase_order;

-- Kiểm tra xem có trường created_date chưa
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'products_sum_purchase_order' 
AND column_name = 'created_date';

-- Xem dữ liệu created_date hiện có
SELECT 
    id,
    code,
    name,
    created_date,
    created_at
FROM products_sum_purchase_order
ORDER BY created_at DESC
LIMIT 10;
```

## 9. Nếu cần xóa dữ liệu test (CẨN THẬN!)

```sql
-- CHỈ CHẠY NẾU CHẮC CHẮN - Xóa các SPOPurchaseOrder test
-- DELETE FROM products_spo_purchase_order WHERE id IN (...);
```

## 10. Kiểm tra index và foreign keys

```sql
-- PostgreSQL - Xem các index
SELECT 
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'products_spo_purchase_order';

-- PostgreSQL - Xem các foreign keys
SELECT
    tc.constraint_name,
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
    AND tc.table_name = 'products_spo_purchase_order';
```

## Lưu ý quan trọng

1. **Luôn backup database trước khi chạy các lệnh DELETE hoặc UPDATE**
2. **Kiểm tra kỹ trước khi xóa dữ liệu**
3. **Nếu dùng PostgreSQL, dùng `\d table_name` để xem cấu trúc**
4. **Nếu dùng MySQL, dùng `DESCRIBE table_name` hoặc `SHOW COLUMNS FROM table_name`**

## Các lệnh Django management để kiểm tra

```bash
# Kiểm tra migration
python manage.py showmigrations products

# Kiểm tra SQL sẽ được tạo
python manage.py sqlmigrate products 0013

# Kiểm tra model
python manage.py shell
>>> from products.models import SPOPurchaseOrder, PurchaseOrder
>>> SPOPurchaseOrder._meta.get_fields()
>>> PurchaseOrder._meta.get_fields()
```

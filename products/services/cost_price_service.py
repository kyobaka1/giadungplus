# products/services/cost_price_service.py
"""
Service để tính toán và quản lý giá vốn (cost price).
"""

from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime, date
import logging

from django.db import transaction
from django.utils import timezone

from products.models import (
    CostHistory, SumPurchaseOrder, PurchaseOrder, 
    SPOPackingListItem, PurchaseOrderCost
)
from core.sapo_client import get_sapo_client
from products.services.sapo_product_service import SapoProductService
from products.services.metadata_helper import get_variant_metadata

logger = logging.getLogger(__name__)


class CostPriceService:
    """
    Service để tính toán giá vốn cho các sản phẩm nhập hàng.
    """
    
    def __init__(self, debug: bool = False):
        self.sapo_client = get_sapo_client()
        self.sapo_product_service = SapoProductService(self.sapo_client)
        self.debug = debug
    
    def debug_print(self, *args, **kwargs):
        """Print debug info nếu debug = True"""
        if self.debug:
            print(f"[DEBUG CostPriceService]", *args, **kwargs)
    
    def find_old_inventory(
        self, 
        variant_id: int, 
        location_id: int, 
        before_date: datetime,
        receipt_code: Optional[str] = None
    ) -> Tuple[Decimal, Decimal]:
        """
        Tìm tồn kho cũ và giá vốn cũ trước thời điểm nhập hàng.
        
        Tham khảo: THAMKHAO/views.py:2820-2830
        
        Args:
            variant_id: ID của variant
            location_id: ID kho hàng
            before_date: Thời điểm cần tìm tồn kho (trước ngày nhập)
            receipt_code: Mã phiếu nhập (để tìm chính xác thời điểm)
        
        Returns:
            Tuple (old_quantity, old_cost_price):
            - old_quantity: Số lượng tồn kho cũ
            - old_cost_price: Giá vốn cũ
        """
        self.debug_print(f"find_old_inventory: Bắt đầu - variant_id={variant_id}, location_id={location_id}, before_date={before_date}, receipt_code={receipt_code}")
        try:
            # Lấy lịch sử tồn kho từ Sapo API
            # Endpoint: /reports/inventories/variants/{variant_id}.json
            old_quantity = Decimal('0')
            old_cost_price = Decimal('0')
            
            # Lấy tất cả các trang
            for page in range(1, 100):  # Tối đa 100 trang
                path = f"reports/inventories/variants/{variant_id}.json"
                params = {
                    'location_ids': location_id,
                    'page': page,
                    'limit': 250
                }
                self.debug_print(f"find_old_inventory: Đang lấy page {page} của inventory history")
                response = self.sapo_client.core.get(path, params=params)
                variant_inventories = response.get('variant_inventories', [])
                
                if not variant_inventories:
                    self.debug_print(f"find_old_inventory: Không còn dữ liệu ở page {page}")
                    break
                
                self.debug_print(f"find_old_inventory: Page {page}: {len(variant_inventories)} traces")
                
                for trace in variant_inventories:
                    # Kiểm tra nếu có receipt_code, tìm chính xác thời điểm đó
                    if receipt_code and trace.get('trans_object_code') == receipt_code:
                        # Tồn kho cũ = onhand - onhand_adj (tại thời điểm nhập)
                        onhand = Decimal(str(trace.get('onhand', 0) or 0))
                        onhand_adj = Decimal(str(trace.get('onhand_adj', 0) or 0))
                        old_quantity = onhand - onhand_adj
                        self.debug_print(f"find_old_inventory: Tìm thấy receipt_code: onhand={onhand}, onhand_adj={onhand_adj}, old_quantity={old_quantity}")
                        if old_quantity < 0:
                            self.debug_print(f"find_old_inventory: old_quantity < 0, set về 0")
                            old_quantity = Decimal('0')
                        break
                    
                    # Nếu không có receipt_code, tìm tồn kho trước before_date
                    issued_at = trace.get('issued_at_utc')
                    if issued_at:
                        try:
                            trace_date = datetime.fromisoformat(
                                issued_at.replace('Z', '+00:00')
                            )
                            if trace_date < before_date:
                                self.debug_print(f"find_old_inventory: Tìm thấy trace trước before_date: trace_date={trace_date}, before_date={before_date}")
                                # Tìm giá vốn từ CostHistory gần nhất trước thời điểm này
                                cost_history = CostHistory.objects.filter(
                                    variant_id=variant_id,
                                    location_id=location_id,
                                    import_date__lt=before_date.date()
                                ).order_by('-import_date').first()
                                
                                if cost_history:
                                    old_cost_price = cost_history.average_cost_price
                                    self.debug_print(f"find_old_inventory: Tìm thấy CostHistory: old_cost_price={old_cost_price}")
                                
                                # Tính tồn kho bằng cách cộng dồn các onhand_adj
                                # (Logic phức tạp hơn, cần tính từ đầu đến before_date)
                                # Tạm thời dùng cách đơn giản: lấy onhand tại thời điểm gần nhất
                                onhand = Decimal(str(trace.get('onhand', 0) or 0))
                                onhand_adj = Decimal(str(trace.get('onhand_adj', 0) or 0))
                                old_quantity = onhand - onhand_adj
                                self.debug_print(f"find_old_inventory: onhand={onhand}, onhand_adj={onhand_adj}, old_quantity={old_quantity}")
                                if old_quantity < 0:
                                    self.debug_print(f"find_old_inventory: old_quantity < 0, set về 0")
                                    old_quantity = Decimal('0')
                                break
                        except Exception as e:
                            self.debug_print(f"find_old_inventory: Error parsing date {issued_at}: {e}")
                            logger.warning(f"Error parsing date {issued_at}: {e}")
                            continue
                
                # Nếu đã tìm thấy receipt_code, break
                if receipt_code and old_quantity > 0:
                    break
            
            # Nếu không tìm thấy từ inventory history, lấy từ CostHistory gần nhất
            if old_cost_price == 0:
                self.debug_print(f"find_old_inventory: Không tìm thấy từ inventory, tìm trong CostHistory")
                cost_history = CostHistory.objects.filter(
                    variant_id=variant_id,
                    location_id=location_id,
                    import_date__lt=before_date.date()
                ).order_by('-import_date').first()
                
                if cost_history:
                    old_cost_price = cost_history.average_cost_price
                    self.debug_print(f"find_old_inventory: Tìm thấy CostHistory: old_cost_price={old_cost_price}")
                    # Nếu chưa có old_quantity, lấy từ CostHistory
                    if old_quantity == 0:
                        old_quantity = cost_history.old_quantity
                        self.debug_print(f"find_old_inventory: Lấy old_quantity từ CostHistory: {old_quantity}")
            
            # Nếu vẫn không có, mặc định là 0
            if old_quantity < 0:
                self.debug_print(f"find_old_inventory: old_quantity < 0, set về 0")
                old_quantity = Decimal('0')
            
            self.debug_print(f"find_old_inventory: Kết quả: old_quantity={old_quantity}, old_cost_price={old_cost_price}")
            return old_quantity, old_cost_price
            
        except Exception as e:
            logger.error(f"Error finding old inventory for variant {variant_id}: {e}", exc_info=True)
            return Decimal('0'), Decimal('0')
    
    def calculate_new_cost_price(
        self,
        variant_id: int,
        spo: SumPurchaseOrder,
        po: PurchaseOrder,
        quantity: Decimal,
        cpm_per_unit: Decimal,
        sku_model_xnk: Optional[str] = None,
        po_total_cbm: Optional[Decimal] = None
    ) -> Dict[str, Any]:
        """
        Tính giá vốn mới cho variant.
        
        Công thức:
        Giá vốn = giá nhập CNY * tỷ giá CNY TB 
                + thuế NK (đơn chiếc) 
                + thuế GTGT (đơn chiếc) 
                + chi phí riêng của PO phân bổ trên CPM cho đơn chiếc 
                + tổng chi phí SPO phân bổ trên CPM cho đơn chiếc
        
        Args:
            variant_id: ID của variant
            spo: SumPurchaseOrder
            po: PurchaseOrder
            quantity: Số lượng nhập
            cpm_per_unit: CBM của 1 chiếc sản phẩm
            sku_model_xnk: SKU-MODEL-XNK để match với packing list
        
        Returns:
            Dict chứa các thành phần giá vốn
        """
        self.debug_print(f"calculate_new_cost_price: Bắt đầu - variant_id={variant_id}, quantity={quantity}, cpm_per_unit={cpm_per_unit}, sku_model_xnk={sku_model_xnk}")
        result = {
            'price_cny': Decimal('0'),
            'exchange_rate_avg': Decimal('0'),
            'import_tax_per_unit': Decimal('0'),
            'vat_per_unit': Decimal('0'),
            'po_cost_per_unit': Decimal('0'),
            'spo_cost_per_unit': Decimal('0'),
            'new_cost_price': Decimal('0'),
        }
        
        try:
            # 1. Lấy giá nhập CNY từ variant metadata (price_tq)
            self.debug_print(f"calculate_new_cost_price: Bước 1: Lấy giá nhập CNY từ variant metadata")
            # Lấy product từ variant
            variant_data = self.sapo_client.core.get_variant_raw(variant_id)
            if variant_data and variant_data.get('variant'):
                product_id = variant_data['variant'].get('product_id')
                self.debug_print(f"calculate_new_cost_price: product_id={product_id}")
                if product_id:
                    product = self.sapo_product_service.get_product(product_id)
                    if product and product.gdp_metadata:
                        variant_metadata = get_variant_metadata(
                            product.gdp_metadata,
                            variant_id
                        )
                        if variant_metadata and variant_metadata.price_tq:
                            result['price_cny'] = Decimal(str(variant_metadata.price_tq))
                            self.debug_print(f"calculate_new_cost_price: price_cny={result['price_cny']}")
                        else:
                            self.debug_print(f"calculate_new_cost_price: Không tìm thấy price_tq trong metadata")
                    else:
                        self.debug_print(f"calculate_new_cost_price: Không có product hoặc gdp_metadata")
                else:
                    self.debug_print(f"calculate_new_cost_price: Không có product_id")
            else:
                self.debug_print(f"calculate_new_cost_price: Không lấy được variant_data")
            
            # 2. Lấy tỷ giá CNY trung bình từ các khoản thanh toán PO
            self.debug_print(f"calculate_new_cost_price: Bước 2: Lấy tỷ giá CNY trung bình")
            exchange_rates = []
            payment_count = 0
            for payment in po.payments.all():
                payment_count += 1
                if payment.exchange_rate:
                    rate = Decimal(str(payment.exchange_rate))
                    exchange_rates.append(rate)
                    self.debug_print(f"calculate_new_cost_price: Payment {payment_count}: exchange_rate={rate}")
                elif payment.balance_transaction:
                    # Lấy từ payment_period
                    period_txn = payment.balance_transaction.payment_periods.first()
                    if period_txn and period_txn.payment_period:
                        rate = period_txn.payment_period.avg_exchange_rate_realtime
                        if rate:
                            rate_decimal = Decimal(str(rate))
                            exchange_rates.append(rate_decimal)
                            self.debug_print(f"calculate_new_cost_price: Payment {payment_count}: rate từ payment_period={rate_decimal}")
            
            if exchange_rates:
                result['exchange_rate_avg'] = sum(exchange_rates) / len(exchange_rates)
                self.debug_print(f"calculate_new_cost_price: Tỷ giá trung bình: {result['exchange_rate_avg']} (từ {len(exchange_rates)} payments)")
            else:
                self.debug_print(f"calculate_new_cost_price: Không tìm thấy tỷ giá nào")
            
            # 3. Lấy thuế NK và GTGT từ packing list (match theo sku_model_xnk)
            self.debug_print(f"calculate_new_cost_price: Bước 3: Lấy thuế NK và GTGT từ packing list")
            if sku_model_xnk:
                packing_item = SPOPackingListItem.objects.filter(
                    sum_purchase_order=spo,
                    sku_nhapkhau=sku_model_xnk
                ).first()
                
                if packing_item:
                    self.debug_print(f"calculate_new_cost_price: Tìm thấy packing_item: quantity={packing_item.quantity}, import_tax_total={packing_item.import_tax_total}, vat_total={packing_item.vat_total}")
                    # Thuế NK đơn chiếc = import_tax_total / quantity
                    if packing_item.quantity > 0:
                        result['import_tax_per_unit'] = (
                            Decimal(str(packing_item.import_tax_total)) / 
                            Decimal(str(packing_item.quantity))
                        )
                        result['vat_per_unit'] = (
                            Decimal(str(packing_item.vat_total)) / 
                            Decimal(str(packing_item.quantity))
                        )
                        self.debug_print(f"calculate_new_cost_price: import_tax_per_unit={result['import_tax_per_unit']}, vat_per_unit={result['vat_per_unit']}")
                    else:
                        self.debug_print(f"calculate_new_cost_price: packing_item.quantity = 0")
                else:
                    self.debug_print(f"calculate_new_cost_price: Không tìm thấy packing_item với sku_model_xnk={sku_model_xnk}")
            else:
                self.debug_print(f"calculate_new_cost_price: Không có sku_model_xnk")
            
            # 4. Tính chi phí riêng của PO phân bổ trên CPM
            self.debug_print(f"calculate_new_cost_price: Bước 4: Tính chi phí PO phân bổ trên CPM")
            
            # Sử dụng po_total_cbm được truyền vào (tổng CBM của toàn bộ PO)
            if po_total_cbm is None or po_total_cbm == 0:
                # Fallback: tính từ cpm_per_unit * quantity của variant này (không chính xác lắm)
                po_total_cbm = cpm_per_unit * quantity
                self.debug_print(f"calculate_new_cost_price: po_total_cbm không được truyền vào, dùng fallback: {po_total_cbm}")
            else:
                self.debug_print(f"calculate_new_cost_price: po_total_cbm={po_total_cbm} (từ PO)")
            
            if po_total_cbm > 0:
                # Tổng chi phí PO (CNY)
                po_total_costs_cny = sum(
                    Decimal(str(cost.amount_cny)) 
                    for cost in po.costs.all()
                )
                self.debug_print(f"calculate_new_cost_price: po_total_costs_cny={po_total_costs_cny} (từ {po.costs.count()} costs)")
                
                # Quy đổi sang VNĐ
                if result['exchange_rate_avg'] > 0:
                    po_total_costs_vnd = po_total_costs_cny * result['exchange_rate_avg']
                    self.debug_print(f"calculate_new_cost_price: po_total_costs_vnd={po_total_costs_vnd} (CNY * tỷ giá)")
                    
                    # Phân bổ theo CPM: chi phí PO cho variant này = (cpm_per_unit / po_total_cbm) * po_total_costs_vnd
                    if cpm_per_unit > 0:
                        result['po_cost_per_unit'] = (
                            po_total_costs_vnd * cpm_per_unit / po_total_cbm
                        )
                        self.debug_print(f"calculate_new_cost_price: po_cost_per_unit={result['po_cost_per_unit']} (po_total_costs_vnd={po_total_costs_vnd} * cpm_per_unit={cpm_per_unit} / po_total_cbm={po_total_cbm})")
                    else:
                        self.debug_print(f"calculate_new_cost_price: cpm_per_unit = 0, không thể phân bổ")
                else:
                    self.debug_print(f"calculate_new_cost_price: Không có tỷ giá để quy đổi (exchange_rate_avg={result['exchange_rate_avg']})")
            else:
                self.debug_print(f"calculate_new_cost_price: po_total_cbm = {po_total_cbm}, bỏ qua chi phí PO")
            
            # 5. Tính chi phí SPO phân bổ trên CPM
            self.debug_print(f"calculate_new_cost_price: Bước 5: Tính chi phí SPO phân bổ trên CPM")
            spo_total_cbm = Decimal(str(spo.total_cbm or 0))
            self.debug_print(f"calculate_new_cost_price: spo_total_cbm={spo_total_cbm}")
            if spo_total_cbm > 0 and cpm_per_unit > 0:
                # Tổng chi phí SPO (VNĐ) - lấy từ spo.costs thay vì từ các trường trực tiếp
                spo_total_costs_vnd = Decimal('0')
                
                # 1. Chi phí VNĐ (cost_side == 'vietnam')
                for cost in spo.costs.all():
                    if cost.cost_side == 'vietnam' and cost.amount_vnd:
                        spo_total_costs_vnd += Decimal(str(cost.amount_vnd))
                        self.debug_print(f"calculate_new_cost_price: Chi phí VNĐ: {cost.name or 'N/A'} = {cost.amount_vnd}")
                
                # 2. Chi phí CNY (cost_side == 'china') quy đổi sang VNĐ
                for cost in spo.costs.all():
                    if cost.cost_side == 'china' and cost.amount_cny:
                        # Lấy tỷ giá từ PaymentPeriod của balance_transaction
                        exchange_rate = None
                        if cost.balance_transaction:
                            period_txn = cost.balance_transaction.payment_periods.first()
                            if period_txn and period_txn.payment_period:
                                period = period_txn.payment_period
                                period_rate = period.avg_exchange_rate_realtime
                                if period_rate:
                                    exchange_rate = Decimal(str(period_rate))
                        
                        # Nếu không có tỷ giá từ payment_period, dùng tỷ giá trung bình đã tính
                        if not exchange_rate:
                            exchange_rate = result.get('exchange_rate_avg', Decimal('0'))
                        
                        if exchange_rate > 0:
                            cost_vnd = Decimal(str(cost.amount_cny)) * exchange_rate
                            spo_total_costs_vnd += cost_vnd
                            self.debug_print(f"calculate_new_cost_price: Chi phí CNY: {cost.name or 'N/A'} = {cost.amount_cny} CNY * {exchange_rate} = {cost_vnd} VNĐ")
                        else:
                            self.debug_print(f"calculate_new_cost_price: Chi phí CNY: {cost.name or 'N/A'} = {cost.amount_cny} CNY nhưng không có tỷ giá")
                
                self.debug_print(f"calculate_new_cost_price: spo_total_costs_vnd={spo_total_costs_vnd} (từ {spo.costs.count()} costs)")
                
                # Phân bổ theo CPM
                if spo_total_costs_vnd > 0:
                    result['spo_cost_per_unit'] = (
                        spo_total_costs_vnd * cpm_per_unit / spo_total_cbm
                    )
                    self.debug_print(f"calculate_new_cost_price: spo_cost_per_unit={result['spo_cost_per_unit']} (spo_total_costs_vnd={spo_total_costs_vnd} * cpm_per_unit={cpm_per_unit} / spo_total_cbm={spo_total_cbm})")
                else:
                    self.debug_print(f"calculate_new_cost_price: spo_total_costs_vnd = 0, không thể phân bổ")
            else:
                self.debug_print(f"calculate_new_cost_price: spo_total_cbm={spo_total_cbm} hoặc cpm_per_unit={cpm_per_unit} = 0, bỏ qua chi phí SPO")
            
            # 6. Tính giá vốn mới
            self.debug_print(f"calculate_new_cost_price: Bước 6: Tính giá vốn mới")
            result['new_cost_price'] = (
                result['price_cny'] * result['exchange_rate_avg'] +
                result['import_tax_per_unit'] +
                result['vat_per_unit'] +
                result['po_cost_per_unit'] +
                result['spo_cost_per_unit']
            )
            self.debug_print(f"calculate_new_cost_price: Giá vốn mới = {result['price_cny']} * {result['exchange_rate_avg']} + {result['import_tax_per_unit']} + {result['vat_per_unit']} + {result['po_cost_per_unit']} + {result['spo_cost_per_unit']} = {result['new_cost_price']}")
            
        except Exception as e:
            logger.error(f"Error calculating new cost price for variant {variant_id}: {e}", exc_info=True)
        
        return result
    
    @transaction.atomic
    def calculate_and_save_cost_history(
        self,
        spo: SumPurchaseOrder,
        po: PurchaseOrder,
        variant_id: int,
        location_id: int,
        quantity: Decimal,
        cpm_per_unit: Decimal,
        import_date: date,
        receipt_code: Optional[str] = None,
        sku: Optional[str] = None,
        sku_model_xnk: Optional[str] = None,
        tkhq_code: Optional[str] = None,
        po_total_cbm: Optional[Decimal] = None,
        user=None
    ) -> CostHistory:
        """
        Tính toán và lưu CostHistory cho một variant.
        
        Args:
            spo: SumPurchaseOrder
            po: PurchaseOrder
            variant_id: ID của variant
            location_id: ID kho hàng
            quantity: Số lượng nhập
            cpm_per_unit: CBM của 1 chiếc
            import_date: Ngày nhập kho
            receipt_code: Mã phiếu nhập
            sku: SKU của variant
            sku_model_xnk: SKU-MODEL-XNK
            tkhq_code: Mã tờ khai hải quan
            user: User tạo record
        
        Returns:
            CostHistory object
        """
        self.debug_print(f"calculate_and_save_cost_history: Bắt đầu - variant_id={variant_id}, location_id={location_id}, quantity={quantity}, import_date={import_date}")
        before_datetime = datetime.combine(import_date, datetime.min.time())
        before_datetime = timezone.make_aware(before_datetime)
        
        # 1. Tìm tồn kho cũ và giá vốn cũ
        self.debug_print(f"calculate_and_save_cost_history: Bước 1: Tìm tồn kho cũ và giá vốn cũ")
        old_quantity, old_cost_price = self.find_old_inventory(
            variant_id=variant_id,
            location_id=location_id,
            before_date=before_datetime,
            receipt_code=receipt_code
        )
        self.debug_print(f"calculate_and_save_cost_history: Kết quả tìm tồn kho cũ: old_quantity={old_quantity}, old_cost_price={old_cost_price}")
        
        # 2. Tính giá vốn mới
        self.debug_print(f"calculate_and_save_cost_history: Bước 2: Tính giá vốn mới")
        cost_calc = self.calculate_new_cost_price(
            variant_id=variant_id,
            spo=spo,
            po=po,
            quantity=quantity,
            cpm_per_unit=cpm_per_unit,
            sku_model_xnk=sku_model_xnk,
            po_total_cbm=po_total_cbm
        )
        self.debug_print(f"calculate_and_save_cost_history: Kết quả tính giá vốn mới: {cost_calc}")
        
        # 3. Tạo hoặc cập nhật CostHistory
        self.debug_print(f"calculate_and_save_cost_history: Bước 3: Tạo hoặc cập nhật CostHistory")
        cost_history, created = CostHistory.objects.update_or_create(
            sum_purchase_order=spo,
            purchase_order=po,
            variant_id=variant_id,
            location_id=location_id,
            import_date=import_date,
            defaults={
                'tkhq_code': tkhq_code or '',
                'receipt_code': receipt_code or '',
                'import_quantity': quantity,
                'old_cost_price': old_cost_price,
                'old_quantity': old_quantity,
                'new_cost_price': cost_calc['new_cost_price'],
                'price_cny': cost_calc['price_cny'],
                'exchange_rate_avg': cost_calc['exchange_rate_avg'],
                'import_tax_per_unit': cost_calc['import_tax_per_unit'],
                'vat_per_unit': cost_calc['vat_per_unit'],
                'po_cost_per_unit': cost_calc['po_cost_per_unit'],
                'spo_cost_per_unit': cost_calc['spo_cost_per_unit'],
                'sku': sku or '',
                'sku_model_xnk': sku_model_xnk or '',
                'cpm_per_unit': cpm_per_unit,
                'created_by': user,
            }
        )
        self.debug_print(f"calculate_and_save_cost_history: CostHistory {'created' if created else 'updated'}: id={cost_history.id}")
        
        # 4. Tính giá vốn trung bình
        self.debug_print(f"calculate_and_save_cost_history: Bước 4: Tính giá vốn trung bình")
        self.debug_print(f"calculate_and_save_cost_history: old_quantity={cost_history.old_quantity}, old_cost_price={cost_history.old_cost_price}, import_quantity={cost_history.import_quantity}, new_cost_price={cost_history.new_cost_price}")
        
        # Kiểm tra nếu không có giá vốn cũ
        if cost_history.old_cost_price == 0 or cost_history.old_cost_price is None:
            self.debug_print(f"calculate_and_save_cost_history: Không có giá vốn cũ (old_cost_price={cost_history.old_cost_price}), dùng giá vốn mới")
        else:
            self.debug_print(f"calculate_and_save_cost_history: Có giá vốn cũ, tính bình quân gia quyền")
        
        cost_history.calculate_average_cost_price()
        self.debug_print(f"calculate_and_save_cost_history: average_cost_price={cost_history.average_cost_price}")
        cost_history.save()
        
        self.debug_print(f"calculate_and_save_cost_history: Hoàn thành - variant={variant_id}, location={location_id}, avg_cost={cost_history.average_cost_price}")
        logger.info(
            f"Created/Updated CostHistory: variant={variant_id}, "
            f"location={location_id}, avg_cost={cost_history.average_cost_price}"
        )
        
        return cost_history
    
    def sync_cost_to_sapo(
        self,
        cost_history: CostHistory,
        code: str = "SUPFINAL"
    ) -> bool:
        """
        Đồng bộ giá vốn lên Sapo price_adjustments.
        
        Tham khảo: THAMKHAO/views.py:2838-2861
        
        Args:
            cost_history: CostHistory object
            code: Mã code cho price_adjustment (mặc định: "SUPFINAL")
        
        Returns:
            True nếu thành công, False nếu thất bại
        """
        self.debug_print(f"sync_cost_to_sapo: Bắt đầu - cost_history_id={cost_history.id}, variant_id={cost_history.variant_id}, location_id={cost_history.location_id}, code={code}")
        try:
            # 1. Tìm hoặc tạo price_adjustment
            self.debug_print(f"sync_cost_to_sapo: Bước 1: Tìm hoặc tạo price_adjustment với code={code}")
            path = "price_adjustments.json"
            params = {'query': code}
            
            response = self.sapo_client.core.get(path, params=params)
            price_adjustments = response.get('price_adjustments', [])
            self.debug_print(f"sync_cost_to_sapo: Tìm thấy {len(price_adjustments)} price_adjustments")
            
            if price_adjustments:
                pa = price_adjustments[0]
                self.debug_print(f"sync_cost_to_sapo: Sử dụng price_adjustment hiện có: id={pa.get('id')}")
            else:
                # Tạo mới
                self.debug_print(f"sync_cost_to_sapo: Tạo price_adjustment mới")
                pa_data = {
                    "location_id": cost_history.location_id,
                    "code": code,
                    "tags": [],
                    "note": "",
                    "line_items": []
                }
                response = self.sapo_client.core.post(
                    "price_adjustments.json",
                    json={"price_adjustment": pa_data}
                )
                pa = response.get('price_adjustment', {})
                self.debug_print(f"sync_cost_to_sapo: Đã tạo price_adjustment mới: id={pa.get('id')}")
            
            # 2. Tạo metadata JSON string
            self.debug_print(f"sync_cost_to_sapo: Bước 2: Tạo metadata JSON string")
            import json
            # Lấy product_id từ variant
            variant_data = self.sapo_client.core.get_variant_raw(cost_history.variant_id)
            product_id = 0
            if variant_data and variant_data.get('variant'):
                product_id = variant_data['variant'].get('product_id', 0)
                self.debug_print(f"sync_cost_to_sapo: product_id={product_id}")
            else:
                self.debug_print(f"sync_cost_to_sapo: Không lấy được variant_data")
            
            # Lấy PO code
            po_code = ''
            if cost_history.purchase_order:
                po_code = cost_history.purchase_order.sapo_code or ''
                self.debug_print(f"sync_cost_to_sapo: po_code={po_code}")
            
            metadata = {
                'vid': cost_history.variant_id,
                'pid': product_id,
                'p': po_code,
                's': cost_history.sku,
                'pu': int(cost_history.average_cost_price),
                'np': int(cost_history.new_cost_price),
                'nq': int(cost_history.import_quantity),
                'date': cost_history.import_date.strftime("%d/%m/%Y"),
                'op': int(cost_history.old_cost_price),
                'oq': int(cost_history.old_quantity),
                'li': cost_history.location_id,
                'rc': cost_history.receipt_code,
            }
            self.debug_print(f"sync_cost_to_sapo: metadata={metadata}")
            
            line_string = json.dumps(metadata).replace(" ", "")
            self.debug_print(f"sync_cost_to_sapo: line_string length={len(line_string)}")
            
            # 3. Tạo line_item
            self.debug_print(f"sync_cost_to_sapo: Bước 3: Tạo line_item")
            line_item = {
                "product_id": metadata['pid'],
                "variant_id": cost_history.variant_id,
                "note": line_string,
                "price": int(cost_history.average_cost_price),
                "product_type": "normal"
            }
            self.debug_print(f"sync_cost_to_sapo: line_item price={line_item['price']}, variant_id={line_item['variant_id']}")
            
            # 4. Cập nhật price_adjustment
            self.debug_print(f"sync_cost_to_sapo: Bước 4: Cập nhật price_adjustment")
            # Lấy line_items hiện tại
            pa_id = pa['id']
            pa_detail = self.sapo_client.core.get(
                f"price_adjustments/{pa_id}.json"
            )
            pa_data = pa_detail.get('price_adjustment', {})
            
            # Tìm và cập nhật line_item nếu đã có, hoặc thêm mới
            line_items = pa_data.get('line_items', [])
            self.debug_print(f"sync_cost_to_sapo: Hiện có {len(line_items)} line_items trong price_adjustment")
            found = False
            for i, item in enumerate(line_items):
                if item.get('variant_id') == cost_history.variant_id:
                    self.debug_print(f"sync_cost_to_sapo: Tìm thấy line_item cũ tại index {i}, sẽ cập nhật")
                    line_items[i] = line_item
                    found = True
                    break
            
            if not found:
                self.debug_print(f"sync_cost_to_sapo: Không tìm thấy line_item cũ, thêm mới")
                line_items.append(line_item)
            
            # PUT để cập nhật
            self.debug_print(f"sync_cost_to_sapo: Bước 5: PUT để cập nhật price_adjustment")
            update_data = {
                "price_adjustment": {
                    "code": pa_data.get('code', code),
                    "note": "",
                    "line_items": line_items
                }
            }
            self.debug_print(f"sync_cost_to_sapo: update_data có {len(line_items)} line_items")
            
            response = self.sapo_client.core.put(
                f"price_adjustments/{pa_id}.json",
                json=update_data
            )
            self.debug_print(f"sync_cost_to_sapo: PUT response: {response}")
            
            # 5. Cập nhật CostHistory
            self.debug_print(f"sync_cost_to_sapo: Bước 6: Cập nhật CostHistory")
            cost_history.synced_to_sapo = True
            cost_history.sapo_price_adjustment_id = pa_id
            cost_history.synced_at = timezone.now()
            cost_history.save()
            
            self.debug_print(f"sync_cost_to_sapo: Hoàn thành - variant={cost_history.variant_id}, PA={pa_id}")
            logger.info(f"Synced cost to Sapo: variant={cost_history.variant_id}, PA={pa_id}")
            return True
            
        except Exception as e:
            self.debug_print(f"sync_cost_to_sapo: LỖI: {e}")
            logger.error(f"Error syncing cost to Sapo: {e}", exc_info=True)
            return False


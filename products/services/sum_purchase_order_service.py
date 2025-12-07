# products/services/sum_purchase_order_service.py
"""
Service quản lý SPO và PO.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging

from django.utils import timezone
from django.db import transaction

from core.sapo_client import SapoClient
from products.models import (
    SumPurchaseOrder, 
    SPOPurchaseOrder,
    ContainerTemplate
)
from products.services.spo_po_service import SPOPOService

logger = logging.getLogger(__name__)


class SumPurchaseOrderService:
    """
    Service quản lý SPO và PO.
    """
    
    def __init__(self, sapo_client: SapoClient):
        """
        Args:
            sapo_client: SapoClient instance
        """
        self.sapo_client = sapo_client
        self.core_api = sapo_client.core
        self.spo_po_service = SPOPOService(sapo_client)
    
    def create_spo(self, container_template_id: int, name: str = None, destination_port: str = None, expected_arrival_date: str = None) -> SumPurchaseOrder:
        """
        Tạo SPO mới với code tự động.
        
        Args:
            container_template_id: ContainerTemplate ID
            name: Tên đợt nhập (optional)
            destination_port: Cảng đến ('hcm' hoặc 'haiphong')
            expected_arrival_date: Ngày dự kiến hàng về (YYYY-MM-DD format)
        
        Returns:
            SumPurchaseOrder instance
        
        Raises:
            ValueError: Nếu expected_arrival_date không hợp lệ (phải cách ngày tạo tối thiểu 12 ngày)
        """
        # Validate expected_arrival_date
        arrival_date = None
        if expected_arrival_date:
            try:
                arrival_date = date.fromisoformat(expected_arrival_date)
                today = date.today()
                min_date = today + timedelta(days=12)
                if arrival_date < min_date:
                    raise ValueError(f"Ngày dự kiến hàng về phải cách ngày hôm nay tối thiểu 12 ngày. Ngày tối thiểu: {min_date.strftime('%d/%m/%Y')}")
            except ValueError as e:
                if "phải cách" in str(e):
                    raise
                raise ValueError(f"Ngày không hợp lệ: {expected_arrival_date}. Vui lòng dùng format YYYY-MM-DD")
        
        container_template = ContainerTemplate.objects.get(id=container_template_id)
        
        # Generate code: SPO-YYYY-XXX (vẫn giữ format cũ cho code để unique)
        year = datetime.now().year
        last_spo = SumPurchaseOrder.objects.filter(
            code__startswith=f"SPO-{year}-"
        ).order_by('-code').first()
        
        if last_spo:
            try:
                last_num = int(last_spo.code.split('-')[-1])
                new_num = last_num + 1
            except (ValueError, IndexError):
                new_num = 1
        else:
            new_num = 1
        
        code = f"SPO-{year}-{new_num:03d}"
        
        # Generate name tự động: CON-SH-{YEAR}-{DESTINATION_PORT}-{NUMBER}
        # Prefix mặc định là CON-SH (có thể lấy từ container template sau)
        prefix = 'CON-SH'
        
        # Map destination_port (bắt buộc phải có để tạo name)
        if not destination_port:
            raise ValueError("Cảng đến là bắt buộc để tạo tên đợt nhập tự động")
        
        port_code = 'HCM'  # Mặc định
        if destination_port.lower() == 'hcm':
            port_code = 'HCM'
        elif destination_port.lower() == 'haiphong':
            port_code = 'HN'
        else:
            raise ValueError(f"Cảng đến không hợp lệ: {destination_port}. Chỉ chấp nhận 'hcm' hoặc 'haiphong'")
        
        # Tìm số thứ tự cuối cùng cho format CON-SH-{YEAR}-{PORT}-{NUMBER}
        # Filter theo prefix, year và port để đảm bảo số tăng đúng
        name_pattern = f"{prefix}-{year}-{port_code}-"
        last_spo_by_name = SumPurchaseOrder.objects.filter(
            name__startswith=name_pattern
        ).order_by('-name').first()
        
        if last_spo_by_name:
            try:
                # Extract số từ name (ví dụ: CON-SH-2025-HCM-01 -> 01)
                last_name_parts = last_spo_by_name.name.split('-')
                if len(last_name_parts) >= 5:
                    last_name_num = int(last_name_parts[-1])
                    new_name_num = last_name_num + 1
                else:
                    new_name_num = 1
            except (ValueError, IndexError):
                new_name_num = 1
        else:
            new_name_num = 1
        
        # Tạo name tự động
        auto_name = f"{prefix}-{year}-{port_code}-{new_name_num:02d}"
        
        spo = SumPurchaseOrder.objects.create(
            code=code,
            name=name or auto_name,
            container_template=container_template,
            status='draft',
            destination_port=destination_port or None,
            expected_arrival_date=arrival_date
        )
        
        # Initialize timeline với planned dates
        self._initialize_timeline(spo)
        
        logger.info(f"[SumPurchaseOrderService] Created SPO: {code}, destination_port={destination_port}, expected_arrival_date={arrival_date}")
        return spo
    
    def get_po_from_sapo(self, sapo_order_supplier_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin PO từ Sapo API (không lưu DB).
        
        Args:
            sapo_order_supplier_id: Sapo order_supplier ID
        
        Returns:
            Dict chứa thông tin PO (từ SPOPOService)
        """
        return self.spo_po_service.get_po_from_sapo(sapo_order_supplier_id)
    
    def add_po_to_spo(
        self, 
        spo_id: int, 
        po_ids: List[int] = None, 
        tag: str = None,
        domestic_shipping_cn: Decimal = None,
        expected_production_date: date = None,
        expected_delivery_date: date = None
    ) -> SumPurchaseOrder:
        """
        Thêm PO vào SPO (chỉ lưu thông tin cơ bản).
        
        Args:
            spo_id: SumPurchaseOrder ID
            po_ids: List Sapo order_supplier IDs (optional)
            tag: Tag để tìm PO (optional)
            domestic_shipping_cn: Vận chuyển nội địa TQ (optional)
            expected_production_date: Thời gian dự kiến sản xuất xong (optional)
            expected_delivery_date: Thời gian dự kiến ship đến nơi nhận (optional)
        
        Returns:
            SumPurchaseOrder instance
        """
        spo = SumPurchaseOrder.objects.get(id=spo_id)
        
        if tag:
            # Lấy PO có tag từ Sapo
            response = self.core_api.list_order_suppliers_raw(tags=tag, limit=250)
            order_suppliers = response.get('order_suppliers', [])
            po_ids = [os.get('id') for os in order_suppliers if os.get('id')]
        
        if not po_ids:
            raise ValueError("Must provide either po_ids or tag")
        
        # Tạo SPOPurchaseOrder cho mỗi PO
        for po_id in po_ids:
            SPOPurchaseOrder.objects.update_or_create(
                sum_purchase_order=spo,
                sapo_order_supplier_id=po_id,
                defaults={
                    'domestic_shipping_cn': domestic_shipping_cn or Decimal('0'),
                    'expected_production_date': expected_production_date,
                    'expected_delivery_date': expected_delivery_date,
                }
            )
        
        # Tính lại total_cbm của SPO
        self._recalculate_spo_cbm(spo)
        
        logger.info(f"[SumPurchaseOrderService] Added {len(po_ids)} PO(s) to SPO {spo.code}")
        return spo
    
    def calculate_cost_allocation(self, spo_id: int) -> Dict[str, Any]:
        """
        Tính toán phân bổ chi phí chung theo CBM (không lưu DB, chỉ tính toán).
        
        Args:
            spo_id: SumPurchaseOrder ID
        
        Returns:
            Dict với allocation details cho từng PO và line item
        """
        spo = SumPurchaseOrder.objects.get(id=spo_id)
        spo_po_ids = [spo_po.sapo_order_supplier_id for spo_po in spo.spo_purchase_orders.all()]
        
        if not spo_po_ids:
            return {
                'status': 'warning',
                'message': 'SPO chưa có PO nào',
                'total_cbm': 0,
                'allocations': []
            }
        
        # Lấy thông tin PO từ Sapo
        pos_data = self.spo_po_service.get_pos_for_spo(spo_po_ids)
        
        # Tính tổng CPM (sử dụng total_cpm hoặc total_cbm để tương thích)
        total_cpm = Decimal('0')
        for po in pos_data:
            total_cpm += po.get('total_cpm', po.get('total_cbm', Decimal('0')))
        
        if total_cpm == 0:
            return {
                'status': 'warning',
                'message': 'Không có dữ liệu CPM để phân bổ',
                'total_cpm': 0,
                'total_cbm': 0,  # Giữ để tương thích
                'allocations': []
            }
        
        allocations = []
        total_line_items = 0
        
        # Phân bổ chi phí chung cho mỗi PO và line items
        for po_data in pos_data:
            po_cpm = po_data.get('total_cpm', po_data.get('total_cbm', Decimal('0')))
            if po_cpm == 0:
                continue
            
            ratio_po = po_cpm / total_cpm
            line_items = po_data.get('line_items', [])
            
            # Tính tổng CPM của PO từ line items (sử dụng cpm hoặc cbm để tương thích)
            po_total_cpm = Decimal('0')
            for item in line_items:
                po_total_cpm += item.get('cpm', item.get('cbm', Decimal('0')))
            
            po_allocation = {
                'po_id': po_data.get('sapo_order_supplier_id'),
                'po_code': po_data.get('code'),
                'po_cpm': float(po_cpm),
                'po_cbm': float(po_cpm),  # Giữ để tương thích
                'ratio': float(ratio_po),
                'line_items': []
            }
            
            if po_total_cpm > 0:
                for item in line_items:
                    item_cpm = item.get('cpm', item.get('cbm', Decimal('0')))
                    if item_cpm == 0:
                        continue
                    
                    item_ratio = item_cpm / po_total_cpm
                    
                    # Tính chi phí phân bổ cho line item
                    item_allocation = {
                        'line_item_id': item.get('sapo_line_item_id'),
                        'sku': item.get('sku'),
                        'quantity': item.get('quantity'),
                        'cpm': float(item_cpm),
                        'cbm': float(item_cpm),  # Giữ để tương thích
                        'ratio': float(item_ratio),
                        'allocated_costs': {
                            'shipping_cn_vn': float(spo.shipping_cn_vn * ratio_po * item_ratio),
                            'customs_processing': float(spo.customs_processing_vn * ratio_po * item_ratio),
                            'other_costs': float(spo.other_costs * ratio_po * item_ratio),
                            'port_to_warehouse': float(spo.port_to_warehouse * ratio_po * item_ratio),
                            'loading_unloading': float(spo.loading_unloading * ratio_po * item_ratio),
                        }
                    }
                    po_allocation['line_items'].append(item_allocation)
                    total_line_items += 1
            
            allocations.append(po_allocation)
        
        logger.info(f"[SumPurchaseOrderService] Calculated cost allocation for {total_line_items} line items in SPO {spo.code}")
        
        return {
            'status': 'success',
            'message': f'Đã tính toán phân bổ chi phí cho {total_line_items} line items',
            'total_cpm': float(total_cpm),
            'total_cbm': float(total_cpm),  # Giữ để tương thích
            'allocations': allocations
        }
    
    def _initialize_timeline(self, spo: SumPurchaseOrder):
        """Khởi tạo timeline với planned dates"""
        now = timezone.now()
        
        # Timeline cơ bản (không bao gồm warehouse)
        timeline = [
            {'stage': 'created', 'planned_date': now.isoformat(), 'actual_date': None, 'note': ''},
            {'stage': 'supplier_confirmed', 'planned_date': None, 'actual_date': None, 'note': ''},
            {'stage': 'producing', 'planned_date': None, 'actual_date': None, 'note': ''},
            {'stage': 'waiting_packing', 'planned_date': None, 'actual_date': None, 'note': ''},
            {'stage': 'packed', 'planned_date': None, 'actual_date': None, 'note': ''},
            {'stage': 'departed_cn', 'planned_date': None, 'actual_date': None, 'note': ''},
            {'stage': 'arrived_vn', 'planned_date': None, 'actual_date': None, 'note': ''},
            {'stage': 'customs_cleared', 'planned_date': None, 'actual_date': None, 'note': ''},
        ]
        
        # Chỉ thêm warehouse stage phù hợp với destination_port
        if spo.destination_port == 'hcm':
            timeline.append({'stage': 'arrived_warehouse_hcm', 'planned_date': None, 'actual_date': None, 'note': ''})
        elif spo.destination_port == 'haiphong':
            timeline.append({'stage': 'arrived_warehouse_hn', 'planned_date': None, 'actual_date': None, 'note': ''})
        else:
            # Mặc định HCM nếu chưa có destination_port
            timeline.append({'stage': 'arrived_warehouse_hcm', 'planned_date': None, 'actual_date': None, 'note': ''})
        
        spo.timeline = timeline
        spo.save()
    
    def _recalculate_spo_cbm(self, spo: SumPurchaseOrder):
        """Tính lại total_cbm của SPO từ các PO (lấy từ Sapo)"""
        spo_po_ids = [spo_po.sapo_order_supplier_id for spo_po in spo.spo_purchase_orders.all()]
        total_cbm = self.spo_po_service.calculate_spo_total_cbm(spo_po_ids)
        spo.total_cbm = total_cbm
        spo.save()

# products/services/container_template_service.py
"""
Service quản lý Container Templates.
"""

from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
from decimal import Decimal

from django.utils import timezone
from core.sapo_client import SapoClient
from products.services.sapo_supplier_service import SapoSupplierService
from products.models import ContainerTemplate, ContainerTemplateSupplier

logger = logging.getLogger(__name__)


class ContainerTemplateService:
    """
    Service quản lý Container Templates.
    """
    
    def __init__(self, sapo_client: SapoClient):
        """
        Args:
            sapo_client: SapoClient instance
        """
        self.sapo_client = sapo_client
        self.supplier_service = SapoSupplierService(sapo_client)
    
    def create_template(self, data: Dict[str, Any]) -> ContainerTemplate:
        """
        Tạo container template mới.
        
        Args:
            data: Dict chứa các fields:
                - code: str (required)
                - name: str (optional)
                - container_type: str (default: "40ft")
                - volume_cbm: float (default: 65.0)
                - default_supplier_id: int (optional)
                - default_supplier_code: str (optional)
                - default_supplier_name: str (optional)
                - ship_time_avg_hn: int (default: 0)
                - ship_time_avg_hcm: int (default: 0)
                - departure_port: str (optional)
                - created_by: User (optional)
        
        Returns:
            ContainerTemplate instance
        """
        template = ContainerTemplate.objects.create(
            code=data.get('code'),
            name=data.get('name', ''),
            container_type=data.get('container_type', '40ft'),
            volume_cbm=data.get('volume_cbm', 65.0),
            default_supplier_id=data.get('default_supplier_id'),
            default_supplier_code=data.get('default_supplier_code', ''),
            default_supplier_name=data.get('default_supplier_name', ''),
            ship_time_avg_hn=data.get('ship_time_avg_hn', 0),
            ship_time_avg_hcm=data.get('ship_time_avg_hcm', 0),
            departure_port=data.get('departure_port', ''),
            created_by=data.get('created_by')
        )
        
        logger.info(f"[ContainerTemplateService] Created template: {template.code}")
        return template
    
    def update_template(self, template_id: int, data: Dict[str, Any]) -> ContainerTemplate:
        """
        Cập nhật container template.
        
        Args:
            template_id: ContainerTemplate ID
            data: Dict chứa các fields cần update
        
        Returns:
            ContainerTemplate instance
        """
        template = ContainerTemplate.objects.get(id=template_id)
        
        # Update các fields
        for key, value in data.items():
            if hasattr(template, key) and key != 'id':
                setattr(template, key, value)
        
        template.save()
        logger.info(f"[ContainerTemplateService] Updated template: {template.code}")
        return template
    
    def add_supplier(self, template_id: int, supplier_id: int) -> ContainerTemplateSupplier:
        """
        Thêm supplier vào container template.
        
        Args:
            template_id: ContainerTemplate ID
            supplier_id: Sapo supplier_id
        
        Returns:
            ContainerTemplateSupplier instance
        """
        template = ContainerTemplate.objects.get(id=template_id)
        
        # Lấy thông tin supplier từ Sapo
        try:
            supplier_response = self.sapo_client.core.get_supplier_raw(supplier_id)
            supplier_data = supplier_response.get('supplier')
            if not supplier_data:
                raise ValueError(f"Supplier {supplier_id} not found in Sapo")
            
            supplier_code = supplier_data.get('code', '')
            supplier_name = supplier_data.get('name', '')
            
            # Lấy logo từ supplier addresses (nếu có)
            # Logo thường lưu trong first_name field của address đầu tiên
            logo_path = ""
            addresses = supplier_data.get('addresses', [])
            if addresses and len(addresses) > 0:
                first_address = addresses[0]
                # Logo thường lưu trong first_name field
                logo_path = first_address.get('first_name', '') or ""
        except Exception as e:
            logger.error(f"[ContainerTemplateService] Error getting supplier {supplier_id}: {e}", exc_info=True)
            raise ValueError(f"Error getting supplier {supplier_id} from Sapo: {e}")
        
        # Tạo hoặc update relationship
        template_supplier, created = ContainerTemplateSupplier.objects.update_or_create(
            container_template=template,
            supplier_id=supplier_id,
            defaults={
                'supplier_code': supplier_code,
                'supplier_name': supplier_name,
                'supplier_logo_path': logo_path
            }
        )
        
        logger.info(f"[ContainerTemplateService] {'Added' if created else 'Updated'} supplier {supplier_code} to template {template.code}")
        return template_supplier
    
    def remove_supplier(self, template_id: int, supplier_id: int):
        """
        Xóa supplier khỏi container template.
        
        Args:
            template_id: ContainerTemplate ID
            supplier_id: Sapo supplier_id
        """
        ContainerTemplateSupplier.objects.filter(
            container_template_id=template_id,
            supplier_id=supplier_id
        ).delete()
        
        logger.info(f"[ContainerTemplateService] Removed supplier {supplier_id} from template {template_id}")
    
    def get_template_with_suppliers(self, template_id: int) -> Dict[str, Any]:
        """
        Lấy template kèm danh sách suppliers (với logo).
        
        Args:
            template_id: ContainerTemplate ID
        
        Returns:
            Dict với template data và suppliers list
        """
        template = ContainerTemplate.objects.get(id=template_id)
        suppliers = template.suppliers.all().order_by('-priority', 'supplier_name')
        
        return {
            'template': template,
            'suppliers': [
                {
                    'id': s.supplier_id,
                    'code': s.supplier_code,
                    'name': s.supplier_name,
                    'logo_path': s.supplier_logo_path,
                    'priority': s.priority
                }
                for s in suppliers
            ]
        }
    
    def calculate_avg_import_cycle(self, template_id: int) -> Optional[int]:
        """
        Tính chu kỳ nhập hàng trung bình dựa trên lịch sử SPO.
        
        Args:
            template_id: ContainerTemplate ID
        
        Returns:
            Số ngày trung bình giữa các lần nhập, hoặc None nếu chưa có đủ dữ liệu
        """
        from products.models import SumPurchaseOrder
        from django.utils import timezone
        from datetime import timedelta
        
        template = ContainerTemplate.objects.get(id=template_id)
        
        # Lấy các SPO đã completed của template này, sắp xếp theo created_at
        spos = SumPurchaseOrder.objects.filter(
            container_template=template,
            status='completed'
        ).order_by('created_at')
        
        if len(spos) < 2:
            # Cần ít nhất 2 SPO để tính chu kỳ
            return None
        
        # Tính khoảng cách giữa các SPO
        intervals = []
        for i in range(1, len(spos)):
            prev_date = spos[i-1].created_at
            curr_date = spos[i].created_at
            interval_days = (curr_date - prev_date).days
            intervals.append(interval_days)
        
        if not intervals:
            return None
        
        # Tính trung bình
        avg_cycle = sum(intervals) / len(intervals)
        
        # Cập nhật vào template
        template.avg_import_cycle_days = int(avg_cycle)
        template.save()
        
        logger.info(f"[ContainerTemplateService] Calculated avg import cycle for {template.code}: {int(avg_cycle)} days")
        return int(avg_cycle)
    
    def resync_template_stats(self, template_id: int) -> Dict[str, Any]:
        """
        Tính toán lại avg_total_amount và avg_import_cycle_days từ các SPO completed.
        
        Args:
            template_id: ContainerTemplate ID
            
        Returns:
            Dict với keys: avg_total_amount, avg_import_cycle_days, spo_count
        """
        from products.models import SumPurchaseOrder
        from products.services.spo_po_service import SPOPOService
        
        template = ContainerTemplate.objects.get(id=template_id)
        
        # Lấy các SPO completed của template này
        completed_spos = SumPurchaseOrder.objects.filter(
            container_template=template,
            status='completed'
        ).order_by('created_at')
        
        if not completed_spos.exists():
            return {
                'status': 'no_data',
                'message': 'Chưa có SPO completed để tính toán',
                'avg_total_amount': None,
                'avg_import_cycle_days': None,
                'spo_count': 0
            }
        
        # 1. Tính avg_total_amount từ các SPO completed
        spo_po_service = SPOPOService(self.sapo_client)
        total_amounts = []
        
        for spo in completed_spos:
            po_ids = [spo_po.purchase_order.sapo_order_supplier_id for spo_po in spo.spo_purchase_orders.select_related('purchase_order').all() if spo_po.purchase_order]
            if po_ids:
                try:
                    spo_total = Decimal('0')
                    for po_id in po_ids:
                        po_data = spo_po_service.get_po_from_sapo(po_id)
                        spo_total += Decimal(str(po_data.get('total_amount', 0)))
                    total_amounts.append(float(spo_total))
                except Exception as e:
                    logger.warning(f"Error calculating total for SPO {spo.id}: {e}")
        
        avg_total_amount = Decimal('0')
        if total_amounts:
            avg_total_amount = Decimal(str(sum(total_amounts) / len(total_amounts)))
        
        # 2. Tính avg_import_cycle_days: từ created_at đến completed_at (từ timeline)
        cycle_days_list = []
        
        for spo in completed_spos:
            # Tìm completed_at từ timeline
            completed_at = None
            for stage in spo.timeline:
                if stage.get('stage') == 'completed' and stage.get('actual_date'):
                    try:
                        date_str = stage['actual_date']
                        # Xử lý format ISO datetime
                        if 'T' in date_str:
                            completed_at = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        else:
                            # Nếu chỉ có date, thêm time
                            completed_at = datetime.fromisoformat(f"{date_str}T00:00:00")
                        
                        # Đảm bảo có timezone
                        if completed_at.tzinfo is None:
                            completed_at = timezone.make_aware(completed_at)
                        break
                    except Exception as e:
                        logger.warning(f"Error parsing completed_at for SPO {spo.id}: {e}")
            
            # Nếu không có trong timeline, dùng updated_at làm fallback
            if not completed_at:
                completed_at = spo.updated_at
            
            # Tính số ngày từ created_at đến completed_at
            if spo.created_at and completed_at:
                days = (completed_at - spo.created_at).days
                if days > 0:  # Chỉ lấy số ngày dương
                    cycle_days_list.append(days)
        
        avg_import_cycle_days = None
        if cycle_days_list:
            avg_import_cycle_days = int(sum(cycle_days_list) / len(cycle_days_list))
        
        # 3. Lưu vào database
        template.avg_total_amount = avg_total_amount
        if avg_import_cycle_days:
            template.avg_import_cycle_days = avg_import_cycle_days
        template.save()
        
        logger.info(f"[ContainerTemplateService] Resynced stats for {template.code}: "
                   f"avg_total={avg_total_amount}, avg_cycle={avg_import_cycle_days} days, "
                   f"from {len(completed_spos)} completed SPOs")
        
        return {
            'status': 'success',
            'message': f'Đã tính toán lại từ {len(completed_spos)} SPO completed',
            'avg_total_amount': float(avg_total_amount),
            'avg_import_cycle_days': avg_import_cycle_days,
            'spo_count': len(completed_spos)
        }

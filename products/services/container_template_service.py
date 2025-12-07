# products/services/container_template_service.py
"""
Service quản lý Container Templates.
"""

from typing import Dict, Any, List, Optional
import logging

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

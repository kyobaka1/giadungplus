# products/services/sapo_supplier_service.py
"""
Service layer for interacting with Sapo Suppliers API.
Handles fetching and parsing suppliers data.
"""

from typing import Optional, List, Dict, Any
import logging
import json

from core.sapo_client import SapoClient
from products.services.dto import SupplierDTO, SupplierAddressDTO

logger = logging.getLogger(__name__)


class SapoSupplierService:
    """
    Service để giao tiếp với Sapo Suppliers API.
    
    Chức năng chính:
    - Fetch suppliers từ Sapo
    - Parse và transform supplier data
    - Đếm số sản phẩm theo supplier
    """
    
    def __init__(self, sapo_client: SapoClient):
        """
        Initialize service với SapoClient.
        
        Args:
            sapo_client: Instance của SapoClient (initialized with tokens)
        """
        self.sapo_client = sapo_client
        self.core_api = sapo_client.core
    
    def list_suppliers(self, page: int = 1, limit: int = 250, status: Optional[str] = None) -> List[SupplierDTO]:
        """
        Lấy danh sách suppliers từ Sapo.
        
        Args:
            page: Số trang (bắt đầu từ 1)
            limit: Số lượng mỗi trang (tối đa 250)
            status: Lọc theo status ("active", "disable", None = tất cả)
            
        Returns:
            List[SupplierDTO] - Danh sách suppliers đã được parse
        """
        try:
            filters = {
                "page": page,
                "limit": limit,
            }
            
            # Fetch suppliers from Sapo
            response = self.core_api.list_suppliers_raw(**filters)
            suppliers_data = response.get('suppliers', [])
            
            # Filter by status nếu có
            if status:
                suppliers_data = [s for s in suppliers_data if s.get('status') == status]
            
            # Parse suppliers to DTOs
            suppliers = []
            for supplier_data in suppliers_data:
                try:
                    # Parse addresses
                    addresses = []
                    for addr_data in supplier_data.get('addresses', []):
                        addresses.append(SupplierAddressDTO.from_dict(addr_data))
                    
                    # Create supplier DTO
                    supplier_dict = supplier_data.copy()
                    supplier_dict['addresses'] = addresses
                    supplier = SupplierDTO.from_dict(supplier_dict)
                    suppliers.append(supplier)
                except Exception as e:
                    logger.warning(f"Failed to parse supplier {supplier_data.get('id')}: {e}")
                    continue
            
            return suppliers
            
        except Exception as e:
            logger.error(f"Error listing suppliers: {e}", exc_info=True)
            return []
    
    def get_all_suppliers(self, status: Optional[str] = "active") -> List[SupplierDTO]:
        """
        Lấy TẤT CẢ suppliers (loop qua nhiều pages).
        
        Args:
            status: Lọc theo status ("active", "disable", None = tất cả)
            
        Returns:
            List[SupplierDTO] - Danh sách tất cả suppliers
        """
        all_suppliers = []
        page = 1
        limit = 250  # Max limit theo Sapo API
        
        while True:
            suppliers = self.list_suppliers(page=page, limit=limit, status=status)
            
            if not suppliers:
                break
            
            all_suppliers.extend(suppliers)
            
            # Nếu số lượng < limit thì đã hết
            if len(suppliers) < limit:
                break
            
            page += 1
            
            # Safety limit để tránh vòng lặp vô hạn
            if page > 100:
                logger.warning("Reached max pages limit (100) in get_all_suppliers")
                break
        
        return all_suppliers
    
    def count_products_by_supplier(self, supplier_name: str) -> int:
        """
        Đếm số sản phẩm thuộc nhà cung cấp (dựa vào brand name).
        
        Args:
            supplier_name: Tên nhà cung cấp (code hoặc name)
            
        Returns:
            int - Số lượng sản phẩm
        """
        try:
            from products.services.sapo_product_service import SapoProductService
            product_service = SapoProductService(self.sapo_client)
            
            # Lấy tất cả products
            all_products = []
            page = 1
            limit = 250
            max_pages = 50  # Giới hạn để tránh quá tải
            
            while page <= max_pages:
                products = product_service.list_products(page=page, limit=limit, status="active")
                if not products:
                    break
                
                # Lọc products theo brand name (supplier name)
                for product in products:
                    if product.brand and product.brand.upper() == supplier_name.upper():
                        all_products.append(product)
                
                if len(products) < limit:
                    break
                page += 1
            
            return len(all_products)
            
        except Exception as e:
            logger.error(f"Error counting products for supplier {supplier_name}: {e}", exc_info=True)
            return 0
    
    def enrich_suppliers_with_product_count(self, suppliers: List[SupplierDTO]) -> List[SupplierDTO]:
        """
        Bổ sung số lượng sản phẩm cho mỗi supplier.
        
        Args:
            suppliers: Danh sách suppliers cần enrich
            
        Returns:
            List[SupplierDTO] - Suppliers đã được bổ sung product_count
        """
        try:
            from products.services.sapo_product_service import SapoProductService
            product_service = SapoProductService(self.sapo_client)
            
            # Lấy tất cả products một lần
            all_products = []
            page = 1
            limit = 250
            max_pages = 50
            
            while page <= max_pages:
                products = product_service.list_products(page=page, limit=limit, status="active")
                if not products:
                    break
                all_products.extend(products)
                if len(products) < limit:
                    break
                page += 1
            
            # Tạo map brand -> count
            brand_count_map = {}
            for product in all_products:
                if product.brand:
                    brand_upper = product.brand.upper()
                    brand_count_map[brand_upper] = brand_count_map.get(brand_upper, 0) + 1
            
            # Gán product_count cho mỗi supplier
            for supplier in suppliers:
                supplier_code_upper = supplier.code.upper()
                supplier_name_upper = supplier.name.upper()
                # Tìm theo code hoặc name
                count = brand_count_map.get(supplier_code_upper, 0)
                if count == 0:
                    count = brand_count_map.get(supplier_name_upper, 0)
                supplier.product_count = count
            
            return suppliers
            
        except Exception as e:
            logger.error(f"Error enriching suppliers with product count: {e}", exc_info=True)
            return suppliers

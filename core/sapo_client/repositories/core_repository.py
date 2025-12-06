# core/sapo_client/repositories/core_repository.py
"""
Repository cho Sapo Core API (https://sisapsan.mysapogo.com/admin).
Handles orders, customers, products, variants, shipments.
"""

from typing import Dict, Any, List, Optional
import logging

from core.base.repository import BaseRepository

logger = logging.getLogger(__name__)


class SapoCoreRepository(BaseRepository):
    """
    Repository cho Sapo Core API.
    Base URL: https://sisapsan.mysapogo.com/admin
    
    Endpoints:
    - /orders.json - List orders
    - /orders/{id}.json - Get order detail
    - /customers/{id}.json - Get/Update customer
    - /products/{id}.json - Get product
    - /variants/{id}.json - Get variant
    - /shipments.json - List shipments
    """
    
    # ==================== ORDERS ====================
    
    def list_orders_raw(self, **filters) -> Dict[str, Any]:
        """
        Lấy danh sách orders từ Sapo Core.
        
        Args:
            **filters: Query parameters
                - page: int
                - limit: int (max 100)
                - location_id: int
                - status: str (finalized, completed, cancelled)
                - created_on_min: str (ISO datetime)
                - created_on_max: str (ISO datetime)
                - etc.
        
        Returns:
            {
                "orders": [...],
                "metadata": {...}
            }
        """
        logger.debug(f"[SapoCoreRepo] list_orders with filters: {filters}")
        return self.get("orders.json", params=filters)
    
    def get_order_raw(self, order_id: int) -> Dict[str, Any]:
        """
        Lấy chi tiết 1 order.
        
        Args:
            order_id: Sapo order ID
            
        Returns:
            {
                "order": {...}
            }
        """
        import time
        api_start = time.time()
        url = f"orders/{order_id}.json"
        logger.debug(f"[SapoCoreRepo] get_order: {order_id} -> GET {self._build_url(url)}")
        result = self.get(url)
        api_time = time.time() - api_start
        logger.info(f"[PERF] API GET {url}: {api_time:.2f}s")
        return result
    
    def get_order_by_reference_number(self, reference_number: str) -> Optional[Dict[str, Any]]:
        """
        Tìm order theo reference_number (mã đơn sàn TMĐT).
        
        Args:
            reference_number: Mã đơn sàn (vd: 25112099T2CASS)
            
        Returns:
            Order dict hoặc None nếu không tìm thấy
        """
        logger.debug(f"[SapoCoreRepo] get_order_by_reference: {reference_number}")
        result = self.get("orders.json", params={
            "query": reference_number,
            "limit": 1,
            "page": 1
        })
        
        orders = result.get("orders", [])
        return orders[0] if orders else None
    
    # ==================== CUSTOMERS ====================
    
    def get_customer_raw(self, customer_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin khách hàng.
        
        Args:
            customer_id: Sapo customer ID
            
        Returns:
            {
                "customer": {...}
            }
        """
        logger.debug(f"[SapoCoreRepo] get_customer: {customer_id}")
        return self.get(f"customers/{customer_id}.json")
    
    def update_customer(self, customer_id: int, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update thông tin khách hàng.
        
        Args:
            customer_id: Sapo customer ID
            customer_data: Dict chứa fields cần update (name, phone, addresses...)
            
        Returns:
            {
                "customer": {...}
            }
        """
        logger.info(f"[SapoCoreRepo] update_customer: {customer_id}")
        return self.put(f"customers/{customer_id}.json", json={
            "customer": customer_data
        })
    
    def update_customer_address(
        self, 
        customer_id: int, 
        address_id: int, 
        address_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update địa chỉ của khách hàng.
        
        Args:
            customer_id: Sapo customer ID
            address_id: Sapo address ID
            address_data: Dict chứa fields cần update (address1, city, district, ward, etc.)
            
        Returns:
            {
                "address": {...}
            }
            
        Note: 
            Endpoint: PUT /admin/customers/{customer_id}/addresses/{address_id}.json
            Verified và tested thành công.
        """
        logger.info(f"[SapoCoreRepo] update_customer_address: customer={customer_id}, address={address_id}")
        return self.put(f"customers/{customer_id}/addresses/{address_id}.json", json={
            "address": address_data
        })
    
    def get_variant_raw(self, variant_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin variant.
        
        Args:
            variant_id: Sapo variant ID
            
        Returns:
            {
                "variant": {...}
            }
        """
        import time
        api_start = time.time()
        url = f"variants/{variant_id}.json"
        logger.debug(f"[SapoCoreRepo] get_variant: {variant_id} -> GET {self._build_url(url)}")
        result = self.get(url)
        api_time = time.time() - api_start
        logger.info(f"[PERF] API GET {url}: {api_time:.2f}s")
        
        # Increment counter nếu có trong session/context
        # Sử dụng thread-local storage hoặc global counter
        import threading
        if hasattr(threading.current_thread(), 'variant_api_counter'):
            threading.current_thread().variant_api_counter += 1
        
        return result
    
    def list_variants_raw(self, **filters) -> Dict[str, Any]:
        """
        Lấy danh sách variants từ Sapo Core.
        
        Args:
            **filters: Query parameters
                - page: int
                - limit: int (max 250)
                - brand_ids: int hoặc str (comma-separated) - Filter theo brand IDs
                - status: str (active, inactive)
                - composite: bool
                - packsize: bool
                - etc.
        
        Returns:
            {
                "variants": [...],
                "metadata": {...}
            }
            
        Example:
            GET /admin/variants.json?page=1&limit=100&brand_ids=2101155
        """
        logger.debug(f"[SapoCoreRepo] list_variants with filters: {filters}")
        return self.get("variants.json", params=filters)
    
    def list_brands_raw(self, **filters) -> Dict[str, Any]:
        """
        Lấy danh sách brands từ Sapo Core.
        
        Args:
            **filters: Query parameters
                - page: int
                - limit: int
                - query: str - Tìm kiếm theo tên
                - name: str - Filter theo tên chính xác
                
        Returns:
            {
                "brands": [...]
            }
            
        Example:
            GET /admin/brands.json?page=1&limit=250
        """
        logger.debug(f"[SapoCoreRepo] list_brands with filters: {filters}")
        return self.get("brands.json", params=filters)
    
    def list_brands_search_raw(self, **filters) -> Dict[str, Any]:
        """
        Lấy danh sách brands từ Sapo Core search endpoint.
        
        Args:
            **filters: Query parameters
                - page: int
                - limit: int (max 220)
                
        Returns:
            {
                "brands": [...]
            }
            
        Example:
            GET /admin/brands/search.json?page=1&limit=220
        """
        logger.debug(f"[SapoCoreRepo] list_brands_search with filters: {filters}")
        return self.get("brands/search.json", params=filters)
    
    # ==================== PRODUCTS ====================
    
    def get_product_raw(self, product_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin product đầy đủ (bao gồm variants).
        
        Args:
            product_id: Sapo product ID
            
        Returns:
            {
                "product": {...}
            }
        """
        logger.debug(f"[SapoCoreRepo] get_product: {product_id}")
        return self.get(f"products/{product_id}.json")
    
    def update_product(self, product_id: int, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update thông tin product (dùng để update description với GDP_META).
        
        Args:
            product_id: Sapo product ID
            product_data: Dict chứa fields cần update (description, tags, etc.)
            
        Returns:
            {
                "product": {...}
            }
        """
        logger.info(f"[SapoCoreRepo] update_product: {product_id}")
        return self.put(f"products/{product_id}.json", json={
            "product": product_data
        })
    
    def list_products_raw(self, **filters) -> Dict[str, Any]:
        """
        Lấy danh sách products.
        
        Args:
            **filters: page, limit, status, etc.
            
        Returns:
            {
                "products": [...],
                "metadata": {...}
            }
        """
        logger.debug(f"[SapoCoreRepo] list_products with filters: {filters}")
        return self.get("products.json", params=filters)
    
    def list_order_sources_raw(self, **filters) -> Dict[str, Any]:
        """
        Lấy danh sách order sources (nguồn đơn hàng).
        
        Args:
            **filters: page, limit, query, etc.
            
        Returns:
            {
                "order_sources": [...],
                "metadata": {...}
            }
            
        Example:
            GET /admin/order_sources.json?page=1&limit=250
        """
        logger.debug(f"[SapoCoreRepo] list_order_sources with filters: {filters}")
        return self.get("order_sources.json", params=filters)
    
    def get_order_source_raw(self, source_id: int) -> Dict[str, Any]:
        """
        Lấy chi tiết 1 order source.
        
        Args:
            source_id: Order source ID
            
        Returns:
            {
                "order_source": {...}
            }
        """
        logger.debug(f"[SapoCoreRepo] get_order_source: {source_id}")
        return self.get(f"order_sources/{source_id}.json")
    
    def get_delivery_service_provider_raw(self, provider_id: int) -> Dict[str, Any]:
        """
        Lấy chi tiết 1 delivery service provider (đơn vị vận chuyển).
        
        Args:
            provider_id: Delivery service provider ID
            
        Returns:
            {
                "delivery_service_provider": {...}
            }
            
        Example:
            GET /admin/delivery_service_providers/373257.json
        """
        logger.debug(f"[SapoCoreRepo] get_delivery_service_provider: {provider_id}")
        return self.get(f"delivery_service_providers/{provider_id}.json")
    
    def list_delivery_service_providers_raw(self, **filters) -> Dict[str, Any]:
        """
        Lấy danh sách delivery service providers.
        
        Args:
            **filters: page, limit, status, etc.
            
        Returns:
            {
                "delivery_service_providers": [...],
                "metadata": {...}
            }
        """
        logger.debug(f"[SapoCoreRepo] list_delivery_service_providers with filters: {filters}")
        return self.get("delivery_service_providers.json", params=filters)
    
    # ==================== SHIPMENTS ====================
    
    def list_shipments_raw(self, **filters) -> Dict[str, Any]:
        """
        Lấy danh sách shipments (vận đơn).
        
        Args:
            **filters:
                - packed_on_min, packed_on_max
                - shipped_on_min, shipped_on_max
                - composite_fulfillment_statuses
                - etc.
                
        Returns:
            {
                "fulfillments": [...],
                "metadata": {...}
            }
        """
        logger.debug(f"[SapoCoreRepo] list_shipments with filters: {filters}")
        return self.get("shipments.json", params=filters)
    
    def get_shipment_raw(self, fulfillment_id: int) -> Dict[str, Any]:
        """
        Lấy chi tiết 1 shipment.
        
        Args:
            fulfillment_id: Sapo fulfillment ID
            
        Returns:
            {
                "fulfillment": {...}
            }
        """
        logger.debug(f"[SapoCoreRepo] get_shipment: {fulfillment_id}")
        return self.get(f"shipments/{fulfillment_id}.json")

    def update_shipment(self, shipment_id: int, note: str) -> Dict[str, Any]:
        """
        Update ghi chú (note) của shipment.
        
        Args:
            shipment_id: Sapo shipment ID (không phải fulfillment ID)
            note: Nội dung ghi chú mới
            
        Returns:
            Updated shipment dict
        """
        logger.info(f"[SapoCoreRepo] update_shipment: {shipment_id}")
        return self.post("shipments/update", data={
            "id": shipment_id,
            "note": note
        })

    def list_fulfillments_raw(self, **filters) -> Dict[str, Any]:
        """
        Lấy danh sách fulfillments.
        
        Args:
            **filters: query, page, limit, etc.
            
        Returns:
            {
                "fulfillments": [...]
            }
        """
        logger.debug(f"[SapoCoreRepo] list_fulfillments with filters: {filters}")
        return self.get("fulfillments.json", params=filters)

    def update_fulfillment(self, fulfillment_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update fulfillment (PUT /admin/fulfillments/{id}.json).
        
        Args:
            fulfillment_id: ID của fulfillment
            data: Dict dữ liệu cần update (vd: {"note": "..."})
            
        Returns:
            Updated fulfillment dict
        """
        logger.info(f"[SapoCoreRepo] update_fulfillment: {fulfillment_id}")
        return self.put(f"fulfillments/{fulfillment_id}.json", json={
            "fulfillment": data
        })
    
    # ==================== SUPPLIERS ====================
    
    def list_suppliers_raw(self, **filters) -> Dict[str, Any]:
        """
        Lấy danh sách suppliers (nhà cung cấp).
        
        Args:
            **filters: Query parameters
                - page: int
                - limit: int (max 250)
                
        Returns:
            {
                "suppliers": [...],
                "metadata": {...}
            }
            
        Example:
            GET /admin/suppliers.json?page=1&limit=250
        """
        logger.debug(f"[SapoCoreRepo] list_suppliers with filters: {filters}")
        return self.get("suppliers.json", params=filters)
    
    def get_supplier_raw(self, supplier_id: int) -> Dict[str, Any]:
        """
        Lấy chi tiết 1 supplier.
        
        Args:
            supplier_id: Sapo supplier ID
            
        Returns:
            {
                "supplier": {...}
            }
        """
        logger.debug(f"[SapoCoreRepo] get_supplier: {supplier_id}")
        return self.get(f"suppliers/{supplier_id}.json")
    
    def update_supplier_address(
        self, 
        supplier_id: int, 
        address_id: int, 
        address_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update địa chỉ của supplier.
        
        Args:
            supplier_id: Sapo supplier ID
            address_id: Sapo address ID
            address_data: Dict chứa fields cần update (address1, first_name, label, etc.)
            
        Returns:
            {
                "address": {...}
            }
            
        Note: 
            Endpoint: PUT /admin/suppliers/{supplier_id}/addresses/{address_id}.json
        """
        logger.info(f"[SapoCoreRepo] update_supplier_address: supplier={supplier_id}, address={address_id}")
        return self.put(f"suppliers/{supplier_id}/addresses/{address_id}.json", json={
            "address": address_data
        })

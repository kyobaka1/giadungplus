# products/services/spo_po_service.py
"""
Service để lấy và tính toán thông tin PO từ Sapo API.
PO không lưu trong DB, chỉ lấy từ Sapo khi cần.
"""

from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import date
import logging

from django.utils import timezone
from core.sapo_client import SapoClient
from products.services.metadata_helper import extract_gdp_metadata
from products.services.dto import VariantMetadataDTO, BoxInfoDTO, ProductMetadataDTO
from products.services.sapo_product_service import SapoProductService

logger = logging.getLogger(__name__)


class SPOPOService:
    """
    Service để lấy và tính toán thông tin PO từ Sapo.
    """
    
    def __init__(self, sapo_client: SapoClient, debug: bool = False):
        self.sapo_client = sapo_client
        self.core_api = sapo_client.core
        self.product_service = SapoProductService(sapo_client)
        self.debug = debug
    
    def debug_print(self, *args, **kwargs):
        """Print debug info nếu debug = True"""
        if self.debug:
            print(f"[DEBUG SPOPOService]", *args, **kwargs)
    
    def get_po_from_sapo(self, sapo_order_supplier_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin PO từ Sapo API.
        
        Args:
            sapo_order_supplier_id: Sapo order_supplier ID
            
        Returns:
            Dict chứa thông tin PO:
            {
                'sapo_order_supplier_id': int,
                'code': str,
                'supplier_id': int,
                'supplier_code': str,
                'supplier_name': str,
                'status': str,
                'tags': List[str],
                'total_amount': Decimal,
                'total_quantity': int,
                'line_items': List[Dict],
                'total_cpm': Decimal  # Tính từ BoxInfo (m³)
            }
        """
        try:
            # GET /admin/order_suppliers/{id}.json
            response = self.core_api.get_order_supplier_raw(sapo_order_supplier_id)
            order_supplier_data = response.get('order_supplier', {})
            
            if not order_supplier_data:
                raise ValueError(f"Order supplier {sapo_order_supplier_id} not found in Sapo")
            
            supplier_data = order_supplier_data.get('supplier_data', {})
            line_items_data = order_supplier_data.get('line_items', [])
            
            self.debug_print(f"=== Processing PO {sapo_order_supplier_id} ===")
            self.debug_print(f"Total line items: {len(line_items_data)}")
            
            # Bước 1: Thu thập tất cả product_ids duy nhất từ line items
            product_ids = set()
            variant_to_product_map = {}  # variant_id -> product_id
            for item_data in line_items_data:
                product_id = item_data.get('product_id')
                variant_id = item_data.get('variant_id')
                sku = item_data.get('sku', '')
                if product_id:
                    product_ids.add(product_id)
                    variant_to_product_map[variant_id] = product_id
                    self.debug_print(f"  Line item: variant_id={variant_id}, product_id={product_id}, sku={sku}")
            
            self.debug_print(f"Unique product_ids collected: {len(product_ids)} - {list(product_ids)}")
            
            # Bước 2: Load tất cả products một lần (dùng SapoProductService để có metadata đã parse)
            products_metadata_map = {}  # product_id -> ProductMetadataDTO
            for product_id in product_ids:
                try:
                    self.debug_print(f"Loading product {product_id}...")
                    # Dùng SapoProductService.get_product() thay vì get_product_raw() để có metadata đã parse
                    product_dto = self.product_service.get_product(product_id)
                    if product_dto:
                        self.debug_print(f"  Product {product_id} DTO loaded: name={product_dto.name}")
                        self.debug_print(f"  Description length: {len(product_dto.description) if product_dto.description else 0}")
                        
                        product_metadata = product_dto.gdp_metadata
                        if product_metadata:
                            products_metadata_map[product_id] = product_metadata
                            self.debug_print(f"  Product {product_id} metadata loaded: {len(product_metadata.variants)} variants")
                            # Debug: in ra variant IDs trong metadata
                            variant_ids_in_meta = [v.id for v in product_metadata.variants]
                            self.debug_print(f"  Variant IDs in metadata: {variant_ids_in_meta[:10]}..." if len(variant_ids_in_meta) > 10 else f"  Variant IDs in metadata: {variant_ids_in_meta}")
                        else:
                            self.debug_print(f"  Product {product_id} gdp_metadata is None")
                            # Thử fallback: lấy description trực tiếp
                            if product_dto.description:
                                self.debug_print(f"  Trying to extract from description (length: {len(product_dto.description)})")
                                # Kiểm tra xem có chứa GDP_META không
                                if '[GDP_META]' in product_dto.description:
                                    self.debug_print(f"  Found [GDP_META] tag in description")
                                else:
                                    self.debug_print(f"  No [GDP_META] tag found in description")
                                product_metadata, _ = extract_gdp_metadata(product_dto.description)
                                if product_metadata:
                                    products_metadata_map[product_id] = product_metadata
                                    self.debug_print(f"  Extracted metadata from description: {len(product_metadata.variants)} variants")
                                else:
                                    self.debug_print(f"  Failed to extract metadata from description")
                            else:
                                self.debug_print(f"  Product {product_id} description is None or empty")
                    else:
                        self.debug_print(f"  Product {product_id} DTO is None")
                except Exception as e:
                    logger.warning(f"[SPOPOService] Error loading product {product_id}: {e}")
                    self.debug_print(f"  ERROR loading product {product_id}: {e}")
                    import traceback
                    self.debug_print(f"  Traceback: {traceback.format_exc()}")
            
            self.debug_print(f"Products metadata loaded: {len(products_metadata_map)}/{len(product_ids)}")
            
            # Bước 3: Tính CPM và product_amount_cny cho từng line item
            total_cpm = Decimal('0')
            total_product_amount_cny = Decimal('0')
            processed_line_items = []
            
            self.debug_print(f"=== Calculating CPM and product_amount_cny for {len(line_items_data)} line items ===")
            for item_data in line_items_data:
                variant_id = item_data.get('variant_id')
                quantity = item_data.get('quantity', 0)
                product_id = variant_to_product_map.get(variant_id)
                sku = item_data.get('sku', '')
                
                self.debug_print(f"  Processing: variant_id={variant_id}, product_id={product_id}, sku={sku}, quantity={quantity}")
                
                # Tính CPM từ product metadata (đã load sẵn)
                product_metadata = products_metadata_map.get(product_id) if product_id else None
                item_cpm = self._calculate_item_cpm(
                    variant_id, 
                    quantity, 
                    product_id, 
                    product_metadata
                )
                total_cpm += item_cpm
                self.debug_print(f"    Result CPM: {item_cpm}")
                
                # Tính product_amount_cny từ price_tq trong metadata
                item_price_cny = self._get_variant_price_cny(
                    variant_id,
                    product_id,
                    product_metadata
                )
                item_amount_cny = Decimal(str(item_price_cny)) * Decimal(str(quantity))
                total_product_amount_cny += item_amount_cny
                self.debug_print(f"    Price CNY: {item_price_cny}, Amount CNY: {item_amount_cny}")
                
                # Lấy full_box từ box_info để tính số kiện hàng
                full_box = 1  # Mặc định 1 item = 1 package
                if product_metadata:
                    variant_meta = None
                    for v_meta in product_metadata.variants:
                        if v_meta.id == variant_id:
                            variant_meta = v_meta
                            break
                    if variant_meta and variant_meta.box_info and variant_meta.box_info.full_box:
                        full_box = variant_meta.box_info.full_box
                
                processed_line_items.append({
                    'sapo_line_item_id': item_data.get('id'),
                    'variant_id': variant_id,
                    'product_id': product_id,
                    'sku': item_data.get('sku', ''),
                    'product_name': item_data.get('product_name', ''),
                    'variant_name': item_data.get('variant_name', ''),
                    'quantity': quantity,
                    'price': Decimal(str(item_data.get('price', 0))),
                    'price_cny': item_price_cny,  # Giá nhập CNY từ metadata
                    'amount_cny': item_amount_cny,  # Tiền hàng = price_cny * quantity
                    'total_amount': Decimal(str(item_data.get('total_line_amount_after_tax', 0))),
                    'cpm': item_cpm,  # CPM tính theo công thức mới
                    'cbm': item_cpm,  # Giữ cbm để tương thích với code cũ
                    'full_box': full_box,  # Số cái/thùng để tính số kiện hàng
                    'unit': item_data.get('unit', ''),
                    'variant_options': item_data.get('variant_options', ''),
                })
            
            self.debug_print(f"=== Final result: total_cpm={total_cpm}, total_product_amount_cny={total_product_amount_cny} ===")
            
            return {
                'sapo_order_supplier_id': sapo_order_supplier_id,
                'code': order_supplier_data.get('code', ''),
                'supplier_id': order_supplier_data.get('supplier_id'),
                'supplier_code': supplier_data.get('code', ''),
                'supplier_name': supplier_data.get('name', ''),
                'status': order_supplier_data.get('status', ''),
                'tags': order_supplier_data.get('tags', []),
                'total_amount': Decimal(str(order_supplier_data.get('total_price', 0))),
                'total_quantity': order_supplier_data.get('total_quantity', 0),
                'product_amount_cny': total_product_amount_cny,  # Tổng tiền hàng (CNY) từ price_tq
                'line_items': processed_line_items,
                'total_cpm': total_cpm,  # CPM tính theo công thức mới
                'total_cbm': total_cpm,  # Giữ total_cbm để tương thích với code cũ
            }
            
        except Exception as e:
            logger.error(f"[SPOPOService] Error getting PO {sapo_order_supplier_id}: {e}", exc_info=True)
            raise
    
    def _calculate_item_cpm(
        self, 
        variant_id: int, 
        quantity: int, 
        product_id: Optional[int] = None,
        product_metadata: Optional[Any] = None
    ) -> Decimal:
        """
        Tính CPM (mét khối) cho 1 line item từ product BoxInfo metadata.
        
        Công thức: CPM = (box_height * box_length * box_width * quantity) / 1,000,000 / full_box
        
        Args:
            variant_id: Sapo variant ID
            quantity: Số lượng
            product_id: Product ID (optional, nếu đã có product_metadata)
            product_metadata: ProductMetadataDTO (optional, nếu đã load sẵn)
            
        Returns:
            CPM (m³) cho line item này
        """
        try:
            self.debug_print(f"    _calculate_item_cpm: variant_id={variant_id}, quantity={quantity}, product_id={product_id}")
            
            # Nếu chưa có product_metadata, load từ product_id
            if not product_metadata and product_id:
                self.debug_print(f"      Loading product_metadata for product_id={product_id}")
                try:
                    product_data = self.core_api.get_product_raw(product_id)
                    if product_data:
                        description = product_data.get('description', '')
                        product_metadata, _ = extract_gdp_metadata(description)
                        self.debug_print(f"      Loaded metadata: {product_metadata is not None}")
                    else:
                        self.debug_print(f"      Product data is None")
                except Exception as e:
                    logger.warning(f"[SPOPOService] Error loading product {product_id}: {e}")
                    self.debug_print(f"      ERROR loading product: {e}")
            
            if not product_metadata:
                self.debug_print(f"      No product_metadata")
                logger.warning(f"[SPOPOService] No metadata for variant {variant_id}")
                return Decimal('0')
            
            if not product_metadata.variants:
                self.debug_print(f"      product_metadata.variants is empty")
                logger.warning(f"[SPOPOService] No variants in metadata for variant {variant_id}")
                return Decimal('0')
            
            self.debug_print(f"      Found {len(product_metadata.variants)} variants in metadata")
            
            # Tìm variant metadata
            variant_meta = None
            for v_meta in product_metadata.variants:
                if v_meta.id == variant_id:
                    variant_meta = v_meta
                    break
            
            if not variant_meta:
                self.debug_print(f"      Variant {variant_id} not found in metadata variants")
                logger.warning(f"[SPOPOService] Variant {variant_id} not found in metadata")
                return Decimal('0')
            
            self.debug_print(f"      Found variant_meta for variant_id={variant_id}")
            
            if not variant_meta.box_info:
                self.debug_print(f"      variant_meta.box_info is None")
                logger.warning(f"[SPOPOService] No box_info for variant {variant_id}")
                return Decimal('0')
            
            box_info = variant_meta.box_info
            self.debug_print(f"      box_info: length_cm={box_info.length_cm}, width_cm={box_info.width_cm}, height_cm={box_info.height_cm}, full_box={box_info.full_box}")
            
            # Kiểm tra đầy đủ thông tin kích thước thùng (đơn vị: cm)
            if not all([box_info.length_cm, box_info.width_cm, box_info.height_cm]):
                self.debug_print(f"      Incomplete box_info: length={box_info.length_cm}, width={box_info.width_cm}, height={box_info.height_cm}")
                logger.warning(f"[SPOPOService] Incomplete box_info for variant {variant_id}: length={box_info.length_cm}, width={box_info.width_cm}, height={box_info.height_cm}")
                return Decimal('0')
            
            # Lấy full_box (số cái/thùng), mặc định = 1 nếu không có
            full_box = box_info.full_box if box_info.full_box and box_info.full_box > 0 else 1
            self.debug_print(f"      Using full_box={full_box}")
            
            # Tính CPM theo công thức: (dài * rộng * cao * quantity) / 1,000,000 / full_box
            # Dữ liệu trong DB là cm, cần chuyển sang m³: / 1,000,000
            length_cm = Decimal(str(box_info.length_cm))
            width_cm = Decimal(str(box_info.width_cm))
            height_cm = Decimal(str(box_info.height_cm))
            quantity_dec = Decimal(str(quantity))
            full_box_dec = Decimal(str(full_box))
            
            # CPM = (length * width * height * quantity) / 1,000,000 / full_box
            cpm = length_cm * width_cm * height_cm * quantity_dec / Decimal('1000000') / full_box_dec
            
            self.debug_print(f"      Calculation: ({length_cm} * {width_cm} * {height_cm} * {quantity_dec}) / 1,000,000 / {full_box_dec} = {cpm}")
            
            return cpm
            
        except Exception as e:
            logger.error(f"[SPOPOService] Error calculating CPM for variant {variant_id}: {e}", exc_info=True)
            self.debug_print(f"      EXCEPTION: {e}")
            import traceback
            self.debug_print(f"      Traceback: {traceback.format_exc()}")
            return Decimal('0')
    
    def _get_variant_price_cny(
        self,
        variant_id: int,
        product_id: Optional[int] = None,
        product_metadata: Optional[Any] = None
    ) -> float:
        """
        Lấy giá nhập CNY (price_tq) của variant từ product metadata.
        
        Ưu tiên: price_tq > import_info.china_price_cny
        
        Args:
            variant_id: Sapo variant ID
            product_id: Product ID (optional, nếu đã có product_metadata)
            product_metadata: ProductMetadataDTO (optional, nếu đã load sẵn)
            
        Returns:
            Giá nhập CNY (float), mặc định 0.0 nếu không tìm thấy
        """
        try:
            self.debug_print(f"    _get_variant_price_cny: variant_id={variant_id}, product_id={product_id}")
            
            # Nếu chưa có product_metadata, load từ product_id
            if not product_metadata and product_id:
                self.debug_print(f"      Loading product_metadata for product_id={product_id}")
                try:
                    product_data = self.core_api.get_product_raw(product_id)
                    if product_data:
                        description = product_data.get('description', '')
                        product_metadata, _ = extract_gdp_metadata(description)
                        self.debug_print(f"      Loaded metadata: {product_metadata is not None}")
                    else:
                        self.debug_print(f"      Product data is None")
                except Exception as e:
                    logger.warning(f"[SPOPOService] Error loading product {product_id}: {e}")
                    self.debug_print(f"      ERROR loading product: {e}")
            
            if not product_metadata:
                self.debug_print(f"      No product_metadata")
                logger.warning(f"[SPOPOService] No metadata for variant {variant_id}")
                return 0.0
            
            if not product_metadata.variants:
                self.debug_print(f"      product_metadata.variants is empty")
                logger.warning(f"[SPOPOService] No variants in metadata for variant {variant_id}")
                return 0.0
            
            self.debug_print(f"      Found {len(product_metadata.variants)} variants in metadata")
            
            # Tìm variant metadata
            variant_meta = None
            for v_meta in product_metadata.variants:
                if v_meta.id == variant_id:
                    variant_meta = v_meta
                    break
            
            if not variant_meta:
                self.debug_print(f"      Variant {variant_id} not found in metadata variants")
                logger.warning(f"[SPOPOService] Variant {variant_id} not found in metadata")
                return 0.0
            
            self.debug_print(f"      Found variant_meta for variant_id={variant_id}")
            
            # Ưu tiên: price_tq > import_info.china_price_cny
            price_cny = 0.0
            
            if variant_meta.price_tq and variant_meta.price_tq > 0:
                price_cny = float(variant_meta.price_tq)
                self.debug_print(f"      Using price_tq: {price_cny}")
            elif variant_meta.import_info and variant_meta.import_info.china_price_cny:
                price_cny = float(variant_meta.import_info.china_price_cny)
                self.debug_print(f"      Using import_info.china_price_cny: {price_cny}")
            else:
                self.debug_print(f"      No price found in metadata")
                logger.warning(f"[SPOPOService] No price_tq or china_price_cny for variant {variant_id}")
            
            return price_cny
            
        except Exception as e:
            logger.error(f"[SPOPOService] Error getting price CNY for variant {variant_id}: {e}", exc_info=True)
            self.debug_print(f"      EXCEPTION: {e}")
            import traceback
            self.debug_print(f"      Traceback: {traceback.format_exc()}")
            return 0.0
    
    def get_pos_for_spo(self, spo_purchase_order_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Lấy thông tin nhiều PO từ Sapo.
        
        Args:
            spo_purchase_order_ids: List Sapo order_supplier IDs
            
        Returns:
            List[Dict] chứa thông tin các PO
        """
        pos = []
        for po_id in spo_purchase_order_ids:
            try:
                po_data = self.get_po_from_sapo(po_id)
                pos.append(po_data)
            except Exception as e:
                logger.warning(f"[SPOPOService] Error getting PO {po_id}: {e}")
        
        return pos
    
    def calculate_spo_total_cbm(self, spo_purchase_order_ids: List[int]) -> Decimal:
        """
        Tính tổng CPM (CBM) của SPO từ các PO.
        
        Args:
            spo_purchase_order_ids: List Sapo order_supplier IDs
            
        Returns:
            Tổng CPM (m³)
        """
        total_cpm = Decimal('0')
        for po_id in spo_purchase_order_ids:
            try:
                po_data = self.get_po_from_sapo(po_id)
                total_cpm += po_data.get('total_cpm', Decimal('0'))
            except Exception as e:
                logger.warning(f"[SPOPOService] Error calculating CPM for PO {po_id}: {e}")
        
        return total_cpm

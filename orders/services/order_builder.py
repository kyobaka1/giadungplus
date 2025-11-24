# orders/services/order_builder.py
"""
OrderDTOFactory - Factory để convert raw Sapo JSON sang OrderDTO.
Refactored từ build_order_from_sapo() function.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional
import json
import logging

from .dto import (
    OrderDTO, AddressDTO, OrderLineItemDTO, OrderLineDiscountDTO,
    FulfillmentDTO, FulfillmentLineItemDTO, ShipmentDTO
)
# Import CustomerDTO from customers module (single source of truth)
from customers.services.dto import CustomerDTO, CustomerGroupDTO, CustomerSaleOrderStatsDTO

logger = logging.getLogger(__name__)

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")
HOLIDAYS = set()  # Có thể load từ config hoặc database

class OrderDTOFactory:
    """
    Factory để convert raw JSON từ Sapo API sang OrderDTO.
    
    Usage:
        factory = OrderDTOFactory()
        order = factory.from_sapo_json(raw_order_dict)
    """
    
    def from_sapo_json(self, payload: Dict[str, Any]) -> OrderDTO:
        """
        Convert JSON từ Sapo API sang OrderDTO.
        
        Args:
            payload: Raw JSON từ /admin/orders/{id}.json
                    Có thể có key "order" bao ngoài hoặc không
                    
        Returns:
            OrderDTO instance với full validation
        """
        # Handle cả 2 format: {"order": {...}} hoặc {...}
        raw_order = payload.get("order") or payload
        
        # Build nested objects
        order_line_items = self._build_order_line_items(
            raw_order.get("order_line_items") or []
        )
        fulfillments = self._build_fulfillments(
            raw_order.get("fulfillments") or []
        )
        customer = self._build_customer(raw_order.get("customer_data"))
        billing_addr = self._build_address(raw_order.get("billing_address"))
        shipping_addr = self._build_address(raw_order.get("shipping_address"))
        
        # Extract packing data
        packing_data = self._extract_packing_data(raw_order)
        
        # Calculate ship deadline
        deadline_dt, deadline_str = self._calculate_ship_deadline(
            raw_order.get("created_on")
        )
        
        # Build OrderDTO (Pydantic will validate)
        return OrderDTO(
            id=raw_order["id"],
            tenant_id=raw_order["tenant_id"],
            location_id=raw_order["location_id"],
            code=raw_order.get("code", ""),
            
            created_on=raw_order.get("created_on"),
            modified_on=raw_order.get("modified_on"),
            issued_on=raw_order.get("issued_on"),
            finalized_on=raw_order.get("finalized_on"),
            completed_on=raw_order.get("completed_on"),
            cancelled_on=raw_order.get("cancelled_on"),
            
            account_id=raw_order.get("account_id"),
            assignee_id=raw_order.get("assignee_id"),
            
            customer_id=raw_order.get("customer_id"),
            customer=customer,
            
            billing_address=billing_addr,
            shipping_address=shipping_addr,
            email=raw_order.get("email"),
            phone_number=raw_order.get("phone_number"),
            
            channel=raw_order.get("channel"),
            reference_number=raw_order.get("reference_number"),
            source_id=raw_order.get("source_id"),
            reference_url=raw_order.get("reference_url"),
            
            status=raw_order.get("status"),
            print_status=bool(raw_order.get("print_status", False)),
            packed_status=raw_order.get("packed_status"),
            fulfillment_status=raw_order.get("fulfillment_status"),
            received_status=raw_order.get("received_status"),
            payment_status=raw_order.get("payment_status"),
            return_status=raw_order.get("return_status"),
            
            total=float(raw_order.get("total", 0) or 0),
            total_discount=float(raw_order.get("total_discount", 0) or 0),
            total_tax=float(raw_order.get("total_tax", 0) or 0),
            delivery_fee=float(raw_order.get("delivery_fee", 0) or 0),
            order_discount_rate=float(raw_order.get("order_discount_rate", 0) or 0),
            order_discount_value=float(raw_order.get("order_discount_value", 0) or 0),
            order_discount_amount=float(raw_order.get("order_discount_amount", 0) or 0),
            
            tags=raw_order.get("tags") or [],
            note=raw_order.get("note") or "",
            
            order_line_items=order_line_items,
            fulfillments=fulfillments,
            
            raw=raw_order,
            
            # Ship deadline
            ship_deadline_fast=deadline_dt,
            ship_deadline_fast_str=deadline_str,
            
            # Packing data
            packing_status=int(packing_data.get("packing_status") or 0),
            nguoi_goi=packing_data.get("nguoi_goi"),
            time_packing=packing_data.get("time_packing"),
            dvvc=packing_data.get("dvvc"),
            shopee_id=str(packing_data.get("shopee_id")) if packing_data.get("shopee_id") is not None else None,
            time_print=packing_data.get("time_print"),
            split=int(packing_data.get("split") or 0),
            time_chia=packing_data.get("time_chia"),
            shipdate=packing_data.get("shipdate"),
            nguoi_chia=packing_data.get("nguoi_chia"),
        )
    
    # ==================== PRIVATE HELPERS ====================
    
    def _build_address(self, data: Optional[Dict[str, Any]]) -> Optional[AddressDTO]:
        """Build AddressDTO từ raw data."""
        if not data:
            return None
        
        # Pydantic will validate và convert
        return AddressDTO.from_dict(data)
    
    def _build_customer(self, data: Optional[Dict[str, Any]]) -> Optional[CustomerDTO]:
        """Build CustomerDTO từ raw data."""
        if not data:
            return None
        
        # Build nested objects
        group_raw = data.get("customer_group") or {}
        group = CustomerGroupDTO.from_dict(group_raw) if group_raw else None
        
        stats_raw = data.get("sale_order") or {}
        stats = CustomerSaleOrderStatsDTO.from_dict(stats_raw) if stats_raw else None
        
        addresses = [
            self._build_address(a)
            for a in (data.get("addresses") or [])
        ]
        
        return CustomerDTO(
            id=data["id"],
            code=data.get("code", ""),
            name=data.get("name", ""),
            phone_number=data.get("phone_number"),
            email=data.get("email"),
            sex=data.get("sex"),
            tax_number=data.get("tax_number"),
           website=data.get("website"),
            group=group,
            sale_stats=stats,
            tags=data.get("tags") or [],
            addresses=[a for a in addresses if a],  # Filter None
        )
    
    def _build_order_line_items(self, data_list: List[Dict[str, Any]]) -> List[OrderLineItemDTO]:
        """
        Build list of OrderLineItemDTO.
        
        Note: Map item_name -> product_name và variation_name -> variant_name
        để hỗ trợ cả Sapo Core API và Marketplace API format.
        
        Xử lý trường hợp các line items đặc biệt (phí vận chuyển, chiết khấu...) 
        có thể có product_id, variant_id, product_name, variant_name là None.
        """
        result = []
        
        for d in (data_list or []):
            try:
                discount_items = [
                    OrderLineDiscountDTO.from_dict(item)
                    for item in (d.get("discount_items") or [])
                ]
                
                # Map item_name -> product_name (Marketplace API format)
                # Fallback về product_name nếu không có item_name (Sapo Core API format)
                product_name = d.get("item_name") or d.get("product_name") or ""
                
                # Map variation_name -> variant_name (Marketplace API format)
                # Fallback về variant_name nếu không có variation_name (Sapo Core API format)
                variant_name = d.get("variation_name") or d.get("variant_name") or ""
                
                # Xử lý product_id và variant_id - có thể None cho các line items đặc biệt
                product_id = d.get("product_id")
                variant_id = d.get("variant_id")
                
                # SKU có thể None
                sku = d.get("sku") or ""
                
                # Product type có thể None
                product_type = d.get("product_type") or "normal"
                
                result.append(OrderLineItemDTO(
                    id=d["id"],
                    product_id=product_id,
                    variant_id=variant_id,
                    product_name=product_name,
                    variant_name=variant_name,
                    sku=sku,
                    barcode=d.get("barcode"),
                    unit=d.get("unit"),
                    variant_options=d.get("variant_options"),
                    price=float(d.get("price", 0) or 0),
                    quantity=float(d.get("quantity", 0) or 0),
                    line_amount=float(d.get("line_amount", 0) or 0),
                    discount_amount=float(d.get("discount_amount", 0) or 0),
                    discount_value=float(d.get("discount_value", 0) or 0),
                    discount_rate=float(d.get("discount_rate", 0) or 0),
                    discount_reason=d.get("discount_reason"),
                    tax_rate=float(d.get("tax_rate", 0) or 0),
                    tax_amount=float(d.get("tax_amount", 0) or 0),
                    product_type=product_type,
                    discount_items=discount_items,
                    # Map shopee_variation_id nếu có (từ Marketplace API)
                    shopee_variation_id=d.get("variation_id") or d.get("shopee_variation_id"),
                ))
            except Exception as e:
                logger.warning(f"Failed to build OrderLineItemDTO for line item {d.get('id')}: {e}")
                # Skip line item nếu có lỗi (không crash toàn bộ order)
                continue
        
        return result
    
    def _build_fulfillments(self, data_list: List[Dict[str, Any]]) -> List[FulfillmentDTO]:
        """Build list of FulfillmentDTO."""
        result = []
        
        for d in (data_list or []):
            fl_items = [
                FulfillmentLineItemDTO.from_dict(item)
                for item in (d.get("fulfillment_line_items") or [])
            ]
            
            shipment_raw = d.get("shipment")
            shipment = ShipmentDTO.from_dict(shipment_raw) if shipment_raw else None
            
            result.append(FulfillmentDTO(
                id=d["id"],
                stock_location_id=d.get("stock_location_id", 0),
                code=d.get("code", ""),
                status=d.get("status", ""),
                total=float(d.get("total", 0) or 0),
                total_discount=float(d.get("total_discount", 0) or 0),
                total_tax=float(d.get("total_tax", 0) or 0),
                packed_on=d.get("packed_on"),
                shipped_on=d.get("shipped_on"),
                received_on=d.get("received_on"),
                payment_status=d.get("payment_status", ""),
                print_status=bool(d.get("print_status", False)),
                composite_fulfillment_status=d.get("composite_fulfillment_status"),
                fulfillment_line_items=fl_items,
                shipment=shipment,
            ))
        
        return result
    
    def _calculate_ship_deadline(
        self,
        created_on_str: Optional[str]
    ) -> tuple[Optional[datetime], Optional[str]]:
        """
        Tính deadline giao hàng nhanh.
        
        Args:
            created_on_str: ISO datetime string UTC từ Sapo
            
        Returns:
            (deadline_datetime, deadline_string)
        """
        if not created_on_str:
            return None, None
        
        try:
            # Parse UTC time
            created_utc = datetime.strptime(
                created_on_str, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
            
            # Convert to Vietnam time
            created_local = created_utc.astimezone(TZ_VN).replace(tzinfo=None)
            
            # Calculate deadline
            deadline = self._get_fast_deadline(created_local)
            deadline_str = deadline.strftime("%d/%m/%Y %H:%M")
            
            return deadline, deadline_str
            
        except Exception as e:
            logger.warning(f"Failed to calculate ship deadline: {e}")
            return None, None
    
    def _get_fast_deadline(self, created_local: datetime) -> datetime:
        """
        Logic tính deadline giống với api_kho_sumreport.
        
        Rules:
        - Nếu tạo đơn trước 18h: deadline = 23:59 cùng ngày
        - Nếu tạo đơn sau 18h: deadline = 12:00 ngày hôm sau
        - Nếu deadline rơi vào Chủ nhật: đẩy sang thứ 2, 12:00
        - Skip các ngày nghỉ lễ
        """
        if 0 <= created_local.hour < 18:
            # Trước 18h -> cuối ngày
            raw = created_local.replace(hour=23, minute=59, second=59, microsecond=0)
        else:
            # Sau 18h -> 12h trưa hôm sau
            raw = (created_local + timedelta(days=1)).replace(
                hour=12, minute=0, second=0, microsecond=0
            )
        
        # Nếu Chủ nhật -> thứ 2 12:00
        if raw.weekday() == 6:  # Sunday
            raw = (raw + timedelta(days=1)).replace(
                hour=12, minute=0, second=0, microsecond=0
            )
        
        return self._next_business_day(raw)
    
    def _next_business_day(self, dt: datetime) -> datetime:
        """Skip Chủ nhật và ngày nghỉ lễ."""
        candidate = dt
        while self._is_non_workday(candidate):
            candidate += timedelta(days=1)
        return candidate
    
    def _is_non_workday(self, dt: datetime) -> bool:
        """Check nếu là Chủ nhật hoặc ngày nghỉ lễ."""
        return dt.weekday() == 6 or dt.date().isoformat() in HOLIDAYS
    
    def _extract_packing_data(self, raw_order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract packing data từ shipment.note (JSON format).
        
        Sử dụng mo_rong_gon() để expand keys từ format rút gọn:
        {"pks": 3} -> {"packing_status": 3}
        
        Returns:
            Dict với keys đã expand (packing_status, nguoi_goi, etc.)
        """
        fulfillments = raw_order.get("fulfillments") or []
        if not fulfillments:
            return {}
        
        # Get latest fulfillment
        latest = fulfillments[-1] or {}
        shipment = latest.get("shipment") or {}
        note = shipment.get("note") or ""
        
        if not note or "{" not in note:
            return {}
        
        # Sử dụng mo_rong_gon từ sapo_service
        from orders.services.sapo_service import mo_rong_gon
        
        try:
            result = mo_rong_gon(note)
            return result
        except Exception as e:
            logger.warning(f"Failed to parse packing data from note: {e}")
            return {}


# Backward compatibility: Keep old function name
def build_order_from_sapo(payload: Dict[str, Any]) -> OrderDTO:
    """
    Deprecated: Use OrderDTOFactory instead.
    Kept for backward compatibility.
    """
    factory = OrderDTOFactory()
    return factory.from_sapo_json(payload)

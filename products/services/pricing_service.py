# products/services/pricing_service.py
"""
Service để tính toán giá vốn, lợi nhuận từ orders và cost_history.
"""

from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import datetime, date, timedelta
from collections import defaultdict
import logging

from django.db.models import Q, Sum, Avg, Count
from django.utils import timezone

from products.models import CostHistory
from orders.services.sapo_order_service import SapoOrderService
from orders.services.dto import OrderDTO, RealItemDTO
from core.sapo_client import get_sapo_client
from products.services.sapo_product_service import SapoProductService

logger = logging.getLogger(__name__)


class PricingService:
    """
    Service để tính toán giá vốn, lợi nhuận từ orders.
    """
    
    def __init__(self):
        sapo_client = get_sapo_client()
        self.order_service = SapoOrderService(sapo_client)
        self.product_service = SapoProductService(sapo_client)
        self.sapo_client = sapo_client
        # Cache variants với inventories (mac field)
        self._variants_cache: Dict[int, Dict[int, float]] = {}  # {variant_id: {location_id: mac}}
    
    def _load_variants_from_sapo(self) -> None:
        """
        Load toàn bộ variants từ Sapo API (request 250 mỗi lần) và cache mac theo location_id.
        """
        if self._variants_cache:
            # Đã cache rồi, không load lại
            return
        
        logger.info("Loading variants from Sapo API...")
        page = 1
        limit = 250
        
        while True:
            try:
                products = self.product_service.list_products(page=page, limit=limit)
                
                if not products:
                    break
                
                for product in products:
                    for variant in product.variants:
                        variant_id = variant.id
                        # Lấy inventories từ variant
                        for inventory in variant.inventories:
                            location_id = inventory.location_id
                            mac = inventory.mac
                            
                            # Chỉ cache nếu mac > 0
                            if mac > 0:
                                if variant_id not in self._variants_cache:
                                    self._variants_cache[variant_id] = {}
                                self._variants_cache[variant_id][location_id] = mac
                
                logger.info(f"Loaded page {page}: {len(products)} products")
                
                if len(products) < limit:
                    break
                
                page += 1
            except Exception as e:
                logger.error(f"Error loading variants page {page}: {e}", exc_info=True)
                break
        
        total_variants = len(self._variants_cache)
        logger.info(f"Loaded {total_variants} variants with mac > 0 from Sapo API")
    
    def get_cost_price_for_variant(
        self,
        variant_id: int,
        location_id: int,
        order_date: date,
        debug: bool = False
    ) -> Optional[Decimal]:
        """
        Lấy giá vốn của variant tại location và thời điểm order_date.
        
        Logic:
        1. Tìm trong CostHistory trước (với đúng location_id)
        2. Nếu không có, lấy từ Sapo API (field mac trong inventories)
        
        Args:
            variant_id: ID của variant
            location_id: ID của location (kho hàng)
            order_date: Ngày tạo đơn hàng
            debug: Bật debug logging chi tiết
            
        Returns:
            Decimal: Giá vốn (VNĐ) hoặc None nếu không tìm thấy
        """
        try:
            # Bước 1: Tìm trong CostHistory trước
            cost_history = CostHistory.objects.filter(
                variant_id=variant_id,
                location_id=location_id,  # PHẢI trùng với location_id của order
                import_date__lte=order_date,
                average_cost_price__gt=0  # Chỉ lấy những record có giá vốn > 0
            ).order_by('-import_date').first()
            
            if cost_history and cost_history.average_cost_price:
                if debug:
                    logger.info(f"✓ Found cost price from CostHistory for variant {variant_id} at location {location_id}: {cost_history.average_cost_price} (date: {cost_history.import_date})")
                return cost_history.average_cost_price
            
            # Bước 2: Nếu không có trong CostHistory, lấy từ Sapo API (mac field)
            # Load variants từ Sapo nếu chưa cache
            if not self._variants_cache:
                self._load_variants_from_sapo()
            
            # Tìm trong cache
            if variant_id in self._variants_cache:
                location_mac_map = self._variants_cache[variant_id]
                if location_id in location_mac_map:
                    mac = location_mac_map[location_id]
                    if mac > 0:
                        if debug:
                            logger.info(f"✓ Found cost price from Sapo API (mac) for variant {variant_id} at location {location_id}: {mac}")
                        return Decimal(str(mac))
            
            # Không tìm thấy
            if debug:
                # Kiểm tra xem có CostHistory nào cho variant này không (bất kỳ location, bất kỳ ngày)
                any_cost_history = CostHistory.objects.filter(
                    variant_id=variant_id,
                    average_cost_price__gt=0
                ).order_by('-import_date').first()
                
                if any_cost_history:
                    logger.warning(f"⚠ Variant {variant_id} has CostHistory but NOT at location {location_id}: order_date={order_date}, order_location={location_id}, cost_history_location={any_cost_history.location_id}, cost_history_date={any_cost_history.import_date}")
                else:
                    logger.warning(f"⚠ Variant {variant_id} has NO CostHistory and NO mac in Sapo API for location {location_id}")
            
            return None
        except Exception as e:
            logger.error(f"Error getting cost price for variant {variant_id} at {order_date}: {e}", exc_info=True)
            return None
    
    def calculate_pricing_overview(
        self,
        start_date: date,
        end_date: date,
        debug: bool = False
    ) -> Dict[str, Any]:
        """
        Tính toán overview giá vốn và lợi nhuận cho khoảng thời gian.
        
        Args:
            start_date: Ngày bắt đầu
            end_date: Ngày kết thúc
            debug: Bật debug logging chi tiết
            
        Returns:
            Dict chứa các số liệu phân tích:
            - total_revenue: Tổng doanh thu
            - total_cost: Tổng giá vốn
            - total_profit: Tổng lợi nhuận gộp
            - total_profit_margin: Tỷ lệ lợi nhuận gộp (%)
            - orders_count: Số lượng đơn hàng
            - sku_stats: Thống kê theo SKU
            - location_stats: Thống kê theo location
            - source_stats: Thống kê theo source
            - shop_stats: Thống kê theo shop (tag)
        """
        # Load variants từ Sapo API trước khi xử lý orders
        logger.info("Loading variants from Sapo API before processing orders...")
        self._load_variants_from_sapo()
        logger.info(f"Calculating pricing overview from {start_date} to {end_date}")
        
        # Chuyển đổi date thành datetime ISO string cho Sapo API
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())
        
        # Format ISO string
        created_on_min = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
        created_on_max = end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Lấy tất cả orders trong khoảng thời gian
        orders = []
        page = 1
        limit = 250
        
        while True:
            try:
                page_orders = self.order_service.list_orders(
                    page=page,
                    limit=limit,
                    created_on_min=created_on_min,
                    created_on_max=created_on_max,
                    status='finalized'  # Chỉ lấy đơn đã finalized
                )
                
                if not page_orders:
                    break
                
                orders.extend(page_orders)
                logger.info(f"Fetched {len(page_orders)} orders from page {page}")
                
                if len(page_orders) < limit:
                    break
                
                page += 1
            except Exception as e:
                logger.error(f"Error fetching orders page {page}: {e}")
                break
        
        logger.info(f"Total orders fetched: {len(orders)}")
        
        # Tính toán các số liệu
        total_revenue = Decimal('0')
        total_cost = Decimal('0')
        orders_count = 0
        
        # Thống kê theo SKU
        sku_stats = defaultdict(lambda: {
            'variant_id': None,
            'sku': '',
            'quantity_sold': Decimal('0'),
            'revenue': Decimal('0'),
            'cost': Decimal('0'),
            'profit': Decimal('0'),
            'avg_selling_price': Decimal('0'),
            'cost_ratio': Decimal('0'),  # Tỷ lệ giá vốn (%)
            'orders_count': 0
        })
        
        # Thống kê theo location
        location_stats = defaultdict(lambda: {
            'location_id': None,
            'revenue': Decimal('0'),
            'cost': Decimal('0'),
            'profit': Decimal('0'),
            'orders_count': 0
        })
        
        # Thống kê theo source
        source_stats = defaultdict(lambda: {
            'source_id': None,
            'revenue': Decimal('0'),
            'cost': Decimal('0'),
            'profit': Decimal('0'),
            'orders_count': 0
        })
        
        # Thống kê theo shop (tag)
        shop_stats = defaultdict(lambda: {
            'shop_name': '',
            'revenue': Decimal('0'),
            'cost': Decimal('0'),
            'profit': Decimal('0'),
            'orders_count': 0
        })
        
        # Thống kê theo ngày (để vẽ biểu đồ)
        daily_stats = defaultdict(lambda: {
            'date': None,
            'revenue': Decimal('0'),
            'cost': Decimal('0'),
            'profit': Decimal('0'),
            'cost_ratio': Decimal('0'),
            'profit_margin': Decimal('0')
        })
        
        # Debug counters
        orders_without_real_items = 0
        items_without_variant_id = 0
        items_without_cost_price = 0
        items_with_cost_price = 0
        variant_ids_checked = set()
        
        # Lấy danh sách variant_id có trong CostHistory để debug
        variant_ids_in_cost_history = set(
            CostHistory.objects.filter(average_cost_price__gt=0)
            .values_list('variant_id', flat=True)
            .distinct()
        )
        
        # Xử lý từng order
        for order in orders:
            try:
                # Parse created_on để lấy date
                if not order.created_on:
                    continue
                
                order_date = datetime.fromisoformat(
                    order.created_on.replace('Z', '+00:00')
                ).date()
                
                # Chỉ xử lý orders có real_items
                if not order.real_items:
                    orders_without_real_items += 1
                    continue
                
                orders_count += 1
                
                order_cost = Decimal('0')
                order_revenue = Decimal('0')  # Chỉ tính doanh thu từ SKU có giá vốn
                
                # Xử lý từng real_item trong order
                for real_item in order.real_items:
                    if not real_item.variant_id:
                        items_without_variant_id += 1
                        continue
                    
                    variant_ids_checked.add(real_item.variant_id)
                    
                    # Lấy giá vốn cho variant tại location và thời điểm order_date
                    # Chỉ debug cho variant_id có trong CostHistory nhưng không tìm thấy giá vốn
                    should_debug = debug and real_item.variant_id in variant_ids_in_cost_history
                    cost_price = self.get_cost_price_for_variant(
                        variant_id=real_item.variant_id,
                        location_id=order.location_id,
                        order_date=order_date,
                        debug=should_debug
                    )
                    
                    # Chỉ tính nếu có giá vốn (theo yêu cầu: chỉ tính SKU đã có cost_history)
                    if cost_price is None:
                        items_without_cost_price += 1
                        continue
                    
                    items_with_cost_price += 1
                    
                    quantity = Decimal(str(real_item.quantity))
                    item_cost = cost_price * quantity
                    order_cost += item_cost
                    
                    # Tìm order_line_item tương ứng để lấy line_amount
                    # Logic: tìm line_item có variant_id match hoặc pack_size_root_id match
                    item_revenue = Decimal('0')
                    for line_item in order.order_line_items:
                        if line_item.variant_id == real_item.variant_id:
                            # Match trực tiếp
                            # Trừ distributed_discount_amount để có giá bán thực tế
                            line_amount = Decimal(str(line_item.line_amount))
                            distributed_discount = Decimal(str(getattr(line_item, 'distributed_discount_amount', 0) or 0))
                            item_revenue = line_amount - distributed_discount
                            break
                        elif line_item.pack_size_root_id == real_item.variant_id:
                            # Match qua packsize: phân bổ line_amount theo tỷ lệ quantity
                            line_quantity = Decimal(str(line_item.quantity))
                            pack_size = Decimal(str(line_item.pack_size_quantity or 1))
                            if line_quantity > 0 and pack_size > 0:
                                # Tính tỷ lệ: real_item.quantity / (line_item.quantity * pack_size)
                                total_real_quantity = line_quantity * pack_size
                                if total_real_quantity > 0:
                                    ratio = quantity / total_real_quantity
                                    line_amount = Decimal(str(line_item.line_amount))
                                    distributed_discount = Decimal(str(getattr(line_item, 'distributed_discount_amount', 0) or 0))
                                    item_revenue = (line_amount - distributed_discount) * ratio
                            break
                        elif real_item.old_id > 0 and line_item.variant_id == real_item.old_id:
                            # Match qua old_id (combo): phân bổ line_amount theo tỷ lệ quantity
                            line_quantity = Decimal(str(line_item.quantity))
                            if line_quantity > 0:
                                ratio = quantity / line_quantity
                                line_amount = Decimal(str(line_item.line_amount))
                                distributed_discount = Decimal(str(getattr(line_item, 'distributed_discount_amount', 0) or 0))
                                item_revenue = (line_amount - distributed_discount) * ratio
                            break
                    
                    # Nếu không tìm thấy line_item, tính từ price * quantity (fallback)
                    if item_revenue == 0:
                        # Tìm price từ line_item
                        for line_item in order.order_line_items:
                            if line_item.variant_id == real_item.variant_id or line_item.pack_size_root_id == real_item.variant_id:
                                price = Decimal(str(line_item.price))
                                item_revenue = price * quantity
                                break
                    
                    avg_selling_price = item_revenue / quantity if quantity > 0 else Decimal('0')
                    
                    # Chỉ tính doanh thu cho SKU có giá vốn
                    order_revenue += item_revenue
                    
                    # Cập nhật thống kê theo SKU
                    sku_key = real_item.sku or f"variant_{real_item.variant_id}"
                    sku_stats[sku_key]['variant_id'] = real_item.variant_id
                    sku_stats[sku_key]['sku'] = real_item.sku or ''
                    sku_stats[sku_key]['quantity_sold'] += quantity
                    sku_stats[sku_key]['revenue'] += item_revenue
                    sku_stats[sku_key]['cost'] += item_cost
                    sku_stats[sku_key]['profit'] += (item_revenue - item_cost)
                    
                    # Tính lại giá bán trung bình
                    if sku_stats[sku_key]['quantity_sold'] > 0:
                        sku_stats[sku_key]['avg_selling_price'] = (
                            sku_stats[sku_key]['revenue'] / sku_stats[sku_key]['quantity_sold']
                        )
                    
                    # Tính tỷ lệ giá vốn
                    if sku_stats[sku_key]['revenue'] > 0:
                        sku_stats[sku_key]['cost_ratio'] = (
                            sku_stats[sku_key]['cost'] / sku_stats[sku_key]['revenue'] * 100
                        )
                
                total_cost += order_cost
                total_revenue += order_revenue  # Chỉ tính doanh thu từ SKU có giá vốn
                
                # Cập nhật thống kê theo ngày
                date_key = order_date.isoformat()
                daily_stats[date_key]['date'] = order_date
                daily_stats[date_key]['revenue'] += order_revenue
                daily_stats[date_key]['cost'] += order_cost
                daily_stats[date_key]['profit'] += (order_revenue - order_cost)
                
                # Tính tỷ lệ cho ngày
                if daily_stats[date_key]['revenue'] > 0:
                    daily_stats[date_key]['cost_ratio'] = (
                        daily_stats[date_key]['cost'] / daily_stats[date_key]['revenue'] * 100
                    )
                    daily_stats[date_key]['profit_margin'] = (
                        daily_stats[date_key]['profit'] / daily_stats[date_key]['revenue'] * 100
                    )
                
                # Cập nhật thống kê theo location
                location_key = str(order.location_id)
                location_stats[location_key]['location_id'] = order.location_id
                location_stats[location_key]['revenue'] += order_revenue
                location_stats[location_key]['cost'] += order_cost
                location_stats[location_key]['profit'] += (order_revenue - order_cost)
                location_stats[location_key]['orders_count'] += 1
                
                # Cập nhật thống kê theo source
                if order.source_id:
                    source_key = str(order.source_id)
                    source_stats[source_key]['source_id'] = order.source_id
                    source_stats[source_key]['revenue'] += order_revenue
                    source_stats[source_key]['cost'] += order_cost
                    source_stats[source_key]['profit'] += (order_revenue - order_cost)
                    source_stats[source_key]['orders_count'] += 1
                
                # Cập nhật thống kê theo shop (tag)
                # Logic: tìm tag có chứa "shop" hoặc các shop cụ thể
                shop_name = "Khác"
                if order.tags:
                    for tag in order.tags:
                        tag_lower = tag.lower()
                        if 'shopee' in tag_lower or 'official' in tag_lower or 'lteng' in tag_lower or 'phaledo' in tag_lower or 'giadungplus' in tag_lower:
                            # Extract shop name từ tag (ví dụ: "shop_shopee" -> "shopee")
                            if '_' in tag:
                                shop_name = tag.split('_')[-1]
                            else:
                                shop_name = tag
                            break
                
                shop_stats[shop_name]['shop_name'] = shop_name
                shop_stats[shop_name]['revenue'] += order_revenue
                shop_stats[shop_name]['cost'] += order_cost
                shop_stats[shop_name]['profit'] += (order_revenue - order_cost)
                shop_stats[shop_name]['orders_count'] += 1
                
            except Exception as e:
                logger.error(f"Error processing order {order.code if hasattr(order, 'code') else 'unknown'}: {e}", exc_info=True)
                continue
        
        # Tính tổng lợi nhuận và tỷ lệ
        total_profit = total_revenue - total_cost
        total_profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0')
        total_cost_ratio = (total_cost / total_revenue * 100) if total_revenue > 0 else Decimal('0')
        
        # Chuyển đổi daily_stats thành list và sắp xếp theo ngày
        daily_stats_list = []
        for date_key in sorted(daily_stats.keys()):
            daily_data = daily_stats[date_key]
            daily_stats_list.append({
                'date': daily_data['date'].isoformat() if daily_data['date'] else date_key,
                'revenue': float(daily_data['revenue']),
                'cost': float(daily_data['cost']),
                'profit': float(daily_data['profit']),
                'cost_ratio': float(daily_data['cost_ratio']),
                'profit_margin': float(daily_data['profit_margin'])
            })
        
        # Chuyển đổi defaultdict thành dict và sắp xếp
        result = {
            'total_revenue': float(total_revenue),
            'total_cost': float(total_cost),
            'total_profit': float(total_profit),
            'total_profit_margin': float(total_profit_margin),
            'total_cost_ratio': float(total_cost_ratio),
            'orders_count': orders_count,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'daily_stats': daily_stats_list,
            'sku_stats': dict(sorted(
                sku_stats.items(),
                key=lambda x: x[1]['revenue'],
                reverse=True
            )),
            'location_stats': dict(sorted(
                location_stats.items(),
                key=lambda x: x[1]['revenue'],
                reverse=True
            )),
            'source_stats': dict(sorted(
                source_stats.items(),
                key=lambda x: x[1]['revenue'],
                reverse=True
            )),
            'shop_stats': dict(sorted(
                shop_stats.items(),
                key=lambda x: x[1]['revenue'],
                reverse=True
            ))
        }
        
        logger.info(f"Pricing overview calculated: {orders_count} orders, revenue={total_revenue}, cost={total_cost}, profit={total_profit}")
        logger.info(f"Debug stats: orders_without_real_items={orders_without_real_items}, items_without_variant_id={items_without_variant_id}, items_without_cost_price={items_without_cost_price}, items_with_cost_price={items_with_cost_price}")
        
        # Thêm debug info vào result
        result['debug_stats'] = {
            'total_orders_fetched': len(orders),
            'orders_processed': orders_count,
            'orders_without_real_items': orders_without_real_items,
            'items_without_variant_id': items_without_variant_id,
            'items_without_cost_price': items_without_cost_price,
            'items_with_cost_price': items_with_cost_price,
            'unique_variant_ids_checked': len(variant_ids_checked),
            'variant_ids_checked': sorted(list(variant_ids_checked))[:20],  # Lấy 20 đầu tiên để debug
        }
        
        return result


# products/services/sales_forecast_service.py
"""
Service để tính toán dự báo bán hàng và cảnh báo tồn kho.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.sapo_client import SapoClient
from orders.services.sapo_order_service import SapoOrderService
from orders.services.dto import OrderDTO, RealItemDTO
from products.services.dto import SalesForecastDTO, VariantMetadataDTO, ProductMetadataDTO
from products.services.metadata_helper import extract_gdp_metadata, inject_gdp_metadata, update_variant_metadata
from products.services.sapo_product_service import SapoProductService
from products.models import VariantSalesForecast

logger = logging.getLogger(__name__)

# Location IDs
LOCATION_HN = 241737
LOCATION_SG = 548744

# Status orders hợp lệ (Đang giao dịch/Hoàn thành)
VALID_ORDER_STATUSES = ["finalized", "completed"]


class SalesForecastService:
    """
    Service để tính toán dự báo bán hàng và cảnh báo tồn kho.
    """
    
    def __init__(self, sapo_client: SapoClient):
        """
        Args:
            sapo_client: SapoClient instance
        """
        self.sapo_client = sapo_client
        self.order_service = SapoOrderService(sapo_client)
        self.product_service = SapoProductService(sapo_client)
    
    def calculate_sales_forecast(
        self, 
        days: int = 7,
        force_refresh: bool = False
    ) -> tuple[Dict[int, SalesForecastDTO], List[Dict[str, Any]], Dict[int, Dict[str, Any]]]:
        """
        Tính toán dự báo bán hàng cho tất cả variants.
        
        Args:
            days: Số ngày để tính toán tốc độ bán (mặc định 7 ngày)
            force_refresh: Nếu True, tính toán lại từ đầu. Nếu False, lấy từ GDP_META nếu có.
            
        Returns:
            Dict {variant_id: SalesForecastDTO}
        """
        import time
        start_time = time.time()
        
        print(f"\n{'='*60}")
        print(f"[DEBUG] ===== BẮT ĐẦU TÍNH TOÁN DỰ BÁO BÁN HÀNG =====")
        print(f"[DEBUG] Days: {days}, Force Refresh: {force_refresh}")
        print(f"{'='*60}\n")
        
        logger.info(f"[SalesForecastService] Calculating sales forecast for {days} days, force_refresh={force_refresh}")
        
        # Tính toán thời gian cho 2 kỳ
        step_start = time.time()
        print(f"[DEBUG] [BƯỚC 1] Tính toán thời gian cho 2 kỳ...")
        now = datetime.now(ZoneInfo("UTC"))
        now_iso = now.isoformat()  # Lưu để dùng trong threads
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=0)
        
        # Kỳ hiện tại: 0 đến x ngày trước
        start_date_current = (end_date - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Kỳ trước: x đến 2x ngày trước (cùng kỳ)
        end_date_previous = start_date_current - timedelta(seconds=1)  # Trước 1 giây của kỳ hiện tại
        start_date_previous = (end_date_previous - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Format cho Sapo API
        created_on_min_current = start_date_current.strftime("%Y-%m-%dT%H:%M:%SZ")
        created_on_max_current = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        created_on_min_previous = start_date_previous.strftime("%Y-%m-%dT%H:%M:%SZ")
        created_on_max_previous = end_date_previous.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        print(f"[DEBUG] [BƯỚC 1] ✅ Hoàn thành ({time.time() - step_start:.2f}s)")
        print(f"[DEBUG]        Kỳ hiện tại: {created_on_min_current} to {created_on_max_current}")
        print(f"[DEBUG]        Kỳ trước: {created_on_min_previous} to {created_on_max_previous}\n")
        logger.info(f"[SalesForecastService] Current period: {created_on_min_current} to {created_on_max_current}")
        logger.info(f"[SalesForecastService] Previous period: {created_on_min_previous} to {created_on_max_previous}")
        
        # Lấy tất cả products từ Sapo (đã bao gồm variants và inventories)
        step_start = time.time()
        print(f"[DEBUG] [BƯỚC 2] Lấy tất cả products từ Sapo (bao gồm variants & inventories)...")
        logger.info("[SalesForecastService] Fetching all products...")
        all_products, all_variants_map = self._get_all_products()
        print(f"[DEBUG] [BƯỚC 2] ✅ Hoàn thành ({time.time() - step_start:.2f}s)")
        print(f"[DEBUG]        Tìm thấy {len(all_products)} products, {len(all_variants_map)} variants\n")
        logger.info(f"[SalesForecastService] Found {len(all_products)} products, {len(all_variants_map)} variants")
        
        # Khởi tạo map variant_id -> SalesForecastDTO
        step_start = time.time()
        print(f"[DEBUG] [BƯỚC 3] Khởi tạo forecast map...")
        forecast_map: Dict[int, SalesForecastDTO] = {}
        for variant_id in all_variants_map.keys():
                forecast_map[variant_id] = SalesForecastDTO(
                    variant_id=variant_id,
                    period_days=days,
                    calculated_at=now.isoformat()
                )
        print(f"[DEBUG] [BƯỚC 3] ✅ Hoàn thành ({time.time() - step_start:.2f}s)")
        print(f"[DEBUG]        Đã khởi tạo {len(forecast_map)} forecast entries\n")
        
        if force_refresh:
            # Chỉ tính toán lại khi force_refresh=True
            print(f"[DEBUG] [BƯỚC 4] 🔄 FORCE REFRESH: Tính toán từ orders (2 kỳ)...")
            logger.info("[SalesForecastService] Force refresh: Calculating from orders...")
            step_start = time.time()
            self._calculate_from_orders(
                forecast_map, 
                created_on_min_current, 
                created_on_max_current,
                created_on_min_previous,
                created_on_max_previous,
                days
            )
            print(f"[DEBUG] [BƯỚC 4] ✅ Hoàn thành ({time.time() - step_start:.2f}s)\n")
            
            # Tính ABC analysis nếu days=30
            if days == 30:
                print(f"[DEBUG] [BƯỚC 5] Tính toán phân loại ABC/Pareto...")
                logger.info("[SalesForecastService] Calculating ABC analysis...")
                step_start = time.time()
                self._calculate_abc_analysis(forecast_map)
                print(f"[DEBUG] [BƯỚC 5] ✅ Hoàn thành ({time.time() - step_start:.2f}s)\n")
                
                # Tính Priority Score nếu days=30
                print(f"[DEBUG] [BƯỚC 5.5] Tính toán Priority Score...")
                logger.info("[SalesForecastService] Calculating Priority Score...")
                step_start = time.time()
                self._calculate_priority_score(forecast_map)
                print(f"[DEBUG] [BƯỚC 5.5] ✅ Hoàn thành ({time.time() - step_start:.2f}s)\n")
            
            # Lưu vào Database
            print(f"[DEBUG] [BƯỚC 6] Lưu dữ liệu vào Database...")
            logger.info("[SalesForecastService] Saving to Database...")
            step_start = time.time()
            self._save_to_database(forecast_map, days)
            print(f"[DEBUG] [BƯỚC 6] ✅ Hoàn thành ({time.time() - step_start:.2f}s)\n")
        else:
            # Chỉ load từ Database, không tính toán lại
            print(f"[DEBUG] [BƯỚC 4] 📥 Load dữ liệu từ Database...")
            logger.info("[SalesForecastService] Loading existing data from Database...")
            step_start = time.time()
            self._load_from_database(forecast_map, days)
            print(f"[DEBUG] [BƯỚC 4] ✅ Hoàn thành ({time.time() - step_start:.2f}s)\n")
            
            # Tính lại tốc độ bán từ dữ liệu đã lưu (nếu có)
            print(f"[DEBUG] [BƯỚC 5] Tính lại tốc độ bán từ dữ liệu đã lưu...")
            logger.info("[SalesForecastService] Recalculating sales rate from saved data...")
            step_start = time.time()
            self._recalculate_from_saved_data(forecast_map, days)
            print(f"[DEBUG] [BƯỚC 5] ✅ Hoàn thành ({time.time() - step_start:.2f}s)\n")
        
        total_time = time.time() - start_time
        print(f"{'='*60}")
        print(f"[DEBUG] ===== HOÀN THÀNH TÍNH TOÁN =====")
        print(f"[DEBUG] Tổng thời gian: {total_time:.2f}s")
        print(f"[DEBUG] Số variants: {len(forecast_map)}")
        print(f"{'='*60}\n")
        
        return forecast_map, all_products, all_variants_map
    
    def _get_all_products(self) -> tuple[List[Dict[str, Any]], Dict[int, Dict[str, Any]]]:
        """
        Lấy tất cả products từ Sapo (đã bao gồm variants và inventories).
        CHỈ lấy variants có packsize = false (1 pcs), loại bỏ packsize = true (combo).
        
        Returns:
            Tuple (all_products, all_variants_map)
            - all_products: List products với variants và inventories
            - all_variants_map: Dict {variant_id: variant_data} để truy cập nhanh (chỉ variants 1 pcs)
        """
        import time
        step_start = time.time()
        
        all_products = []
        all_variants_map: Dict[int, Dict[str, Any]] = {}
        skipped_packsize_count = 0  # Đếm số variants packsize bị bỏ qua
        page = 1
        limit = 250  # Tăng limit lên 250
        
        while True:
            if page == 1 or page % 5 == 0:
                print(f"[DEBUG]        └─ Đang lấy products page {page}...")
            
            page_start = time.time()
            response = self.sapo_client.core.list_products_raw(
                page=page,
                limit=limit,
                status="active",
                product_types="normal"  # Chỉ lấy products có type = normal (loại bỏ packed, combo)
            )
            
            products_data = response.get("products", [])
            if not products_data:
                break
            
            all_products.extend(products_data)
            
            # Extract variants từ products và tạo map
            # CHỈ lấy variants có packsize = false (1 pcs), loại bỏ packsize = true (combo)
            for product in products_data:
                variants = product.get("variants", [])
                for variant in variants:
                    variant_id = variant.get("id")
                    if variant_id:
                        # Bỏ qua variant có packsize = true (combo)
                        packsize = variant.get("packsize", False)
                        if packsize is True:
                            skipped_packsize_count += 1
                            continue
                        # Lưu variant với inventories đã có sẵn
                        all_variants_map[variant_id] = variant
            
            if page == 1 or page % 5 == 0:
                print(f"[DEBUG]        └─ Page {page}: {len(products_data)} products, tổng: {len(all_products)} products, {len(all_variants_map)} variants ({time.time() - page_start:.2f}s)")
            
            if len(products_data) < limit:
                break
            
            page += 1
            
            # Safety limit
            if page > 100:
                logger.warning("[SalesForecastService] Reached max pages limit (100)")
                break
        
        print(f"[DEBUG]        └─ ✅ Tổng cộng {len(all_products)} products, {len(all_variants_map)} variants (1 pcs), đã bỏ qua {skipped_packsize_count} variants packsize (combo) ({time.time() - step_start:.2f}s)")
        if skipped_packsize_count > 0:
            logger.info(f"[SalesForecastService] Skipped {skipped_packsize_count} packsize variants (combo)")
        return all_products, all_variants_map
    
    def _calculate_from_orders(
        self,
        forecast_map: Dict[int, SalesForecastDTO],
        created_on_min_current: str,
        created_on_max_current: str,
        created_on_min_previous: str,
        created_on_max_previous: str,
        days: int
    ):
        """Tính toán từ đơn hàng cho 2 kỳ (xử lý song song)"""
        import time
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        step_start = time.time()
        
        # Dùng ThreadPoolExecutor để xử lý song song 2 kỳ
        print(f"[DEBUG]        └─ Bắt đầu lấy orders 2 kỳ song song từ Sapo...")
        
        # Tạo lock để đảm bảo thread-safe khi update forecast_map
        forecast_lock = threading.Lock()
        
        # Lưu now_iso và days để dùng trong threads (capture từ outer scope)
        now_iso_value = datetime.now(ZoneInfo("UTC")).isoformat()
        days_value = days
        
        def calculate_period_threaded(is_current: bool):
            """Wrapper function để chạy trong thread"""
            try:
                if is_current:
                    print(f"[DEBUG]        └─ [THREAD] Bắt đầu kỳ hiện tại...")
                    self._calculate_period(
                        forecast_map,
                        created_on_min_current,
                        created_on_max_current,
                        is_current_period=True,
                        lock=forecast_lock,
                        now_iso=now_iso_value,
                        days=days_value
                    )
                else:
                    print(f"[DEBUG]        └─ [THREAD] Bắt đầu kỳ trước...")
                    self._calculate_period(
                        forecast_map,
                        created_on_min_previous,
                        created_on_max_previous,
                        is_current_period=False,
                        lock=forecast_lock,
                        now_iso=now_iso_value,
                        days=days_value
                    )
            except Exception as e:
                logger.error(f"[SalesForecastService] Error in thread for {'current' if is_current else 'previous'} period: {e}", exc_info=True)
                print(f"[DEBUG]        └─ [THREAD] ❌ Lỗi kỳ {'hiện tại' if is_current else 'trước'}: {e}")
        
        # Chạy 2 threads song song
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(calculate_period_threaded, True),   # Kỳ hiện tại
                executor.submit(calculate_period_threaded, False)   # Kỳ trước
            ]
            
            # Đợi cả 2 threads hoàn thành
            for future in as_completed(futures):
                try:
                    future.result()  # Kiểm tra exception nếu có
                except Exception as e:
                    logger.error(f"[SalesForecastService] Thread error: {e}", exc_info=True)
        
        print(f"[DEBUG]        └─ ✅ Đã hoàn thành cả 2 kỳ song song trong {time.time() - step_start:.2f}s")
        
        # Tính tốc độ bán và % tăng trưởng
        print(f"[DEBUG]        └─ Tính tốc độ bán và % tăng trưởng cho {len(forecast_map)} variants...")
        calc_start = time.time()
        variants_with_sales = 0
        for forecast in forecast_map.values():
            if days > 0:
                forecast.sales_rate = forecast.total_sold / days
                if forecast.total_sold > 0:
                    variants_with_sales += 1
            else:
                forecast.sales_rate = 0.0
            
            # Tính % tăng trưởng
            if forecast.total_sold_previous_period > 0:
                forecast.growth_percentage = ((forecast.total_sold - forecast.total_sold_previous_period) / forecast.total_sold_previous_period) * 100
            elif forecast.total_sold > 0 and forecast.total_sold_previous_period == 0:
                forecast.growth_percentage = 100.0  # Tăng 100% (từ 0 lên có bán)
            else:
                forecast.growth_percentage = 0.0
        
        # Debug: Log một vài variants có bán để kiểm tra
        sample_variants = []
        for variant_id, forecast in list(forecast_map.items())[:5]:
            if forecast.total_sold > 0:
                sample_variants.append(f"V{variant_id}: {forecast.total_sold} (kỳ trước: {forecast.total_sold_previous_period})")
        if sample_variants:
            print(f"[DEBUG]        └─ Mẫu variants có bán: {', '.join(sample_variants)}")
        
        print(f"[DEBUG]        └─ ✅ {variants_with_sales} variants có lượt bán ({time.time() - calc_start:.2f}s)")
        print(f"[DEBUG]        └─ ✅ Đã tính toán xong trong {time.time() - step_start:.2f}s")
        logger.info(f"[SalesForecastService] Calculated sales for {variants_with_sales} variants (period_days={days})")
    
    def _fetch_orders_page_with_retry(
        self,
        page: int,
        limit: int,
        created_on_min: str,
        created_on_max: str,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch một page orders với retry logic.
        
        Args:
            page: Số trang
            limit: Số lượng orders mỗi trang
            created_on_min: Ngày bắt đầu
            created_on_max: Ngày kết thúc
            max_retries: Số lần retry tối đa
            retry_delay: Thời gian chờ giữa các lần retry (giây)
            
        Returns:
            Response dict hoặc None nếu lỗi
        """
        import time
        
        for attempt in range(max_retries):
            try:
                response = self.sapo_client.core.list_orders_raw(
                    page=page,
                    limit=limit,
                    created_on_min=created_on_min,
                    created_on_max=created_on_max,
                    status=",".join(VALID_ORDER_STATUSES)
                )
                return response
            except Exception as e:
                error_msg = str(e)
                # Kiểm tra nếu là lỗi Bad Gateway hoặc timeout
                if "Bad Gateway" in error_msg or "502" in error_msg or "timeout" in error_msg.lower():
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)  # Exponential backoff
                        logger.warning(f"[SalesForecastService] Bad Gateway/Timeout on page {page}, retry {attempt + 1}/{max_retries} after {wait_time}s")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"[SalesForecastService] Failed to fetch page {page} after {max_retries} retries: {e}")
                        return None
                else:
                    # Lỗi khác, không retry
                    logger.error(f"[SalesForecastService] Error fetching page {page}: {e}")
                    return None
        
        return None
    
    def _process_orders_page(
        self,
        page: int,
        limit: int,
        created_on_min: str,
        created_on_max: str,
        is_current_period: bool,
        forecast_map: Dict[int, SalesForecastDTO],
        lock: Optional[threading.Lock],
        now_iso: str,
        days: int
    ) -> Dict[str, Any]:
        """
        Xử lý một page orders (dùng trong thread).
        
        Returns:
            Dict với keys: orders_count, items_count, accumulator, revenue_accumulator (nếu days=30)
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from decimal import Decimal
        
        local_accumulator: Dict[int, int] = {}
        local_revenue_accumulator: Dict[int, Decimal] = {}  # Chỉ dùng khi days=30
        orders_count = 0
        items_count = 0
        
        # Fetch page với retry
        response = self._fetch_orders_page_with_retry(
            page=page,
            limit=limit,
            created_on_min=created_on_min,
            created_on_max=created_on_max
        )
        
        if not response:
            return {"orders_count": 0, "items_count": 0, "accumulator": {}}
        
        orders_data = response.get("orders", [])
        if not orders_data:
            return {"orders_count": 0, "items_count": 0, "accumulator": {}}
        
        # Process orders
        for order_data in orders_data:
            try:
                order = self.order_service.factory.from_sapo_json(
                    order_data,
                    sapo_client=self.sapo_client
                )
                
                if not order.real_items:
                    continue
                
                # Tạo set các variant_ids có trong real_items để chỉ tính revenue cho những variant này
                real_variant_ids = set()
                for real_item in order.real_items:
                    if real_item.variant_id:
                        real_variant_ids.add(real_item.variant_id)
                
                # Xử lý quantity từ real_items (đã qui đổi)
                for real_item in order.real_items:
                    variant_id = real_item.variant_id
                    if not variant_id:
                        continue
                    
                    # Tạo forecast entry nếu chưa có
                    if variant_id not in forecast_map:
                        if lock:
                            with lock:
                                if variant_id not in forecast_map:
                                    forecast_map[variant_id] = SalesForecastDTO(
                                        variant_id=variant_id,
                                        period_days=days,
                                        calculated_at=now_iso if is_current_period else None
                                    )
                        else:
                            if variant_id not in forecast_map:
                                forecast_map[variant_id] = SalesForecastDTO(
                                    variant_id=variant_id,
                                    period_days=days,
                                    calculated_at=now_iso if is_current_period else None
                                )
                    
                    # Accumulate quantity
                    if variant_id not in local_accumulator:
                        local_accumulator[variant_id] = 0
                    local_accumulator[variant_id] += int(real_item.quantity)
                    items_count += 1
                
                # Tính revenue từ order_line_items (cho period_days=30 hoặc 10 và is_current_period)
                if (days == 30 or days == 10) and is_current_period:
                    for line_item in order.order_line_items:
                        variant_id = line_item.variant_id
                        if not variant_id or variant_id not in real_variant_ids:
                            continue
                        
                        # Bỏ qua các line items không phải sản phẩm
                        if not line_item.product_id or not line_item.variant_id:
                            continue
                        
                        line_amount = float(line_item.line_amount or 0)
                        if line_amount > 0:
                            if variant_id not in local_revenue_accumulator:
                                local_revenue_accumulator[variant_id] = Decimal("0")
                            local_revenue_accumulator[variant_id] += Decimal(str(line_amount))
                
                orders_count += 1
            except Exception as e:
                logger.warning(f"[SalesForecastService] Error processing order {order_data.get('id')}: {e}")
                continue
        
        return {
            "orders_count": orders_count,
            "items_count": items_count,
            "accumulator": local_accumulator,
            "revenue_accumulator": local_revenue_accumulator if (days == 30 or days == 10) else {},
            "has_more": len(orders_data) >= limit
        }
    
    def _calculate_period(
        self,
        forecast_map: Dict[int, SalesForecastDTO],
        created_on_min: str,
        created_on_max: str,
        is_current_period: bool = True,
        lock: Optional[threading.Lock] = None,
        now_iso: Optional[str] = None,
        days: int = 7
    ):
        """Tính toán cho một kỳ cụ thể (thread-safe, multi-threaded pages)"""
        import time
        import threading
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        period_start = time.time()
        
        # Nếu không có now_iso, tạo mới
        if not now_iso:
            now_iso = datetime.now(ZoneInfo("UTC")).isoformat()
        
        limit = 250
        total_orders = 0
        total_items_processed = 0
        
        # Tạo lock cho accumulator nếu chưa có
        if lock is None:
            lock = threading.Lock()
        
        # Tìm số pages đầu tiên để xác định phạm vi
        # Fetch page 1 để biết có bao nhiêu pages
        first_page_result = self._process_orders_page(
            page=1,
            limit=limit,
            created_on_min=created_on_min,
            created_on_max=created_on_max,
            is_current_period=is_current_period,
            forecast_map=forecast_map,
            lock=lock,
            now_iso=now_iso,
            days=days
        )
        
        if not first_page_result.get("has_more", False):
            # Chỉ có 1 page
            total_orders += first_page_result["orders_count"]
            total_items_processed += first_page_result["items_count"]
            # Update accumulator
            with lock:
                for variant_id, quantity in first_page_result["accumulator"].items():
                    if variant_id in forecast_map:
                        if is_current_period:
                            forecast_map[variant_id].total_sold += quantity
                        else:
                            forecast_map[variant_id].total_sold_previous_period += quantity
                
                # Update revenue accumulator (cho days=30 hoặc 10 và is_current_period)
                if (days == 30 or days == 10) and is_current_period and "revenue_accumulator" in first_page_result:
                    for variant_id, revenue in first_page_result["revenue_accumulator"].items():
                        if variant_id in forecast_map:
                            if forecast_map[variant_id].revenue is None:
                                forecast_map[variant_id].revenue = 0.0
                            forecast_map[variant_id].revenue += float(revenue)
                
                # Update revenue accumulator (cho days=30 hoặc 10 và is_current_period)
                if (days == 30 or days == 10) and is_current_period and "revenue_accumulator" in first_page_result:
                    for variant_id, revenue in first_page_result["revenue_accumulator"].items():
                        if variant_id in forecast_map:
                            if forecast_map[variant_id].revenue is None:
                                forecast_map[variant_id].revenue = 0.0
                            forecast_map[variant_id].revenue += float(revenue)
        else:
            # Có nhiều pages, xử lý song song
            # Sử dụng ThreadPoolExecutor với 4-8 workers để fetch pages song song
            max_workers = 6  # Số threads song song cho mỗi kỳ
            page = 2  # Bắt đầu từ page 2 (page 1 đã xử lý)
            max_pages = 1000  # Safety limit
            
            # Update accumulator từ page 1
            total_orders += first_page_result["orders_count"]
            total_items_processed += first_page_result["items_count"]
            with lock:
                for variant_id, quantity in first_page_result["accumulator"].items():
                    if variant_id in forecast_map:
                        if is_current_period:
                            forecast_map[variant_id].total_sold += quantity
                        else:
                            forecast_map[variant_id].total_sold_previous_period += quantity
                
                # Update revenue accumulator (cho days=30 hoặc 10 và is_current_period)
                if (days == 30 or days == 10) and is_current_period and "revenue_accumulator" in first_page_result:
                    for variant_id, revenue in first_page_result["revenue_accumulator"].items():
                        if variant_id in forecast_map:
                            if forecast_map[variant_id].revenue is None:
                                forecast_map[variant_id].revenue = 0.0
                            forecast_map[variant_id].revenue += float(revenue)
            
            # Xử lý các pages còn lại song song
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                has_more = True
                
                while has_more and page <= max_pages:
                    # Submit các pages để xử lý song song
                    while len(futures) < max_workers and page <= max_pages:
                        future = executor.submit(
                            self._process_orders_page,
                            page=page,
                            limit=limit,
                            created_on_min=created_on_min,
                            created_on_max=created_on_max,
                            is_current_period=is_current_period,
                            forecast_map=forecast_map,
                            lock=lock,
                            now_iso=now_iso,
                            days=days
                        )
                        futures[future] = page
                        page += 1
                    
                    # Xử lý các futures hoàn thành
                    for future in as_completed(futures):
                        page_num = futures.pop(future)
                        try:
                            result = future.result()
                            total_orders += result["orders_count"]
                            total_items_processed += result["items_count"]
                            
                            # Update accumulator
                            with lock:
                                for variant_id, quantity in result["accumulator"].items():
                                    if variant_id in forecast_map:
                                        if is_current_period:
                                            forecast_map[variant_id].total_sold += quantity
                                        else:
                                            forecast_map[variant_id].total_sold_previous_period += quantity
                                
                                # Update revenue accumulator (cho days=30 hoặc 10 và is_current_period)
                                if (days == 30 or days == 10) and is_current_period and "revenue_accumulator" in result:
                                    for variant_id, revenue in result["revenue_accumulator"].items():
                                        if variant_id in forecast_map:
                                            if forecast_map[variant_id].revenue is None:
                                                forecast_map[variant_id].revenue = 0.0
                                            forecast_map[variant_id].revenue += float(revenue)
                            
                            # Kiểm tra xem còn pages không
                            if not result.get("has_more", False):
                                has_more = False
                                # Cancel các futures còn lại
                                for f in list(futures.keys()):
                                    f.cancel()
                                futures.clear()
                                break
                            
                            if page_num % 20 == 0:
                                period_name = "hiện tại" if is_current_period else "trước"
                                thread_id = threading.current_thread().name
                                print(f"[DEBUG]        └─ [{thread_id}] Đã xử lý page {page_num} (kỳ {period_name}): {total_orders} orders")
                        except Exception as e:
                            logger.error(f"[SalesForecastService] Error processing page {page_num}: {e}", exc_info=True)
                            continue
        
        period_name = "hiện tại" if is_current_period else "trước"
        thread_id = threading.current_thread().name
        print(f"[DEBUG]        └─ [{thread_id}] ✅ Kỳ {period_name}: {total_orders} orders, {total_items_processed} items trong {time.time() - period_start:.2f}s")
        logger.info(f"[SalesForecastService] Processed {total_orders} orders for {'current' if is_current_period else 'previous'} period")
    
    def _load_from_database(
        self,
        forecast_map: Dict[int, SalesForecastDTO],
        days: int
    ):
        """Load dữ liệu từ Database"""
        import time
        step_start = time.time()
        
        # Lấy tất cả variant_ids
        variant_ids = list(forecast_map.keys())
        if not variant_ids:
            print(f"[DEBUG]        └─ Không có variants để load")
            return
        
        print(f"[DEBUG]        └─ Load forecasts từ Database cho {len(variant_ids)} variants (period_days={days})...")
        logger.info(f"[SalesForecastService] Loading forecasts from Database for {len(variant_ids)} variants")
        
        # Query database với bulk để tối ưu
        # Không cần select_for_update vì chỉ đọc, không cần lock
        forecasts_db = VariantSalesForecast.objects.filter(
            variant_id__in=variant_ids,
            period_days=days
        )
        
        # Tạo map variant_id -> forecast_db
        forecast_db_map = {f.variant_id: f for f in forecasts_db}
        
        loaded_count = 0
        for variant_id, forecast_dto in forecast_map.items():
            if variant_id in forecast_db_map:
                forecast_db = forecast_db_map[variant_id]
                # Copy data từ DB vào DTO
                forecast_dto.total_sold = forecast_db.total_sold
                forecast_dto.total_sold_previous_period = forecast_db.total_sold_previous_period
                forecast_dto.period_days = forecast_db.period_days
                forecast_dto.sales_rate = forecast_db.sales_rate
                forecast_dto.growth_percentage = forecast_db.growth_percentage
                if forecast_db.calculated_at:
                    forecast_dto.calculated_at = forecast_db.calculated_at.isoformat()
                # Revenue field (cho period_days=30 hoặc 10)
                if days == 30 or days == 10:
                    forecast_dto.revenue = float(forecast_db.revenue) if forecast_db.revenue else None
                
                # ABC fields (chỉ cho period_days=30)
                if days == 30:
                    forecast_dto.revenue_percentage = forecast_db.revenue_percentage
                    forecast_dto.cumulative_percentage = forecast_db.cumulative_percentage
                    forecast_dto.abc_category = forecast_db.abc_category
                    forecast_dto.abc_rank = forecast_db.abc_rank
                    
                    # Priority Score fields (chỉ cho period_days=30)
                    forecast_dto.priority_score = forecast_db.priority_score
                    forecast_dto.velocity_stability_score = forecast_db.velocity_stability_score
                    forecast_dto.velocity_score = forecast_db.velocity_score
                    forecast_dto.stability_bonus = forecast_db.stability_bonus
                    forecast_dto.asp_score = forecast_db.asp_score
                    forecast_dto.revenue_contribution_score = forecast_db.revenue_contribution_score
                loaded_count += 1
        
        print(f"[DEBUG]        └─ ✅ Tổng cộng load {loaded_count} forecasts từ Database ({time.time() - step_start:.2f}s)")
        logger.info(f"[SalesForecastService] Loaded {loaded_count} forecasts from Database")
    
    def _save_to_database(
        self,
        forecast_map: Dict[int, SalesForecastDTO],
        days: int
    ):
        """Lưu dữ liệu vào Database"""
        import time
        from django.utils import timezone
        from django.db import transaction
        
        step_start = time.time()
        
        # Lưu tất cả variants (kể cả những variants có total_sold = 0)
        # Để khi load lại có dữ liệu đầy đủ
        forecasts_to_save = list(forecast_map.items())
        
        if not forecasts_to_save:
            print(f"[DEBUG]        └─ Không có dữ liệu để lưu")
            return
        
        # Debug: Đếm số variants có bán
        variants_with_sales = sum(1 for _, f in forecasts_to_save if f.total_sold > 0 or f.total_sold_previous_period > 0)
        print(f"[DEBUG]        └─ Lưu {len(forecasts_to_save)} forecasts vào Database (period_days={days}), trong đó {variants_with_sales} có lượt bán...")
        logger.info(f"[SalesForecastService] Saving {len(forecasts_to_save)} forecasts to Database (period_days={days}), {variants_with_sales} with sales")
        
        # Dùng bulk_update để tối ưu performance
        now = timezone.now()
        saved_count = 0
        updated_count = 0
        created_count = 0
        
        # Batch processing để tránh quá tải
        batch_size = 500
        for i in range(0, len(forecasts_to_save), batch_size):
            batch = forecasts_to_save[i:i+batch_size]
            batch_start = time.time()
            
            with transaction.atomic():
                # Lấy existing records
                variant_ids_batch = [variant_id for variant_id, _ in batch]
                existing_forecasts = VariantSalesForecast.objects.filter(
                    variant_id__in=variant_ids_batch,
                    period_days=days
                )
                existing_map = {f.variant_id: f for f in existing_forecasts}
                
                to_create = []
                to_update = []
                
                for variant_id, forecast_dto in batch:
                    if variant_id in existing_map:
                        # Update existing
                        forecast_db = existing_map[variant_id]
                        forecast_db.total_sold = forecast_dto.total_sold
                        forecast_db.total_sold_previous_period = forecast_dto.total_sold_previous_period
                        forecast_db.sales_rate = forecast_dto.sales_rate
                        forecast_db.growth_percentage = forecast_dto.growth_percentage
                        forecast_db.calculated_at = now
                        # Revenue fields (cho period_days=30 hoặc 10)
                        if days == 30 or days == 10:
                            if forecast_dto.revenue is not None:
                                forecast_db.revenue = Decimal(str(forecast_dto.revenue))
                            else:
                                forecast_db.revenue = None
                        # ABC fields (chỉ cho period_days=30)
                        if days == 30:
                            forecast_db.revenue_percentage = forecast_dto.revenue_percentage
                            forecast_db.cumulative_percentage = forecast_dto.cumulative_percentage
                            forecast_db.abc_category = forecast_dto.abc_category
                            forecast_db.abc_rank = forecast_dto.abc_rank
                            
                            # Priority Score fields (chỉ cho period_days=30)
                            forecast_db.priority_score = forecast_dto.priority_score
                            forecast_db.velocity_stability_score = forecast_dto.velocity_stability_score
                            forecast_db.velocity_score = forecast_dto.velocity_score
                            forecast_db.stability_bonus = forecast_dto.stability_bonus
                            forecast_db.asp_score = forecast_dto.asp_score
                            forecast_db.revenue_contribution_score = forecast_dto.revenue_contribution_score
                        to_update.append(forecast_db)
                    else:
                        # Create new
                        forecast_db = VariantSalesForecast(
                            variant_id=variant_id,
                            period_days=days,
                            total_sold=forecast_dto.total_sold,
                            total_sold_previous_period=forecast_dto.total_sold_previous_period,
                            sales_rate=forecast_dto.sales_rate,
                            growth_percentage=forecast_dto.growth_percentage,
                            calculated_at=now
                        )
                        # Revenue field (cho period_days=30 hoặc 10)
                        if days == 30 or days == 10:
                            if forecast_dto.revenue is not None:
                                forecast_db.revenue = Decimal(str(forecast_dto.revenue))
                            else:
                                forecast_db.revenue = None
                        
                        # ABC fields (chỉ cho period_days=30)
                        if days == 30:
                            forecast_db.revenue_percentage = forecast_dto.revenue_percentage
                            forecast_db.cumulative_percentage = forecast_dto.cumulative_percentage
                            forecast_db.abc_category = forecast_dto.abc_category
                            forecast_db.abc_rank = forecast_dto.abc_rank
                            
                            # Priority Score fields (chỉ cho period_days=30)
                            forecast_db.priority_score = forecast_dto.priority_score
                            forecast_db.velocity_stability_score = forecast_dto.velocity_stability_score
                            forecast_db.velocity_score = forecast_dto.velocity_score
                            forecast_db.stability_bonus = forecast_dto.stability_bonus
                            forecast_db.asp_score = forecast_dto.asp_score
                            forecast_db.revenue_contribution_score = forecast_dto.revenue_contribution_score
                        to_create.append(forecast_db)
                
                # Bulk create và update
                if to_create:
                    VariantSalesForecast.objects.bulk_create(to_create, ignore_conflicts=True)
                    created_count += len(to_create)
                
                if to_update:
                    # Fields cần update
                    update_fields = ['total_sold', 'total_sold_previous_period', 'sales_rate', 'growth_percentage', 'calculated_at']
                    # Revenue cho cả 30 và 10 ngày
                    if days == 30 or days == 10:
                        update_fields.append('revenue')
                    # ABC fields chỉ cho 30 ngày
                    if days == 30:
                        update_fields.extend(['revenue_percentage', 'cumulative_percentage', 'abc_category', 'abc_rank'])
                        # Priority Score fields chỉ cho 30 ngày
                        update_fields.extend([
                            'priority_score', 
                            'velocity_stability_score', 
                            'velocity_score', 
                            'stability_bonus', 
                            'asp_score', 
                            'revenue_contribution_score'
                        ])
                    VariantSalesForecast.objects.bulk_update(
                        to_update,
                        fields=update_fields
                    )
                    updated_count += len(to_update)
            
            saved_count += len(batch)
            if (i // batch_size + 1) % 5 == 0 or i + batch_size >= len(forecasts_to_save):
                print(f"[DEBUG]        └─ Batch {i // batch_size + 1}: Đã xử lý {saved_count}/{len(forecasts_to_save)} forecasts ({time.time() - batch_start:.2f}s)")
        
        print(f"[DEBUG]        └─ ✅ Tổng cộng: {created_count} created, {updated_count} updated ({time.time() - step_start:.2f}s)")
        logger.info(f"[SalesForecastService] Saved {created_count} created, {updated_count} updated forecasts to Database")
    
    def _calculate_abc_analysis(
        self,
        forecast_map: Dict[int, SalesForecastDTO]
    ):
        """
        Tính toán phân loại ABC/Pareto cho variants (chỉ cho period_days=30).
        Phân loại: A (70-80%), B (15-25%), C (5-10%).
        """
        from decimal import Decimal
        
        # Lọc variants có revenue > 0
        variants_with_revenue = [
            (variant_id, forecast) 
            for variant_id, forecast in forecast_map.items()
            if forecast.revenue and forecast.revenue > 0
        ]
        
        if not variants_with_revenue:
            print(f"[DEBUG]        └─ Không có variants có doanh thu để phân loại ABC")
            return
        
        # Tính tổng doanh thu
        total_revenue = sum(f.revenue for _, f in variants_with_revenue)
        print(f"[DEBUG]        └─ Tổng doanh thu: {total_revenue:,.0f} VNĐ từ {len(variants_with_revenue)} variants")
        
        # Sắp xếp theo revenue từ cao xuống thấp
        variants_with_revenue.sort(key=lambda x: x[1].revenue, reverse=True)
        
        # Tính % và % tích lũy, phân loại ABC
        cumulative_revenue = 0.0
        for rank, (variant_id, forecast) in enumerate(variants_with_revenue, start=1):
            revenue = forecast.revenue
            
            # % doanh thu
            if total_revenue > 0:
                revenue_percentage = (revenue / total_revenue) * 100
            else:
                revenue_percentage = 0.0
            
            # % tích lũy
            cumulative_revenue += revenue
            if total_revenue > 0:
                cumulative_percentage = (cumulative_revenue / total_revenue) * 100
            else:
                cumulative_percentage = 0.0
            
            # Phân loại ABC
            if cumulative_percentage <= 80.0:
                abc_category = "A"
            elif cumulative_percentage <= 95.0:
                abc_category = "B"
            else:
                abc_category = "C"
            
            # Cập nhật forecast (abc_rank sẽ được tính lại sau theo từng nhóm)
            forecast.revenue_percentage = revenue_percentage
            forecast.cumulative_percentage = cumulative_percentage
            forecast.abc_category = abc_category
        
        # Tính lại abc_rank cho từng nhóm riêng biệt (top 1, top 2, ... trong mỗi nhóm)
        # Gom variants theo category
        category_a_variants = [(vid, f) for vid, f in variants_with_revenue if f.abc_category == "A"]
        category_b_variants = [(vid, f) for vid, f in variants_with_revenue if f.abc_category == "B"]
        category_c_variants = [(vid, f) for vid, f in variants_with_revenue if f.abc_category == "C"]
        
        # Sắp xếp lại từng nhóm theo revenue từ cao xuống thấp và gán rank
        category_a_variants.sort(key=lambda x: x[1].revenue, reverse=True)
        category_b_variants.sort(key=lambda x: x[1].revenue, reverse=True)
        category_c_variants.sort(key=lambda x: x[1].revenue, reverse=True)
        
        # Gán rank cho nhóm A (top 1, top 2, ...)
        for rank, (variant_id, forecast) in enumerate(category_a_variants, start=1):
            forecast.abc_rank = rank
        
        # Gán rank cho nhóm B (top 1, top 2, ...)
        for rank, (variant_id, forecast) in enumerate(category_b_variants, start=1):
            forecast.abc_rank = rank
        
        # Gán rank cho nhóm C (top 1, top 2, ...)
        for rank, (variant_id, forecast) in enumerate(category_c_variants, start=1):
            forecast.abc_rank = rank
        
        # Đếm theo category
        category_a_count = len(category_a_variants)
        category_b_count = len(category_b_variants)
        category_c_count = len(category_c_variants)
        
        print(f"[DEBUG]        └─ Nhóm A: {category_a_count}, B: {category_b_count}, C: {category_c_count}")
        logger.info(f"[SalesForecastService] ABC Analysis: A={category_a_count}, B={category_b_count}, C={category_c_count}")
    
    def _calculate_priority_score(
        self,
        forecast_map: Dict[int, SalesForecastDTO]
    ):
        """
        Tính toán Priority Score cho variants (chỉ cho period_days=30).
        
        PriorityScore = 45% Velocity Stability Score + 30% ASP Score + 25% Revenue Contribution Score
        
        Velocity Stability Score = VelocityScore + Stability Bonus (tối đa 12)
        - VelocityScore: dựa trên phân vị tốc độ bán (2, 4, 6, 8, 10)
        - Stability Bonus: dựa trên so sánh cùng kỳ 7 ngày (0, 1, 2)
        
        ASP Score: dựa trên phân vị giá trị SKU (2, 4, 6, 8, 10)
        
        Revenue Contribution Score: từ nhóm ABC (A=10, B=7, C=4)
        """
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        
        print(f"[DEBUG]        └─ Bắt đầu tính Priority Score cho {len(forecast_map)} variants...")
        
        # ========== 1. TÍNH VELOCITY STABILITY SCORE ==========
        print(f"[DEBUG]        └─ [1/3] Tính Velocity Stability Score...")
        
        # Lấy dữ liệu 7 ngày để tính stability bonus
        now = datetime.now(ZoneInfo("UTC"))
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=0)
        start_date_current_7d = (end_date - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date_previous_7d = start_date_current_7d - timedelta(seconds=1)
        start_date_previous_7d = (end_date_previous_7d - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Fetch orders 7 ngày để tính stability
        forecast_7d_map: Dict[int, SalesForecastDTO] = {}
        for variant_id in forecast_map.keys():
            forecast_7d_map[variant_id] = SalesForecastDTO(
                variant_id=variant_id,
                period_days=7,
                calculated_at=now.isoformat()
            )
        
        # Tính 7 ngày hiện tại và trước đó
        created_on_min_current_7d = start_date_current_7d.strftime("%Y-%m-%dT%H:%M:%SZ")
        created_on_max_current_7d = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        created_on_min_previous_7d = start_date_previous_7d.strftime("%Y-%m-%dT%H:%M:%SZ")
        created_on_max_previous_7d = end_date_previous_7d.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Tính 7 ngày hiện tại
        self._calculate_period(
            forecast_7d_map,
            created_on_min_current_7d,
            created_on_max_current_7d,
            is_current_period=True,
            lock=None,
            now_iso=now.isoformat(),
            days=7
        )
        
        # Tính 7 ngày trước
        self._calculate_period(
            forecast_7d_map,
            created_on_min_previous_7d,
            created_on_max_previous_7d,
            is_current_period=False,
            lock=None,
            now_iso=now.isoformat(),
            days=7
        )
        
        # Tính tốc độ bán 30 ngày và sắp xếp để tính phân vị
        variants_with_velocity = [
            (variant_id, forecast)
            for variant_id, forecast in forecast_map.items()
            if forecast.sales_rate and forecast.sales_rate > 0
        ]
        
        if not variants_with_velocity:
            print(f"[DEBUG]        └─ Không có variants có tốc độ bán để tính Velocity Score")
            return
        
        # Sắp xếp theo sales_rate từ cao xuống thấp
        variants_with_velocity.sort(key=lambda x: x[1].sales_rate, reverse=True)
        total_skus = len(variants_with_velocity)
        
        # Tính Velocity Score và Stability Bonus cho từng variant
        for rank, (variant_id, forecast) in enumerate(variants_with_velocity, start=1):
            # Velocity Score dựa trên phân vị
            percentile = (rank / total_skus) * 100
            
            if percentile <= 10:
                velocity_score = 10  # Top 10%
            elif percentile <= 30:
                velocity_score = 8   # 10-30%
            elif percentile <= 60:
                velocity_score = 6   # 30-60%
            elif percentile <= 80:
                velocity_score = 4   # 60-80%
            else:
                velocity_score = 2   # 80-100%
            
            # Stability Bonus: so sánh 7 ngày hiện tại vs 7 ngày trước
            forecast_7d = forecast_7d_map.get(variant_id)
            stability_bonus = 0
            
            if forecast_7d and forecast_7d.total_sold_previous_period > 0:
                # Tính % thay đổi
                change_percentage = ((forecast_7d.total_sold - forecast_7d.total_sold_previous_period) / forecast_7d.total_sold_previous_period) * 100
                
                if abs(change_percentage) <= 20:
                    stability_bonus = 2  # SS cùng kỳ 7d +/- 20%
                elif change_percentage >= 20:
                    stability_bonus = 1  # SS cùng kỳ 7d >= 20%
                else:
                    stability_bonus = 0  # SS cùng kỳ 7d < -20%
            elif forecast_7d and forecast_7d.total_sold > 0 and forecast_7d.total_sold_previous_period == 0:
                # Từ 0 lên có bán -> bonus 1
                stability_bonus = 1
            
            # Velocity Stability Score = VelocityScore + Bonus (tối đa 12)
            velocity_stability_score = min(12, velocity_score + stability_bonus)
            
            forecast.velocity_score = velocity_score
            forecast.stability_bonus = stability_bonus
            forecast.velocity_stability_score = velocity_stability_score
        
        print(f"[DEBUG]        └─ ✅ Đã tính Velocity Stability Score cho {len(variants_with_velocity)} variants")
        
        # ========== 2. TÍNH ASP SCORE ==========
        print(f"[DEBUG]        └─ [2/3] Tính ASP Score...")
        
        # Tính ASP cho từng variant: ASP = revenue / total_sold
        variants_with_asp = []
        for variant_id, forecast in forecast_map.items():
            if forecast.revenue and forecast.revenue > 0 and forecast.total_sold and forecast.total_sold > 0:
                asp = forecast.revenue / forecast.total_sold
                variants_with_asp.append((variant_id, forecast, asp))
        
        if not variants_with_asp:
            print(f"[DEBUG]        └─ Không có variants có ASP để tính ASP Score")
        else:
            # Sắp xếp theo ASP từ cao xuống thấp
            variants_with_asp.sort(key=lambda x: x[2], reverse=True)
            total_asp_skus = len(variants_with_asp)
            
            # Tính ASP Score dựa trên phân vị
            for rank, (variant_id, forecast, asp) in enumerate(variants_with_asp, start=1):
                percentile = (rank / total_asp_skus) * 100
                
                if percentile <= 10:
                    asp_score = 10  # Top 10%
                elif percentile <= 30:
                    asp_score = 8   # 10-30%
                elif percentile <= 60:
                    asp_score = 6   # 30-60%
                elif percentile <= 80:
                    asp_score = 4   # 60-80%
                else:
                    asp_score = 2   # 80-100%
                
                forecast.asp_score = asp_score
            
            print(f"[DEBUG]        └─ ✅ Đã tính ASP Score cho {len(variants_with_asp)} variants")
        
        # ========== 3. TÍNH REVENUE CONTRIBUTION SCORE ==========
        print(f"[DEBUG]        └─ [3/3] Tính Revenue Contribution Score (từ ABC)...")
        
        # Revenue Contribution Score từ ABC category
        for variant_id, forecast in forecast_map.items():
            if forecast.abc_category:
                if forecast.abc_category == "A":
                    revenue_contribution_score = 10  # Top 70-80% doanh thu
                elif forecast.abc_category == "B":
                    revenue_contribution_score = 7    # Tiếp theo 15-25%
                else:  # C
                    revenue_contribution_score = 4   # Còn lại
            else:
                revenue_contribution_score = 4  # Mặc định C nếu không có ABC
            
            forecast.revenue_contribution_score = revenue_contribution_score
        
        print(f"[DEBUG]        └─ ✅ Đã tính Revenue Contribution Score cho {len(forecast_map)} variants")
        
        # ========== 4. TÍNH PRIORITY SCORE TỔNG HỢP ==========
        print(f"[DEBUG]        └─ [4/4] Tính Priority Score tổng hợp...")
        
        variants_with_priority = 0
        for variant_id, forecast in forecast_map.items():
            # Chỉ tính nếu có velocity_stability_score và revenue_contribution_score
            # ASP score có thể None nếu không có revenue
            if (forecast.velocity_stability_score is not None and 
                forecast.revenue_contribution_score is not None):
                
                # Normalize các score về thang 0-10
                # Velocity Stability: 0-12 -> 0-10
                velocity_stability_norm = (forecast.velocity_stability_score / 12) * 10
                
                # ASP: 2-10 -> normalize về 0-10 (nếu None thì dùng 0)
                if forecast.asp_score is not None:
                    asp_norm = forecast.asp_score  # Đã là 2-10, giữ nguyên
                else:
                    asp_norm = 0  # Không có ASP thì dùng 0
                
                # Revenue Contribution: 4-10 -> giữ nguyên (đã là 4-10)
                revenue_contribution_norm = forecast.revenue_contribution_score
                
                # PriorityScore = 45% Velocity Stability + 30% ASP + 25% Revenue Contribution
                priority_score = (
                    0.45 * velocity_stability_norm +
                    0.30 * asp_norm +
                    0.25 * revenue_contribution_norm
                )
                
                # Đảm bảo trong khoảng 0-10
                priority_score = max(0.0, min(10.0, priority_score))
                
                forecast.priority_score = round(priority_score, 2)
                variants_with_priority += 1
        
        print(f"[DEBUG]        └─ ✅ Đã tính Priority Score cho {variants_with_priority} variants")
        logger.info(f"[SalesForecastService] Calculated Priority Score for {variants_with_priority} variants")
    
    def _recalculate_from_saved_data(
        self,
        forecast_map: Dict[int, SalesForecastDTO],
        days: int
    ):
        """Tính lại từ dữ liệu đã lưu"""
        import time
        step_start = time.time()
        
        variants_with_sales = 0
        for forecast in forecast_map.values():
            if forecast.total_sold > 0 and days > 0:
                forecast.sales_rate = forecast.total_sold / days
                variants_with_sales += 1
            
            # Tính lại % tăng trưởng nếu có dữ liệu kỳ trước
            if forecast.total_sold_previous_period > 0:
                forecast.growth_percentage = ((forecast.total_sold - forecast.total_sold_previous_period) / forecast.total_sold_previous_period) * 100
            elif forecast.total_sold > 0 and forecast.total_sold_previous_period == 0:
                forecast.growth_percentage = 100.0  # Tăng 100% (từ 0 lên có bán)
            else:
                forecast.growth_percentage = 0.0
        
        print(f"[DEBUG]        └─ ✅ Tính lại tốc độ bán và % tăng trưởng cho {variants_with_sales} variants có lượt bán ({time.time() - step_start:.2f}s)")
    
    def calculate_suggested_purchase_qty(
        self,
        forecast_30: Optional[SalesForecastDTO],
        stock_now: int,
        stock_inbound: int = 0,
        strategy_factor: Optional[float] = None
    ) -> Optional[float]:
        """
        Tính gợi ý số lượng nhập theo công thức mới.
        
        Công thức:
        - L = Leadtime = 20 ngày (thời gian hàng về)
        - V = Tốc độ bán (số lượng/ngày) = sales_rate từ forecast_30
        - MinStock = (Leadtime + 5) * V = 25 * V
        - Cần đủ bán 45 ngày = 45 * V
        - Snow = Tồn hàng hiện tại (stock_now)
        - Sfuture = Tồn hàng vào leadtime sau đó = max(0, Snow - V * L)
        - Sin = Hàng đang về (stock_inbound), mặc định 0
        - F = Hệ số chiến lược: Nhóm A x1.2, Nhóm B và C x1.0
        
        Công thức cuối cùng:
        SuggestQty = round(((Cần đủ bán 45 ngày + MinStock) - Sfuture - Sin) * F)
                   = round(((45 * V + 25 * V) - max(0, Snow - V * 20) - Sin) * F)
                   = round((70 * V - max(0, Snow - V * 20) - Sin) * F)
        
        Args:
            forecast_30: Forecast data 30 ngày
            stock_now: Tồn kho hiện tại (Snow)
            stock_inbound: Hàng đang về (Sin), mặc định 0
            strategy_factor: Hệ số chiến lược (F), nếu None sẽ tự động tính từ ABC category
            
        Returns:
            Suggested purchase quantity hoặc None nếu không thể tính
        """
        if not forecast_30 or forecast_30.sales_rate <= 0:
            return None
        
        # Tính hệ số chiến lược nếu chưa có
        if strategy_factor is None:
            # F = 1.2 nếu Nhóm A, 1.0 nếu Nhóm B hoặc C
            if forecast_30.abc_category == "A":
                strategy_factor = 1.2
            else:
                strategy_factor = 1.0
        
        # L = Leadtime = 20 ngày (thời gian hàng về)
        leadtime = 20
        
        # V = Tốc độ bán (số lượng/ngày)
        velocity = forecast_30.sales_rate
        
        # MinStock = (Leadtime + 5) * V = 25 * V
        min_stock = (leadtime + 5) * velocity
        
        # Cần đủ bán 45 ngày = 45 * V
        need_45_days = 45 * velocity
        
        # Sfuture = Tồn hàng vào leadtime sau đó = max(0, Snow - V * L)
        sfuture = max(0, stock_now - velocity * leadtime)
        
        # Sin = Hàng đang về (mặc định 0)
        sin = stock_inbound
        
        # Số lượng nhập = ((Cần đủ bán 45 ngày + MinStock) - Sfuture - Sin) * F
        suggest = ((need_45_days + min_stock) - sfuture - sin) * strategy_factor
        
        # Đảm bảo không âm và làm tròn
        return round(max(0, suggest))
    
    def get_variant_forecast_with_inventory(
        self,
        variant_id: int,
        forecast_map: Dict[int, SalesForecastDTO],
        variant_data: Optional[Dict[str, Any]] = None,
        product_data: Optional[Dict[str, Any]] = None,
        forecast_30: Optional[SalesForecastDTO] = None
    ) -> Dict[str, Any]:
        """
        Lấy dự báo kèm thông tin tồn kho và số ngày còn bán được.
        
        Args:
            variant_id: Variant ID
            forecast_map: Map forecast data
            variant_data: Variant data từ products (đã có inventories) - nếu None thì sẽ fetch
        
        Returns:
            Dict với các thông tin: forecast, inventory_hn, inventory_sg, total_inventory, 
            days_remaining, warning_color
        """
        try:
            # Nếu không có variant_data, fetch từ API (fallback)
            if not variant_data:
                variant_response = self.sapo_client.core.get_variant_raw(variant_id)
                variant_data = variant_response.get("variant", {})
            
            # Lấy tồn kho từ 2 kho (dùng available - có thể bán, không phải on_hand)
            inventories = variant_data.get("inventories", [])
            inventory_hn = 0
            inventory_sg = 0
            stock_inbound = 0  # Hàng đang về (incoming)
            
            for inv in inventories:
                location_id = inv.get("location_id")
                available = inv.get("available", 0) or 0
                incoming = inv.get("incoming", 0) or 0
                # Nếu tồn âm thì set = 0
                available = max(0, int(available))
                incoming = max(0, int(incoming))
                if location_id == LOCATION_HN:
                    inventory_hn = available
                    stock_inbound += incoming
                elif location_id == LOCATION_SG:
                    inventory_sg = available
                    stock_inbound += incoming
            
            total_inventory = inventory_hn + inventory_sg
            
            # Lấy forecast
            forecast = forecast_map.get(variant_id)
            if not forecast:
                forecast = SalesForecastDTO(
                    variant_id=variant_id,
                    period_days=7
                )
            
            # Tính số ngày còn bán được
            days_remaining = 0.0
            if forecast.sales_rate > 0:
                days_remaining = total_inventory / forecast.sales_rate
            elif total_inventory > 0:
                days_remaining = float('inf')  # Vô hạn nếu không bán
            
            # Xác định màu cảnh báo
            warning_color = "green"  # > 60 ngày
            if days_remaining < 30:
                warning_color = "red"  # < 30 ngày
            elif days_remaining < 60:
                warning_color = "yellow"  # 30-60 ngày
            
            # Convert float('inf') thành None để template có thể xử lý
            days_remaining_display = None if days_remaining == float('inf') else days_remaining
            
            # Lấy ảnh variant (lấy ảnh đầu tiên nếu có)
            image_url = None
            images = variant_data.get("images", [])
            if images and len(images) > 0:
                image_url = images[0].get("full_path") or images[0].get("path")
            
            # Lấy thông tin brand từ product_data (nếu có), fallback về variant_data
            brand = ""
            if product_data:
                brand = product_data.get("brand") or ""
            if not brand:
                brand = variant_data.get("brand") or ""
            
            opt1 = variant_data.get("opt1") or ""  # Tên phân loại
            product_name = variant_data.get("product_name") or variant_data.get("name", "")  # Tên sản phẩm
            
            # Tính gợi ý nhập hàng (dùng forecast_30 nếu có, nếu không dùng forecast hiện tại)
            forecast_for_calc = forecast_30 if forecast_30 else forecast
            # Tạm thời bỏ Sin (hàng đang về) = 0
            suggested_purchase_qty = self.calculate_suggested_purchase_qty(
                forecast_for_calc, 
                stock_now=total_inventory,
                stock_inbound=0  # Tạm thời bỏ qua hàng đang về
            )
            
            # Tính min_stock và sfuture để hiển thị (chỉ khi có forecast_30)
            min_stock = None
            sfuture = None
            if forecast_30 and forecast_30.sales_rate > 0:
                leadtime = 20
                velocity = forecast_30.sales_rate
                min_stock = round((leadtime + 5) * velocity)  # MinStock = 25 * V
                sfuture = int(max(0, total_inventory - velocity * leadtime))  # Sfuture = max(0, Snow - V * L) - làm tròn thành integer
            
            return {
                "variant_id": variant_id,
                "sku": variant_data.get("sku", ""),
                "name": variant_data.get("name", ""),
                "product_name": product_name,  # Tên sản phẩm (không có opt1)
                "opt1": opt1,  # Tên phân loại
                "brand": brand,  # Nhà sản xuất
                "image_url": image_url,  # Ảnh variant để hiển thị
                "forecast": forecast,
                "inventory_hn": inventory_hn,
                "inventory_sg": inventory_sg,
                "total_inventory": total_inventory,
                "days_remaining": days_remaining,
                "days_remaining_display": days_remaining_display,  # None nếu là inf
                "is_infinite": days_remaining == float('inf'),  # Flag để template kiểm tra
                "warning_color": warning_color,
                "growth_percentage": forecast.growth_percentage,  # % tăng trưởng
                "suggested_purchase_qty": suggested_purchase_qty,  # Gợi ý số lượng nhập
                "min_stock": min_stock,  # MinStock để hiển thị
                "sfuture": sfuture,  # Sfuture để hiển thị
            }
        except Exception as e:
            logger.error(f"[SalesForecastService] Error getting variant {variant_id}: {e}", exc_info=True)
            return {
                "variant_id": variant_id,
                "sku": "",
                "name": "",
                "product_name": "",
                "opt1": "",
                "brand": "",
                "image_url": None,  # Không có ảnh
                "forecast": forecast_map.get(variant_id) or SalesForecastDTO(variant_id=variant_id),
                "inventory_hn": 0,
                "inventory_sg": 0,
                "total_inventory": 0,
                "days_remaining": 0.0,
                "days_remaining_display": 0.0,
                "is_infinite": False,
                "warning_color": "gray",
                "suggested_purchase_qty": None,
                "min_stock": None,
                "sfuture": None,
            }
    
    def calculate_supplier_purchase_suggestions_from_db(
        self,
        days: int = 30
    ) -> Dict[str, Dict[str, Any]]:
        """
        Tính gợi ý nhập hàng theo NSX chỉ từ database (không tính toán lại).
        Chỉ load forecast từ DB và lấy products để lấy brand + box_info.
        
        Args:
            days: Số ngày (mặc định 30)
            
        Returns:
            Dict {brand_name: {
                "total_pcs": int,
                "total_boxes": int,
                "total_cbm": float,
                "variants": List[Dict]
            }}
        """
        from products.models import VariantSalesForecast
        from products.services.metadata_helper import extract_gdp_metadata
        import math
        
        logger.info(f"[SalesForecastService] Calculating supplier purchase suggestions from DB only (days={days})")
        
        # Load forecast từ database
        forecasts_db = VariantSalesForecast.objects.filter(period_days=days)
        
        # Tạo forecast_map và lấy danh sách variant_ids
        forecast_map: Dict[int, SalesForecastDTO] = {}
        variant_ids = []
        
        for forecast_db in forecasts_db:
            forecast_dto = SalesForecastDTO(
                variant_id=forecast_db.variant_id,
                total_sold=forecast_db.total_sold,
                total_sold_previous_period=forecast_db.total_sold_previous_period,
                period_days=forecast_db.period_days,
                sales_rate=forecast_db.sales_rate,
                growth_percentage=forecast_db.growth_percentage,
                calculated_at=forecast_db.calculated_at.isoformat() if forecast_db.calculated_at else None
            )
            forecast_map[forecast_db.variant_id] = forecast_dto
            variant_ids.append(forecast_db.variant_id)
        
        if not variant_ids:
            logger.info(f"[SalesForecastService] No forecast data found in database")
            return {}
        
        logger.info(f"[SalesForecastService] Loaded {len(forecast_map)} forecasts from database")
        
        # Lấy products chỉ cho các variants có trong forecast (tối ưu)
        # Fetch products theo batch để lấy brand và box_info
        all_products = []
        all_variants_map: Dict[int, Dict[str, Any]] = {}
        page = 1
        limit = 250
        
        # Fetch products để lấy brand và metadata
        while True:
            response = self.sapo_client.core.list_products_raw(
                page=page,
                limit=limit,
                status="active",
                product_types="normal"
            )
            
            products_data = response.get("products", [])
            if not products_data:
                break
            
            all_products.extend(products_data)
            
            # Extract variants
            for product in products_data:
                variants = product.get("variants", [])
                for variant in variants:
                    variant_id = variant.get("id")
                    if variant_id and variant_id in variant_ids:  # Chỉ lấy variants có trong forecast
                        packsize = variant.get("packsize", False)
                        if packsize is not True:
                            all_variants_map[variant_id] = variant
            
            if len(products_data) < limit:
                break
            
            page += 1
            if page > 100:
                break
        
        logger.info(f"[SalesForecastService] Fetched {len(all_products)} products, {len(all_variants_map)} variants for purchase suggestions")
        
        # Tạo map variant_id -> product_data để lấy brand
        variant_to_product: Dict[int, Dict[str, Any]] = {}
        for product in all_products:
            variants = product.get("variants", [])
            for variant in variants:
                variant_id = variant.get("id")
                if variant_id and variant_id in variant_ids:
                    variant_to_product[variant_id] = product
        
        # Gom theo brand và tính gợi ý nhập
        supplier_suggestions: Dict[str, Dict[str, Any]] = {}
        
        for variant_id, forecast_30 in forecast_map.items():
            # Tính suggested_purchase_qty từ forecast và inventory
            variant_data = all_variants_map.get(variant_id)
            if not variant_data:
                continue
            
            # Lấy tồn kho và hàng đang về
            inventories = variant_data.get("inventories", [])
            total_inventory = 0
            stock_inbound = 0
            for inv in inventories:
                available = inv.get("available", 0) or 0
                incoming = inv.get("incoming", 0) or 0
                total_inventory += max(0, int(available))
                stock_inbound += max(0, int(incoming))
            
            # Tính suggested_purchase_qty
            # Tạm thời bỏ Sin (hàng đang về) = 0
            suggested_purchase_qty = self.calculate_suggested_purchase_qty(
                forecast_30, 
                stock_now=total_inventory,
                stock_inbound=0  # Tạm thời bỏ qua hàng đang về
            )
            
            if not suggested_purchase_qty or suggested_purchase_qty <= 0:
                continue
            
            # Lấy brand từ product_data (ưu tiên) hoặc variant_data
            product_data = variant_to_product.get(variant_id)
            brand = ""
            if product_data:
                brand = product_data.get("brand") or ""
            if not brand:
                brand = variant_data.get("brand") or ""
            brand = brand.strip()
            
            if not brand:
                continue
            
            # Lấy metadata để lấy box_info
            box_info = None
            full_box = None
            box_length = None
            box_width = None
            box_height = None
            
            if product_data:
                description = product_data.get("description") or ""
                if description:
                    metadata, _ = extract_gdp_metadata(description)
                    if metadata:
                        # Tìm variant metadata
                        for v_meta in metadata.variants:
                            if v_meta.id == variant_id and v_meta.box_info:
                                box_info = v_meta.box_info
                                full_box = box_info.full_box
                                box_length = box_info.length_cm
                                box_width = box_info.width_cm
                                box_height = box_info.height_cm
                                break
            
            # Nếu không có box_info, bỏ qua variant này
            if not full_box or full_box <= 0:
                continue
            
            # Tính số thùng: suggested_purchase_qty / full_box
            # Làm tròn lên từ 0.5, dưới 0.5 thì bỏ qua
            boxes_float = suggested_purchase_qty / full_box
            if boxes_float < 0.5:
                continue  # Bỏ qua nếu dưới 0.5 thùng
            
            # Làm tròn lên
            boxes = math.ceil(boxes_float)
            
            # Tính CPM (mét khối) = số thùng * (dài x rộng x cao / 1,000,000)
            cbm = 0.0
            if box_length and box_width and box_height:
                box_volume_cm3 = box_length * box_width * box_height
                box_volume_m3 = box_volume_cm3 / 1_000_000  # Chuyển từ cm³ sang m³
                cbm = boxes * box_volume_m3
            
            # Khởi tạo brand entry nếu chưa có
            if brand not in supplier_suggestions:
                supplier_suggestions[brand] = {
                    "total_pcs": 0,
                    "total_boxes": 0,
                    "total_cbm": 0.0,
                    "variants": []
                }
            
            # Cộng dồn
            supplier_suggestions[brand]["total_pcs"] += int(suggested_purchase_qty)
            supplier_suggestions[brand]["total_boxes"] += boxes
            supplier_suggestions[brand]["total_cbm"] += cbm
            
            # Lưu chi tiết variant
            supplier_suggestions[brand]["variants"].append({
                "variant_id": variant_id,
                "sku": variant_data.get("sku", ""),
                "name": variant_data.get("name", ""),
                "suggested_pcs": int(suggested_purchase_qty),
                "boxes": boxes,
                "cbm": cbm,
                "full_box": full_box
            })
        
        logger.info(f"[SalesForecastService] Calculated purchase suggestions for {len(supplier_suggestions)} suppliers")
        return supplier_suggestions
    
    def calculate_container_template_suggestions(
        self,
        template_suppliers: List[Dict[str, Any]],
        volume_cbm: float
    ) -> Dict[str, Any]:
        """
        Tính gợi ý nhập hàng cho container template.
        
        Args:
            template_suppliers: List suppliers trong container template [
                {"supplier_code": "...", "supplier_name": "..."},
                ...
            ]
            volume_cbm: Thể tích container (m³)
            
        Returns:
            Dict {
                "current_cbm": float,  # Tổng CPM hiện tại
                "percentage": float,     # % đã đủ (0-100)
                "daily_cbm_growth": float,  # Tốc độ tăng CPM/ngày
                "days_to_full": Optional[int],  # Số ngày để đủ container (None nếu không tính được)
                "estimated_date": Optional[str],  # Ngày dự kiến đủ container (format: DD/MM/YYYY)
            }
        """
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        
        # Lấy gợi ý nhập hàng theo NSX
        supplier_suggestions = self.calculate_supplier_purchase_suggestions_from_db(days=30)
        
        if not supplier_suggestions:
            return {
                "current_cbm": 0.0,
                "percentage": 0.0,
                "daily_cbm_growth": 0.0,
                "days_to_full": None,
                "estimated_date": None,
            }
        
        # Tính tổng CPM từ các NSX trong container template
        current_cbm = 0.0
        daily_cbm_growth = 0.0
        
        # Tạo set các brand names từ template suppliers (để match)
        template_brand_names = set()
        for supplier in template_suppliers:
            supplier_code = (supplier.get("supplier_code") or "").strip().upper()
            supplier_name = (supplier.get("supplier_name") or "").strip().upper()
            if supplier_code:
                template_brand_names.add(supplier_code)
            if supplier_name:
                template_brand_names.add(supplier_name)
        
        # Load forecast map để lấy sales_rate
        from products.models import VariantSalesForecast
        forecasts_db = VariantSalesForecast.objects.filter(period_days=30)
        forecast_map = {f.variant_id: f for f in forecasts_db}
        
        # Match và tính tổng
        for brand_name, suggestion_data in supplier_suggestions.items():
            brand_upper = brand_name.upper()
            if brand_upper in template_brand_names:
                current_cbm += suggestion_data.get("total_cbm", 0.0)
                
                # Tính tốc độ tăng CPM/ngày từ tốc độ bán
                # Dựa vào variants trong suggestion để tính daily_cbm_growth
                for variant_info in suggestion_data.get("variants", []):
                    variant_id = variant_info.get("variant_id")
                    if variant_id and variant_id in forecast_map:
                        forecast = forecast_map[variant_id]
                        sales_rate = forecast.sales_rate or 0.0
                        
                        if sales_rate > 0:
                            # Tính CPM/ngày từ sales_rate
                            # CPM/ngày = (sales_rate / full_box) * box_volume_m3
                            full_box = variant_info.get("full_box", 1)
                            if full_box > 0:
                                boxes_per_day = sales_rate / full_box
                                variant_cbm = variant_info.get("cbm", 0.0)
                                variant_boxes = variant_info.get("boxes", 1)
                                if variant_boxes > 0:
                                    box_volume_m3 = variant_cbm / variant_boxes
                                    daily_cbm_growth += boxes_per_day * box_volume_m3
        
        # Tính phần trăm
        percentage = (current_cbm / volume_cbm * 100) if volume_cbm > 0 else 0.0
        percentage = min(100.0, max(0.0, percentage))  # Clamp 0-100
        
        # Tính số ngày để đủ container
        days_to_full = None
        estimated_date = None
        
        if daily_cbm_growth > 0:
            remaining_cbm = volume_cbm - current_cbm
            if remaining_cbm > 0:
                days_to_full = int(remaining_cbm / daily_cbm_growth)
                
                # Tính ngày dự kiến
                now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
                estimated_date_obj = now + timedelta(days=days_to_full)
                estimated_date = estimated_date_obj.strftime("%d/%m/%Y")
        elif current_cbm >= volume_cbm:
            # Đã đủ container
            days_to_full = 0
            estimated_date = "Đã đủ"
        
        return {
            "current_cbm": round(current_cbm, 3),
            "percentage": round(percentage, 1),
            "daily_cbm_growth": round(daily_cbm_growth, 3),
            "days_to_full": days_to_full,
            "estimated_date": estimated_date,
        }
    
    def calculate_supplier_purchase_suggestions(
        self,
        forecast_map_30: Dict[int, SalesForecastDTO],
        all_products: List[Dict[str, Any]],
        all_variants_map: Dict[int, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Tính gợi ý nhập hàng theo NSX (supplier/brand).
        
        Gom tất cả variants có suggested_purchase_qty theo brand và tính:
        - Tổng số lượng pcs cần nhập
        - Số thùng (làm tròn lên từ 0.5, dưới 0.5 thì bỏ qua)
        - Tổng CPM (mét khối)
        
        Args:
            forecast_map_30: Map forecast 30 ngày {variant_id: SalesForecastDTO}
            all_products: Danh sách products từ Sapo
            all_variants_map: Map variants {variant_id: variant_data}
            
        Returns:
            Dict {brand_name: {
                "total_pcs": int,
                "total_boxes": int,
                "total_cbm": float,
                "variants": List[Dict]  # Chi tiết từng variant
            }}
        """
        from products.services.metadata_helper import extract_gdp_metadata
        import math
        
        # Tạo map variant_id -> product_data để lấy brand
        variant_to_product: Dict[int, Dict[str, Any]] = {}
        for product in all_products:
            product_id = product.get("id")
            variants = product.get("variants", [])
            for variant in variants:
                variant_id = variant.get("id")
                if variant_id:
                    variant_to_product[variant_id] = product
        
        # Gom theo brand
        supplier_suggestions: Dict[str, Dict[str, Any]] = {}
        
        for variant_id, forecast_30 in forecast_map_30.items():
            # Chỉ xử lý variants có suggested_purchase_qty > 0
            if not forecast_30.suggested_purchase_qty or forecast_30.suggested_purchase_qty <= 0:
                continue
            
            variant_data = all_variants_map.get(variant_id)
            if not variant_data:
                continue
            
            # Lấy brand từ product_data (ưu tiên) hoặc variant_data
            product_data = variant_to_product.get(variant_id)
            brand = ""
            if product_data:
                brand = product_data.get("brand") or ""
            if not brand:
                brand = variant_data.get("brand") or ""
            brand = brand.strip()
            
            if not brand:
                continue
            
            # Lấy metadata để lấy box_info
            box_info = None
            full_box = None
            box_length = None
            box_width = None
            box_height = None
            
            if product_data:
                description = product_data.get("description") or ""
                if description:
                    metadata, _ = extract_gdp_metadata(description)
                    if metadata:
                        # Tìm variant metadata
                        for v_meta in metadata.variants:
                            if v_meta.id == variant_id and v_meta.box_info:
                                box_info = v_meta.box_info
                                full_box = box_info.full_box
                                box_length = box_info.length_cm
                                box_width = box_info.width_cm
                                box_height = box_info.height_cm
                                break
            
            # Nếu không có box_info, bỏ qua variant này (không thể tính số thùng)
            if not full_box or full_box <= 0:
                continue
            
            # Tính số thùng: suggested_purchase_qty / full_box
            # Làm tròn lên từ 0.5, dưới 0.5 thì bỏ qua
            boxes_float = forecast_30.suggested_purchase_qty / full_box
            if boxes_float < 0.5:
                continue  # Bỏ qua nếu dưới 0.5 thùng
            
            # Làm tròn lên
            boxes = math.ceil(boxes_float)
            
            # Tính CPM (mét khối) = số thùng * (dài x rộng x cao / 1,000,000)
            cbm = 0.0
            if box_length and box_width and box_height:
                box_volume_cm3 = box_length * box_width * box_height
                box_volume_m3 = box_volume_cm3 / 1_000_000  # Chuyển từ cm³ sang m³
                cbm = boxes * box_volume_m3
            
            # Khởi tạo brand entry nếu chưa có
            if brand not in supplier_suggestions:
                supplier_suggestions[brand] = {
                    "total_pcs": 0,
                    "total_boxes": 0,
                    "total_cbm": 0.0,
                    "variants": []
                }
            
            # Cộng dồn
            supplier_suggestions[brand]["total_pcs"] += int(forecast_30.suggested_purchase_qty)
            supplier_suggestions[brand]["total_boxes"] += boxes
            supplier_suggestions[brand]["total_cbm"] += cbm
            
            # Lưu chi tiết variant
            supplier_suggestions[brand]["variants"].append({
                "variant_id": variant_id,
                "sku": variant_data.get("sku", ""),
                "name": variant_data.get("name", ""),
                "suggested_pcs": int(forecast_30.suggested_purchase_qty),
                "boxes": boxes,
                "cbm": cbm,
                "full_box": full_box
            })
        
        return supplier_suggestions

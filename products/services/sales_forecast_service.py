# products/services/sales_forecast_service.py
"""
Service để tính toán dự báo bán hàng và cảnh báo tồn kho.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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
            
            # Lưu vào Database
            print(f"[DEBUG] [BƯỚC 5] Lưu dữ liệu vào Database...")
            logger.info("[SalesForecastService] Saving to Database...")
            step_start = time.time()
            self._save_to_database(forecast_map, days)
            print(f"[DEBUG] [BƯỚC 5] ✅ Hoàn thành ({time.time() - step_start:.2f}s)\n")
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
        """Tính toán cho một kỳ cụ thể (thread-safe)"""
        import time
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        period_start = time.time()
        
        # Nếu không có now_iso, tạo mới
        if not now_iso:
            now_iso = datetime.now(ZoneInfo("UTC")).isoformat()
        
        page = 1
        limit = 250
        total_orders = 0
        total_items_processed = 0
        
        # Tạo local dict để accumulate trước, sau đó update vào forecast_map một lần (giảm lock contention)
        local_accumulator: Dict[int, int] = {}
        
        while True:
            try:
                page_start = time.time()
                if page == 1 or page % 10 == 0:
                    period_name = "hiện tại" if is_current_period else "trước"
                    thread_id = threading.current_thread().name
                    print(f"[DEBUG]        └─ [{thread_id}] Đang lấy page {page} (kỳ {period_name})...")
                
                response = self.sapo_client.core.list_orders_raw(
                    page=page,
                    limit=limit,
                    created_on_min=created_on_min,
                    created_on_max=created_on_max,
                    status=",".join(VALID_ORDER_STATUSES)
                )
                
                orders_data = response.get("orders", [])
                if not orders_data:
                    break
                
                # Convert sang OrderDTO và tính toán vào local accumulator
                for order_data in orders_data:
                    try:
                        order = self.order_service.factory.from_sapo_json(
                            order_data,
                            sapo_client=self.sapo_client
                        )
                        
                        # Lấy real_items (đã bỏ combo, packsize)
                        # TÍNH TẤT CẢ variants từ orders, không chỉ những variants có trong forecast_map
                        # Vì có thể có variants trong orders nhưng không có trong products list (đã xóa, inactive, v.v.)
                        if not order.real_items:
                            # Debug: Log nếu order không có real_items
                            logger.debug(f"[SalesForecastService] Order {order.id} has no real_items")
                            continue
                        
                        for real_item in order.real_items:
                            variant_id = real_item.variant_id
                            if not variant_id:
                                logger.debug(f"[SalesForecastService] real_item has no variant_id: {real_item}")
                                continue
                            
                            # Tạo forecast entry nếu chưa có (cho variants không có trong products list)
                            # Cần lock khi tạo mới entry
                            if variant_id not in forecast_map:
                                if lock:
                                    with lock:
                                        if variant_id not in forecast_map:  # Double check
                                            forecast_map[variant_id] = SalesForecastDTO(
                                                variant_id=variant_id,
                                                period_days=days,
                                                calculated_at=now_iso if is_current_period else None
                                            )
                                else:
                                    # Single-threaded fallback
                                    if variant_id not in forecast_map:
                                        forecast_map[variant_id] = SalesForecastDTO(
                                            variant_id=variant_id,
                                            period_days=days,
                                            calculated_at=now_iso if is_current_period else None
                                        )
                            
                            # Accumulate vào local dict (không cần lock)
                            if variant_id not in local_accumulator:
                                local_accumulator[variant_id] = 0
                            local_accumulator[variant_id] += int(real_item.quantity)
                            total_items_processed += 1
                        
                        total_orders += 1
                    except Exception as e:
                        logger.warning(f"[SalesForecastService] Error processing order {order_data.get('id')}: {e}")
                        continue
                
                if page == 1 or page % 10 == 0:
                    period_name = "hiện tại" if is_current_period else "trước"
                    thread_id = threading.current_thread().name
                    print(f"[DEBUG]        └─ [{thread_id}] Page {page} (kỳ {period_name}): {len(orders_data)} orders, tổng: {total_orders} orders ({time.time() - page_start:.2f}s)")
                
                if len(orders_data) < limit:
                    break
                
                page += 1
                
                # Safety limit
                if page > 1000:
                    logger.warning("[SalesForecastService] Reached max pages limit (1000)")
                    break
                    
            except Exception as e:
                logger.error(f"[SalesForecastService] Error fetching orders page {page}: {e}", exc_info=True)
                break
        
        # Update vào forecast_map một lần với lock (giảm lock contention)
        if lock:
            with lock:
                for variant_id, quantity in local_accumulator.items():
                    if variant_id in forecast_map:
                        if is_current_period:
                            forecast_map[variant_id].total_sold += quantity
                        else:
                            forecast_map[variant_id].total_sold_previous_period += quantity
        else:
            # Fallback nếu không có lock (single-threaded)
            for variant_id, quantity in local_accumulator.items():
                if variant_id in forecast_map:
                    if is_current_period:
                        forecast_map[variant_id].total_sold += quantity
                    else:
                        forecast_map[variant_id].total_sold_previous_period += quantity
        
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
                        to_create.append(forecast_db)
                
                # Bulk create và update
                if to_create:
                    VariantSalesForecast.objects.bulk_create(to_create, ignore_conflicts=True)
                    created_count += len(to_create)
                
                if to_update:
                    VariantSalesForecast.objects.bulk_update(
                        to_update,
                        fields=['total_sold', 'total_sold_previous_period', 'sales_rate', 'growth_percentage', 'calculated_at']
                    )
                    updated_count += len(to_update)
            
            saved_count += len(batch)
            if (i // batch_size + 1) % 5 == 0 or i + batch_size >= len(forecasts_to_save):
                print(f"[DEBUG]        └─ Batch {i // batch_size + 1}: Đã xử lý {saved_count}/{len(forecasts_to_save)} forecasts ({time.time() - batch_start:.2f}s)")
        
        print(f"[DEBUG]        └─ ✅ Tổng cộng: {created_count} created, {updated_count} updated ({time.time() - step_start:.2f}s)")
        logger.info(f"[SalesForecastService] Saved {created_count} created, {updated_count} updated forecasts to Database")
    
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
        total_inventory: int
    ) -> Optional[float]:
        """
        Tính gợi ý số lượng nhập cho 60 ngày.
        
        Công thức:
        - Tỉ lệ tăng trưởng: 1.2 nếu tăng trưởng (growth_percentage > 0), else 1.0
        - Tồn kho dự kiến (15 ngày sau) = tồn kho - tốc độ bán * 15 (min = 0)
        - Gợi ý SL NHẬP = Tỉ lệ tăng trưởng * 60 * tốc độ bán - tồn kho dự kiến
        
        Args:
            forecast_30: Forecast data 30 ngày
            total_inventory: Tổng tồn kho hiện tại
            
        Returns:
            Suggested purchase quantity hoặc None nếu không thể tính
        """
        if not forecast_30 or forecast_30.sales_rate <= 0:
            return None
        
        # Tỉ lệ tăng trưởng: 1.2 nếu có tăng trưởng, else 1.0
        growth_rate = 1.2 if (forecast_30.growth_percentage is not None and forecast_30.growth_percentage > 0) else 1.0
        
        # Tồn kho dự kiến (15 ngày sau) = tồn kho - tốc độ bán * 15 (min = 0)
        expected_inventory = max(0, total_inventory - forecast_30.sales_rate * 15)
        
        # Gợi ý SL NHẬP = Tỉ lệ tăng trưởng * 60 * tốc độ bán - tồn kho dự kiến
        suggested_qty = growth_rate * 60 * forecast_30.sales_rate - expected_inventory
        
        # Đảm bảo không âm
        return max(0, suggested_qty)
    
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
            
            for inv in inventories:
                location_id = inv.get("location_id")
                available = inv.get("available", 0) or 0
                # Nếu tồn âm thì set = 0
                available = max(0, int(available))
                if location_id == LOCATION_HN:
                    inventory_hn = available
                elif location_id == LOCATION_SG:
                    inventory_sg = available
            
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
            suggested_purchase_qty = self.calculate_suggested_purchase_qty(forecast_for_calc, total_inventory)
            
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
            
            # Lấy tồn kho
            inventories = variant_data.get("inventories", [])
            total_inventory = 0
            for inv in inventories:
                available = inv.get("available", 0) or 0
                total_inventory += max(0, int(available))
            
            # Tính suggested_purchase_qty
            suggested_purchase_qty = self.calculate_suggested_purchase_qty(forecast_30, total_inventory)
            
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

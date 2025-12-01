# cskh/services/feedback_service.py
"""
Service để xử lý feedbacks/reviews từ Sapo Marketplace API.
"""

from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import os
import json

from django.utils import timezone
from core.sapo_client import SapoClient
from core.system_settings import get_connection_ids, get_shop_by_connection_id
from cskh.models import Feedback, FeedbackLog
from orders.services.dto import OrderDTO
from products.services.sapo_product_service import SapoProductService

logger = logging.getLogger(__name__)

# Path to log file for saving/loading page number
FEEDBACK_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'settings', 'log_feedback.log')


class FeedbackService:
    """
    Service để xử lý feedbacks từ Sapo MP.
    """
    
    def __init__(self, sapo_client: SapoClient):
        """
        Initialize service với SapoClient.
        
        Args:
            sapo_client: Instance của SapoClient (initialized with tokens)
        """
        self.sapo_client = sapo_client
        self.mp_repo = sapo_client.marketplace
        self.product_service = SapoProductService(sapo_client)
    
    def _load_last_page(self) -> int:
        """
        Đọc page cuối cùng đã request từ log file.
        
        Returns:
            Page number (default: 1 nếu không có log)
        """
        try:
            if os.path.exists(FEEDBACK_LOG_PATH):
                with open(FEEDBACK_LOG_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('last_page', 1)
        except Exception as e:
            logger.warning(f"Error loading last page from log: {e}")
        return 1
    
    def _save_page(self, page: int):
        """
        Lưu page hiện tại vào log file.
        
        Args:
            page: Page number hiện tại
        """
        try:
            # Tạo thư mục nếu chưa có
            os.makedirs(os.path.dirname(FEEDBACK_LOG_PATH), exist_ok=True)
            
            data = {
                'last_page': page,
                'updated_at': datetime.now().isoformat()
            }
            with open(FEEDBACK_LOG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Error saving page to log: {e}")
    
    def sync_feedbacks(
        self,
        tenant_id: int,
        connection_ids: Optional[str] = None,
        rating: str = "1,2,3,4,5",
        limit_per_page: int = 250,
        max_feedbacks: Optional[int] = None,
        num_threads: int = 25
    ) -> Dict[str, Any]:
        """
        Sync feedbacks từ Sapo MP API vào database với multi-threading.
        
        Args:
            tenant_id: Sapo tenant ID (vd: 1262)
            connection_ids: Comma-separated connection IDs. Nếu None, lấy tất cả từ config
            rating: Comma-separated ratings to filter (default: "1,2,3,4,5")
            limit_per_page: Số items mỗi page (default: 250)
            max_feedbacks: Giới hạn số lượng feedbacks để sync (default: 3000)
            num_threads: Số thread để xử lý song song (default: 25)
            
        Returns:
            {
                "success": True/False,
                "total_feedbacks": 100,
                "synced": 50,
                "updated": 10,
                "errors": [...],
                "logs": [...]  # Progress logs
            }
        """
        if not connection_ids:
            connection_ids = get_connection_ids()
        
        # Set default max_feedbacks to 3000 if not provided
        if max_feedbacks is None:
            max_feedbacks = 3000
        
        logger.info(f"[FeedbackService] Starting sync with tenant_id={tenant_id}, connection_ids={connection_ids}, max_feedbacks={max_feedbacks}, threads={num_threads}")
        
        result = {
            "success": True,
            "total_feedbacks": 0,
            "synced": 0,
            "updated": 0,
            "errors": [],
            "logs": []
        }
        
        # Thread-safe counters
        synced_counter = {"value": 0}
        updated_counter = {"value": 0}
        errors_list = []
        logs_list = []
        lock = threading.Lock()
        
        def log_progress(message: str):
            """Thread-safe logging với timestamp"""
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_message = f"[{timestamp}] {message}"
            with lock:
                logs_list.append(log_message)
                logger.info(f"[FeedbackService] {log_message}")
                # Print để debug
                print(f"[FeedbackService] {log_message}")
        
        # Đọc page cuối cùng từ log file
        last_saved_page = self._load_last_page()
        # Bắt đầu từ page đã lưu (tiếp tục từ đó)
        start_page = last_saved_page if last_saved_page > 0 else 1
        page = start_page
        all_feedbacks = []
        feedbacks_fetched_this_run = 0
        
        try:
            log_progress("🚀 Bắt đầu fetch feedbacks từ Sapo MP...")
            log_progress(f"📋 Cấu hình: tenant_id={tenant_id}, max_feedbacks={max_feedbacks}, threads={num_threads}")
            if last_saved_page > 0:
                log_progress(f"📄 Tiếp tục từ page {start_page} (đã lưu trong log_feedback.log)")
            else:
                log_progress(f"📄 Không có log trước đó, bắt đầu từ page 1")
            
            while True:
                log_progress(f"📄 Đang fetch page {page} với limit={limit_per_page}...")
                response = self.mp_repo.list_feedbacks_raw(
                    tenant_id=tenant_id,
                    connection_ids=connection_ids,
                    page=page,
                    limit=limit_per_page,
                    rating=rating
                )
                
                feedbacks = response.get("feedbacks", [])
                if not feedbacks:
                    log_progress(f"Không còn feedbacks, dừng fetch")
                    break
                
                all_feedbacks.extend(feedbacks)
                feedbacks_fetched_this_run += len(feedbacks)
                
                metadata = response.get("metadata", {})
                total = metadata.get("total", 0)
                current_page = metadata.get("page", page)
                limit = metadata.get("limit", limit_per_page)
                
                log_progress(f"📊 Metadata: total={total}, page={current_page}, limit={limit}, fetched={len(feedbacks)}")
                
                # Lưu page hiện tại vào log file sau mỗi lần fetch thành công
                self._save_page(current_page)
                
                # Calculate total_pages if not provided
                if total > 0 and limit > 0:
                    total_pages = (total + limit - 1) // limit
                else:
                    total_pages = current_page
                
                log_progress(f"📄 Page {current_page}/{total_pages}: Đã fetch {len(feedbacks)} feedbacks (Tổng đã lấy trong lần chạy này: {feedbacks_fetched_this_run}/{max_feedbacks})")
                
                # Update result total from metadata
                if result["total_feedbacks"] == 0 or total > result["total_feedbacks"]:
                    result["total_feedbacks"] = total
                
                # Check max_feedbacks limit - dừng khi đã fetch đủ 3000 feedbacks trong lần chạy này
                if feedbacks_fetched_this_run >= max_feedbacks:
                    # Chỉ lấy đủ số lượng cần thiết
                    excess = feedbacks_fetched_this_run - max_feedbacks
                    if excess > 0:
                        all_feedbacks = all_feedbacks[:-excess]
                    log_progress(f"⏹️ Đã đạt giới hạn {max_feedbacks} feedbacks trong lần chạy này, dừng fetch. Page cuối: {current_page}")
                    break
                
                # Check if there are more pages
                # Chỉ dừng nếu:
                # 1. Đã đạt giới hạn max_feedbacks (đã check ở trên)
                # 2. Đã đạt total (nếu có total) - nhưng chỉ dừng nếu chưa đạt max_feedbacks
                # 3. Hoặc current_page >= total_pages
                # 4. Hoặc không còn feedbacks (đã check ở trên)
                
                # Nếu đã đạt max_feedbacks thì không cần check các điều kiện khác
                if feedbacks_fetched_this_run >= max_feedbacks:
                    break
                
                if total > 0 and len(all_feedbacks) >= total:
                    log_progress(f"✅ Đã lấy đủ {total} feedbacks từ metadata")
                    break
                
                if current_page >= total_pages:
                    log_progress(f"✅ Đã fetch hết {total_pages} pages")
                    break
                
                # Nếu page này có ít feedbacks hơn limit, có thể là page cuối
                # Nhưng vẫn tiếp tục nếu chưa đạt total và chưa đạt max_feedbacks
                if len(feedbacks) < limit:
                    if total > 0 and len(all_feedbacks) >= total:
                        log_progress(f"✅ Page cuối, đã đủ {total} feedbacks")
                        break
                    elif feedbacks_fetched_this_run >= max_feedbacks:
                        break
                    else:
                        log_progress(f"⚠️ Page {current_page} có ít feedbacks ({len(feedbacks)} < {limit}), nhưng chưa đạt total. Tiếp tục...")
                
                page += 1
            
            log_progress(f"Hoàn thành fetch: {len(all_feedbacks)} feedbacks")
            
            # Process feedbacks với multi-threading
            log_progress(f"Bắt đầu xử lý {len(all_feedbacks)} feedbacks với {num_threads} threads...")
            
            def process_feedback_batch(feedback_batch: List[Dict[str, Any]], batch_num: int):
                """Process một batch feedbacks"""
                batch_synced = 0
                batch_updated = 0
                batch_errors = []
                
                for feedback_data in feedback_batch:
                    try:
                        updated = self._process_feedback(feedback_data)
                        batch_synced += 1
                        if updated:
                            batch_updated += 1
                        
                        # Log progress mỗi 100 items
                        if batch_synced % 100 == 0:
                            with lock:
                                total_synced = synced_counter["value"] + batch_synced
                                log_progress(f"Thread {batch_num}: Đã xử lý {batch_synced}/{len(feedback_batch)} (Tổng: {total_synced}/{len(all_feedbacks)})")
                    except Exception as e:
                        error_msg = f"Error processing feedback {feedback_data.get('id')}: {str(e)}"
                        batch_errors.append(error_msg)
                        logger.error(error_msg, exc_info=True)
                
                # Update counters
                with lock:
                    synced_counter["value"] += batch_synced
                    updated_counter["value"] += batch_updated
                    errors_list.extend(batch_errors)
                    log_progress(f"Thread {batch_num} hoàn thành: {batch_synced} synced, {batch_updated} updated")
            
            # Chia feedbacks thành batches cho các threads
            batch_size = len(all_feedbacks) // num_threads
            if batch_size == 0:
                batch_size = 1
            
            batches = []
            for i in range(0, len(all_feedbacks), batch_size):
                batches.append((all_feedbacks[i:i + batch_size], i // batch_size + 1))
            
            log_progress(f"Chia thành {len(batches)} batches, mỗi batch ~{batch_size} feedbacks")
            
            # Process với ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = []
                for batch, batch_num in batches:
                    future = executor.submit(process_feedback_batch, batch, batch_num)
                    futures.append(future)
                
                # Wait for all threads to complete
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        error_msg = f"Error in thread: {str(e)}"
                        logger.error(error_msg, exc_info=True)
                        with lock:
                            errors_list.append(error_msg)
            
            # Update result
            result["synced"] = synced_counter["value"]
            result["updated"] = updated_counter["value"]
            result["errors"] = errors_list
            result["total_feedbacks"] = len(all_feedbacks)
            
            # Add final summary log
            final_log = f"✅ Hoàn thành sync: {result['synced']} synced, {result['updated']} updated, {len(result['errors'])} errors"
            log_progress(final_log)
            
            # Copy logs to result (sau khi đã thêm final log)
            result["logs"] = logs_list.copy()
            
            logger.info(f"[FeedbackService] Final result: {result}")
            
        except Exception as e:
            error_msg = f"Error in sync_feedbacks: {str(e)}"
            logger.error(error_msg, exc_info=True)
            with lock:
                errors_list.append(error_msg)
                logs_list.append(f"❌ Lỗi: {error_msg}")
            
            result["errors"] = errors_list
            result["logs"] = logs_list
            result["success"] = False
        
        # Đảm bảo logs luôn được copy vào result
        if "logs" not in result or not result["logs"]:
            result["logs"] = logs_list.copy() if logs_list else ["Không có logs"]
        
        logger.info(f"[FeedbackService] Returning result with {len(result.get('logs', []))} logs")
        return result
    
    def _process_feedback(self, feedback_data: Dict[str, Any]) -> bool:
        """
        Process một feedback từ Sapo MP và lưu/update vào database.
        
        Args:
            feedback_data: Feedback data từ Sapo MP API
            
        Returns:
            True nếu đã update, False nếu không cần update
        """
        feedback_id = feedback_data.get("id")
        if not feedback_id:
            return False
        
        # Get or create feedback
        feedback, created = Feedback.objects.get_or_create(
            feedback_id=feedback_id,
            defaults={
                "tenant_id": feedback_data.get("tenant_id", 0),
                "connection_id": feedback_data.get("connection_id", 0),
                "cmt_id": feedback_data.get("cmt_id"),
                "item_id": feedback_data.get("item_id"),
                "product_name": feedback_data.get("name", ""),
                "product_image": feedback_data.get("image", ""),
                "channel_order_number": feedback_data.get("channel_order_number", ""),
                "buyer_user_name": feedback_data.get("buyer_user_name", ""),
                "rating": feedback_data.get("rating", 0),
                "comment": feedback_data.get("comment", ""),
                "images": self._normalize_media(feedback_data.get("images", [])),
                "status_reply": feedback_data.get("status_reply"),
                "reply": feedback_data.get("reply") or "",  # Đảm bảo không phải None
                "reply_time": feedback_data.get("reply_time"),
                "user_reply": feedback_data.get("user_reply") or "",  # Đảm bảo không phải None
                "reply_type": feedback_data.get("reply_type"),
                "create_time": feedback_data.get("create_time", 0),
            }
        )
        
        if not created:
            # Update existing feedback
            updated = False
            
            # Check if any field changed
            if feedback.rating != feedback_data.get("rating", 0):
                updated = True
            if feedback.comment != feedback_data.get("comment", ""):
                updated = True
            if feedback.reply != feedback_data.get("reply", ""):
                updated = True
            if feedback.status_reply != feedback_data.get("status_reply"):
                updated = True
            
            if updated:
                feedback.rating = feedback_data.get("rating", 0)
                feedback.comment = feedback_data.get("comment", "")
                feedback.reply = feedback_data.get("reply") or ""  # Đảm bảo không phải None
                feedback.status_reply = feedback_data.get("status_reply")
                feedback.reply_time = feedback_data.get("reply_time")
                feedback.user_reply = feedback_data.get("user_reply") or ""  # Đảm bảo không phải None
                feedback.reply_type = feedback_data.get("reply_type")
                feedback.images = self._normalize_media(feedback_data.get("images", []))
                feedback.save()
                return True
        
        # Try to link với Sapo data (order, customer, product)
        self._link_sapo_data(feedback, feedback_data)
        
        return created
    
    def _link_sapo_data(self, feedback: Feedback, feedback_data: Dict[str, Any]):
        """
        Link feedback với Sapo data (order, customer, product, variant) theo yêu cầu FEEDBACK_CENTER.md.
        
        Logic:
        1. Link với Sapo order qua channel_order_number
        2. Từ order, lấy customer và update username nếu chưa có
        3. Tìm product từ item_id bằng cách đọc GDP_META từ tất cả products
        4. Tìm variant_id từ shopee_connections trong GDP_META
        
        Args:
            feedback: Feedback instance
            feedback_data: Feedback data từ API
        """
        try:
            # 1. Link với Sapo order qua channel_order_number
            if feedback.channel_order_number and not feedback.sapo_order_id:
                try:
                    from orders.services.sapo_order_service import SapoOrderService
                    order_service = SapoOrderService(self.sapo_client)
                    
                    # Lấy raw order để có thông tin item_id trong line items
                    raw_order = self.sapo_client.core.get_order_by_reference_number(feedback.channel_order_number)
                    
                    if raw_order:
                        # Convert sang OrderDTO
                        order = order_service.get_order_by_reference(feedback.channel_order_number)
                        
                        if order:
                            feedback.sapo_order_id = order.id
                            
                            # 2. Link với customer từ order và update username
                            if order.customer_id and not feedback.sapo_customer_id:
                                feedback.sapo_customer_id = order.customer_id
                                
                                # Update username vào customer nếu chưa có
                                if feedback.buyer_user_name:
                                    try:
                                        from customers.services.customer_service import CustomerService
                                        customer_service = CustomerService(self.sapo_client)
                                        customer = customer_service.get_customer(order.customer_id)
                                        
                                        if customer:
                                            # Kiểm tra xem customer đã có username chưa
                                            current_username = customer.website or ""
                                            if current_username != feedback.buyer_user_name:
                                                customer_service.update_customer_info(
                                                    customer_id=order.customer_id,
                                                    short_name=feedback.buyer_user_name
                                                )
                                                logger.info(f"Updated customer {order.customer_id} username: {feedback.buyer_user_name}")
                                    except Exception as e:
                                        logger.warning(f"Error updating customer username: {e}")
                            
                            # 3. Link với product và variant từ order line items
                            # Logic mới: Lấy sản phẩm từ đơn hàng, không phải search tất cả products
                            if feedback.item_id:
                                variant_ids = self._find_variant_ids_from_order(
                                    raw_order=raw_order,
                                    item_id=feedback.item_id,
                                    connection_id=feedback.connection_id
                                )
                                
                                if variant_ids:
                                    # Lấy variant đầu tiên (có thể mở rộng để lưu nhiều variants nếu cần)
                                    feedback.sapo_variant_id = variant_ids[0]
                                    
                                    # Lấy product_id từ variant
                                    try:
                                        variant_data = self.sapo_client.core.get_variant_raw(feedback.sapo_variant_id)
                                        if variant_data and variant_data.get('variant'):
                                            feedback.sapo_product_id = variant_data['variant'].get('product_id')
                                    except Exception as e:
                                        logger.warning(f"Error getting variant {feedback.sapo_variant_id}: {e}")
                                    
                                    logger.debug(f"Linked feedback {feedback.feedback_id} with variant {feedback.sapo_variant_id} from order {order.id}")
                                else:
                                    logger.debug(f"Could not find variant in order for item_id={feedback.item_id}, connection_id={feedback.connection_id}")
                            
                            feedback.save()
                            logger.debug(f"Linked feedback {feedback.feedback_id} with order {order.id}")
                except Exception as e:
                    logger.warning(f"Error linking order for feedback {feedback.feedback_id}: {e}")
            
        except Exception as e:
            logger.warning(f"Error linking Sapo data for feedback {feedback.feedback_id}: {e}")
    
    def _find_variant_ids_from_order(self, raw_order: Dict[str, Any], item_id: int, connection_id: int) -> List[int]:
        """
        Tìm variant_ids từ order line items theo item_id.
        
        Logic mới theo yêu cầu:
        1. Lấy các sản phẩm trong đơn hàng (order line items)
        2. Tìm line item có item_id khớp với feedback.item_id
        3. Lấy variant_id từ line item đó
        4. Một feedback có thể có nhiều sản phẩm trong đơn bị đánh giá (list)
        
        Args:
            raw_order: Raw order data từ Sapo API (có chứa line_items)
            item_id: Shopee item_id từ feedback
            connection_id: Shopee connection_id từ feedback
            
        Returns:
            List of variant_ids (có thể nhiều variants nếu nhiều sản phẩm trong đơn)
        """
        variant_ids = []
        
        try:
            order_data = raw_order.get('order', raw_order)  # Có thể là {"order": {...}} hoặc {...}
            line_items = order_data.get('line_items', []) or order_data.get('order_line_items', [])
            
            item_id_str = str(item_id)
            
            logger.debug(f"Searching variant in order for item_id={item_id}, connection_id={connection_id}, line_items_count={len(line_items)}")
            
            # Nếu không tìm thấy item_id trực tiếp trong line_items, 
            # cần match qua variant_id: lấy variant_id từ line_item, sau đó tìm trong GDP_META
            for line_item in line_items:
                variant_id = line_item.get('variant_id')
                if not variant_id:
                    continue
                
                # Thử tìm item_id trực tiếp trong line_item
                line_item_id = None
                if 'item_id' in line_item:
                    line_item_id = str(line_item.get('item_id', ''))
                elif 'product_item_id' in line_item:
                    line_item_id = str(line_item.get('product_item_id', ''))
                
                # Match item_id trực tiếp
                if line_item_id == item_id_str:
                    variant_ids.append(variant_id)
                    logger.debug(f"Found variant {variant_id} in order line item for item_id={item_id} (direct match)")
                else:
                    # Fallback: Match qua GDP_META của variant
                    # Lấy product_id từ line_item
                    product_id = line_item.get('product_id')
                    if product_id:
                        # Lấy product và đọc GDP_META
                        try:
                            product = self.product_service.get_product(product_id)
                            if product and product.gdp_metadata:
                                # Tìm variant trong product metadata
                                for variant_meta in product.gdp_metadata.variants:
                                    if variant_meta.id == variant_id:
                                        # Kiểm tra shopee_connections
                                        if variant_meta.shopee_connections:
                                            for conn in variant_meta.shopee_connections:
                                                conn_connection_id = conn.get('connection_id')
                                                conn_item_id = str(conn.get('item_id', ''))
                                                
                                                if conn_connection_id == connection_id and conn_item_id == item_id_str:
                                                    variant_ids.append(variant_id)
                                                    logger.debug(f"Found variant {variant_id} in order line item for item_id={item_id} (via GDP_META)")
                                                    break
                                        break
                        except Exception as e:
                            logger.debug(f"Error checking GDP_META for variant {variant_id}: {e}")
            
            if variant_ids:
                logger.info(f"Found {len(variant_ids)} variants in order for item_id={item_id}: {variant_ids}")
            else:
                logger.debug(f"No variants found in order for item_id={item_id}, connection_id={connection_id}")
                
        except Exception as e:
            logger.warning(f"Error finding variant from order for item_id {item_id}: {e}")
        
        return variant_ids
    
    def _find_variant_ids_from_item_id(self, item_id: int, connection_id: int) -> List[int]:
        """
        Tìm variant_ids từ item_id bằng cách đọc GDP_META từ products.
        
        Logic theo FEEDBACK_CENTER.md:
        1. Đọc GDP_META từ product description
        2. Tìm trong shopee_connections của variants với connection_id và item_id khớp
        3. Trả về list variant_ids (có thể nhiều variants cùng item_id)
        
        Args:
            item_id: Shopee item_id từ feedback
            connection_id: Shopee connection_id từ feedback
            
        Returns:
            List of variant_ids (có thể nhiều variants cùng item_id)
        """
        from products.services.metadata_helper import extract_gdp_metadata
        
        variant_ids = []
        
        try:
            # Lấy danh sách products từ Sapo
            # Note: Có thể cache để tối ưu performance
            logger.debug(f"Searching variant for item_id={item_id}, connection_id={connection_id}")
            
            # Lấy products từ Sapo (có thể giới hạn số lượng hoặc cache)
            # Theo FEEDBACK_CENTER.md: "Trước khi đồng bộ feedback -> Lấy thông tin toàn bộ products"
            # Tạm thời lấy 1000 products đầu tiên (có thể tăng hoặc cache)
            products = self.product_service.list_products(page=1, limit=250, status='active')
            
            # Nếu cần, có thể paginate để lấy tất cả products
            # Tạm thời chỉ search trong 250 products đầu tiên
            # TODO: Có thể cache products hoặc implement search API nếu có
            
            item_id_str = str(item_id)
            
            for product in products:
                if not product.gdp_metadata or not product.gdp_metadata.variants:
                    continue
                
                # Tìm trong variants của product này
                for variant_meta in product.gdp_metadata.variants:
                    if not variant_meta.shopee_connections:
                        continue
                    
                    # Tìm trong shopee_connections với connection_id và item_id khớp
                    for conn in variant_meta.shopee_connections:
                        conn_connection_id = conn.get('connection_id')
                        conn_item_id = str(conn.get('item_id', ''))
                        
                        if conn_connection_id == connection_id and conn_item_id == item_id_str:
                            # Tìm thấy variant khớp
                            variant_ids.append(variant_meta.id)
                            logger.debug(f"Found variant {variant_meta.id} for item_id={item_id}, connection_id={connection_id}")
                            break  # Break inner loop, tiếp tục variant tiếp theo
            
            if variant_ids:
                logger.info(f"Found {len(variant_ids)} variants for item_id={item_id}, connection_id={connection_id}: {variant_ids}")
            else:
                logger.debug(f"No variants found for item_id={item_id}, connection_id={connection_id}")
            
        except Exception as e:
            logger.warning(f"Error finding variant from item_id {item_id}: {e}")
        
        return variant_ids
    
    def _normalize_media(self, media_data: Any) -> List[str]:
        """
        Normalize media data (images/videos) từ API response.
        
        Args:
            media_data: Có thể là list URLs hoặc dict với keys 'images', 'videos'
            
        Returns:
            List of image URLs
        """
        if not media_data:
            return []
        
        if isinstance(media_data, list):
            return [str(url) for url in media_data if url]
        
        if isinstance(media_data, dict):
            images = media_data.get("images", [])
            videos = media_data.get("videos", [])
            result = []
            if images:
                result.extend([str(url) for url in images if url])
            if videos:
                result.extend([str(url) for url in videos if url])
            return result
        
        return []
    
    def reply_feedback(
        self,
        feedback_id: int,
        reply_content: str,
        tenant_id: int,
        user: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Gửi phản hồi cho feedback.
        
        Args:
            feedback_id: Feedback ID (local database ID)
            reply_content: Nội dung phản hồi
            tenant_id: Sapo tenant ID
            user: User đang phản hồi (để lưu log)
            
        Returns:
            {
                "success": True/False,
                "message": "..."
            }
        """
        try:
            feedback = Feedback.objects.get(id=feedback_id)
            
            # Gửi reply lên Sapo MP
            response = self.mp_repo.reply_feedback_raw(
                feedback_id=feedback.feedback_id,  # Sapo MP feedback ID
                reply_content=reply_content,
                tenant_id=tenant_id
            )
            
            if response.get("success"):
                # Update feedback trong DB
                feedback.reply = reply_content
                feedback.status_reply = "replied"
                feedback.reply_time = int(timezone.now().timestamp())
                feedback.user_reply = user.get_full_name() if user else "System"
                feedback.save()
                
                # Lưu log
                FeedbackLog.objects.create(
                    feedback=feedback,
                    action_type="reply",
                    action_data={
                        "reply_content": reply_content,
                        "sapo_response": response
                    },
                    user=user,
                    user_name=user.get_full_name() if user else "System",
                    rating_before=feedback.rating,
                    note=f"Phản hồi đánh giá: {reply_content[:100]}"
                )
                
                logger.info(f"✓ Replied to feedback {feedback.feedback_id} by {user.get_full_name() if user else 'System'}")
                
                return {
                    "success": True,
                    "message": "Đã gửi phản hồi thành công"
                }
            else:
                return {
                    "success": False,
                    "message": response.get("message", "Lỗi không xác định")
                }
                
        except Feedback.DoesNotExist:
            return {
                "success": False,
                "message": "Không tìm thấy feedback"
            }
        except Exception as e:
            logger.error(f"Error replying to feedback {feedback_id}: {e}", exc_info=True)
            return {
                "success": False,
                "message": str(e)
            }
    
    def create_ticket_from_bad_review(
        self,
        feedback_id: int,
        user: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Tạo ticket từ bad review.
        
        Args:
            feedback_id: Feedback ID (local database ID)
            user: User đang tạo ticket
            
        Returns:
            {
                "success": True/False,
                "ticket_id": int,
                "ticket_number": str,
                "message": "..."
            }
        """
        try:
            from cskh.models import Ticket
            from orders.services.sapo_order_service import SapoOrderService
            
            feedback = Feedback.objects.get(id=feedback_id)
            
            # Đảm bảo feedback đã được link với Sapo order
            order_id = feedback.sapo_order_id
            customer_id = feedback.sapo_customer_id
            order_code = None
            location_id = None
            
            # Nếu chưa có order_id, thử link lại
            if not order_id and feedback.channel_order_number:
                try:
                    order_service = SapoOrderService(self.sapo_client)
                    order = order_service.get_order_by_reference(feedback.channel_order_number)
                    
                    if order:
                        order_id = order.id
                        customer_id = order.customer_id
                        order_code = order.code
                        location_id = order.location_id
                        
                        # Update feedback với order_id
                        feedback.sapo_order_id = order_id
                        if customer_id and not feedback.sapo_customer_id:
                            feedback.sapo_customer_id = customer_id
                        feedback.save()
                        
                        logger.info(f"Linked feedback {feedback.feedback_id} with order {order_id} when creating ticket")
                except Exception as e:
                    logger.warning(f"Error linking order when creating ticket: {e}")
            
            # Nếu đã có order_id nhưng chưa có order_code, thử lấy từ order
            if order_id and not order_code:
                try:
                    order_service = SapoOrderService(self.sapo_client)
                    order = order_service.get_order_dto(order_id)
                    
                    if order:
                        order_code = order.code
                        if not customer_id:
                            customer_id = order.customer_id
                        if not location_id:
                            location_id = order.location_id
                except Exception as e:
                    logger.warning(f"Error getting order details: {e}")
            
            # Lấy variants_issue từ feedback
            variants_issue = []
            if feedback.sapo_variant_id:
                variants_issue = [feedback.sapo_variant_id]
            
            # Tạo ticket
            ticket = Ticket.objects.create(
                order_id=order_id,
                order_code=order_code or feedback.channel_order_number,
                reference_number=feedback.channel_order_number,
                customer_id=customer_id,
                customer_name=feedback.buyer_user_name,
                location_id=location_id,
                shop=feedback.shop_name,
                rating=feedback.rating,
                ticket_type="bad_review",
                ticket_status="new",
                source_ticket="automation",
                depart="cskh",
                note=f"Tự động tạo từ đánh giá xấu: {feedback.comment[:200]}",
                created_by=user,
                variants_issue=variants_issue
            )
            
            # Link feedback với ticket
            feedback.ticket = ticket
            feedback.save()
            
            # Lưu log
            FeedbackLog.objects.create(
                feedback=feedback,
                action_type="create_ticket",
                action_data={
                    "ticket_id": ticket.id,
                    "ticket_number": ticket.ticket_number,
                    "order_id": order_id,
                    "order_code": order_code
                },
                user=user,
                user_name=user.get_full_name() if user else "System",
                rating_before=feedback.rating,
                note=f"Tạo ticket {ticket.ticket_number} từ đánh giá xấu"
            )
            
            logger.info(f"✓ Created ticket {ticket.ticket_number} from feedback {feedback.feedback_id} with order_id={order_id}")
            
            return {
                "success": True,
                "ticket_id": ticket.id,
                "ticket_number": ticket.ticket_number,
                "message": f"Đã tạo ticket {ticket.ticket_number}"
            }
            
        except Feedback.DoesNotExist:
            return {
                "success": False,
                "message": "Không tìm thấy feedback"
            }
        except Exception as e:
            logger.error(f"Error creating ticket from feedback {feedback_id}: {e}", exc_info=True)
            return {
                "success": False,
                "message": str(e)
            }


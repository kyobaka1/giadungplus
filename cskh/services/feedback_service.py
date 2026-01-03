# cskh/services/feedback_service.py
"""
Service để xử lý feedbacks/reviews từ Shopee API và Sapo Marketplace API.
"""

from typing import Dict, Any, List, Optional, Callable
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import threading
# Removed ThreadPoolExecutor - using sequential processing only
import time
import os
import json
import math

from django.utils import timezone
from core.sapo_client import SapoClient
from core.shopee_client import ShopeeClient
from core.system_settings import get_connection_ids, get_shop_by_connection_id, load_shopee_shops_detail
from cskh.models import Feedback, FeedbackLog
from orders.services.dto import OrderDTO
from products.services.sapo_product_service import SapoProductService

logger = logging.getLogger(__name__)

# Path to log file for saving/loading page number
FEEDBACK_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'settings', 'log_feedback.log')


class FeedbackService:
    """
    Service để xử lý feedbacks từ Shopee API và Sapo MP.
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
        # Cache index: (connection_id, item_id_str) -> List[variant_id]
        # Được build 1 lần cho mỗi lần chạy sync Shopee để tránh gọi Sapo liên tục.
        self._shopee_variant_index: Optional[Dict[tuple, List[int]]] = None
    
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
    
    def _fetch_feedbacks_with_retry(
        self,
        tenant_id: int,
        connection_ids: str,
        page: int,
        limit_per_page: int,
        rating: str,
        max_retries: int = 5,
        retry_delay: int = 3
    ) -> Dict[str, Any]:
        """
        Fetch feedbacks từ API với retry logic.
        
        Args:
            tenant_id: Sapo tenant ID
            connection_ids: Comma-separated connection IDs
            page: Page number
            limit_per_page: Items per page
            rating: Comma-separated ratings
            max_retries: Số lần retry tối đa (default: 5)
            retry_delay: Thời gian nghỉ giữa các lần retry (giây, default: 3)
            
        Returns:
            Response dict từ API
            
        Raises:
            Exception: Nếu tất cả các lần retry đều thất bại
        """
        last_exception = None
        
        for attempt in range(1, max_retries + 1):
            try:
                response = self.mp_repo.list_feedbacks_raw(
                    tenant_id=tenant_id,
                    connection_ids=connection_ids,
                    page=page,
                    limit=limit_per_page,
                    rating=rating
                )
                # Nếu thành công, trả về response
                if attempt > 1:
                    logger.info(f"[FeedbackService] Fetch page {page} thành công sau {attempt} lần thử")
                return response
            except Exception as e:
                last_exception = e
                logger.warning(f"[FeedbackService] Lỗi khi fetch page {page} (lần thử {attempt}/{max_retries}): {e}")
                
                # Nếu chưa phải lần thử cuối, đợi rồi thử lại
                if attempt < max_retries:
                    logger.info(f"[FeedbackService] Đợi {retry_delay} giây trước khi thử lại...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"[FeedbackService] Đã thử {max_retries} lần nhưng vẫn thất bại khi fetch page {page}")
        
        # Nếu tất cả các lần thử đều thất bại, raise exception
        raise Exception(f"Không thể fetch page {page} sau {max_retries} lần thử: {str(last_exception)}")
    
    def sync_feedbacks(
        self,
        tenant_id: int,
        connection_ids: Optional[str] = None,
        rating: str = "1,2,3,4,5",
        limit_per_page: int = 250,
        max_feedbacks: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Sync feedbacks từ Sapo MP API vào database (xử lý tuần tự).
        
        Args:
            tenant_id: Sapo tenant ID (vd: 1262)
            connection_ids: Comma-separated connection IDs. Nếu None, lấy tất cả từ config
            rating: Comma-separated ratings to filter (default: "1,2,3,4,5")
            limit_per_page: Số items mỗi page (default: 250)
            max_feedbacks: Giới hạn số lượng feedbacks để sync (default: 5000)
            
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
        
        # Set default max_feedbacks to 5000 if not provided
        if max_feedbacks is None:
            max_feedbacks = 5000
        
        logger.info(f"[FeedbackService] Starting sync with tenant_id={tenant_id}, connection_ids={connection_ids}, max_feedbacks={max_feedbacks}")
        
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
            log_progress(f"📋 Cấu hình: tenant_id={tenant_id}, max_feedbacks={max_feedbacks}")
            if last_saved_page > 0:
                log_progress(f"📄 Tiếp tục từ page {start_page} (đã lưu trong log_feedback.log)")
            else:
                log_progress(f"📄 Không có log trước đó, bắt đầu từ page 1")
            
            while True:
                log_progress(f"📄 Đang fetch page {page} với limit={limit_per_page}...")
                try:
                    response = self._fetch_feedbacks_with_retry(
                        tenant_id=tenant_id,
                        connection_ids=connection_ids,
                        page=page,
                        limit_per_page=limit_per_page,
                        rating=rating,
                        max_retries=5,
                        retry_delay=3
                    )
                except Exception as e:
                    error_msg = f"Lỗi khi fetch page {page} sau 5 lần thử: {str(e)}"
                    log_progress(f"❌ {error_msg}")
                    logger.error(error_msg, exc_info=True)
                    with lock:
                        errors_list.append(error_msg)
                    # Tiếp tục với page tiếp theo thay vì dừng hoàn toàn
                    page += 1
                    continue
                
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
                
                # Check max_feedbacks limit - dừng khi đã fetch đủ 5000 feedbacks trong lần chạy này
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
            
            # Process feedbacks tuần tự (không dùng threading)
            log_progress(f"Bắt đầu xử lý {len(all_feedbacks)} feedbacks tuần tự...")
            
            # Xử lý từng feedback một
            for idx, feedback_data in enumerate(all_feedbacks, 1):
                try:
                    updated = self._process_feedback(feedback_data)
                    with lock:
                        synced_counter["value"] += 1
                        if updated:
                            updated_counter["value"] += 1
                    
                    # Log progress mỗi 100 items
                    if synced_counter["value"] % 100 == 0:
                        progress_msg = f"Đã xử lý {synced_counter['value']}/{len(all_feedbacks)} feedbacks"
                        log_progress(progress_msg)
                except Exception as e:
                    error_msg = f"Error processing feedback {feedback_data.get('id')}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    with lock:
                        synced_counter["value"] += 1
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
        
        # Kiểm tra comment_id nếu có để tránh trùng lặp
        comment_id = feedback_data.get("comment_id")
        
        # Dùng feedback_id làm unique key (chính)
        # Nếu có comment_id, set feedback_id = comment_id
        if comment_id and not feedback_id:
            feedback_id = comment_id
        
        # Kiểm tra feedback_id đã tồn tại chưa
        try:
            existing_feedback = Feedback.objects.filter(feedback_id=feedback_id).first()
            if existing_feedback:
                logger.debug(f"Feedback với feedback_id {feedback_id} đã tồn tại (ID: {existing_feedback.id}), sẽ update")
                feedback = existing_feedback
                created = False
            else:
                # Tạo mới với feedback_id làm unique key
                feedback, created = Feedback.objects.get_or_create(
                    feedback_id=feedback_id,
                    defaults={
                        "comment_id": comment_id,  # Giữ lại để tương thích
                        "tenant_id": feedback_data.get("tenant_id", 0),
                        "connection_id": feedback_data.get("connection_id", 0),
                        "item_id": feedback_data.get("item_id"),
                        "product_name": feedback_data.get("name", ""),
                        "product_image": feedback_data.get("image", ""),
                        "channel_order_number": feedback_data.get("channel_order_number", ""),
                        "buyer_user_name": feedback_data.get("buyer_user_name", ""),
                        "rating": feedback_data.get("rating", 0),
                        "comment": feedback_data.get("comment", ""),
                        "images": self._normalize_media(feedback_data.get("images", [])),
                        "status_reply": feedback_data.get("status_reply"),
                        "reply": feedback_data.get("reply") or "",
                        "reply_time": feedback_data.get("reply_time"),
                        "user_reply": feedback_data.get("user_reply") or "",
                        "reply_type": feedback_data.get("reply_type"),
                        "create_time": feedback_data.get("create_time", 0),
                    }
                )
        except Exception as e:
            logger.warning(f"Error checking feedback_id {feedback_id}: {e}")
            # Fallback về logic cũ nếu có lỗi
            feedback, created = Feedback.objects.get_or_create(
                feedback_id=feedback_id,
                defaults={
                    "comment_id": comment_id,
                    "tenant_id": feedback_data.get("tenant_id", 0),
                    "connection_id": feedback_data.get("connection_id", 0),
                    "item_id": feedback_data.get("item_id"),
                    "product_name": feedback_data.get("name", ""),
                    "product_image": feedback_data.get("image", ""),
                    "channel_order_number": feedback_data.get("channel_order_number", ""),
                    "buyer_user_name": feedback_data.get("buyer_user_name", ""),
                    "rating": feedback_data.get("rating", 0),
                    "comment": feedback_data.get("comment", ""),
                    "images": self._normalize_media(feedback_data.get("images", [])),
                    "status_reply": feedback_data.get("status_reply"),
                    "reply": feedback_data.get("reply") or "",
                    "reply_time": feedback_data.get("reply_time"),
                    "user_reply": feedback_data.get("user_reply") or "",
                    "reply_type": feedback_data.get("reply_type"),
                    "create_time": feedback_data.get("create_time", 0),
                }
            )
        else:
            # Không có comment_id, dùng feedback_id làm key
            feedback, created = Feedback.objects.get_or_create(
                feedback_id=feedback_id,
                defaults={
                "comment_id": None,  # Không có comment_id
                "tenant_id": feedback_data.get("tenant_id", 0),
                "connection_id": feedback_data.get("connection_id", 0),
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
            
            # Đảm bảo đã có index Shopee (được build 1 lần cho mỗi lần sync)
            self._ensure_shopee_variant_index()
            index = self._shopee_variant_index or {}
            key = (connection_id, item_id_str)
            indexed_variants = set(index.get(key, []))

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
                # Nếu không khớp trực tiếp, fallback: dùng index đã build từ GDP_META
                elif indexed_variants and variant_id in indexed_variants:
                    variant_ids.append(variant_id)
                    logger.debug(
                        f"Found variant {variant_id} in order line item for item_id={item_id} "
                        f"(via preloaded Shopee index)"
                    )
            
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
        variant_ids: List[int] = []
        
        try:
            # Đảm bảo index đã được build
            self._ensure_shopee_variant_index()
            if not self._shopee_variant_index:
                logger.debug("Shopee variant index is empty; cannot resolve item_id → variant_id")
                return []

            item_id_str = str(item_id)
            key = (connection_id, item_id_str)
            variant_ids = list(self._shopee_variant_index.get(key, []))

            if variant_ids:
                logger.info(
                    f"Found {len(variant_ids)} variants in preloaded index "
                    f"for item_id={item_id}, connection_id={connection_id}: {variant_ids}"
                )
            else:
                logger.debug(
                    f"No variants found in preloaded index for item_id={item_id}, "
                    f"connection_id={connection_id}"
                )
            
        except Exception as e:
            logger.warning(f"Error finding variant from item_id {item_id} using index: {e}")
        
        return variant_ids

    def _ensure_shopee_variant_index(self):
        """
        Build index (connection_id, item_id) -> [variant_id] từ toàn bộ products trên Sapo.
        Chỉ chạy 1 lần cho mỗi vòng đời FeedbackService (hoặc mỗi lần sync), 
        tránh việc gọi list_products / get_product lặp lại trong từng feedback.
        """
        if self._shopee_variant_index is not None:
            return

        logger.info("[FeedbackService] Building Shopee variant index from all Sapo products...")
        index: Dict[tuple, List[int]] = {}

        try:
            start_time = time.time()
            page = 1
            limit = 250
            total_products = 0

            while True:
                products = self.product_service.list_products(page=page, limit=limit, status='active')
                if not products:
                    break

                total_products += len(products)

                for product in products:
                    if not product.gdp_metadata or not product.gdp_metadata.variants:
                        continue

                    for variant_meta in product.gdp_metadata.variants:
                        if not variant_meta.shopee_connections:
                            continue

                        for conn in variant_meta.shopee_connections:
                            conn_connection_id = conn.get('connection_id')
                            conn_item_id = conn.get('item_id')
                            if not conn_connection_id or not conn_item_id:
                                continue

                            key = (int(conn_connection_id), str(conn_item_id))
                            index.setdefault(key, []).append(variant_meta.id)

                page += 1

            self._shopee_variant_index = index
            duration = time.time() - start_time
            logger.info(
                f"[FeedbackService] Built Shopee variant index with {len(index)} keys "
                f"from {total_products} products in {duration:.2f}s"
            )
        except Exception as e:
            logger.error(f"[FeedbackService] Error building Shopee variant index: {e}", exc_info=True)
            # Nếu lỗi, vẫn giữ index = {}, tránh None để không build lại liên tục
            self._shopee_variant_index = self._shopee_variant_index or {}
    
    def _extract_reply_comment(self, reply_data: Any) -> str:
        """
        Extract comment từ reply object của Shopee API.
        Reply có thể là:
        - Dict: {"comment": "...", "ctime": 123, ...}
        - JSON String: '{"comment": "...", "ctime": 123, ...}'
        - String: "..." (trường hợp cũ - plain text)
        - None: không có reply
        """
        if not reply_data:
            return ""
        
        if isinstance(reply_data, dict):
            return reply_data.get("comment", "") or ""
        elif isinstance(reply_data, str):
            # Thử parse JSON string nếu có
            if reply_data.strip().startswith("{") or reply_data.strip().startswith("'"):
                try:
                    import json
                    # Thử parse JSON string
                    parsed = json.loads(reply_data)
                    if isinstance(parsed, dict):
                        return parsed.get("comment", "") or ""
                except (json.JSONDecodeError, ValueError, TypeError):
                    # Nếu không parse được, có thể là string representation của dict
                    # Thử eval (cẩn thận với security, nhưng đây là dữ liệu từ API)
                    try:
                        import ast
                        parsed = ast.literal_eval(reply_data)
                        if isinstance(parsed, dict):
                            return parsed.get("comment", "") or ""
                    except (ValueError, SyntaxError, TypeError):
                        pass
            # Nếu không phải JSON, trả về string gốc
            return reply_data
        else:
            # Nếu là object khác, thử convert sang string và parse
            reply_str = str(reply_data)
            if reply_str.strip().startswith("{") or reply_str.strip().startswith("'"):
                try:
                    import json
                    parsed = json.loads(reply_str)
                    if isinstance(parsed, dict):
                        return parsed.get("comment", "") or ""
                except (json.JSONDecodeError, ValueError, TypeError):
                    try:
                        import ast
                        parsed = ast.literal_eval(reply_str)
                        if isinstance(parsed, dict):
                            return parsed.get("comment", "") or ""
                    except (ValueError, SyntaxError, TypeError):
                        pass
            return reply_str if reply_data else ""
    
    def _extract_reply_time(self, reply_data: Any) -> Optional[int]:
        """
        Extract ctime (timestamp) từ reply object của Shopee API.
        Reply có thể là:
        - Dict: {"comment": "...", "ctime": 123, ...}
        - JSON String: '{"comment": "...", "ctime": 123, ...}'
        - String hoặc None: không có timestamp
        """
        if not reply_data:
            return None
        
        if isinstance(reply_data, dict):
            ctime = reply_data.get("ctime")
            if ctime:
                try:
                    return int(ctime)
                except (ValueError, TypeError):
                    return None
        elif isinstance(reply_data, str):
            # Thử parse JSON string nếu có
            if reply_data.strip().startswith("{") or reply_data.strip().startswith("'"):
                try:
                    import json
                    parsed = json.loads(reply_data)
                    if isinstance(parsed, dict):
                        ctime = parsed.get("ctime")
                        if ctime:
                            try:
                                return int(ctime)
                            except (ValueError, TypeError):
                                return None
                except (json.JSONDecodeError, ValueError, TypeError):
                    try:
                        import ast
                        parsed = ast.literal_eval(reply_data)
                        if isinstance(parsed, dict):
                            ctime = parsed.get("ctime")
                            if ctime:
                                try:
                                    return int(ctime)
                                except (ValueError, TypeError):
                                    return None
                    except (ValueError, SyntaxError, TypeError):
                        pass
        else:
            # Nếu là object khác, thử convert sang string và parse
            reply_str = str(reply_data)
            if reply_str.strip().startswith("{") or reply_str.strip().startswith("'"):
                try:
                    import json
                    parsed = json.loads(reply_str)
                    if isinstance(parsed, dict):
                        ctime = parsed.get("ctime")
                        if ctime:
                            try:
                                return int(ctime)
                            except (ValueError, TypeError):
                                return None
                except (json.JSONDecodeError, ValueError, TypeError):
                    try:
                        import ast
                        parsed = ast.literal_eval(reply_str)
                        if isinstance(parsed, dict):
                            ctime = parsed.get("ctime")
                            if ctime:
                                try:
                                    return int(ctime)
                                except (ValueError, TypeError):
                                    return None
                    except (ValueError, SyntaxError, TypeError):
                        pass
        return None
    
    def _normalize_media(self, media_data: Any) -> List[str]:
        """
        Normalize media data (images/videos) từ API response.
        Nếu image chỉ là ID (vd: vn-11134103-820l4-mj16ni7wn8qt20), thêm prefix https://cf.shopee.vn/file/
        
        Args:
            media_data: Có thể là list URLs hoặc dict với keys 'images', 'videos'
            
        Returns:
            List of image URLs (đã normalize)
        """
        if not media_data:
            return []
        
        def normalize_image_url(url: str) -> str:
            """Normalize một image URL: thêm prefix nếu chỉ là ID"""
            if not url:
                return ""
            url_str = str(url).strip()
            if not url_str:
                return ""
            
            # Nếu đã có full URL (bắt đầu bằng http), dùng trực tiếp
            if url_str.startswith("http://") or url_str.startswith("https://"):
                return url_str
            
            # Nếu chỉ là ID (không có http và không có dấu /), thêm prefix
            if "/" not in url_str and not url_str.startswith("http"):
                return f"https://cf.shopee.vn/file/{url_str}"
            
            # Trường hợp khác, dùng trực tiếp
            return url_str
        
        if isinstance(media_data, list):
            return [normalize_image_url(url) for url in media_data if url]
        
        if isinstance(media_data, dict):
            images = media_data.get("images", [])
            videos = media_data.get("videos", [])
            result = []
            if images:
                result.extend([normalize_image_url(url) for url in images if url])
            if videos:
                result.extend([normalize_image_url(url) for url in videos if url])
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
    
    def crawl_shopee_ratings(
        self,
        shopee_client: ShopeeClient,
        base_url_params: Dict[str, Any],
        max_pages: int = 100,
        page_size: int = 50,
        delay: float = 0.1,
        max_feedbacks: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Crawl ratings từ Shopee API với pagination.
        
        Args:
            shopee_client: ShopeeClient instance đã switch_shop
            base_url_params: Dict chứa các params cơ bản (rating_star, time_start, time_end, language)
            max_pages: Số trang tối đa
            page_size: Số items mỗi trang
            delay: Thời gian delay giữa các request (giây)
            max_feedbacks: Số đánh giá tối đa cần lấy (None = không giới hạn)
            
        Returns:
            List of rating comments
        """
        cursor = 0
        page_number = 1
        from_page_number = 1
        all_ratings = []
        
        for i in range(max_pages):
            try:
                # Kiểm tra giới hạn trước khi request
                if max_feedbacks and len(all_ratings) >= max_feedbacks:
                    logger.info(f"Đã đạt giới hạn {max_feedbacks} đánh giá, dừng crawl")
                    break
                
                response = shopee_client.repo.get_shop_ratings_raw(
                    rating_star=base_url_params.get("rating_star", "5,4,3,2,1"),
                    time_start=base_url_params.get("time_start"),
                    time_end=base_url_params.get("time_end"),
                    page_number=page_number,
                    page_size=page_size,
                    cursor=cursor,
                    from_page_number=from_page_number,
                    language=base_url_params.get("language", "vi")
                )
                
                if response.get("code") != 0:
                    logger.warning(f"Shopee API returned error: {response.get('message')}")
                    break
                
                data = response.get("data", {})
                page_data = data.get("list", [])
                
                logger.info(f"[crawl_shopee_ratings] Page {page_number}: API returned {len(page_data) if page_data else 0} items (requested page_size={page_size})")
                
                if not page_data:
                    logger.info("Hết dữ liệu.")
                    break
                
                # Thêm vào all_ratings, nhưng giới hạn theo max_feedbacks
                if max_feedbacks:
                    remaining = max_feedbacks - len(all_ratings)
                    if remaining > 0:
                        all_ratings.extend(page_data[:remaining])
                    else:
                        break
                else:
                    all_ratings.extend(page_data)
                
                # Lấy comment_id cuối làm cursor cho trang tiếp theo
                if page_data:
                    cursor = page_data[-1].get("comment_id", cursor)
                
                logger.info(f"Page {page_number} | Cursor {cursor} | FromPage {from_page_number} | Fetched {len(page_data)} ratings (Total: {len(all_ratings)}/{max_feedbacks if max_feedbacks else 'unlimited'})")
                
                # Kiểm tra lại sau khi thêm
                if max_feedbacks and len(all_ratings) >= max_feedbacks:
                    logger.info(f"Đã đạt giới hạn {max_feedbacks} đánh giá sau page {page_number}, dừng crawl")
                    break
                
                page_number += 1
                from_page_number = page_number - 1
                
                time.sleep(delay)
                
            except Exception as e:
                logger.error(f"Error crawling page {page_number}: {e}", exc_info=True)
                break
        
        return all_ratings
    
    def sync_feedbacks_from_shopee(
        self,
        days: int = 30,
        page_size: int = 50,
        max_feedbacks_per_shop: Optional[int] = 100,
        connection_ids: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Đồng bộ feedbacks từ Shopee API cho tất cả các shop.
        Lấy đánh giá của N ngày gần nhất (mặc định 30 ngày).
        
        Args:
            days: Số ngày gần nhất cần lấy (default: 30)
            page_size: Số items mỗi trang (default: 50, max: 50)
            max_feedbacks_per_shop: Số đánh giá tối đa mỗi shop (default: 100)
            
        Returns:
            {
                "success": True/False,
                "total_feedbacks": 100,
                "synced": 50,
                "updated": 10,
                "errors": [...],
                "logs": [...]
            }
        """
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
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_message = f"[{timestamp}] {message}"
            with lock:
                logs_list.append(log_message)
                logger.info(f"[FeedbackService] {log_message}")
                print(f"[FeedbackService] {log_message}")
            # Call progress callback nếu có
            if progress_callback:
                try:
                    progress_callback(message)
                except Exception as e:
                    logger.warning(f"Error in progress_callback: {e}")
        
        try:
            # Tính toán time_start và time_end (N ngày gần nhất)
            tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
            now_vn = datetime.now(tz_vn)
            time_end = int(now_vn.timestamp())
            time_start = int((now_vn - timedelta(days=days)).timestamp())
            
            log_progress(f"🚀 Bắt đầu sync feedbacks từ Shopee API ({days} ngày gần nhất: {time_start} -> {time_end})")
            log_progress(f"📊 Giới hạn: {max_feedbacks_per_shop} đánh giá mỗi shop")
            
            # Lấy danh sách tất cả shops
            shops_detail = load_shopee_shops_detail()
            
            if not shops_detail:
                log_progress("❌ Không tìm thấy shops trong cấu hình")
                result["success"] = False
                result["errors"].append("Không tìm thấy shops trong cấu hình")
                return result
            
            log_progress(f"📋 Tìm thấy {len(shops_detail)} shops")
            
            # Filter theo connection_ids nếu có
            if connection_ids:
                shops_detail = {
                    k: v for k, v in shops_detail.items()
                    if v.get("shop_connect") in connection_ids
                }
                log_progress(f"🔍 Đã filter: {len(shops_detail)} shop(s) theo connection_ids")
            
            # TEST MODE: Chỉ test với shop giadungplus_official (connection_id: 10925)
            # Chỉ bật nếu không có connection_ids filter
            if not connection_ids:
                TEST_MODE = True
                TEST_SHOP_CONNECTION_ID = 10925  # giadungplus_official
                TEST_SHOP_NAME = "giadungplus_official"
                
                if TEST_MODE:
                    log_progress(f"🧪 TEST MODE: Chỉ sync shop {TEST_SHOP_NAME} (connection_id: {TEST_SHOP_CONNECTION_ID})")
                    # Filter chỉ shop test
                    shops_detail = {
                        k: v for k, v in shops_detail.items() 
                        if v.get("shop_connect") == TEST_SHOP_CONNECTION_ID
                    }
                    if not shops_detail:
                        log_progress(f"❌ Không tìm thấy shop test (connection_id: {TEST_SHOP_CONNECTION_ID})")
                        result["success"] = False
                        result["errors"].append(f"Không tìm thấy shop test (connection_id: {TEST_SHOP_CONNECTION_ID})")
                        return result
                    log_progress(f"✅ Đã filter: {len(shops_detail)} shop(s) cho test")
            
            # Base URL params
            base_url_params = {
                "rating_star": "5,4,3,2,1",  # Lấy tất cả ratings
                "time_start": time_start,
                "time_end": time_end,
                "language": "vi"
            }
            
            # Batch processing: mỗi batch 1000 items, xử lý ngay, luân phiên giữa các shops
            BATCH_SIZE = 1000  # Số feedbacks mỗi batch
            shop_list = list(shops_detail.items())
            
            # Track progress cho mỗi shop
            shop_progress = {}  # {shop_name: {'total': int, 'fetched': int, 'cursor': int, 'page': int, 'from_page': int, 'connection_id': int}}
            
            # Khởi tạo progress cho mỗi shop
            for shop_name, shop_info in shop_list:
                connection_id = shop_info.get("shop_connect")
                if not connection_id:
                    continue
                
                # Probe để lấy total
                try:
                    shopee_client = ShopeeClient(shop_key=connection_id)
                    probe_response = shopee_client.repo.get_shop_ratings_raw(
                        rating_star=base_url_params["rating_star"],
                        time_start=time_start,
                        time_end=time_end,
                        page_number=1,
                        page_size=page_size,
                        cursor=0,
                        from_page_number=1,
                        language="vi"
                    )
                    
                    if probe_response.get("code") == 0:
                        page_info = probe_response.get("data", {}).get("page_info", {})
                        total = int(page_info.get("total", 0) or 0)
                        if total > 0:
                            max_items = total if max_feedbacks_per_shop is None else min(total, max_feedbacks_per_shop)
                            shop_progress[shop_name] = {
                                'connection_id': connection_id,
                                'total': max_items,
                                'fetched': 0,
                                'cursor': 0,
                                'page': 1,
                                'from_page': 1,
                                'done': False
                            }
                            log_progress(f"📊 Shop {shop_name}: Tổng {total} đánh giá (sẽ fetch {max_items})")
                except Exception as e:
                    logger.warning(f"Error probing shop {shop_name}: {e}")
                    continue
            
            # Luân phiên giữa các shops, mỗi shop fetch batch 1000 items rồi xử lý
            total_processed = 0
            first_profile_logged = False
            
            while True:
                # Tìm shop còn feedbacks chưa fetch hết
                active_shops = [name for name, prog in shop_progress.items() 
                               if not prog['done'] and prog['fetched'] < prog['total']]
                
                if not active_shops:
                    # Tất cả shops đã xong
                    break
                
                # Luân phiên giữa các shops
                for shop_name in active_shops:
                    shop_prog = shop_progress[shop_name]
                    connection_id = shop_prog['connection_id']
                    
                    # Tính số items còn lại cần fetch cho shop này
                    remaining = shop_prog['total'] - shop_prog['fetched']
                    if remaining <= 0:
                        shop_prog['done'] = True
                        continue
                    
                    # Fetch batch (tối đa BATCH_SIZE)
                    batch_size = min(BATCH_SIZE, remaining)
                    pages_needed = math.ceil(batch_size / page_size)
                    
                    log_progress(f"🛍️ Shop {shop_name}: Fetching batch {batch_size} items (đã fetch {shop_prog['fetched']}/{shop_prog['total']})")
                    
                    try:
                        shopee_client = ShopeeClient(shop_key=connection_id)
                        
                        # Crawl batch này
                        batch_ratings = []
                        cursor = shop_prog['cursor']
                        page = shop_prog['page']
                        from_page = shop_prog['from_page']
                        
                        for _ in range(pages_needed):
                            if len(batch_ratings) >= batch_size:
                                break
                            
                            response = shopee_client.repo.get_shop_ratings_raw(
                                rating_star=base_url_params["rating_star"],
                                time_start=time_start,
                                time_end=time_end,
                                page_number=page,
                                page_size=page_size,
                                cursor=cursor,
                                from_page_number=from_page,
                                language="vi"
                            )
                            
                            if response.get("code") != 0:
                                log_progress(f"⚠️ Shop {shop_name}: API error: {response.get('message')}")
                                break
                            
                            page_data = response.get("data", {}).get("list", [])
                            if not page_data:
                                shop_prog['done'] = True
                                break
                            
                            # Thêm vào batch, giới hạn theo batch_size
                            remaining_in_batch = batch_size - len(batch_ratings)
                            if remaining_in_batch > 0:
                                batch_ratings.extend(page_data[:remaining_in_batch])
                            
                            # Update cursor và page
                            if page_data:
                                cursor = page_data[-1].get("comment_id", cursor)
                            page += 1
                            from_page = page - 1
                            
                            time.sleep(0.1)  # Delay giữa các request
                        
                        if not batch_ratings:
                            shop_prog['done'] = True
                            continue
                        
                        # Gắn connection_id vào mỗi rating
                        for rating in batch_ratings:
                            rating["connection_id"] = connection_id
                        
                        log_progress(f"✅ Shop {shop_name}: Đã fetch {len(batch_ratings)} items trong batch này")
                        
                        # Xử lý batch này ngay
                        log_progress(f"🔄 Shop {shop_name}: Xử lý {len(batch_ratings)} feedbacks...")
                        for idx, feedback_data in enumerate(batch_ratings, 1):
                            try:
                                comment_id = feedback_data.get("comment_id")
                                if not comment_id:
                                    continue
                                
                                # Profile thời gian xử lý feedback đầu tiên
                                if not first_profile_logged:
                                    t0 = time.time()
                                    updated = self._process_feedback_from_shopee(feedback_data)
                                    duration = time.time() - t0
                                    first_profile_logged = True
                                    log_progress(
                                        f"⏱ Thời gian xử lý feedback đầu tiên: "
                                        f"{duration:.3f}s (Shopee -> DB + link Sapo)"
                                    )
                                else:
                                    updated = self._process_feedback_from_shopee(feedback_data)
                                
                                with lock:
                                    synced_counter["value"] += 1
                                    if updated:
                                        updated_counter["value"] += 1
                                
                                total_processed += 1
                                
                                # Log progress mỗi 50 items
                                if total_processed % 50 == 0:
                                    progress_msg = f"Đã xử lý {total_processed} feedbacks (synced: {synced_counter['value']}, updated: {updated_counter['value']})"
                                    log_progress(progress_msg)
                                    logger.info(f"[FeedbackService] {progress_msg}")
                                
                            except Exception as e:
                                error_msg = f"Error processing feedback {comment_id}: {str(e)}"
                                logger.error(error_msg, exc_info=True)
                                with lock:
                                    synced_counter["value"] += 1
                                    errors_list.append(error_msg)
                        
                        # Update shop progress
                        shop_prog['fetched'] += len(batch_ratings)
                        shop_prog['cursor'] = cursor
                        shop_prog['page'] = page
                        shop_prog['from_page'] = from_page
                        
                        if shop_prog['fetched'] >= shop_prog['total']:
                            shop_prog['done'] = True
                            log_progress(f"✅ Shop {shop_name}: Hoàn thành ({shop_prog['fetched']}/{shop_prog['total']})")
                        
                    except Exception as e:
                        error_msg = f"Lỗi khi xử lý shop {shop_name}: {str(e)}"
                        log_progress(f"❌ {error_msg}")
                        logger.error(error_msg, exc_info=True)
                        with lock:
                            errors_list.append(error_msg)
                        shop_prog['done'] = True  # Mark as done để tránh lặp lại lỗi
                        continue
            
            log_progress(f"📦 Tổng cộng đã xử lý: {total_processed} feedbacks từ tất cả shops")
            
            # Log sau khi xử lý xong tất cả feedbacks
            if total_processed > 0:
                log_progress(f"📊 Tổng kết xử lý: {synced_counter['value']} synced, {updated_counter['value']} updated, {len(errors_list)} errors")
                logger.info(f"[FeedbackService] Processing completed: {synced_counter['value']} synced, {updated_counter['value']} updated")
                print(f"[FeedbackService] Processing completed: {synced_counter['value']} synced, {updated_counter['value']} updated")
            
            # Update result
            result["synced"] = synced_counter["value"]
            result["updated"] = updated_counter["value"]
            result["errors"] = errors_list
            result["total_feedbacks"] = total_processed
            
            # Add final summary log
            final_log = f"✅ Hoàn thành sync: {result['synced']} synced, {result['updated']} updated, {len(result['errors'])} errors (Tổng feedbacks: {total_processed})"
            log_progress(final_log)
            
            # Copy logs to result
            result["logs"] = logs_list.copy()
            
            logger.info(f"[FeedbackService] Final result: synced={result['synced']}, updated={result['updated']}, total_feedbacks={result['total_feedbacks']}, errors={len(result['errors'])}")
            print(f"[FeedbackService] Final result: {result}")
            
        except Exception as e:
            error_msg = f"Error in sync_feedbacks_from_shopee: {str(e)}"
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
        
        # Log final result trước khi return
        logger.info(f"[FeedbackService] Returning result: success={result.get('success')}, synced={result.get('synced')}, total_feedbacks={result.get('total_feedbacks')}, errors={len(result.get('errors', []))}")
        print(f"[FeedbackService] Returning result: success={result.get('success')}, synced={result.get('synced')}, total_feedbacks={result.get('total_feedbacks')}")
        print(f"[FeedbackService] Result keys: {list(result.keys())}")
        print(f"[FeedbackService] Result logs count: {len(result.get('logs', []))}")
        
        return result
    
    def _truncate_field(self, value: Any, max_length: int) -> str:
        """
        Truncate string field nếu vượt quá max_length.
        
        Args:
            value: Giá trị cần truncate
            max_length: Độ dài tối đa
            
        Returns:
            String đã được truncate nếu cần
        """
        if value is None:
            return ""
        value_str = str(value)
        if len(value_str) > max_length:
            return value_str[:max_length]
        return value_str
    
    def _process_feedback_from_shopee(self, feedback_data: Dict[str, Any]) -> bool:
        """
        Process một feedback từ Shopee API và lưu/update vào database.
        
        Args:
            feedback_data: Feedback data từ Shopee API
            
        Returns:
            True nếu đã update, False nếu tạo mới
        """
        comment_id = feedback_data.get("comment_id")
        if not comment_id:
            logger.warning("Feedback data missing comment_id, skipping")
            return False
        
        # Set feedback_id = comment_id (dùng feedback_id làm key chính)
        feedback_id = comment_id
        
        # Kiểm tra feedback_id đã tồn tại chưa để tránh trùng lặp
        try:
            existing_feedback = Feedback.objects.filter(feedback_id=feedback_id).first()
            if existing_feedback:
                logger.debug(f"Feedback với feedback_id {feedback_id} đã tồn tại, sẽ update thay vì tạo mới")
        except Exception as e:
            logger.warning(f"Error checking existing feedback_id {feedback_id}: {e}")
        
        # Map dữ liệu từ Shopee API sang model
        connection_id = feedback_data.get("connection_id", 0)
        
        # Truncate các trường có thể vượt quá max_length
        product_name = self._truncate_field(feedback_data.get("product_name", ""), 1000)
        model_name = feedback_data.get("model_name", "")  # TextField, không cần truncate (nhưng sẽ không lưu theo yêu cầu)
        buyer_user_name = self._truncate_field(feedback_data.get("user_name", ""), 200)
        
        # user_portrait: Lưu chỉ ID (không có prefix URL)
        # Nếu API trả về full URL, extract chỉ ID
        user_portrait_raw = feedback_data.get("user_portrait", "")
        if user_portrait_raw:
            # Nếu đã có full URL, extract chỉ ID
            if "cf.shopee.vn/file/" in user_portrait_raw:
                user_portrait = user_portrait_raw.split("cf.shopee.vn/file/")[-1]
            elif user_portrait_raw.startswith("http"):
                # Có thể là URL khác, extract phần cuối
                user_portrait = user_portrait_raw.split("/")[-1]
            else:
                # Chỉ là ID, dùng trực tiếp
                user_portrait = user_portrait_raw
            user_portrait = self._truncate_field(user_portrait, 200)
        else:
            user_portrait = ""
        
        channel_order_number = self._truncate_field(feedback_data.get("order_sn", ""), 100)
        
        # Convert product_cover thành product_image URL
        # Format: https://cf.shopee.vn/file/{product_cover}
        product_cover = feedback_data.get("product_cover", "")
        product_image = ""
        if product_cover:
            # Nếu product_cover đã có full URL, dùng trực tiếp
            if product_cover.startswith("http://") or product_cover.startswith("https://"):
                product_image = product_cover
            # Nếu chỉ là ID, thêm prefix
            elif "/" not in product_cover:
                product_image = f"https://cf.shopee.vn/file/{product_cover}"
            else:
                # Có thể là path khác, dùng trực tiếp
                product_image = product_cover
        
        # Get or create feedback (sử dụng feedback_id làm unique key)
        logger.debug(f"[_process_feedback_from_shopee] Getting or creating feedback {feedback_id}")
        try:
            feedback, created = Feedback.objects.get_or_create(
                feedback_id=feedback_id,
                defaults={
                    "connection_id": connection_id,
                    # Set comment_id = feedback_id (giữ lại để tương thích)
                    "comment_id": comment_id,
                    "tenant_id": None,  # Không có từ Shopee API
                    # Product info
                    "item_id": feedback_data.get("item_id"),
                    "product_id": feedback_data.get("product_id"),
                    "product_name": product_name,
                    "product_image": product_image,  # URL từ product_cover
                    "product_cover": product_cover,  # ID gốc từ Shopee
                    "model_id": feedback_data.get("model_id"),
                    "model_name": "",  # KHÔNG lưu model_name từ Shopee (để trống)
                    # Order info
                    "channel_order_number": channel_order_number,
                    "order_id": feedback_data.get("order_id"),
                    # Customer info
                    "buyer_user_name": buyer_user_name,
                    "user_portrait": user_portrait,
                    "user_id": feedback_data.get("user_id"),
                    # Rating & Comment
                    "rating": feedback_data.get("rating_star", 0),
                    "comment": feedback_data.get("comment", ""),
                    "images": self._normalize_media(feedback_data.get("images", [])),
                    # Reply info - Parse reply object từ Shopee API
                    "reply": self._extract_reply_comment(feedback_data.get("reply")),
                    "reply_time": self._extract_reply_time(feedback_data.get("reply")),
                    # Additional fields from Shopee
                    "is_hidden": feedback_data.get("is_hidden", False),
                    "status": feedback_data.get("status"),
                    "can_follow_up": feedback_data.get("can_follow_up"),
                    "follow_up": feedback_data.get("follow_up"),
                    "submit_time": feedback_data.get("submit_time"),
                    "low_rating_reasons": feedback_data.get("low_rating_reasons", []),
                    # Timestamps
                    "create_time": feedback_data.get("ctime", 0) or feedback_data.get("submit_time", 0),
                    "ctime": feedback_data.get("ctime"),
                    "mtime": feedback_data.get("mtime"),
                }
            )
            logger.debug(f"[_process_feedback_from_shopee] Got feedback: created={created}, id={feedback.id}")
        except Exception as e:
            logger.error(f"[_process_feedback_from_shopee] Error in get_or_create for feedback {feedback_id}: {e}", exc_info=True)
            raise
        
        if not created:
            # Update existing feedback
            logger.debug(f"[_process_feedback_from_shopee] Updating existing feedback {feedback_id}")
            updated = False
            
            # Update các trường có thể thay đổi
            if feedback.rating != feedback_data.get("rating_star", 0):
                feedback.rating = feedback_data.get("rating_star", 0)
                updated = True
            if feedback.comment != feedback_data.get("comment", ""):
                feedback.comment = feedback_data.get("comment", "")
                updated = True
            # Update reply và reply_time từ reply object
            reply_comment = self._extract_reply_comment(feedback_data.get("reply"))
            reply_time = self._extract_reply_time(feedback_data.get("reply"))
            
            if feedback.reply != reply_comment:
                feedback.reply = reply_comment
                updated = True
            if feedback.reply_time != reply_time:
                feedback.reply_time = reply_time
                updated = True
            if feedback.user_portrait != user_portrait:
                feedback.user_portrait = user_portrait
                updated = True
            if feedback.product_name != product_name:
                feedback.product_name = product_name
                updated = True
            # model_name: KHÔNG update theo yêu cầu (không lưu model_name)
            if feedback.buyer_user_name != buyer_user_name:
                feedback.buyer_user_name = buyer_user_name
                updated = True
            if feedback.channel_order_number != channel_order_number:
                feedback.channel_order_number = channel_order_number
                updated = True
            # Update product_image từ product_cover
            if feedback.product_image != product_image:
                feedback.product_image = product_image
                updated = True
            if feedback.product_cover != product_cover:
                feedback.product_cover = product_cover
                updated = True
            # Update comment_id nếu chưa có (giữ lại để tương thích)
            if not feedback.comment_id and comment_id:
                feedback.comment_id = comment_id
                updated = True
            # Update các trường khác từ Shopee
            if feedback.is_hidden != feedback_data.get("is_hidden", False):
                feedback.is_hidden = feedback_data.get("is_hidden", False)
                updated = True
            if feedback.status != feedback_data.get("status"):
                feedback.status = feedback_data.get("status")
                updated = True
            if feedback.can_follow_up != feedback_data.get("can_follow_up"):
                feedback.can_follow_up = feedback_data.get("can_follow_up")
                updated = True
            if feedback.follow_up != feedback_data.get("follow_up"):
                feedback.follow_up = feedback_data.get("follow_up")
                updated = True
            if feedback.submit_time != feedback_data.get("submit_time"):
                feedback.submit_time = feedback_data.get("submit_time")
                updated = True
            if feedback.ctime != feedback_data.get("ctime"):
                feedback.ctime = feedback_data.get("ctime")
                updated = True
            if feedback.mtime != feedback_data.get("mtime"):
                feedback.mtime = feedback_data.get("mtime")
                updated = True
            
            # Update images (normalize URLs)
            normalized_images = self._normalize_media(feedback_data.get("images", []))
            if feedback.images != normalized_images:
                feedback.images = normalized_images
                updated = True
            
            if updated:
                logger.debug(f"[_process_feedback_from_shopee] Saving updated feedback {feedback_id}")
                try:
                    feedback.save()
                    logger.debug(f"[_process_feedback_from_shopee] Saved updated feedback {feedback_id}")
                except Exception as e:
                    logger.error(f"[_process_feedback_from_shopee] Error saving updated feedback {feedback_id}: {e}", exc_info=True)
            
            # Vẫn cố gắng link với Sapo data nếu chưa có (có thể order mới được tạo trên Sapo)
            logger.debug(f"[_process_feedback_from_shopee] Checking if need to link Sapo data: sapo_order_id={feedback.sapo_order_id}, sapo_variant_id={feedback.sapo_variant_id}")
            if not feedback.sapo_order_id or not feedback.sapo_variant_id:
                logger.debug(f"[_process_feedback_from_shopee] Linking Sapo data for feedback {feedback_id}")
                self._link_sapo_data_from_shopee(feedback, feedback_data)
                logger.debug(f"[_process_feedback_from_shopee] Finished linking Sapo data for feedback {feedback_id}")
            else:
                logger.debug(f"[_process_feedback_from_shopee] Skipping Sapo link (already linked)")
            
            logger.debug(f"[_process_feedback_from_shopee] Returning updated={updated} for feedback {feedback_id}")
            return updated
        
        # Try to link với Sapo data (order, customer, product)
        logger.debug(f"[_process_feedback_from_shopee] Starting to link Sapo data for new feedback {feedback.comment_id}")
        try:
            self._link_sapo_data_from_shopee(feedback, feedback_data)
            logger.debug(f"[_process_feedback_from_shopee] Finished linking Sapo data for new feedback {feedback.comment_id}")
        except Exception as e:
            logger.warning(f"[_process_feedback_from_shopee] Error linking Sapo data for new feedback {feedback.comment_id}: {e}")
        
        # Push user_portrait lên Sapo customer note nếu có.
        # Lưu ý: thao tác này gọi Sapo API và khá nặng, nên mặc định TẮT trong sync hàng loạt.
        # Chỉ bật khi đặt biến môi trường CSKH_PUSH_USER_PORTRAIT=1 để tránh làm treo/buộc chờ lâu.
        try:
            if (
                os.getenv("CSKH_PUSH_USER_PORTRAIT", "0") == "1"
                and feedback.user_portrait
                and feedback.sapo_customer_id
            ):
                logger.debug(f"[_process_feedback_from_shopee] Pushing user_portrait for feedback {feedback.comment_id}")
                self._push_user_portrait_to_customer(feedback)
        except Exception as e:
            logger.warning(
                f"Error pushing user_portrait to customer {feedback.sapo_customer_id}: {e}"
            )
        
        logger.debug(f"[_process_feedback_from_shopee] Returning created={created} for new feedback {feedback.comment_id}")
        return created
    
    def _link_sapo_data_from_shopee(self, feedback: Feedback, feedback_data: Dict[str, Any]):
        """
        Link feedback với Sapo data (order, customer, product, variant) từ Shopee data.
        
        Args:
            feedback: Feedback instance
            feedback_data: Feedback data từ Shopee API
        """
        try:
            # 1. Link với Sapo order qua channel_order_number (order_sn)
            if feedback.channel_order_number and not feedback.sapo_order_id:
                logger.debug(f"[_link_sapo_data_from_shopee] Linking order for {feedback.channel_order_number}")
                try:
                    from orders.services.sapo_order_service import SapoOrderService
                    order_service = SapoOrderService(self.sapo_client)
                    
                    # Lấy raw order để có thông tin item_id trong line items (với timeout)
                    logger.debug(f"[_link_sapo_data_from_shopee] Getting raw order for {feedback.channel_order_number}")
                    try:
                        raw_order = self.sapo_client.core.get_order_by_reference_number(feedback.channel_order_number)
                        logger.debug(f"[_link_sapo_data_from_shopee] Got raw order: {raw_order is not None}")
                    except Exception as e:
                        logger.warning(f"Error getting raw order for {feedback.channel_order_number}: {e}")
                        raw_order = None
                    
                    if raw_order:
                        # Convert sang OrderDTO (với timeout)
                        logger.debug(f"[_link_sapo_data_from_shopee] Getting order DTO for {feedback.channel_order_number}")
                        try:
                            order = order_service.get_order_by_reference(feedback.channel_order_number)
                            logger.debug(f"[_link_sapo_data_from_shopee] Got order DTO: {order is not None}")
                        except Exception as e:
                            logger.warning(f"Error getting order DTO for {feedback.channel_order_number}: {e}")
                            order = None
                        
                        if order:
                            feedback.sapo_order_id = order.id
                            
                            # 2. Link với customer từ order và update username
                            if order.customer_id and not feedback.sapo_customer_id:
                                feedback.sapo_customer_id = order.customer_id
                            
                            # 3. Link với product và variant từ order line items
                            if feedback.item_id:
                                logger.debug(f"[_link_sapo_data_from_shopee] Finding variant for item_id {feedback.item_id}")
                                try:
                                    variant_ids = self._find_variant_ids_from_order(
                                        raw_order=raw_order,
                                        item_id=feedback.item_id,
                                        connection_id=feedback.connection_id
                                    )
                                    logger.debug(f"[_link_sapo_data_from_shopee] Found {len(variant_ids)} variants")
                                    
                                    if variant_ids:
                                        feedback.sapo_variant_id = variant_ids[0]
                                        
                                        # Lấy product_id từ variant (với timeout)
                                        logger.debug(f"[_link_sapo_data_from_shopee] Getting variant {feedback.sapo_variant_id}")
                                        try:
                                            variant_data = self.sapo_client.core.get_variant_raw(feedback.sapo_variant_id)
                                            if variant_data and variant_data.get('variant'):
                                                feedback.sapo_product_id = variant_data['variant'].get('product_id')
                                                logger.debug(f"[_link_sapo_data_from_shopee] Got product_id: {feedback.sapo_product_id}")
                                        except Exception as e:
                                            logger.warning(f"Error getting variant {feedback.sapo_variant_id}: {e}")
                                except Exception as e:
                                    logger.warning(f"Error finding variant for item_id {feedback.item_id}: {e}")
                            
                            logger.debug(f"[_link_sapo_data_from_shopee] Saving feedback {feedback.comment_id}")
                            try:
                                feedback.save()
                                logger.debug(f"Linked feedback {feedback.comment_id} with order {order.id}")
                            except Exception as e:
                                logger.warning(f"Error saving feedback after linking: {e}")
                except Exception as e:
                    logger.warning(f"Error linking order for feedback {feedback.comment_id}: {e}")
            else:
                logger.debug(f"[_link_sapo_data_from_shopee] Skipping link (channel_order_number={feedback.channel_order_number}, sapo_order_id={feedback.sapo_order_id})")
            
        except Exception as e:
            logger.warning(f"Error linking Sapo data for feedback {feedback.comment_id}: {e}")
    
    def _push_user_portrait_to_customer(self, feedback: Feedback):
        """
        Push user_portrait lên Sapo customer note (dạng JSON).
        
        Args:
            feedback: Feedback instance có user_portrait và sapo_customer_id
        """
        try:
            from customers.services.customer_service import CustomerService
            customer_service = CustomerService(self.sapo_client)
            
            customer = customer_service.get_customer(feedback.sapo_customer_id)
            if not customer:
                return
            
            # Lấy note hiện tại
            current_note = customer.note or ""
            
            # Parse note thành JSON nếu có thể
            note_data = {}
            if current_note:
                try:
                    note_data = json.loads(current_note)
                except json.JSONDecodeError:
                    # Nếu không phải JSON, giữ nguyên text cũ
                    note_data = {"text": current_note}
            
            # Thêm user_portrait vào note
            if "user_portrait" not in note_data:
                note_data["user_portrait"] = feedback.user_portrait
            elif note_data.get("user_portrait") != feedback.user_portrait:
                # Update nếu khác
                note_data["user_portrait"] = feedback.user_portrait
            
            # Update customer note
            customer_service.update_customer_info(
                customer_id=feedback.sapo_customer_id,
                note=json.dumps(note_data, ensure_ascii=False)
            )
            
            logger.info(f"Pushed user_portrait {feedback.user_portrait} to customer {feedback.sapo_customer_id}")
            
        except Exception as e:
            logger.warning(f"Error pushing user_portrait to customer {feedback.sapo_customer_id}: {e}")


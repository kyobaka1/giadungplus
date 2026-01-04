# cskh/services/feedback_sync_service.py
"""
Service để quản lý sync feedback jobs (full sync và incremental sync).
"""

from typing import Dict, Any, List, Optional, Callable
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time

from django.utils import timezone
from django.db import transaction

from core.sapo_client import SapoClient
from core.shopee_client import ShopeeClient
from core.system_settings import load_shopee_shops_detail
from cskh.models import Feedback, FeedbackSyncJob
from cskh.services.feedback_service import FeedbackService

logger = logging.getLogger(__name__)


class FeedbackSyncService:
    """
    Service để quản lý sync feedback jobs (full sync và incremental sync).
    """
    
    def __init__(self, sapo_client: SapoClient):
        self.sapo_client = sapo_client
        self.feedback_service = FeedbackService(sapo_client)
    
    def create_full_sync_job(
        self,
        days: Optional[int] = None,
        page_size: int = 50,
        max_feedbacks_per_shop: Optional[int] = None
    ) -> FeedbackSyncJob:
        """
        Tạo full sync job.
        
        Args:
            days: Số ngày gần nhất cần sync (None = không giới hạn, lấy tất cả feedbacks)
            page_size: Số items mỗi trang
            max_feedbacks_per_shop: Số feedbacks tối đa mỗi shop (None = không giới hạn)
            
        Returns:
            FeedbackSyncJob instance
        """
        job = FeedbackSyncJob.objects.create(
            sync_type='full',
            status='pending',
            days=days,
            page_size=page_size,
            max_feedbacks_per_shop=max_feedbacks_per_shop
        )
        logger.info(f"Created full sync job {job.id}: days={days}, page_size={page_size}")
        return job
    
    def create_incremental_sync_job(self, batch_size: int = 50) -> FeedbackSyncJob:
        """
        Tạo incremental sync job.
        
        Args:
            batch_size: Số feedbacks mỗi batch
            
        Returns:
            FeedbackSyncJob instance
        """
        job = FeedbackSyncJob.objects.create(
            sync_type='incremental',
            status='pending',
            batch_size=batch_size
        )
        logger.info(f"Created incremental sync job {job.id}: batch_size={batch_size}")
        return job
    
    def update_job_progress(
        self,
        job: FeedbackSyncJob,
        processed: Optional[int] = None,
        synced: Optional[int] = None,
        updated: Optional[int] = None,
        errors: Optional[int] = None,
        current_shop_name: Optional[str] = None,
        current_shop_index: Optional[int] = None,
        current_page: Optional[int] = None,
        current_cursor: Optional[int] = None,
        last_processed_feedback_id: Optional[int] = None,
        log_message: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """
        Cập nhật progress của job.
        
        Args:
            job: FeedbackSyncJob instance
            processed: Số feedbacks đã xử lý
            synced: Số feedbacks đã sync thành công
            updated: Số feedbacks đã update
            errors: Số lỗi
            current_shop_name: Tên shop hiện tại
            current_shop_index: Index shop hiện tại
            current_page: Page hiện tại
            current_cursor: Cursor hiện tại
            last_processed_feedback_id: Feedback ID cuối cùng đã xử lý
            log_message: Log message để thêm vào logs
            error_message: Error message để thêm vào errors
        """
        with transaction.atomic():
            job.refresh_from_db()
            
            if processed is not None:
                job.processed_feedbacks += processed
            if synced is not None:
                job.synced_feedbacks += synced
            if updated is not None:
                job.updated_feedbacks += updated
            if errors is not None:
                job.error_count += errors
            
            if current_shop_name is not None:
                job.current_shop_name = current_shop_name
            if current_shop_index is not None:
                job.current_shop_index = current_shop_index
            if current_page is not None:
                job.current_page = current_page
            if current_cursor is not None:
                job.current_cursor = current_cursor
            if last_processed_feedback_id is not None:
                job.last_processed_feedback_id = last_processed_feedback_id
            
            # Thêm log message
            if log_message:
                timestamp = datetime.now().strftime("%H:%M:%S")
                log_entry = f"[{timestamp}] {log_message}"
                job.logs.append(log_entry)
                # Giữ chỉ 1000 logs gần nhất
                if len(job.logs) > 1000:
                    job.logs = job.logs[-1000:]
            
            # Thêm error message
            if error_message:
                timestamp = datetime.now().strftime("%H:%M:%S")
                error_entry = f"[{timestamp}] {error_message}"
                job.errors.append(error_entry)
                # Giữ chỉ 500 errors gần nhất
                if len(job.errors) > 500:
                    job.errors = job.errors[-500:]
            
            job.save()
    
    def get_job_status(self, job_id: int) -> Dict[str, Any]:
        """
        Lấy status của job để hiển thị trên UI.
        
        Args:
            job_id: Job ID
            
        Returns:
            Dict chứa status và progress
        """
        try:
            job = FeedbackSyncJob.objects.get(id=job_id)
            return {
                'id': job.id,
                'sync_type': job.sync_type,
                'status': job.status,
                'total_shops': job.total_shops,
                'current_shop_index': job.current_shop_index,
                'current_shop_name': job.current_shop_name,
                'total_feedbacks': job.total_feedbacks,
                'processed_feedbacks': job.processed_feedbacks,
                'synced_feedbacks': job.synced_feedbacks,
                'updated_feedbacks': job.updated_feedbacks,
                'error_count': job.error_count,
                'progress_percentage': job.progress_percentage,
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'duration_seconds': job.duration.total_seconds() if job.duration else None,
                'recent_logs': job.logs[-50:],  # 50 logs gần nhất
                'recent_errors': job.errors[-20:],  # 20 errors gần nhất
            }
        except FeedbackSyncJob.DoesNotExist:
            return {'error': 'Job not found'}
    
    def run_full_sync(self, job: FeedbackSyncJob) -> Dict[str, Any]:
        """
        Chạy full sync với resume support.
        - Lưu progress vào job sau mỗi batch
        - Có thể resume từ điểm dừng
        
        Args:
            job: FeedbackSyncJob instance
            
        Returns:
            Dict chứa kết quả
        """
        result = {
            "success": True,
            "synced": 0,
            "updated": 0,
            "errors": []
        }
        
        try:
            # Update job status
            job.status = 'running'
            if not job.started_at:
                job.started_at = timezone.now()
            job.save()
            
            self.update_job_progress(job, log_message="🚀 Bắt đầu full sync")
            
            # Tính toán time range (chỉ nếu có days)
            time_start = None
            time_end = None
            
            if job.days:
                tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
                now_vn = datetime.now(tz_vn)
                time_end = int(now_vn.timestamp())
                time_start = int((now_vn - timedelta(days=job.days)).timestamp())
                self.update_job_progress(
                    job,
                    log_message=f"📅 Time range: {time_start} -> {time_end} ({job.days} ngày)"
                )
            else:
                self.update_job_progress(
                    job,
                    log_message=f"📅 Time range: Không giới hạn (lấy tất cả feedbacks)"
                )
            
            # Lấy danh sách shops
            shops_detail = load_shopee_shops_detail()
            if not shops_detail:
                job.status = 'failed'
                job.completed_at = timezone.now()
                job.save()
                result["success"] = False
                result["errors"].append("Không tìm thấy shops trong cấu hình")
                return result
            
            # Update total shops
            job.total_shops = len(shops_detail)
            job.save()
            
            self.update_job_progress(
                job,
                log_message=f"📋 Tìm thấy {len(shops_detail)} shops"
            )
            
            # Resume từ shop hiện tại nếu có
            shop_list = list(shops_detail.items())
            # Fix: Check current_shop_index thay vì status (vì status có thể đã bị đổi thành 'pending')
            # Cho phép resume từ shop index 0 nếu có page > 1
            if job.current_shop_index is not None and job.current_shop_index >= 0:
                start_index = job.current_shop_index
            else:
                start_index = 0
            
            # Process từng shop
            for shop_idx in range(start_index, len(shop_list)):
                shop_name, shop_info = shop_list[shop_idx]
                connection_id = shop_info.get("shop_connect")
                
                if not connection_id:
                    self.update_job_progress(
                        job,
                        log_message=f"⚠️ Shop {shop_name} không có connection_id, bỏ qua"
                    )
                    continue
                
                # Kiểm tra xem có page/cursor để resume không (TRƯỚC KHI update job)
                resume_page = None
                resume_cursor = None
                
                # Auto-resume từ DB: Nếu không có page/cursor trong job nhưng có feedbacks trong DB
                if not job.current_page or job.current_page <= 1:
                    from cskh.models import Feedback
                    import math
                    feedback_count = Feedback.objects.filter(connection_id=connection_id).count()
                    if feedback_count > 0:
                        # Tính page/cursor từ số feedbacks trong DB
                        estimated_page = math.ceil(feedback_count / job.page_size) + 1
                        latest_feedback = Feedback.objects.filter(
                            connection_id=connection_id
                        ).order_by('-create_time').first()
                        if latest_feedback:
                            resume_page = estimated_page
                            resume_cursor = latest_feedback.feedback_id
                            self.update_job_progress(
                                job,
                                log_message=f"🔄 Auto-resume từ DB: shop {shop_name} có {feedback_count} feedbacks, "
                                           f"estimate page {resume_page}, cursor {resume_cursor}"
                            )
                
                # Nếu đang resume shop này (shop tại start_index), dùng page/cursor đã lưu
                # Check: shop_index match HOẶC connection_id match (linh hoạt hơn)
                # Cho phép resume từ shop đầu tiên (index 0) nếu có page > 1
                if not resume_page and (
                    shop_idx == start_index and
                    (job.current_shop_name == shop_name or job.current_connection_id == connection_id) and
                    job.current_page and job.current_page > 1
                ):
                    is_resume_shop = True
                else:
                    is_resume_shop = False
                
                # Nếu có resume_page từ auto-resume DB hoặc từ job, xử lý resume
                if resume_page:
                    # Đã có resume_page từ auto-resume DB, không cần làm gì thêm
                    pass
                elif is_resume_shop:
                    # Resume từ job đã lưu
                    self.update_job_progress(
                        job,
                        log_message=f"🔍 Check resume: shop_idx={shop_idx}, start_index={start_index}, "
                                   f"job.shop={job.current_shop_name}, current.shop={shop_name}, "
                                   f"job.conn={job.current_connection_id}, current.conn={connection_id}, "
                                   f"job.page={job.current_page}, job.cursor={job.current_cursor}"
                    )
                    
                    # Kiểm tra feedback cuối cùng đã xử lý để đảm bảo không bỏ sót
                    from cskh.models import Feedback
                    latest_feedback = Feedback.objects.filter(
                        connection_id=connection_id
                    ).order_by('-create_time').first()
                    
                    if latest_feedback:
                        # Có feedback trong DB, dùng page/cursor đã lưu
                        resume_page = job.current_page
                        resume_cursor = job.current_cursor
                        self.update_job_progress(
                            job,
                            log_message=f"🔄 Resume shop {shop_name} từ page {resume_page}, cursor {resume_cursor or 0} (feedback cuối: {latest_feedback.feedback_id})"
                        )
                    else:
                        # Chưa có feedback nào, nhưng vẫn dùng page/cursor đã lưu (có thể đang sync shop khác)
                        if job.current_connection_id == connection_id:
                            resume_page = job.current_page
                            resume_cursor = job.current_cursor
                            self.update_job_progress(
                                job,
                                log_message=f"🔄 Resume shop {shop_name} từ page {resume_page}, cursor {resume_cursor or 0} (chưa có feedback trong DB)"
                            )
                        else:
                            # Connection ID khác, reset về đầu
                            resume_page = None
                            resume_cursor = None
                            self.update_job_progress(
                                job,
                                log_message=f"🔄 Resume shop {shop_name}: connection_id khác, bắt đầu từ đầu"
                            )
                
                # Update current shop
                job.current_connection_id = connection_id
                job.current_shop_index = shop_idx
                job.current_shop_name = shop_name
                job.save()
                
                self.update_job_progress(
                    job,
                    current_shop_name=shop_name,
                    current_shop_index=shop_idx,
                    log_message=f"🛍️ Đang xử lý shop: {shop_name} (connection_id: {connection_id})"
                )
                
                # Callback để lưu page/cursor vào job sau mỗi batch
                def update_page_cursor_callback(shop_name_inner: str, page: int, cursor: int):
                    """Callback để lưu page/cursor vào job sau mỗi batch"""
                    job.refresh_from_db()
                    if job.current_shop_name == shop_name_inner and job.current_connection_id == connection_id:
                        job.current_page = page
                        job.current_cursor = cursor
                        job.save()
                
                try:
                    # Gọi feedback_service để sync shop này
                    shop_result = self.feedback_service.sync_feedbacks_from_shopee(
                        days=job.days,
                        page_size=job.page_size,
                        max_feedbacks_per_shop=job.max_feedbacks_per_shop,
                        connection_ids=[connection_id],  # Chỉ sync shop này
                        progress_callback=lambda msg: self.update_job_progress(job, log_message=msg),
                        resume_page=resume_page,  # Thêm resume page
                        resume_cursor=resume_cursor,  # Thêm resume cursor
                        progress_update_callback=update_page_cursor_callback  # Callback để lưu page/cursor
                    )
                    
                    # Update total_feedbacks nếu chưa có
                    if job.total_feedbacks == 0:
                        job.total_feedbacks = shop_result.get('total_feedbacks', 0)
                        job.save()
                    
                    # Update progress
                    # sync_feedbacks_from_shopee trả về 'synced' là tổng số đã xử lý (bao gồm cả updated)
                    # 'updated' là số đã update (không phải mới)
                    total_processed = shop_result.get('synced', 0)
                    updated_count = shop_result.get('updated', 0)
                    new_synced = total_processed - updated_count
                    
                    self.update_job_progress(
                        job,
                        processed=total_processed,
                        synced=new_synced,
                        updated=updated_count,
                        errors=len(shop_result.get('errors', [])),
                        log_message=f"✅ Shop {shop_name}: {new_synced} synced, {updated_count} updated"
                    )
                    
                    result["synced"] += new_synced
                    result["updated"] += updated_count
                    result["errors"].extend(shop_result.get('errors', []))
                    
                except Exception as e:
                    error_msg = f"Lỗi khi xử lý shop {shop_name}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    self.update_job_progress(
                        job,
                        errors=1,
                        error_message=error_msg
                    )
                    result["errors"].append(error_msg)
                    continue
            
            # Mark as completed
            job.status = 'completed'
            job.completed_at = timezone.now()
            job.save()
            
            self.update_job_progress(
                job,
                log_message=f"✅ Hoàn thành full sync: {result['synced']} synced, {result['updated']} updated"
            )
            
        except Exception as e:
            error_msg = f"Lỗi trong run_full_sync: {str(e)}"
            logger.error(error_msg, exc_info=True)
            job.status = 'failed'
            job.completed_at = timezone.now()
            job.save()
            result["success"] = False
            result["errors"].append(error_msg)
        
        return result
    
    def run_incremental_sync(self, job: FeedbackSyncJob) -> Dict[str, Any]:
        """
        Chạy incremental sync:
        - Time range: 7 ngày gần nhất (cố định)
        - Bắt đầu từ page 1, cursor 0, page_size 50
        - Xử lý page 1 (50 feedbacks)
        - Nếu có feedback trùng trong page 1 -> tiếp tục page 2
        - Nếu page 2 cũng có feedback trùng -> dừng shop này, chuyển sang shop tiếp theo
        
        Args:
            job: FeedbackSyncJob instance
            
        Returns:
            Dict chứa kết quả
        """
        result = {
            "success": True,
            "synced": 0,
            "updated": 0,
            "stopped_at_existing": False,
            "errors": []
        }
        
        try:
            # Update job status
            job.status = 'running'
            if not job.started_at:
                job.started_at = timezone.now()
            job.save()
            
            self.update_job_progress(job, log_message="🚀 Bắt đầu incremental sync")
            
            # Time range: 7 ngày gần nhất (cố định)
            tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
            now_vn = datetime.now(tz_vn)
            time_end = int(now_vn.timestamp())
            time_start = int((now_vn - timedelta(days=7)).timestamp())
            
            self.update_job_progress(
                job,
                log_message=f"📅 Time range: 7 ngày gần nhất ({time_start} -> {time_end})"
            )
            
            # Lấy danh sách shops
            shops_detail = load_shopee_shops_detail()
            if not shops_detail:
                job.status = 'failed'
                job.completed_at = timezone.now()
                job.save()
                result["success"] = False
                result["errors"].append("Không tìm thấy shops trong cấu hình")
                return result
            
            job.total_shops = len(shops_detail)
            job.save()
            
            # Process từng shop
            for shop_name, shop_info in shops_detail.items():
                connection_id = shop_info.get("shop_connect")
                if not connection_id:
                    continue
                
                self.update_job_progress(
                    job,
                    current_shop_name=shop_name,
                    log_message=f"🛍️ Đang quét shop: {shop_name}"
                )
                
                try:
                    # Logic mới: 
                    # 1. Bắt đầu từ page 1, cursor 0, page_size 50
                    # 2. Xử lý page 1 (50 feedbacks)
                    # 3. Nếu có feedback trùng -> tiếp tục page 2
                    # 4. Nếu page 2 cũng có feedback trùng -> dừng shop này
                    
                    page_size = job.batch_size  # 50
                    page = 1
                    cursor = 0
                    total_synced = 0
                    found_existing_in_page1 = False
                    found_existing_in_page2 = False
                    
                    # Tạo ShopeeClient
                    shopee_client = ShopeeClient(shop_key=connection_id)
                    
                    # === PAGE 1 ===
                    self.update_job_progress(
                        job,
                        log_message=f"📄 Shop {shop_name}: Fetching page 1 (cursor=0, page_size={page_size})"
                    )
                    
                    response = shopee_client.repo.get_shop_ratings_raw(
                        rating_star="5,4,3,2,1",
                        time_start=time_start,
                        time_end=time_end,
                        page_number=page,
                        page_size=page_size,
                        cursor=cursor,
                        from_page_number=1,
                        language="vi"
                    )
                    
                    if response.get("code") != 0:
                        self.update_job_progress(
                            job,
                            error_message=f"Shopee API error (page 1): {response.get('message')}"
                        )
                        continue
                    
                    feedbacks_page1 = response.get("data", {}).get("list", [])
                    if not feedbacks_page1:
                        # Không có feedback nào trong page 1, chuyển sang shop tiếp theo
                        self.update_job_progress(
                            job,
                            log_message=f"ℹ️ Shop {shop_name}: Không có feedback nào trong page 1"
                        )
                        continue
                    
                    # Xử lý page 1
                    page1_synced = 0
                    for feedback_data in feedbacks_page1:
                        comment_id = feedback_data.get("comment_id")
                        if not comment_id:
                            continue
                        
                        # Check xem đã có trong DB chưa
                        if Feedback.objects.filter(feedback_id=comment_id).exists():
                            found_existing_in_page1 = True
                            self.update_job_progress(
                                job,
                                log_message=f"⚠️ Shop {shop_name}: Page 1 có feedback trùng (ID: {comment_id})"
                            )
                            break
                        
                        # Chưa có -> sync (tạo mới)
                        try:
                            feedback_data["connection_id"] = connection_id
                            self.feedback_service._process_feedback_from_shopee(feedback_data)
                            
                            page1_synced += 1
                            total_synced += 1
                            result["synced"] += 1
                            self.update_job_progress(
                                job,
                                processed=1,
                                synced=1,
                                updated=0
                            )
                            
                        except Exception as e:
                            error_msg = f"Error processing feedback {comment_id}: {str(e)}"
                            logger.error(error_msg, exc_info=True)
                            self.update_job_progress(
                                job,
                                errors=1,
                                error_message=error_msg
                            )
                            result["errors"].append(error_msg)
                    
                    self.update_job_progress(
                        job,
                        log_message=f"📄 Shop {shop_name}: Page 1 - {page1_synced} synced, found_existing={found_existing_in_page1}"
                    )
                    
                    # Nếu page 1 có feedback trùng -> tiếp tục page 2
                    if found_existing_in_page1:
                        # Update cursor từ page 1
                        if feedbacks_page1:
                            cursor = feedbacks_page1[-1].get("comment_id", cursor)
                        
                        # === PAGE 2 ===
                        page = 2
                        self.update_job_progress(
                            job,
                            log_message=f"📄 Shop {shop_name}: Fetching page 2 (cursor={cursor}, page_size={page_size})"
                        )
                        
                        response = shopee_client.repo.get_shop_ratings_raw(
                            rating_star="5,4,3,2,1",
                            time_start=time_start,
                            time_end=time_end,
                            page_number=page,
                            page_size=page_size,
                            cursor=cursor,
                            from_page_number=1,
                            language="vi"
                        )
                        
                        if response.get("code") != 0:
                            self.update_job_progress(
                                job,
                                error_message=f"Shopee API error (page 2): {response.get('message')}"
                            )
                            continue
                        
                        feedbacks_page2 = response.get("data", {}).get("list", [])
                        if not feedbacks_page2:
                            # Không có feedback nào trong page 2
                            self.update_job_progress(
                                job,
                                log_message=f"ℹ️ Shop {shop_name}: Không có feedback nào trong page 2"
                            )
                            continue
                        
                        # Xử lý page 2
                        page2_synced = 0
                        for feedback_data in feedbacks_page2:
                            comment_id = feedback_data.get("comment_id")
                            if not comment_id:
                                continue
                            
                            # Check xem đã có trong DB chưa
                            if Feedback.objects.filter(feedback_id=comment_id).exists():
                                found_existing_in_page2 = True
                                result["stopped_at_existing"] = True
                                self.update_job_progress(
                                    job,
                                    log_message=f"⏹️ Shop {shop_name}: Page 2 có feedback trùng (ID: {comment_id}), dừng"
                                )
                                break
                            
                            # Chưa có -> sync (tạo mới)
                            try:
                                feedback_data["connection_id"] = connection_id
                                self.feedback_service._process_feedback_from_shopee(feedback_data)
                                
                                page2_synced += 1
                                total_synced += 1
                                result["synced"] += 1
                                self.update_job_progress(
                                    job,
                                    processed=1,
                                    synced=1,
                                    updated=0
                                )
                                
                            except Exception as e:
                                error_msg = f"Error processing feedback {comment_id}: {str(e)}"
                                logger.error(error_msg, exc_info=True)
                                self.update_job_progress(
                                    job,
                                    errors=1,
                                    error_message=error_msg
                                )
                                result["errors"].append(error_msg)
                        
                        self.update_job_progress(
                            job,
                            log_message=f"📄 Shop {shop_name}: Page 2 - {page2_synced} synced, found_existing={found_existing_in_page2}"
                        )
                    else:
                        # Page 1 không có feedback trùng -> dừng shop này
                        self.update_job_progress(
                            job,
                            log_message=f"✅ Shop {shop_name}: Page 1 không có feedback trùng, dừng"
                        )
                    
                    if total_synced > 0:
                        self.update_job_progress(
                            job,
                            log_message=f"✅ Shop {shop_name}: Tổng {total_synced} feedbacks mới"
                        )
                    
                except Exception as e:
                    error_msg = f"Lỗi khi xử lý shop {shop_name}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    self.update_job_progress(
                        job,
                        errors=1,
                        error_message=error_msg
                    )
                    result["errors"].append(error_msg)
                    continue
            
            # Mark as completed
            job.status = 'completed'
            job.completed_at = timezone.now()
            job.save()
            
            self.update_job_progress(
                job,
                log_message=f"✅ Hoàn thành incremental sync: {result['synced']} synced, {result['updated']} updated"
            )
            
        except Exception as e:
            error_msg = f"Lỗi trong run_incremental_sync: {str(e)}"
            logger.error(error_msg, exc_info=True)
            job.status = 'failed'
            job.completed_at = timezone.now()
            job.save()
            result["success"] = False
            result["errors"].append(error_msg)
        
        return result


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
        days: int = 365,
        page_size: int = 50,
        max_feedbacks_per_shop: Optional[int] = None
    ) -> FeedbackSyncJob:
        """
        Tạo full sync job.
        
        Args:
            days: Số ngày gần nhất cần sync
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
            
            # Tính toán time range
            tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
            now_vn = datetime.now(tz_vn)
            time_end = int(now_vn.timestamp())
            time_start = int((now_vn - timedelta(days=job.days)).timestamp())
            
            self.update_job_progress(
                job,
                log_message=f"📅 Time range: {time_start} -> {time_end} ({job.days} ngày)"
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
            start_index = job.current_shop_index if job.status == 'paused' else 0
            
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
                
                try:
                    # Gọi feedback_service để sync shop này
                    shop_result = self.feedback_service.sync_feedbacks_from_shopee(
                        days=job.days,
                        page_size=job.page_size,
                        max_feedbacks_per_shop=job.max_feedbacks_per_shop,
                        connection_ids=[connection_id],  # Chỉ sync shop này
                        progress_callback=lambda msg: self.update_job_progress(job, log_message=msg)
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
        - Quét từ mới nhất (time_end = now)
        - Mỗi batch 50 feedbacks
        - Nếu gặp feedback đã có trong DB -> dừng (đã hết mới)
        - Nếu chưa có -> tiếp tục quét
        
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
            
            # Lấy feedback mới nhất từ DB để biết điểm bắt đầu
            latest_feedback = Feedback.objects.order_by('-create_time').first()
            
            if latest_feedback:
                # create_time là BigInteger (timestamp), set time_start = latest_feedback.create_time - buffer (1 giờ)
                time_start = latest_feedback.create_time - 3600
                self.update_job_progress(
                    job,
                    log_message=f"📅 Lấy feedbacks mới hơn feedback ID {latest_feedback.feedback_id} (create_time: {latest_feedback.create_time})"
                )
            else:
                # Nếu chưa có feedback nào, sync 7 ngày gần nhất
                tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
                now_vn = datetime.now(tz_vn)
                time_start = int((now_vn - timedelta(days=7)).timestamp())
                self.update_job_progress(
                    job,
                    log_message="📅 Chưa có feedback nào, sync 7 ngày gần nhất"
                )
            
            time_end = int(datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).timestamp())
            
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
                    # Quét từng batch
                    batch_synced = 0
                    page = 1
                    cursor = 0
                    found_existing = False
                    
                    while True:
                        # Tạo ShopeeClient
                        shopee_client = ShopeeClient(shop_key=connection_id)
                        
                        # Fetch batch
                        response = shopee_client.repo.get_shop_ratings_raw(
                            rating_star="5,4,3,2,1",
                            time_start=time_start,
                            time_end=time_end,
                            page_number=page,
                            page_size=job.batch_size,
                            cursor=cursor,
                            from_page_number=1,
                            language="vi"
                        )
                        
                        if response.get("code") != 0:
                            self.update_job_progress(
                                job,
                                error_message=f"Shopee API error: {response.get('message')}"
                            )
                            break
                        
                        feedbacks = response.get("data", {}).get("list", [])
                        if not feedbacks:
                            # Hết dữ liệu
                            break
                        
                        # Process từng feedback trong batch
                        for feedback_data in feedbacks:
                            comment_id = feedback_data.get("comment_id")
                            if not comment_id:
                                continue
                            
                            # Check xem đã có trong DB chưa
                            if Feedback.objects.filter(feedback_id=comment_id).exists():
                                # Đã có -> dừng
                                found_existing = True
                                result["stopped_at_existing"] = True
                                self.update_job_progress(
                                    job,
                                    log_message=f"⏹️ Gặp feedback đã có (ID: {comment_id}), dừng incremental sync cho shop {shop_name}"
                                )
                                break
                            
                            # Chưa có -> sync (tạo mới)
                            try:
                                feedback_data["connection_id"] = connection_id
                                # _process_feedback_from_shopee sẽ tạo mới vì ta đã check không tồn tại ở trên
                                self.feedback_service._process_feedback_from_shopee(feedback_data)
                                
                                batch_synced += 1
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
                        
                        # Nếu gặp feedback đã có, dừng
                        if found_existing:
                            break
                        
                        # Nếu batch có ít hơn batch_size, đã hết
                        if len(feedbacks) < job.batch_size:
                            break
                        
                        # Update cursor và page cho batch tiếp theo
                        if feedbacks:
                            cursor = feedbacks[-1].get("comment_id", cursor)
                        page += 1
                        
                        # Giới hạn số batch để tránh chạy quá lâu
                        if page > 100:
                            self.update_job_progress(
                                job,
                                log_message=f"⚠️ Đã quét 100 batches cho shop {shop_name}, dừng"
                            )
                            break
                    
                    if batch_synced > 0:
                        self.update_job_progress(
                            job,
                            log_message=f"✅ Shop {shop_name}: {batch_synced} feedbacks mới"
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


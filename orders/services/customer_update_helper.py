# orders/services/customer_update_helper.py
"""
Helper functions để auto-update customer info từ Shopee data.
Non-blocking - errors won't stop order printing.
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def update_customer_from_shopee_data(
    customer_id: int,
    shopee_order_info: Dict[str, Any],
    pdf_bytes: bytes
) -> None:
    """
    Non-blocking helper to auto-update customer info from Shopee data.
    
    Updates:
    1. Shopee username → customer.website (format: "short_name/username")
    2. Customer email from Shopee KNB API (if available and not masked)
    3. Customer name from PDF (only if masked with *****)
    4. Customer address from PDF (only if masked with *****)
    5. Shopee data (short_name, user_name, user_portrait) → customer.description (JSON)
    
    ⭐ TẤT CẢ UPDATES (email + description) ĐƯỢC GỘP VÀO 1 API CALL DUY NHẤT
    
    Args:
        customer_id: Sapo customer ID
        shopee_order_info: Dict from ShopeeClient.get_shopee_order_id() containing:
            - order_id: Shopee order ID
            - buyer_name: Shopee username
            - buyer_image: Shopee avatar ID (user_portrait)
            - shop_name: (optional) Shop name for email API call
        pdf_bytes: PDF bytes for extracting customer info
    """
    logger.info(f"[CustomerUpdateHelper] ========== START ==========")
    logger.info(f"[CustomerUpdateHelper] Customer ID: {customer_id}")
    logger.info(f"[CustomerUpdateHelper] Shopee order info keys: {list(shopee_order_info.keys())}")
    
    try:
        # Initialize services
        from core.sapo_client import get_sapo_client
        from customers.services import CustomerService
        from orders.services.pdf_customer_extractor import extract_customer_info_from_pdf
        
        sapo = get_sapo_client()
        customer_service = CustomerService(sapo)
        
        # Get current customer để lấy thông tin hiện tại
        current_customer = customer_service.get_customer(customer_id)
        
        # ===================================================================
        # 1. PREPARE DATA FOR DESCRIPTION UPDATE
        # ===================================================================
        buyer_name = shopee_order_info.get("buyer_name", "")
        buyer_image = shopee_order_info.get("buyer_image", "")
        
        logger.info(f"[CustomerUpdateHelper] Buyer name: {buyer_name}, Buyer image: {buyer_image}")
        
        # Parse buyer_name để tách short_name và user_name
        # Format có thể là: "hang2530." hoặc "short_name/user_name"
        user_name = buyer_name.strip() if buyer_name else ""
        short_name = None
        
        if "/" in buyer_name:
            # Có format "short_name/user_name"
            parts = buyer_name.split("/", 1)
            short_name = parts[0].strip() if parts[0] else None
            user_name = parts[1].strip() if len(parts) > 1 and parts[1] else ""
        else:
            # Chỉ có user_name, lấy short_name từ customer hiện tại (nếu có)
            # Không set short_name nếu customer chưa có (để không update vào description)
            current_short_name = current_customer.short_name or current_customer.name or ""
            if current_short_name and not current_short_name.startswith("****"):
                # Chỉ dùng nếu không bị mask
                short_name = current_short_name
        
        # Chuẩn hóa user_portrait từ buyer_image
        user_portrait = None
        if buyer_image and buyer_image.strip():
            # buyer_image có thể là:
            # - Empty string ""
            # - Avatar ID như "vn-11134233-7qukw-ljp38pnhuxmc97"
            # - Full URL (hiếm)
            if buyer_image.startswith("http"):
                # Extract ID từ URL
                if "cf.shopee.vn/file/" in buyer_image:
                    user_portrait = buyer_image.split("cf.shopee.vn/file/")[-1]
                else:
                    user_portrait = buyer_image.split("/")[-1]
            else:
                # Đã là ID rồi
                user_portrait = buyer_image.strip()
            
            # Chỉ giữ nếu có giá trị thực sự
            if not user_portrait:
                user_portrait = None
        
        logger.info(f"[CustomerUpdateHelper] Parsed: short_name={short_name}, user_name={user_name}, user_portrait={user_portrait}")
        
        # ===================================================================
        # 2. GET EMAIL FROM SHOPEE KNB API
        # ===================================================================
        email = None
        shopee_order_id = shopee_order_info.get("order_id")
        if shopee_order_id:
            try:
                from core.shopee_client import ShopeeClient
                from core.system_settings import get_shop_by_connection_id
                
                # Try to get shop_name from shopee_order_info or use connection_id
                shop_name = shopee_order_info.get("shop_name")
                if not shop_name:
                    # Try to get from connection_id if available
                    connection_id = shopee_order_info.get("connection_id")
                    if connection_id:
                        shop_cfg = get_shop_by_connection_id(connection_id)
                        if shop_cfg:
                            shop_name = shop_cfg.get("name")
                
                # Default fallback
                if not shop_name:
                    shop_name = "giadungplus_official"
                
                logger.info(f"[CustomerUpdateHelper] Getting email from Shopee KNB for order {shopee_order_id} (shop: {shop_name})")
                shopee_client = ShopeeClient(shop_name)
                
                email = shopee_client.get_customer_email(shopee_order_id)
                
                if not email:
                    email = "noemail@gmail.com"
                    logger.info(f"[CustomerUpdateHelper] No email from Shopee, using default: {email}")
                else:
                    logger.info(f"[CustomerUpdateHelper] Found email from Shopee: {email}")
            except Exception as e:
                logger.warning(f"[CustomerUpdateHelper] Failed to get email from Shopee: {e}", exc_info=True)
        
        # ===================================================================
        # 3. EXTRACT CUSTOMER INFO FROM PDF
        # ===================================================================
        logger.info(f"[CustomerUpdateHelper] Extracting customer info from PDF (size: {len(pdf_bytes)} bytes)...")
        pdf_customer_info = extract_customer_info_from_pdf(pdf_bytes)
        logger.info(f"[CustomerUpdateHelper] PDF extraction result: {pdf_customer_info}")
        
        pdf_name = pdf_customer_info.get("name")
        pdf_address = pdf_customer_info.get("address")
        
        # ===================================================================
        # 4. UPDATE CUSTOMER - GỘP TẤT CẢ VÀO 1 API CALL DUY NHẤT
        # ===================================================================
        try:
            # Build description JSON - LUÔN UPDATE NẾU CÓ BẤT KỲ DATA NÀO
            new_description = None
            # Kiểm tra xem có data để update description không
            has_description_data = bool(user_name) or bool(user_portrait) or bool(short_name)
            
            if has_description_data:
                # Import helper function từ customer_service module
                from customers.services import customer_service as cs_module
                
                # Chỉ truyền các giá trị không rỗng (không truyền None nếu là empty string)
                desc_kwargs = {}
                if short_name and short_name.strip():
                    desc_kwargs["short_name"] = short_name.strip()
                if user_name and user_name.strip():
                    desc_kwargs["user_name"] = user_name.strip()
                if user_portrait and user_portrait.strip():
                    desc_kwargs["user_portrait"] = user_portrait.strip()
                
                if desc_kwargs:
                    new_description = cs_module.merge_customer_description(
                        current_description=current_customer.description,
                        **desc_kwargs
                    )
                    logger.info(f"[CustomerUpdateHelper] Prepared description: {new_description}")
                else:
                    logger.warning(f"[CustomerUpdateHelper] No valid description data to update (all empty)")
            else:
                logger.info(f"[CustomerUpdateHelper] No description data available (user_name, user_portrait, short_name all empty)")
            
            # ⭐ GỘP TẤT CẢ UPDATES VÀO 1 API CALL (CHỈ EMAIL + DESCRIPTION, BỎ WEBSITE)
            update_kwargs = {}
            if email:
                update_kwargs["email"] = email
            if new_description:
                update_kwargs["description"] = new_description
            
            if update_kwargs:
                logger.info(f"[CustomerUpdateHelper] Updating customer with: {list(update_kwargs.keys())}")
                updated_customer = customer_service.update_customer_info(
                    customer_id=customer_id,
                    **update_kwargs
                )
                logger.info(f"[CustomerUpdateHelper] ✅ Customer updated successfully!")
                if email:
                    logger.info(f"[CustomerUpdateHelper]   - Email: {updated_customer.email}")
                if new_description:
                    logger.info(f"[CustomerUpdateHelper]   - Description: {updated_customer.description}")
            else:
                logger.info(f"[CustomerUpdateHelper] No updates needed (no email or description)")
            
        except Exception as e:
            logger.error(f"[CustomerUpdateHelper] ❌ Customer update failed: {e}", exc_info=True)
        
        # ===================================================================
        # 5. UPDATE NAME/ADDRESS FROM PDF (separate call - không gộp)
        # ===================================================================
        if pdf_name or pdf_address:
            try:
                logger.info(f"[CustomerUpdateHelper] Calling update_from_pdf_data with name={pdf_name}, address={pdf_address} (force_update=True)...")
                updated_customer = customer_service.update_from_pdf_data(
                    customer_id=customer_id,
                    pdf_name=pdf_name,
                    pdf_address=pdf_address,
                    force_update=True  # ⭐ Always update, not just when masked
                )
                logger.info(f"[CustomerUpdateHelper] ✅ PDF data update completed! Customer name: {updated_customer.name}")
            except Exception as e:
                logger.error(f"[CustomerUpdateHelper] ❌ PDF data update failed: {e}", exc_info=True)
        else:
            logger.info(f"[CustomerUpdateHelper] No data extracted from PDF, skipping PDF update")
        
        logger.info(f"[CustomerUpdateHelper] ========== DONE ==========")
        
    except Exception as e:
        # Non-blocking: log error but don't raise
        logger.error(f"[CustomerUpdateHelper] ❌ Customer auto-update failed: {e}", exc_info=True)


def update_customer_from_pdf_only(
    customer_id: int,
    pdf_bytes: bytes
) -> None:
    """
    Non-blocking helper to auto-update customer info from PDF only.
    Sử dụng cho express_orders (không có shopee_order_info).
    
    Updates:
    1. Customer name from PDF (only if masked with *****)
    2. Customer address from PDF (only if masked with *****)
    
    Args:
        customer_id: Sapo customer ID
        pdf_bytes: PDF bytes for extracting customer info
    """
    logger.info(f"[CustomerUpdateHelper] ========== START (PDF Only) ==========")
    logger.info(f"[CustomerUpdateHelper] Customer ID: {customer_id}")
    
    try:
        # Initialize services
        from core.sapo_client import get_sapo_client
        from customers.services import CustomerService
        from orders.services.pdf_customer_extractor import extract_customer_info_from_pdf
        
        sapo = get_sapo_client()
        customer_service = CustomerService(sapo)
        
        # Extract customer info from PDF (chỉ đọc 25% đầu file)
        logger.info(f"[CustomerUpdateHelper] Extracting customer info from PDF (size: {len(pdf_bytes)} bytes)...")
        pdf_customer_info = extract_customer_info_from_pdf(pdf_bytes)
        logger.info(f"[CustomerUpdateHelper] PDF extraction result: {pdf_customer_info}")
        
        pdf_name = pdf_customer_info.get("name")
        pdf_address = pdf_customer_info.get("address")
        
        # Update name/address from PDF (force update - always update if data available)
        if pdf_name or pdf_address:
            try:
                logger.info(f"[CustomerUpdateHelper] Calling update_from_pdf_data with name={pdf_name}, address={pdf_address} (force_update=True)...")
                updated_customer = customer_service.update_from_pdf_data(
                    customer_id=customer_id,
                    pdf_name=pdf_name,
                    pdf_address=pdf_address,
                    force_update=True  # ⭐ Always update, not just when masked
                )
                logger.info(f"[CustomerUpdateHelper] ✅ PDF data update completed! Customer name: {updated_customer.name}")
            except Exception as e:
                logger.error(f"[CustomerUpdateHelper] ❌ PDF data update failed: {e}", exc_info=True)
        else:
            logger.info(f"[CustomerUpdateHelper] No data extracted from PDF, skipping PDF update")
        
        logger.info(f"[CustomerUpdateHelper] ========== DONE (PDF Only) ==========")
        
    except Exception as e:
        # Non-blocking: log error but don't raise
        logger.error(f"[CustomerUpdateHelper] ❌ Customer auto-update from PDF failed: {e}", exc_info=True)
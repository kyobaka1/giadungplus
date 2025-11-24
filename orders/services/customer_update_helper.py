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
    
    Args:
        customer_id: Sapo customer ID
        shopee_order_info: Dict from ShopeeClient.get_shopee_order_id() containing:
            - order_id: Shopee order ID
            - buyer_name: Shopee username
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
        
        # 1. Update username from Shopee
        buyer_name = shopee_order_info.get("buyer_name")
        logger.info(f"[CustomerUpdateHelper] Buyer name from Shopee: {buyer_name}")
        
        if buyer_name:
            try:
                logger.info(f"[CustomerUpdateHelper] Calling update_username...")
                updated_customer = customer_service.update_username(customer_id, buyer_name)
                logger.info(f"[CustomerUpdateHelper] ✅ Username updated! New website: {updated_customer.website}")
            except Exception as e:
                logger.error(f"[CustomerUpdateHelper] ❌ Username update failed: {e}", exc_info=True)
        else:
            logger.warning(f"[CustomerUpdateHelper] No buyer_name in shopee_order_info, skipping username update")
        
        # 1.5. Update email from Shopee KNB API
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
                
                # If no email from Shopee, use default to indicate we tried
                if not email:
                    email = "noemail@gmail.com"
                    logger.info(f"[CustomerUpdateHelper] No email from Shopee, using default: {email}")
                else:
                    logger.info(f"[CustomerUpdateHelper] Found email from Shopee: {email}")
                
                # Always update email (either real email or default)
                try:
                    updated_customer = customer_service.update_customer_info(
                        customer_id=customer_id,
                        email=email
                    )
                    logger.info(f"[CustomerUpdateHelper] ✅ Email updated! New email: {updated_customer.email}")
                except Exception as e:
                    logger.error(f"[CustomerUpdateHelper] ❌ Email update failed: {e}", exc_info=True)
            except Exception as e:
                logger.warning(f"[CustomerUpdateHelper] Failed to get email from Shopee: {e}", exc_info=True)
        
        # 2. Extract customer info from PDF
        logger.info(f"[CustomerUpdateHelper] Extracting customer info from PDF (size: {len(pdf_bytes)} bytes)...")
        pdf_customer_info = extract_customer_info_from_pdf(pdf_bytes)
        logger.info(f"[CustomerUpdateHelper] PDF extraction result: {pdf_customer_info}")
        
        pdf_name = pdf_customer_info.get("name")
        pdf_address = pdf_customer_info.get("address")
        
        # 3. Update name/address from PDF if masked
        if pdf_name or pdf_address:
            try:
                logger.info(f"[CustomerUpdateHelper] Calling update_from_pdf_data with name={pdf_name}, address={pdf_address}...")
                updated_customer = customer_service.update_from_pdf_data(
                    customer_id=customer_id,
                    pdf_name=pdf_name,
                    pdf_address=pdf_address
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
        
        # Update name/address from PDF if available
        if pdf_name or pdf_address:
            try:
                logger.info(f"[CustomerUpdateHelper] Calling update_from_pdf_data with name={pdf_name}, address={pdf_address}...")
                updated_customer = customer_service.update_from_pdf_data(
                    customer_id=customer_id,
                    pdf_name=pdf_name,
                    pdf_address=pdf_address
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
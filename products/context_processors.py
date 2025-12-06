"""
Context processors for products app.
Provides product and variant counts to all templates.
"""

from typing import Dict, Any
import logging

from core.sapo_client import get_sapo_client
from products.services.sapo_product_service import SapoProductService

logger = logging.getLogger(__name__)


def product_counts(request) -> Dict[str, Any]:
    """
    Context processor để cung cấp số lượng sản phẩm và phân loại cho tất cả templates.
    
    Returns:
        {
            "product_count": int,
            "variant_count": int
        }
    """
    try:
        sapo_client = get_sapo_client()
        core_repo = sapo_client.core
        
        # Lấy response raw để có metadata
        response = core_repo.list_products_raw(page=1, limit=1, status="active")
        metadata = response.get("metadata", {})
        
        # Lấy tổng số products từ metadata nếu có
        product_count = metadata.get("total", 0)
        
        # Nếu không có metadata.total, đếm từ danh sách products
        if product_count == 0:
            products_data = response.get("products", [])
            product_count = len(products_data)
        
        # Đếm tổng số variants: lấy một số products để đếm variants
        # Tối ưu: chỉ lấy page 1 với limit=250 để đếm variants
        variant_count = 0
        if product_count > 0:
            # Lấy products để đếm variants
            products = SapoProductService(sapo_client).list_products(page=1, limit=250, status="active")
            variant_count = sum(p.variant_count for p in products)
            
            # Nếu có nhiều hơn 250 products, ước tính dựa trên tỷ lệ
            if product_count > 250:
                avg_variants_per_product = variant_count / len(products) if products else 0
                variant_count = int(product_count * avg_variants_per_product)
        
        return {
            "product_count": product_count,
            "variant_count": variant_count,
        }
        
    except Exception as e:
        logger.error(f"Error in product_counts context processor: {e}", exc_info=True)
        # Trả về giá trị mặc định nếu có lỗi
        return {
            "product_count": 0,
            "variant_count": 0,
        }


# settings/services/negative_stock_balance_service.py
"""
Service để xử lý cân bằng tồn kho âm (Negative Stock Balance).

Chức năng:
- Lấy tất cả products và variants từ Sapo
- Tìm variants có tồn kho âm (< 0) trong inventories
- Chia thành 2 nhóm: kho Gele (241737) và kho Tokyo Sài Gòn (548744)
- Tạo phiếu kiểm hàng (stock adjustment) để đưa tồn kho âm về 0
"""

from typing import List, Dict, Any, Optional, Tuple
import logging
import json

from core.sapo_client import get_sapo_client

logger = logging.getLogger(__name__)

# Debug print function
DEBUG_PRINT_ENABLED = True  # Bật debug để theo dõi luồng làm việc

def debug_print(*args, **kwargs):
    """Debug print function cho negative stock balance service"""
    if DEBUG_PRINT_ENABLED:
        print("[NegativeStockBalance DEBUG]", *args, **kwargs)

# Location IDs
LOCATION_GELE = 241737  # Hà Nội
LOCATION_TOKY = 548744  # Hồ Chí Minh

# Adjustment account ID (staff_id)
ADJUSTMENT_ACCOUNT_ID = 319911


class NegativeStockBalanceService:
    """
    Service để xử lý cân bằng tồn kho âm.
    """
    
    def __init__(self):
        """Initialize service với SapoClient."""
        self.sapo_client = get_sapo_client()
        self.core_repo = self.sapo_client.core
    
    def get_all_variants_with_inventory(self) -> List[Dict[str, Any]]:
        """
        Lấy tất cả variants có inventory từ Sapo.
        
        Returns:
            List of variants với inventory data
        """
        debug_print("="*60)
        debug_print("BƯỚC 1: Bắt đầu lấy tất cả products và variants...")
        debug_print("="*60)
        logger.info("[NegativeStockBalance] Bắt đầu lấy tất cả products và variants...")
        
        all_variants = []
        page = 1
        limit = 250
        
        while True:
            try:
                debug_print(f"\n📄 Đang lấy products (trang {page}, limit {limit})...")
                
                # Lấy products từ Sapo
                response = self.core_repo.get("products.json", params={
                    "page": page,
                    "limit": limit,
                    "status": "active"  # Chỉ lấy sản phẩm active
                })
                
                products = response.get("products", [])
                debug_print(f"   ✓ API response: {len(products)} products")
                
                if not products:
                    debug_print(f"   ⚠️  Không có products nào ở trang {page}, dừng pagination")
                    break
                
                logger.info(f"[NegativeStockBalance] Đã lấy {len(products)} products (trang {page})")
                debug_print(f"   → Đã lấy {len(products)} products (trang {page})")
                
                # Xử lý từng product
                variants_count = 0
                skipped_combo = 0
                for product in products:
                    variants = product.get("variants", [])
                    product_product_type = product.get("product_type", "normal")  # Kiểm tra product_type ở level product
                    debug_print(f"   Product {product.get('id')}: {product.get('name')[:50]}... - {len(variants)} variants, product_type={product_product_type}")
                    
                    # Bỏ qua toàn bộ product nếu product_type là composite hoặc packed
                    if product_product_type in ["composite", "packed"]:
                        skipped_combo += len(variants)
                        if skipped_combo <= 5:  # Debug: In ra 5 products combo đầu tiên
                            debug_print(f"   ⏭️  Bỏ qua toàn bộ product {product.get('id')} (product_type={product_product_type}), {len(variants)} variants")
                        continue
                    
                    for variant in variants:
                        # Bỏ qua variants có product_type là composite hoặc packed (combo) - kiểm tra cả variant level
                        variant_product_type = variant.get("product_type", product_product_type)  # Fallback về product level
                        if variant_product_type in ["composite", "packed"]:
                            skipped_combo += 1
                            if skipped_combo <= 5:  # Debug: In ra 5 variants combo đầu tiên
                                debug_print(f"   ⏭️  Bỏ qua variant {variant.get('id')} (SKU: {variant.get('sku')}): variant_product_type={variant_product_type}")
                            continue
                        
                        # Lấy inventories của variant
                        inventories = variant.get("inventories", [])
                        
                        # Thêm thông tin product vào variant để dễ xử lý
                        variant_with_product = {
                            "variant_id": variant.get("id"),
                            "product_id": variant.get("product_id"),
                            "product_name": product.get("name"),
                            "variant_name": variant.get("name"),
                            "sku": variant.get("sku"),
                            "product_type": variant_product_type,  # Lưu product_type để dùng sau (đã kiểm tra cả variant và product level)
                            "inventories": inventories
                        }
                        all_variants.append(variant_with_product)
                        variants_count += 1
                
                debug_print(f"   → Tổng variants đã lấy: {variants_count} (từ trang {page})")
                debug_print(f"   → Tổng variants tích lũy: {len(all_variants)}")
                
                # Kiểm tra xem còn trang tiếp theo không
                metadata = response.get("metadata", {})
                total_pages = metadata.get("total_pages", 0)
                debug_print(f"   → Metadata: total_pages = {total_pages}, current_page = {page}")
                
                if page >= total_pages:
                    debug_print(f"   ✓ Đã đến trang cuối ({page}/{total_pages}), dừng pagination")
                    break
                
                page += 1
                
            except Exception as e:
                debug_print(f"   ❌ LỖI khi lấy products (trang {page}): {e}")
                logger.error(f"[NegativeStockBalance] Lỗi khi lấy products (trang {page}): {e}", exc_info=True)
                break
        
        debug_print(f"\n✅ Hoàn tất: Tổng cộng lấy được {len(all_variants)} variants từ {page-1} trang")
        if skipped_combo > 0:
            debug_print(f"   ⏭️  Đã bỏ qua {skipped_combo} variants combo/packed")
        logger.info(f"[NegativeStockBalance] Tổng cộng lấy được {len(all_variants)} variants (đã bỏ qua {skipped_combo} combo/packed)")
        return all_variants
    
    def find_negative_stocks(self, variants: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Tìm variants có tồn kho âm, chia thành 2 nhóm theo location.
        
        Args:
            variants: List variants với inventory data
            
        Returns:
            Tuple (gele_items, toky_items)
            Mỗi item có format:
            {
                "variant_id": int,
                "product_id": int,
                "product_name": str,
                "variant_name": str,
                "sku": str,
                "before_quantity": float (tồn kho hiện tại, < 0),
                "location_id": int
            }
        """
        debug_print("\n" + "="*60)
        debug_print("BƯỚC 2: Đang tìm variants có tồn kho âm...")
        debug_print("="*60)
        logger.info("[NegativeStockBalance] Đang tìm variants có tồn kho âm...")
        
        gele_items = []
        toky_items = []
        
        debug_print(f"   → Kiểm tra {len(variants)} variants...")
        
        for idx, variant in enumerate(variants, 1):
            inventories = variant.get("inventories", [])
            
            for inventory in inventories:
                location_id = inventory.get("location_id")
                on_hand = inventory.get("on_hand", 0)
                
                # Debug: In ra một số inventory mẫu
                if idx <= 5 or on_hand < 0:
                    debug_print(f"   Variant {variant.get('variant_id')} (SKU: {variant.get('sku')}): location_id={location_id}, on_hand={on_hand}")
                
                # Chỉ xử lý nếu tồn kho < 0
                if on_hand < 0:
                    # Bỏ qua variants có product_type là composite hoặc packed (combo)
                    product_type = variant.get("product_type", "normal")
                    if product_type in ["composite", "packed"]:
                        debug_print(f"   ⏭️  Bỏ qua variant {variant.get('variant_id')} (SKU: {variant.get('sku')}): product_type={product_type}, on_hand={on_hand}")
                        continue
                    
                    item = {
                        "variant_id": variant.get("variant_id"),
                        "product_id": variant.get("product_id"),
                        "product_name": variant.get("product_name"),
                        "variant_name": variant.get("variant_name"),
                        "sku": variant.get("sku"),
                        "product_type": product_type,  # Lưu product_type để dùng khi tạo line_item
                        "before_quantity": int(on_hand),  # Integer, không phải float
                        "location_id": location_id
                    }
                    
                    debug_print(f"   ⚠️  Tìm thấy tồn kho âm: Variant {item['variant_id']} (SKU: {item['sku']}), on_hand={on_hand}, location_id={location_id}")
                    
                    if location_id == LOCATION_GELE:
                        gele_items.append(item)
                    elif location_id == LOCATION_TOKY:
                        toky_items.append(item)
                    else:
                        debug_print(f"   ⚠️  Location ID {location_id} không khớp với Gele ({LOCATION_GELE}) hoặc Tokyo ({LOCATION_TOKY})")
        
        debug_print(f"\n✅ Kết quả:")
        debug_print(f"   → Kho Gele (241737): {len(gele_items)} variants âm")
        debug_print(f"   → Kho Tokyo (548744): {len(toky_items)} variants âm")
        
        logger.info(f"[NegativeStockBalance] Tìm thấy {len(gele_items)} variants âm ở kho Gele")
        logger.info(f"[NegativeStockBalance] Tìm thấy {len(toky_items)} variants âm ở kho Tokyo")
        
        return gele_items, toky_items
    
    def create_stock_adjustment(self, location_id: int, items: List[Dict[str, Any]], note: str = "") -> Optional[Dict[str, Any]]:
        """
        Tạo phiếu kiểm hàng trên Sapo để đưa tồn kho âm về 0.
        
        Args:
            location_id: Location ID (241737 hoặc 548744)
            items: List các variants cần điều chỉnh
            note: Ghi chú cho phiếu kiểm
            
        Returns:
            Dict response từ Sapo hoặc None nếu lỗi
        """
        location_name = "Gele (Hà Nội)" if location_id == LOCATION_GELE else "Tokyo (Hồ Chí Minh)"
        
        debug_print("\n" + "="*60)
        debug_print(f"BƯỚC 3: Tạo phiếu kiểm cho {location_name} (location_id={location_id})")
        debug_print("="*60)
        
        if not items:
            debug_print(f"   ⚠️  Không có items nào để tạo phiếu kiểm cho location {location_id}")
            logger.warning(f"[NegativeStockBalance] Không có items nào để tạo phiếu kiểm cho location {location_id}")
            return None
        
        debug_print(f"   → Số lượng items: {len(items)}")
        logger.info(f"[NegativeStockBalance] Đang tạo phiếu kiểm cho {location_name} với {len(items)} items...")
        
        # Tạo line_items cho phiếu kiểm
        line_items = []
        skipped_combo_items = []
        debug_print(f"\n   📝 Đang tạo line_items...")
        for idx, item in enumerate(items, start=1):
            # Kiểm tra lại product_type (phòng trường hợp đã lọc ở bước trước nhưng double-check)
            product_type = item.get("product_type", "normal")
            if product_type in ["composite", "packed"]:
                skipped_combo_items.append(item)
                debug_print(f"   ⏭️  Bỏ qua item {idx}: variant_id={item['variant_id']}, product_type={product_type}")
                continue
            
            before_quantity = int(item["before_quantity"])  # Integer
            after_quantity = 0  # Đưa về 0, integer
            quantity = 0  # Theo API example, quantity luôn = 0
            
            if len(line_items) < 3:  # Debug: In ra 3 line_items đầu tiên
                debug_print(f"   Line {len(line_items) + 1}: variant_id={item['variant_id']}, before={before_quantity}, after={after_quantity}, quantity={quantity}, product_type={product_type}")
            
            line_item = {
                "quantity": quantity,
                "product_id": item["product_id"],
                "variant_id": item["variant_id"],
                "before_quantity": before_quantity,
                "after_quantity": after_quantity,
                "product_type": product_type,  # Dùng product_type từ item, default là "normal"
                "reason": "Khác",
                "position": len(line_items) + 1,  # Position theo số lượng line_items đã thêm (bỏ qua combo)
                "lineIndex": len(line_items) + 1,  # lineIndex theo số lượng line_items đã thêm
                "isEdited": True
            }
            line_items.append(line_item)
        
        if skipped_combo_items:
            debug_print(f"   ⚠️  Đã bỏ qua {len(skipped_combo_items)} items combo/packed khi tạo line_items")
        
        debug_print(f"   ✓ Đã tạo {len(line_items)} line_items")
        
        # Tạo payload cho stock adjustment
        stock_adjustment_data = {
            "location_id": location_id,
            "adjustment_account_id": ADJUSTMENT_ACCOUNT_ID,
            "balance_account_id": ADJUSTMENT_ACCOUNT_ID,  # Thêm balance_account_id
            "code": "",  # Sapo sẽ tự tạo
            "tags": "",
            "note": note or f"Cân bằng tồn kho âm - {location_name} ({len(items)} variants)",
            "line_items": line_items,
            "inventoried": True  # Thêm inventoried = true
        }
        
        # Payload cuối cùng sẽ được wrap trong "stock_adjustment" bởi repository
        final_payload = {
            "stock_adjustment": stock_adjustment_data
        }
        
        debug_print(f"\n   📦 Payload stock adjustment:")
        debug_print(f"   → location_id: {location_id}")
        debug_print(f"   → adjustment_account_id: {ADJUSTMENT_ACCOUNT_ID}")
        debug_print(f"   → balance_account_id: {ADJUSTMENT_ACCOUNT_ID}")
        debug_print(f"   → inventoried: {stock_adjustment_data['inventoried']}")
        debug_print(f"   → note: {stock_adjustment_data['note']}")
        debug_print(f"   → line_items count: {len(line_items)}")
        
        # Debug: In ra payload JSON cuối cùng (sau khi wrap trong stock_adjustment)
        payload_json = json.dumps(final_payload, indent=2, ensure_ascii=False)
        if len(payload_json) > 2000:
            debug_print(f"\n   📤 FULL PAYLOAD (first 2000 chars):")
            debug_print(f"   {'='*70}")
            debug_print(f"   {payload_json[:2000]}...")
            debug_print(f"   ... (truncated, total length: {len(payload_json)} chars)")
            debug_print(f"   {'='*70}")
        else:
            debug_print(f"\n   📤 FULL PAYLOAD:")
            debug_print(f"   {'='*70}")
            debug_print(f"   {payload_json}")
            debug_print(f"   {'='*70}")
        
        try:
            debug_print(f"\n   🚀 Đang gọi API create_stock_adjustment_raw...")
            response = self.core_repo.create_stock_adjustment_raw(stock_adjustment_data)
            
            debug_print(f"\n   ✓ API response received")
            debug_print(f"   → Response type: {type(response)}")
            debug_print(f"   → Response keys: {list(response.keys()) if isinstance(response, dict) else 'Not a dict'}")
            
            # In toàn bộ response để debug
            response_json = json.dumps(response, indent=2, ensure_ascii=False)
            debug_print(f"\n   📥 FULL API RESPONSE:")
            debug_print(f"   {'='*70}")
            if len(response_json) > 2000:
                debug_print(f"   {response_json[:2000]}...")
                debug_print(f"   ... (truncated, total length: {len(response_json)} chars)")
            else:
                debug_print(f"   {response_json}")
            debug_print(f"   {'='*70}")
            
            stock_adjustment = response.get("stock_adjustment", {})
            adjustment_id = stock_adjustment.get("id")
            
            if adjustment_id:
                debug_print(f"\n   ✅ Tạo phiếu kiểm thành công: ID {adjustment_id}")
                debug_print(f"   → Stock adjustment details:")
                debug_print(f"      - ID: {adjustment_id}")
                debug_print(f"      - Code: {stock_adjustment.get('code', 'N/A')}")
                debug_print(f"      - Location ID: {stock_adjustment.get('location_id', 'N/A')}")
                debug_print(f"      - Note: {stock_adjustment.get('note', 'N/A')}")
                debug_print(f"      - Line items count: {len(stock_adjustment.get('line_items', []))}")
            else:
                debug_print(f"\n   ⚠️  Response không có stock_adjustment.id")
                debug_print(f"   → Checking response structure...")
                if isinstance(response, dict):
                    if "stock_adjustment" not in response:
                        debug_print(f"   → Response không có key 'stock_adjustment'")
                    else:
                        debug_print(f"   → stock_adjustment type: {type(stock_adjustment)}")
                        debug_print(f"   → stock_adjustment keys: {list(stock_adjustment.keys()) if isinstance(stock_adjustment, dict) else 'Not a dict'}")
                debug_print(f"   → Full response (first 1000 chars): {response_json[:1000]}")
            
            logger.info(f"[NegativeStockBalance] Tạo phiếu kiểm thành công: ID {adjustment_id} cho {location_name}")
            return response
            
        except Exception as e:
            debug_print(f"\n   ❌ LỖI khi tạo phiếu kiểm:")
            debug_print(f"   → Exception type: {type(e).__name__}")
            debug_print(f"   → Exception message: {str(e)}")
            
            # Nếu có response object trong exception, in ra
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_text = e.response.text
                    debug_print(f"   → Status code: {e.response.status_code}")
                    debug_print(f"   → Error response (raw text, first 2000 chars):")
                    debug_print(f"   {'='*70}")
                    debug_print(f"   {error_text[:2000]}")
                    if len(error_text) > 2000:
                        debug_print(f"   ... (truncated, total length: {len(error_text)} chars)")
                    debug_print(f"   {'='*70}")
                    
                    # Thử parse JSON
                    try:
                        error_response = e.response.json()
                        debug_print(f"   → Error response (parsed JSON):")
                        debug_print(f"   {json.dumps(error_response, indent=2, ensure_ascii=False)}")
                    except:
                        debug_print(f"   → Cannot parse error response as JSON")
                except Exception as parse_error:
                    debug_print(f"   → Error parsing response: {parse_error}")
            
            import traceback
            debug_print(f"   → Traceback:\n{traceback.format_exc()}")
            logger.error(f"[NegativeStockBalance] Lỗi khi tạo phiếu kiểm cho {location_name}: {e}", exc_info=True)
            return None
    
    def balance_negative_stocks(self) -> Dict[str, Any]:
        """
        Workflow chính: Cân bằng tồn kho âm cho cả 2 kho.
        
        Returns:
            Dict kết quả:
            {
                "success": bool,
                "message": str,
                "gele": {
                    "items_count": int,
                    "adjustment_id": int or None,
                    "error": str or None
                },
                "toky": {
                    "items_count": int,
                    "adjustment_id": int or None,
                    "error": str or None
                },
                "total_gele_items": int,
                "total_toky_items": int
            }
        """
        debug_print("\n" + "="*80)
        debug_print("🎯 BẮT ĐẦU QUÁ TRÌNH CÂN BẰNG TỒN KHO ÂM")
        debug_print("="*80)
        logger.info("[NegativeStockBalance] Bắt đầu quá trình cân bằng tồn kho âm...")
        
        result = {
            "success": False,
            "message": "",
            "gele": {
                "items_count": 0,
                "adjustment_id": None,
                "error": None
            },
            "toky": {
                "items_count": 0,
                "adjustment_id": None,
                "error": None
            },
            "total_gele_items": 0,
            "total_toky_items": 0
        }
        
        try:
            # Bước 1: Lấy tất cả variants
            variants = self.get_all_variants_with_inventory()
            debug_print(f"\n✅ Bước 1 hoàn tất: {len(variants)} variants")
            
            # Bước 2: Tìm variants có tồn kho âm
            gele_items, toky_items = self.find_negative_stocks(variants)
            debug_print(f"\n✅ Bước 2 hoàn tất: Gele={len(gele_items)}, Tokyo={len(toky_items)}")
            
            result["total_gele_items"] = len(gele_items)
            result["total_toky_items"] = len(toky_items)
            
            # Bước 3: Tạo phiếu kiểm cho kho Gele
            debug_print(f"\n📍 Bước 3: Xử lý kho Gele...")
            if gele_items:
                result["gele"]["items_count"] = len(gele_items)
                debug_print(f"   → Có {len(gele_items)} items, đang tạo phiếu kiểm...")
                adjustment_response = self.create_stock_adjustment(
                    LOCATION_GELE,
                    gele_items,
                    note=f"Cân bằng tồn kho âm - Gele (Hà Nội) - {len(gele_items)} variants"
                )
                
                if adjustment_response:
                    adjustment = adjustment_response.get("stock_adjustment", {})
                    adjustment_id = adjustment.get("id")
                    result["gele"]["adjustment_id"] = adjustment_id
                    debug_print(f"   ✅ Kho Gele: Tạo phiếu kiểm thành công, ID = {adjustment_id}")
                else:
                    result["gele"]["error"] = "Không thể tạo phiếu kiểm"
                    debug_print(f"   ❌ Kho Gele: Không thể tạo phiếu kiểm (adjustment_response = None)")
            else:
                debug_print(f"   ⚠️  Kho Gele: Không có variants âm")
                logger.info("[NegativeStockBalance] Không có variants âm ở kho Gele")
            
            # Bước 4: Tạo phiếu kiểm cho kho Tokyo
            debug_print(f"\n📍 Bước 4: Xử lý kho Tokyo...")
            if toky_items:
                result["toky"]["items_count"] = len(toky_items)
                debug_print(f"   → Có {len(toky_items)} items, đang tạo phiếu kiểm...")
                adjustment_response = self.create_stock_adjustment(
                    LOCATION_TOKY,
                    toky_items,
                    note=f"Cân bằng tồn kho âm - Tokyo (Hồ Chí Minh) - {len(toky_items)} variants"
                )
                
                if adjustment_response:
                    adjustment = adjustment_response.get("stock_adjustment", {})
                    adjustment_id = adjustment.get("id")
                    result["toky"]["adjustment_id"] = adjustment_id
                    debug_print(f"   ✅ Kho Tokyo: Tạo phiếu kiểm thành công, ID = {adjustment_id}")
                else:
                    result["toky"]["error"] = "Không thể tạo phiếu kiểm"
                    debug_print(f"   ❌ Kho Tokyo: Không thể tạo phiếu kiểm (adjustment_response = None)")
            else:
                debug_print(f"   ⚠️  Kho Tokyo: Không có variants âm")
                logger.info("[NegativeStockBalance] Không có variants âm ở kho Tokyo")
            
            # Kiểm tra kết quả
            success_count = 0
            if result["gele"]["adjustment_id"]:
                success_count += 1
            if result["toky"]["adjustment_id"]:
                success_count += 1
            
            if (result["total_gele_items"] > 0 or result["total_toky_items"] > 0):
                if success_count > 0:
                    result["success"] = True
                    result["message"] = f"Đã tạo {success_count} phiếu kiểm hàng thành công"
                else:
                    result["message"] = "Có lỗi xảy ra khi tạo phiếu kiểm hàng"
            else:
                result["success"] = True
                result["message"] = "Không có variants nào có tồn kho âm"
            
            debug_print(f"\n" + "="*80)
            debug_print(f"🏁 KẾT QUẢ: {result['message']}")
            debug_print(f"   → Gele: {result['gele']['adjustment_id'] or 'Không tạo được'} ({result['gele']['items_count']} items)")
            debug_print(f"   → Tokyo: {result['toky']['adjustment_id'] or 'Không tạo được'} ({result['toky']['items_count']} items)")
            debug_print("="*80)
            logger.info(f"[NegativeStockBalance] Hoàn tất: {result['message']}")
            
        except Exception as e:
            debug_print(f"\n❌ LỖI NGHIÊM TRỌNG trong quá trình cân bằng:")
            debug_print(f"   → {type(e).__name__}: {str(e)}")
            import traceback
            debug_print(f"   → Traceback:\n{traceback.format_exc()}")
            logger.error(f"[NegativeStockBalance] Lỗi trong quá trình cân bằng: {e}", exc_info=True)
            result["message"] = f"Lỗi: {str(e)}"
        
        return result


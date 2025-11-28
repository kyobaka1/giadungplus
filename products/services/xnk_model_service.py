# products/services/xnk_model_service.py
"""
Service để quản lý Model Xuất Nhập Khẩu (XNK).
Model XNK được lưu trong Customer Notes trên Sapo với customer_id = 759930912.
"""

import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Customer ID để lưu Model XNK (đã chuyển sang customer mới)
XNK_CUSTOMER_ID = '851379103'
MAIN_URL = "https://sisapsan.mysapogo.com/admin"


class XNKModelService:
    """
    Service để quản lý Model XNK từ Sapo Customer Notes.
    """
    
    def __init__(self, sapo_session):
        """
        Initialize service với Sapo session.
        
        Args:
            sapo_session: requests.Session đã login vào Sapo (có thể là SapoClient.core_session hoặc loginss)
        """
        self.session = sapo_session
        self.customer_id = XNK_CUSTOMER_ID
    
    def get_all_models(self) -> List[Dict[str, Any]]:
        """
        Lấy tất cả model XNK từ customer notes.
        
        Returns:
            List[Dict]: Danh sách model XNK, mỗi item có thêm note_id và customer_id
        """
        try:
            url_notes = f"{MAIN_URL}/customers/{self.customer_id}.json"
            res = self.session.get(url_notes)
            
            if res.status_code != 200:
                logger.error(f"Failed to get customer notes: {res.status_code}")
                return []
            
            customer = res.json().get("customer", {})
            active_notes = [n for n in customer.get("notes", []) if n.get("status") == "active"]
            
            data_list = []
            for note in active_notes:
                try:
                    content = json.loads(note.get("content", "{}"))
                    # Thêm metadata
                    content['note_id'] = note.get('id')
                    content['customer_id'] = self.customer_id
                    data_list.append(content)
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"Failed to parse note {note.get('id')}: {e}")
                    continue
            
            return data_list
            
        except Exception as e:
            logger.error(f"Error in get_all_models: {e}", exc_info=True)
            return []
    
    def search_models(self, query: str) -> List[Dict[str, Any]]:
        """
        Tìm kiếm model XNK theo SKU, tên tiếng anh, hoặc tên tiếng việt.
        
        Args:
            query: Từ khóa tìm kiếm (SKU, tên tiếng anh, hoặc tên tiếng việt)
            
        Returns:
            List[Dict]: Danh sách model XNK khớp với query
        """
        all_models = self.get_all_models()
        
        if not query:
            return all_models
        
        query_lower = query.lower().strip()
        results = []
        seen_skus = set()  # Để tránh duplicate
        
        for model in all_models:
            sku = str(model.get("sku", "")).strip()
            if sku in seen_skus:
                continue
            
            # Tìm theo SKU
            if query_lower in sku.lower():
                results.append(model)
                seen_skus.add(sku)
                continue
            
            # Tìm theo tên tiếng anh (có thể là field "name_en", "name_english", "english_name", etc.)
            name_en = str(model.get("name_en", "") or 
                         model.get("name_english", "") or 
                         model.get("english_name", "") or 
                         model.get("en_name", "") or "").lower()
            if query_lower in name_en:
                results.append(model)
                seen_skus.add(sku)
                continue
            
            # Tìm theo tên tiếng việt
            name_vn = str(model.get("vn_name", "") or 
                         model.get("name_vn", "") or 
                         model.get("vietnam_name", "") or 
                         model.get("name_vietnam", "") or "").lower()
            if query_lower in name_vn:
                results.append(model)
                seen_skus.add(sku)
                continue
        
        return results
    
    def get_model_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Lấy model XNK theo SKU.
        
        Args:
            sku: SKU của model
            
        Returns:
            Dict hoặc None nếu không tìm thấy
        """
        all_models = self.get_all_models()
        sku_clean = str(sku).strip()
        
        for model in all_models:
            if str(model.get("sku", "")).strip() == sku_clean:
                return model
        
        return None
    
    def update_model(self, sku: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cập nhật model XNK.
        
        Args:
            sku: SKU của model cần cập nhật
            updates: Dict chứa các field cần cập nhật
            
        Returns:
            Dict với status và message
        """
        try:
            # Lấy model hiện tại
            model = self.get_model_by_sku(sku)
            if not model:
                return {"status": "error", "msg": "Không tìm thấy model với SKU này"}
            
            note_id = model.get("note_id")
            if not note_id:
                return {"status": "error", "msg": "Không tìm thấy note_id"}
            
            # Merge updates vào model hiện tại
            updated_model = {**model, **updates}
            # Loại bỏ metadata fields
            updated_model.pop('note_id', None)
            updated_model.pop('customer_id', None)
            
            # Lấy note hiện tại
            url_get = f"{MAIN_URL}/customers/{self.customer_id}/notes/{note_id}.json"
            res_get = self.session.get(url_get)
            
            if res_get.status_code != 200:
                return {"status": "error", "msg": f"Không tìm thấy note ID {note_id}"}
            
            note_obj = res_get.json().get("note", {})
            note_obj["content"] = json.dumps(updated_model, ensure_ascii=False)
            
            # Cập nhật note
            url_put = f"{MAIN_URL}/customers/{self.customer_id}/notes/{note_id}.json"
            res_put = self.session.put(url_put, json={"note": note_obj})
            
            if res_put.status_code == 200:
                return {"status": "success", "msg": "Cập nhật thành công", "note_id": note_id}
            else:
                return {"status": "error", "msg": f"Lỗi khi cập nhật: {res_put.text}"}
                
        except Exception as e:
            logger.error(f"Error in update_model: {e}", exc_info=True)
            return {"status": "error", "msg": str(e)}
    
    def create_model(self, model_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tạo model XNK mới.
        
        Args:
            model_data: Dict chứa thông tin model (phải có SKU)
            
        Returns:
            Dict với status và message
        """
        try:
            sku = str(model_data.get("sku", "")).strip()
            if not sku:
                return {"status": "error", "msg": "Thiếu SKU trong dữ liệu"}
            
            # Kiểm tra SKU đã tồn tại chưa
            existing = self.get_model_by_sku(sku)
            if existing:
                return {"status": "error", "msg": f"SKU {sku} đã tồn tại"}
            
            # Tạo note mới
            url_post = f"{MAIN_URL}/customers/{self.customer_id}/notes.json"
            payload = {
                "content": json.dumps(model_data, ensure_ascii=False)
            }
            res = self.session.post(url_post, json=payload)
            
            if res.status_code == 201:
                new_id = res.json().get("note", {}).get("id")
                return {"status": "success", "msg": "Tạo mới thành công", "note_id": new_id}
            else:
                return {"status": "error", "msg": f"Lỗi khi tạo note: {res.text}"}
                
        except Exception as e:
            logger.error(f"Error in create_model: {e}", exc_info=True)
            return {"status": "error", "msg": str(e)}
    
    def delete_model(self, sku: str) -> Dict[str, Any]:
        """
        Xóa model XNK (dùng DELETE method).
        
        Args:
            sku: SKU của model cần xóa
            
        Returns:
            Dict với status và message
        """
        try:
            # Lấy model hiện tại
            model = self.get_model_by_sku(sku)
            if not model:
                return {"status": "error", "msg": "Không tìm thấy model với SKU này"}
            
            note_id = model.get("note_id")
            if not note_id:
                return {"status": "error", "msg": "Không tìm thấy note_id"}
            
            # Xóa note bằng DELETE method
            url_delete = f"{MAIN_URL}/customers/{self.customer_id}/notes/{note_id}.json"
            res_delete = self.session.delete(url_delete)
            
            if res_delete.status_code == 200:
                return {"status": "success", "msg": "Xóa thành công", "note_id": note_id}
            else:
                return {"status": "error", "msg": f"Lỗi khi xóa: {res_delete.status_code} - {res_delete.text}"}
                
        except Exception as e:
            logger.error(f"Error in delete_model: {e}", exc_info=True)
            return {"status": "error", "msg": str(e)}


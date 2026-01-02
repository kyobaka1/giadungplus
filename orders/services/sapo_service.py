# orders/services/sapo_service.py
from typing import Dict, Any, List, Optional
import datetime
import json
import time
import requests

from core.sapo_client import get_sapo_client, BaseFilter
from orders.services.dto import OrderDTO, MarketplaceConfirmOrderDTO
from orders.services.order_builder import build_order_from_sapo

SAPO_ACCOUNT_ID = 319911
DEBUG_PRINT = True

def debug_print(*args, **kwargs):
    if DEBUG_PRINT:
        print("[DEBUG]", *args, **kwargs)

def gopnhan_gon(json_data: Dict[str, Any]) -> Dict[str, Any]:
    """Compress keys to save space (160 char limit)"""
    key_mapping = {
        "packing_status": "pks", "nguoi_goi": "human", "time_packing": "tgoi",
        "dvvc": "vc", "shopee_id": "spid", "time_print": "tin",
        "split": "sp", "time_chia": "tc", "shipdate": "sd", "nguoi_chia": "nc",
        "receive_cancel": "rc"
    }
    return {key_mapping.get(k, k): v for k, v in json_data.items()}

def mo_rong_gon(json_string: str) -> Dict[str, Any]:
    """Expand compressed keys"""
    try:
        data = json.loads(json_string)
    except:
        return {}
    reverse_mapping = {
        "pks": "packing_status", "human": "nguoi_goi", "tgoi": "time_packing",
        "vc": "dvvc", "spid": "shopee_id", "tin": "time_print",
        "sp": "split", "sd": "shipdate", "tc": "time_chia", "nc": "nguoi_chia",
        "rc": "receive_cancel"
    }
    return {reverse_mapping.get(k, k): v for k, v in data.items()}


class SapoCoreOrderService:
    def __init__(self):
        sapo = get_sapo_client()
        self._core_api = sapo.core
        self._sapo = sapo

    def _parse_sapo_time(self, s: str) -> datetime.datetime:
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)

    def get_order_dto(self, order_id: int) -> OrderDTO:
        import logging
        logger = logging.getLogger(__name__)
        import time
        
        api_start = time.time()
        logger.debug(f"[SapoCoreOrderService] Calling API: GET /orders/{order_id}.json")
        payload = self._core_api.get_order_raw(order_id)
        api_time = time.time() - api_start
        logger.info(f"[PERF] SapoCoreOrderService.get_order_dto({order_id}): API call took {api_time:.2f}s")
        
        build_start = time.time()
        result = build_order_from_sapo(payload)
        build_time = time.time() - build_start
        if build_time > 0.1:  # Log nếu build chậm hơn 0.1s
            logger.info(f"[PERF] SapoCoreOrderService.get_order_dto({order_id}): build_order_from_sapo took {build_time:.2f}s")
        
        return result

    def get_order_dto_from_shopee_sn(self, shopee_sn: str) -> Optional[OrderDTO]:
        payload = self._core_api.get_order_by_reference_number(shopee_sn)
        if not payload:
            return None
        return build_order_from_sapo(payload)

    def list_orders(self, flt: BaseFilter) -> Dict[str, Any]:
        return self._core_api.list_orders_raw(**flt.to_params())

    def update_fulfillment_packing_status(
        self, 
        order_id: int, 
        fulfillment_id: int, 
        packing_status: int,
        dvvc: Optional[str] = None,
        time_packing: Optional[str] = None,
        nguoi_goi: Optional[str] = None,
        max_retries: int = 3, 
        retry_delay: float = 2.0
    ) -> bool:
        """
        Update packing_status and other order info in fulfillment shipment note.
        
        Args:
            order_id: Sapo order ID
            fulfillment_id: Fulfillment ID
            packing_status: Packing status to update
            shopee_id: Optional Shopee order ID
            split: Optional number of packages (split count)
            dvvc: Optional shipping carrier name (only update if not already set)
            nguoi_goi: Optional packer username
            time_packing: Optional packing time (format: "HH:MM DD-MM-YYYY")
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries in seconds
            
        Returns:
            True if successful, False otherwise
        """
        for attempt in range(max_retries):
            try:
                # Get current fulfillment
                url_get = f"shipments/{fulfillment_id}.json"
                result = self._sapo.core.get(url_get)
                
                if not result or "fulfillment" not in result:
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    return False
                
                fulfillment = result["fulfillment"]
                shipment = fulfillment.get("shipment")
                
                if not shipment:
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    return False
                
                # Parse existing note
                note_data = {}
                if shipment.get("note") and "{" in shipment.get("note", ""):
                    note_data = mo_rong_gon(shipment["note"])
                
                # XÓA shopee_id (spid) khỏi note_data - không gửi trường này nữa
                if "shopee_id" in note_data:
                    del note_data["shopee_id"]
                
                # Update packing_status (always)
                note_data["packing_status"] = packing_status
                
                # Update dvvc: ưu tiên giá trị được truyền vào, nếu không có thì lấy từ shipment.service_name
                # Luôn đảm bảo có dvvc nếu có thể
                if dvvc and dvvc.strip():  # Nếu có giá trị và không rỗng
                    note_data["dvvc"] = dvvc.strip()
                elif shipment.get("service_name") and shipment.get("service_name").strip():
                    # Auto-fill from shipment nếu không có giá trị được truyền vào
                    note_data["dvvc"] = shipment.get("service_name").strip()
                elif note_data.get("dvvc") and note_data.get("dvvc").strip():
                    # Giữ nguyên dvvc từ note cũ nếu có
                    pass
                
                # Update time_packing
                if time_packing is not None:
                    note_data["time_packing"] = time_packing
                
                # Update nguoi_goi
                if nguoi_goi is not None and nguoi_goi.strip():
                    note_data["nguoi_goi"] = nguoi_goi.strip()
                
                # Compress and create JSON
                compressed = gopnhan_gon(note_data)
                new_note = json.dumps(compressed, ensure_ascii=False, separators=(',', ':'))
                
                # FULL PAYLOAD
                # Update note in the original fulfillment object
                fulfillment["shipment"]["note"] = new_note
                
                full_payload = {
                    "fulfillment": fulfillment
                }
                
                url_put = f"orders/{order_id}/fulfillments/{fulfillment_id}.json"
                # PUT update
                update_result = self._sapo.core.put(
                    url_put,
                    json=full_payload
                )
                
                if update_result:
                    return True
                else:
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                    return False
                    
            except requests.exceptions.HTTPError as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    return False
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    return False
        
        return False


class SapoMarketplaceService:
    def __init__(self):
        sapo = get_sapo_client()
        self._mp_api = sapo.marketplace

    def list_orders(self, flt: BaseFilter) -> Dict[str, Any]:
        p = flt.to_params().copy()
        connection_ids = p.pop("connectionIds", "")
        return self._mp_api.list_orders_raw(
            connection_ids=connection_ids,
            account_id=SAPO_ACCOUNT_ID,
            **p
        )

    def init_confirm(self, order_ids: List[int]) -> Dict[str, Any]:
        return self._mp_api.init_confirm_raw(order_ids, account_id=SAPO_ACCOUNT_ID)

    def confirm_orders(self, items: List[MarketplaceConfirmOrderDTO]) -> Dict[str, Any]:
        grouped: Dict[tuple, List[Dict[str, Any]]] = {}
        for dto in items:
            key = (dto.connection_id, dto.pick_up_type, dto.address_id)
            order_model: Dict[str, Any] = {"order_id": dto.order_id}
            if dto.pickup_time_id not in (None, "", 0, "0"):
                order_model["pickup_time_id"] = str(dto.pickup_time_id)
            grouped.setdefault(key, []).append(order_model)

        confirm_order_request_model: List[Dict[str, Any]] = []
        for (connection_id, pick_up_type, address_id), order_models in grouped.items():
            confirm_order_request_model.append({
                "connection_id": connection_id,
                "order_models": order_models,
                "shopee_logistic": {
                    "pick_up_type": pick_up_type,
                    "address_id": address_id,
                },
            })
        return self._mp_api.confirm_orders_raw(
            confirm_payload=confirm_order_request_model,
            account_id=SAPO_ACCOUNT_ID,
        )


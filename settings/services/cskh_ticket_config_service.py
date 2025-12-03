import json
from pathlib import Path
from typing import Dict, List, Any

from django.conf import settings

BASE_DIR = Path(settings.BASE_DIR)
SETTINGS_LOGS_DIR = BASE_DIR / "settings" / "logs"
CSKH_TICKET_CONFIG_FILE = SETTINGS_LOGS_DIR / "cskh_ticket_config.json"


DEFAULT_CONFIG: Dict[str, List[str]] = {
    "nguon_loi": [
        "Lỗi kho",
        "Lỗi sản phẩm",
        "Lỗi vận chuyển",
        "Lỗi CSKH",
        "Đánh giá xấu (1-3 sao)",
        "Khách yêu cầu",
    ],
    "loai_van_de": [
        "Đánh giá xấu",
        "Đổi trả",
        "Bảo hành",
        "Hỏng vỡ",
        "Khách yêu cầu",
        "Giao sai, thiếu",
        "Lên đơn sai",
    ],
    "loai_loi": [
        "Gói thiếu",
        "Gói sai",
        "Đóng gói kém",
        "Vỡ/nứt",
        "Thiếu chi tiết",
        "Lỗi QC",
        "Móp méo",
        "Thất lạc",
        "Hướng dẫn sai",
        "Thao tác sai",
        "Complain chất lượng",
        "Complain giao hàng",
        "Muốn đổi mẫu/màu"
    ],
    "trang_thai": [
        "Mới",
        "Đang xử lý",
        "Chờ khách",
        "Chờ kho",
        "Đã xử lý",
        "Đóng",
    ],
    "huong_xu_ly": [
        "Hoàn tiền 1 phần",
        "Hoàn tiền toàn phần",
        "Gửi bù hàng",
        "Đổi hàng",
        "Trả hàng hoàn tiền",
        "Khác",
    ],
    "loai_chi_phi": [
        "Hàng hỏng vỡ",
        "Chi phí gửi mới",
        "Chi phí đổi trả",
        "Chi phí hoàn tiền",
        "Voucher giảm giá",
        "Chi phí khác",
    ],
    # Cấu hình riêng cho ticket kho
    "nguon_loi_kho": [
        "Lỗi soạn hàng",
        "Lỗi đóng gói",
        "Lỗi kiểm hàng",
        "Lỗi nhập kho",
    ],
    "loai_loi_kho": [
        "Soạn thiếu",
        "Soạn nhầm mẫu/màu",
        "Đóng gói không kỹ",
        "Giao nhầm kho",
    ],
    "huong_xu_ly_kho": [
        "Kiểm kê lại tồn kho",
        "Soạn bù hàng",
        "Thu hồi hàng sai",
        "Báo CSKH xử lý với khách",
    ],
}


class CSKHTicketConfigService:
    @staticmethod
    def get_config() -> Dict[str, List[str]]:
        """
        Đọc cấu hình ticket CSKH từ file JSON.
        Nếu file chưa tồn tại, trả về DEFAULT_CONFIG.
        """
        if not CSKH_TICKET_CONFIG_FILE.exists():
            return DEFAULT_CONFIG.copy()

        try:
            with open(CSKH_TICKET_CONFIG_FILE, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)
        except (json.JSONDecodeError, OSError):
            return DEFAULT_CONFIG.copy()

        # Merge với default để đảm bảo đủ keys
        config: Dict[str, List[str]] = {}
        for key, default_list in DEFAULT_CONFIG.items():
            value = data.get(key) or []
            if not isinstance(value, list):
                value = []
            # Loại bỏ item rỗng & strip
            cleaned = []
            for item in value:
                if not isinstance(item, str):
                    continue
                item = item.strip()
                if item:
                    cleaned.append(item)
            config[key] = cleaned or default_list

        return config

    @staticmethod
    def save_config(data: Dict[str, List[str]]) -> None:
        """
        Ghi cấu hình ticket CSKH ra file JSON.
        """
        SETTINGS_LOGS_DIR.mkdir(parents=True, exist_ok=True)

        # Chỉ lưu các key hợp lệ, loại bỏ item rỗng & strip
        to_save: Dict[str, List[str]] = {}
        for key, default_list in DEFAULT_CONFIG.items():
            raw_list = data.get(key) or []
            cleaned: List[str] = []
            for item in raw_list:
                if not isinstance(item, str):
                    continue
                item = item.strip()
                if item:
                    cleaned.append(item)
            to_save[key] = cleaned or default_list

        with open(CSKH_TICKET_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2)



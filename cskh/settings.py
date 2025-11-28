"""
Settings cho Ticket system - Reason sources/types và Cost types
Có thể mở rộng sau này bằng cách thêm/xóa items trong list này
"""

# Reason Sources - Nguồn lỗi
REASON_SOURCES = [
    ('Lỗi kho', [
        'gói thiếu',
        'gói sai màu',
        'dán sai mã',
        'đóng gói kém',
    ]),
    ('Lỗi sản phẩm', [
        'vỡ',
        'nứt',
        'thiếu chi tiết',
        'lỗi QC',
    ]),
    ('Lỗi vận chuyển', [
        'móp méo',
        'thất lạc',
    ]),
    ('Lỗi CSKH', [
        'hướng dẫn sai',
        'thao tác sai',
    ]),
    ('Đánh giá xấu (1-3 sao)', [
        'complain chất lượng',
        'complain giao hàng',
    ]),
    ('Khách yêu cầu', [
        'muốn đổi mẫu',
        'muốn đổi màu',
    ]),
]

# Cost Types - Loại chi phí
COST_TYPES = [
    'Hàng hỏng vỡ',
    'Chi phí gửi mới',
    'Chi phí đổi trả',
    'Chi phí hoàn tiền',
    'Voucher giảm giá',
    'Chi phí khác',
]


def get_reason_sources():
    """Trả về danh sách reason sources"""
    return [source[0] for source in REASON_SOURCES]


def get_reason_types_by_source(source_reason: str):
    """Trả về danh sách reason types theo source"""
    for source, types in REASON_SOURCES:
        if source == source_reason:
            return types
    return []


def get_all_reason_types():
    """Trả về tất cả reason types"""
    all_types = []
    for source, types in REASON_SOURCES:
        all_types.extend(types)
    return list(set(all_types))  # Remove duplicates


def get_cost_types():
    """Trả về danh sách cost types"""
    return COST_TYPES


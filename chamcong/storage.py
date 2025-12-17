from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class ChamCongPhotoStorage(FileSystemStorage):
    """
    Lưu ảnh chấm công vào thư mục assets/nhanvien/chamcong
    và phục vụ qua URL /static/nhanvien/chamcong/...
    """

    def __init__(self, *args, **kwargs):
        base_dir = Path(settings.BASE_DIR)
        location = base_dir / "assets" / "nhanvien" / "chamcong"
        base_url = "/static/nhanvien/chamcong/"
        kwargs.setdefault("location", str(location))
        kwargs.setdefault("base_url", base_url)
        super().__init__(*args, **kwargs)


attendance_photo_storage = ChamCongPhotoStorage()



Vietnamese Customer Gender Classification System

*Role*: Senior Django Developer / Data Engineer.

*Objective*: Xây dựng một module APP để phân loại giới tính khách hàng (Nam/Nữ) từ đơn hàng dựa trên tên khách hàng, username và avatar URL.

##1. Stack & Libraries:
- Language: Python 3.10+, Django 4.2+.
- NLP: undersea (để tokenize tiếng Việt), re (Regex).
- Image & AI: google-generativeai (Gemini 1.5 Flash - Multimodal).
- Task Queue: Celery (để chạy sync ngầm không treo server).
- Fuzzy Matching: thefuzz (xử lý sai chính tả).

##2. Data Model (Input/Output):

- Input: raw_name (string), username (string), avatar_url (url).
- Output trong DB:
    gender: Choices (Nam, Nữ, Unknown).
    source: Choices (Rule, AI, Human).
    confidence: Integer (0-100).
    status: Choices (Pending, Processing, Completed, Need_Review).

##3. Logic Flow (4 Tầng):

*Tầng 1 - Preprocessing & Hard Rules (0đ)*

Clean name: Xóa số điện thoại, icon, chuyển về lowercase.

Prefix Check: Nếu có "Chị, Cô, Bà, Ms" -> Nữ; "Anh, Chú, Ông, Mr" -> Nam.

Tokenize: Dùng undersea lấy tên đệm và tên chính. So khớp với Dictionary (Cần Claude tự tạo bộ Dict ~200 từ phổ biến nhất).

*Tầng 2 - Username Heuristics (0đ)*

Dùng Regex tìm keywords trong username (ví dụ: _9x, _boy, _girl, _mẹ_bé).

*Tầng 3 - Gemini Multimodal API (Phí thấp)*

Chỉ gọi API khi Tầng 1 & 2 trả về Unknown hoặc Confidence < 80.

Gửi đồng thời name, username và avatar_url cho Gemini 1.5 Flash.

Prompt cho AI yêu cầu trả về JSON chuẩn: {"gender": "...", "confidence": ..., "reason": "..."}.

*Tầng 4 - Human-in-the-loop (Control)*

Xây dựng một Custom Django Admin Action hoặc một Vue/React Dashboard đơn giản.

Hiển thị ảnh đại diện và thông tin khách hàng cạnh nhau.

Hỗ trợ Hotkeys: Nhấn 1 là Nam, 2 là Nữ, Space để bỏ qua. Cập nhật status = 'Completed' và source = 'Human'.

##4. Yêu cầu Code:

Viết theo cấu trúc Service Pattern (services/gender_service.py).

Sử dụng Batch Processing để gửi tối đa 30 records mỗi lần gọi API Gemini nhằm tiết kiệm token và thời gian.

Log lỗi chi tiết vào một file gender_debug.log (bao gồm PID để truy vết khi chạy ngầm).

##5. Khả năng chịu tải:

Phải xử lý được trường hợp tắt SSH khi đang chạy sync (Hướng dẫn cách dùng management commands kết hợp nohup hoặc screen).
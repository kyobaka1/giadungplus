"""
Tạo file order_express.html hoàn chỉnh với fix cho vấn đề reload trang
"""

# Đọc file gốc
with open(r'd:\giadungplus\giadungplus-1\kho\templates\kho\orders\order_express_backup.html', 'r', encoding='utf-8') as f:
    content = f.read()

# JavaScript mới để thay thế
new_indon_function = '''<script>
    function inDon(mp_order_id, event) {
        // Ng chặn hành vi mặc định
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        
        if (!mp_order_id) return;
        
        const url = `/kho/orders/print_now/?ids=${mp_order_id}&print=yes`;
        const btn = event ? event.target : null;
        
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Đang in...';
        }
        
        // Fetch PDF và mở trong tab mới
        fetch(url, { method: "GET" })
            .then(response => {
                if (!response.ok) throw new Error('Network error');
                return response.blob();
            })
            .then(blob => {
                // Tạo URL từ blob
                const pdfUrl = URL.createObjectURL(blob);
                
                // Mở PDF trong tab mới
                const newWindow = window.open(pdfUrl, '_blank');
                
                if (newWindow) {
                    // Sau khi mở, revoke URL để giải phóng memory
                    setTimeout(() => URL.revokeObjectURL(pdfUrl), 1000);
                    
                    showToast('✅ Đã gửi yêu cầu in đơn!', 'success');
                    
                    // Xóa row ngay lập tức
                    removeOrderRow(mp_order_id);
                } else {
                    showToast('❌ Vui lòng cho phép popup để in đơn', 'error');
                    if (btn) {
                        btn.disabled = false;
                        btn.textContent = 'In Đơn';
                    }
                }
            })
            .catch(err => {
                console.error('Print error:', err);
                showToast('❌ Lỗi khi in đơn', 'error');
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = 'In Đơn';
                }
            });
        
        // Return false để ngăn reload
        return false;
    }
</script>'''

# Tìm và thay thế hàm inDon cũ
import re

# Pattern để tìm hàm inDon cũ
old_pattern = r'<script>\s*function inDon\(mp_order_id\)[\s\S]*?</script>'

# Thay thế
content = re.sub(old_pattern, new_indon_function, content)

# Lưu file mới
with open(r'd:\giadungplus\giadungplus-1\kho\templates\kho\orders\order_express.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("File da duoc cap nhat thanh cong!")
print("Da thay the ham inDon() de su dung fetch + blob thay vi window.open()")

https://127.0.0.1:8000/cskh/value-center/customers/l1/?district=Qu%E1%BA%ADn+1 

Cải tiến tính năng với những yêu cầu sau:

- Khi lọc bằng district thì phải thêm district.in vào URL request tới Sapo API.
- Cập nhật link mới khi request khách hàng với những yêu cầu cũ.
    Link example: https://sisapsan.mysapogo.com/admin/customers/doSearch.json?district.in=Th%E1%BB%8B%20x%C3%A3%20S%C6%A1n%20T%C3%A2y&city.in=H%C3%A0%20N%E1%BB%99i&filterType=advanced&page=1&limit=250&condition_type=must

* File log:
    - Lưu vào 1 file log duy nhất tất cả customer đã request phù hợp với yêu cầu. Trừ yêu cầu Quận. Với bộ lọc quận thì sẽ lọc khi lấy từ cache file ra và lọc xem có đúng Quận đang request lên hay không.
    - {"metadata":{"total":40,"page":1,"limit":100},"customers":[{"id":820414777,"tenant_id":236571,"default_location_id":null,"created_on":"2025-10-19T15:10:05Z","modified_on":"2025-10-19T15:10:05Z","code":"CUZN434944","name":"Nguyễn Phương","dob":null,"sex":"other","description":null,"email":"","fax":null,"phone_number":"0914870691","tax_number":"","website":"","customer_group_id":963454,"group_id":963454,"group_ids":[963454],"group_name":"Bán lẻ","assignee_id":1210144,"default_payment_term_id":null,"default_payment_

     => Dựa vào total của mỗi quận để lưu request tới số page phù hợp, limit=250, ví dụ total=2500 -> chia 250 -> bằng 10.


     - Khi lọc quận nào thì chạy full toàn bộ thông tin khách hàng của quận đó (ko lưu page_now nữa.)
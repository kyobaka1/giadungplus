Xây dựng lại /orders ở các hàm DTO, services... với yêu cầu như sau, kết hợp với /products DTO.

***MÔ TẢ YÊU CẦU***

- Xây dựng lại đơn hàng với products/variants DTO trong /products
- Xây dựng lại danh sách sản phẩm của đơn hàng thành các phân loại đơn lẻ (tách từ combo, packed ra).

***LOGIC VÀ XỬ LÝ***

1. Danh sách sản phẩm
    ** Các bước xử lý

    - Từ json đơn hàng, ta dò lại các order_line_items.
    - Xem thử product_type (normal/combo) và is_packsize (true/false) để xử lý tiếp.
    - Nếu là sản phẩm thường -> không cần xử lý.
    - Nếu là sản phẩm packsize (combo 2 cái trở lên) -> qui đổi thành sản phẩm đơn dựa vào pack_size_quantity. Nếu trong đơn hàng có tồn tại sản phẩm qui đổi thì cộng lên, còn nếu ko thì thêm sản phẩm qui đổi đơn với số lượng tương ứng -> xoá packsize ra khỏi danh sách sản phẩm.
    - Nếu sản phẩm là composite -> là tổ hợp của nhiều sản phẩm đơn khác mã hoặc combo cùng mã -> thì ta sẽ vào composite_item_domains để lấy thông tin các phân loại có trong đó + số lượng, id  -> dựa vào id lấy thông tin sản phẩm rồi add ngược lại vào danh sách sản phẩm trong đơn với số lượng tương ứng.

    ** Yêu cầu:
    - Xử lý ở cấp độ dto lúc init -> để có thể lấy ra sản phẩm để dùng khi cần, chứ ko xây dựng hàm đơn lẻ -> phải có tính kế thừa và phát triển sau này.

    ** Chú ý:
    - Có thể cần lưu lại old_id -> tức là variant_id của combo hoặc packsize -> Mục đích là để khi sang Sapo MP hoặc Shopee KNB, dù đã qui đổi nhưng kiện hàng nào chứa sản phẩm nào -> vẫn có thể biết được để in ra trong kiện hàng đó.


***ĐOẠN CODE THAM KHẢO - CHỈ THAM KHẢO TƯ DUY***
for order_id in order_ids:
        order = js_get_url(f"{MAIN_URL}/orders/{order_id}.json")['order']
        order['real_items'] = []
        for item in order['order_line_items']:
            item['pr_name'] = ''
            
            # Sản phẩm thường
            if item['product_name'] != None:
                if '/' in item['product_name']:
                    item['pr_name'] = item['product_name'].split('/')[0]

            if item['unit'] == None:
                item['unit'] = "cái"
            if item['product_type'] == "normal" and item['is_packsize'] == False:
                flag = 0
                for line in order['real_items']:
                    if line['id'] == item['variant_id']:
                        line['quantity'] += int(item['quantity'])
                        flag = 1
                        break
                if flag == 0:
                    order['real_items'].append({
                        'old_id': 0,
                        'id': item['variant_id'],
                        'sku': item['sku'][3:],
                        'variant_options': item['variant_options'],  
                        'quantity': int(item['quantity']),
                        'unit': item['unit'],
                        'pr_name':item['pr_name'],
                        'print':0
                    })

            # Sản phẩm thường & packed nhiều.
            elif item['product_type'] == "normal" and item['is_packsize'] == True:
                flag = 0
                for line in order['real_items']:
                    if line['id'] == item['pack_size_root_id']:
                        line['quantity'] += int(item['quantity']*item['pack_size_quantity'])
                        flag = 1
                        break
                if flag == 0:
                    vari = js_get_url(f"{MAIN_URL}/variants/{item['pack_size_root_id']}.json")['variant']
                    order['real_items'].append({
                        'old_id': item['variant_id'],
                        'id': vari['id'],
                        'sku': vari['sku'][3:],
                        'variant_options': vari['opt1'],
                        'old_id': item['variant_id'],
                        'unit': "cái",
                        'pr_name':item['pr_name'],
                        'quantity': int(item['quantity']*item['pack_size_quantity']),
                        'print':0
                    })
                    
            if item['product_type'] == "composite":
                for xitem in item['composite_item_domains']:
                    flag = 0
                    for line in order['real_items']:
                        if line['id'] == xitem['variant_id']:
                            line['quantity'] += int(xitem['quantity'])
                            flag = 1
                            break
                    if flag == 0:
                        vari = js_get_url(f"{MAIN_URL}/variants/{xitem['variant_id']}.json")['variant']
                        order['real_items'].append({
                            'id': xitem['variant_id'],
                            'sku': vari['sku'][3:],
                            'barcode': vari['barcode'],
                            'old_id': item['variant_id'],
                            'unit': "cái",
                            'pr_name':item['pr_name'],
                            'variant_options': vari['opt1'],  
                            'quantity': int(xitem['quantity']),
                            'print':0
                        })

        order['total_quantity'] = 0
        for line in order['real_items']:
            if line['sku'] != 'KEO':
                order['total_quantity'] += line['quantity']

        order['real_items'] = sorted(
            order['real_items'],
            key=lambda item: item['sku'].split('-')[0]
        )

        # Hàm lấy phần số từ SKU trước dấu '-'
        def get_sku_number(sku):
            try:
                # Tách phần trước dấu '-' và chuyển thành số (nếu có thể)
                sku_number = sku.split('-')[0]
                # Kiểm tra xem phần số có phải là số hay không
                if sku_number.isdigit():
                    return int(sku_number)
                else:
                    # Nếu không phải số, trả về một giá trị mặc định cho các SKU không phải số
                    return float('inf')  # Đặt các SKU không phải số ở cuối
            except Exception as e:
                # Nếu có lỗi trong quá trình tách hoặc chuyển đổi, trả về giá trị mặc định
                return float('inf')

        # Sắp xếp order['real_items'] theo SKU (sắp xếp theo phần số trong SKU trước dấu '-')
        order['real_items'] = sorted(order['real_items'], key=lambda item: get_sku_number(item['sku']))

*** KẾT QUẢ MONG MUỐN ***

- Ví dụ đơn hàng SON02345 - Có 1 order_lines là: SQ-0101-CB2 (SKU) SL: 2 -> Sau khi init đơn hàng dto -> SQ-0101-BS 4 chiếc. Với SQ-0101-CB2 là loại packed có orgin là 2 chiếc SQ-0101-BS.

- Ví dụ đơn hàng SON97432 - Có 1 order_lines là: CB-0306 SL : 1 -> Sau khi init đơn hàng -> Sẽ có:
    + SL:1 JX-0306-S3
    + SL:1 JX-0306-S4
    + SL:2 JX-0306-S5
(với combo CB-0306 là 1 jx-0306-s3 + 1 jx-0306-s4 + 2 jx-0306-s5)

- Ví dụ đơn hàng SON02366 - Có 1 order_lines là: SQ-0101-CB2 (SKU) SL: 2, SQ-0101-BS SL: 2 -> Sau khi init đơn hàng dto:
    SL: SQ-0101-BS SL: 6 chiếc.


*** MÔ TẢ app customers ***
/customers sẽ làm việc với Sapo, Sapo MP, Shopee KNB về các thông tin của khách hàng như tên người dùng, số điện thoại, email, giới tính, địa chỉ... và các thông tin khác liên quan đến khách hàng.

Thông tin khách hàng vẫn sẽ được lưu trên Sapo. Còn app chỉ bổ trợ việc giao tiếp với Sapo để bổ sung thông tin, hoặc cung cấp các ứng dụng tools hỗ trợ cần thiết.

*** Sapo customers ***
- Các API của Sapo customers:
    - List customers - GET -/admin/customers.json?page=1&litmit=(max 250)
    - Get customer by id - GET - /admin/customers/{id}.json
    - Update customer - PUT - /admin/customers/{id}.json
        +Payload example change email: {"customer":{"id":846791668,"name":"T******n","code":"CUZN454327","customer_group_id":963454,"email":"xxx@gmail.com","sex":"other","status":"active","assignee_id":319911,"tags":["Shopee","Gia Dụng Plus +"],"apply_incentives":"group"}}

    - Delete customer - DELETE - /admin/customers/{id}.json
    - Thêm ghi chú cho khách hàng -> nơi để tôi custom coi như là nơi lữu các dữ liệu database của khách hàng đó -> ví dụ như đánh giá, ghi chú về CSKH, các action marketing đã triển khai...
        POST / /admin/customers/846791668/notes.json
        Payload example: {content: "Ghi chú được ghi tại đây."}
        - GET thông tin: 
        GET/admin/customers/846791668/notes.json?page=1&limit=250
        Reponse trả về:
        {
    "metadata": {
        "total": 1,
        "page": 1,
        "limit": 20
    },
    "notes": [
        {
            "id": 2368356,
            "tenant_id": 236571,
            "created_on": "2025-11-21T16:46:32Z",
            "modified_on": "2025-11-21T16:46:32Z",
            "account_id": 319911,
            "content": "Ghi chú được ghi tại đây.",
            "status": "active"
        }
    ]
}


- Cấu trúc JSON của customer được lưu trên Sapo:
    {
    "customer": {
        "id": 846791668,
        "tenant_id": 236571,
        "default_location_id": null,
        "created_on": "2025-11-21T16:38:56Z",
        "modified_on": "2025-11-21T16:44:33Z",
        "code": "CUZN454327",
        "name": "T******n",
        "dob": null,
        "sex": "other",
        "description": null,
        "email": "xxx@gmail.com",
        "fax": null,
        "phone_number": null,
        "tax_number": null,
        "website": null,
        "customer_group_id": 963454,
        "group_id": 963454,
        "group_ids": [
            963454
        ],
        "group_name": "Bán lẻ",
        "assignee_id": 319911,
        "default_payment_term_id": null,
        "default_payment_method_id": null,
        "default_tax_type_id": null,
        "default_discount_rate": null,
        "default_price_list_id": null,
        "tags": [
            "Shopee",
            "Gia Dụng Plus +"
        ],
        "addresses": [
            {
                "id": 793609964,
                "created_on": "2025-11-21T16:38:56Z",
                "modified_on": "2025-11-21T16:38:56Z",
                "country": "Việt Nam",
                "city": "Hà Nội",
                "district": "Quận Đống Đa",
                "ward": "Phường Láng Hạ",
                "address1": "******rung, Phường Láng Hạ, Quận Đống Đa, Hà Nội",
                "address2": null,
                "zip_code": null,
                "email": null,
                "first_name": null,
                "last_name": null,
                "full_name": "T******n",
                "label": null,
                "phone_number": null,
                "status": "active"
            }
        ],
        "contacts": [],
        "notes": [],
        "customer_group": {
            "id": 963454,
            "tenant_id": 236571,
            "created_on": "2020-03-03T02:35:42Z",
            "modified_on": "2020-03-03T02:35:42Z",
            "name": "RETAIL",
            "name_translate": "Bán lẻ",
            "status": "active",
            "is_default": true,
            "default_payment_term_id": null,
            "default_payment_method_id": null,
            "default_tax_type_id": null,
            "default_discount_rate": null,
            "default_price_list_id": null,
            "note": null,
            "code": "BANLE",
            "count_customer": null,
            "type": "customer",
            "group_type": null,
            "condition_type": null,
            "conditions": null
        },
        "status": "active",
        "is_default": false,
        "debt": 0,
        "apply_incentives": "group",
        "total_expense": null,
        "loyalty_customer": null,
        "sale_order": null,
        "social_customers": []
    }
}


- Một số thông tin khách của khách hàng cần quan tâm:
    + username:
        - Có thể lấy thông qua 2 phương thức:
        + Dùng API Shopee KNB: https://banhang.shopee.vn/api/v3/order/get_order_list_search_bar_hint -> {
    "code": 0,
    "data": {
        "product_name_result": null,
        "item_sku_result": null,
        "model_sku_result": null,
        "order_sn_result": {
            "total": 1,
            "list": [
                {
                    "order_id": 217442165277926,
                    "order_sn": "251122CUSHND76",
                    "buyer_image": "",
                    "buyer_name": "tmanhhong370",
                    "model_image": "vn-11134207-7r98o-lu0vqc9ufmdtf9"
                }
            ]
        } -> Res trả về có buyer_name = username
        
        + Dùng Sapo MP API - /v2/orders -> Khi trả về có orders->customer: 
        "customer": {
                "id": 676847606,
                "tenant_id": 1262,
                "sapo_customer_id": 846795991,
                "first_name": null,
                "last_name": null,
                "full_name": "đ******i",
                "address": "******ải, Phường Hải Sơn, Quận Đồ Sơn, Hải Phòng",
                "phone": "******83",
                "email": null,
                "ward": "Phường Hải Sơn",
                "district": "Quận Đồ Sơn",
                "city": "Hải Phòng",
                "country": "Việt Nam",
                "zip_code": "",
                "created_at": 1763743878,
                "user_id": 1037109217,
                "user_name": "dinhducloi1983"
            },
    
    + Email của khách hàng trên Shopee KNB:
        - POST https://banhang.shopee.vn/api/v4/invoice/seller/get_order_receipt_settings_batch?SPC_CDS=a4ef0c3a-4b1a-4920-a8bf-4fccf56c8808&SPC_CDS_VER=2
        - Payload: {"queries":[{"order_id":217342375296630}]}
        - Res trả về: {
    "data": {
        "order_receipt_settings": [
            {
                "order_id": 217342375296630,
                "receipt_type": 1,
                "receipt_settings": {
                    "personal": {
                        "email": "dadieu007@gmail.com",
                        "address": {
                            "address": "******"
                        },
                        "name": "******"
                    }
                },
                "is_requested": false,
                "tooltip": {
                    "content": "Thông tin này chỉ được hiển thị khi Người mua yêu cầu xuất hóa đơn. \u003ca href=\"https://banhang.shopee.vn/edu/article/18524\" target=\"_blank\"\u003eXem thêm\u003c/a\u003e"
                }
            }
        ]
    },
    "code": 0
}

    
     
***** QUI ĐỊNH LƯU DỮ LIỆU KHÁCH HÀNG TRÊN SAPO customer. 
Do một số cấu hình, dữ liệu trên Sapo không có lưu trữ mà tôi muốn lưu trữ -> nên tôi sẽ dùng các key khác để lưu thông tin khác so với tên thật của key đó, với qui ước như sau:

- name -> Full name của khách hàng
- website -> Tên rút gọn của khách hàng -> short_name
- sex -> Giới tính, có female, male, other
- email -> lưu email -> có định dạng @
- tax_number (0 hoặc 1 hoặc null) -> nếu tax_number = 1, chứng tỏ tôi đã từng duyệt qua việc lấy sex và short_name của khách hàng rồi. Còn nếu tax_number = null hoặc 0, chứng tỏ tôi chưa từng xử lý bằng tools với khách hàng đó.

*** YÊU CẦU XÂY DỰNG CÔNG CỤ /customer ***

Xây cấu trúc giao tiếp với các API để có thể can thiệp tự động bằng công cụ với 1 số chức năng chính sau:

- Xây dựng giống /orders -> có DTO, các services để giao tiếp để lấy, init thông tin khách hàng. Covert theo qui ước để lấy về đúng thông tin khách hàng.
- Xây dựng help -> change info cho customer -> gửi lên sapo để đổi thông tin khách hàng -> ví dụ như sex, địa chỉ, name, email, tax_number (status processing).
- Xây dựng help -> thêm note cho customer -> gửi lên sapo để thêm note cho khách hàng để ứng dụng phát triển sau này -> tôi dùng note để lưu trữ các dạng thông tin DTO khác như (chăm sóc khách hàng, review của khách...)

*** QUI ĐỊNH ***
- Sử dụng /core và tham khảo /orders để xây dựng các chức năng.
- Nếu muốn lấy thêm thông tin gì URL API hoặc method, hãy hỏi tôi thay vì tự suy diễn ra API.

Xây dựng thêm tính năng cho apps /products/

-> NHẬP HÀNG
- Overview
- Nhà cung cấp 
- Đơn đặt hàng
- Container
- Tài chính

** Giờ bắt tay vào xây dựng: Nhà cung cấp
- Hiển thị danh sách nhà cung cấp và quản lý các nhà cung cấp.
    1. Lấy danh sách: GET https://sisapsan.mysapogo.com/admin/suppliers.json?page=1&limit=250
    2. JSON mẫu của danh sách:
        {"metadata":{"total":40,"page":1,"limit":250},"suppliers":[{"id":857154285,"tenant_id":236571,"default_location_id":null,"created_on":"2025-12-05T03:23:14Z","modified_on":"2025-12-06T02:28:18Z","code":"NAIBEN","name":"NAIBEN","description":null,"email":null,"fax":null,"phone_number":null,"tax_number":null,"website":null,"supplier_group_id":3147762,"debt":0,"group_name":"PHÂN PHỐI","assignee_id":null,"default_payment_term_id":null,"default_payment_method_id":null,"default_tax_type_id":null,"default_discount_rate":null,"default_price_list_id":null,"tags":[],"addresses":[{"id":804131455,"created_on":"2025-12-05T03:23:14Z","modified_on":"2025-12-05T03:23:14Z","country":"Việt Nam","city":null,"district":null,"ward":null,"address1":"HÀ BẮC","address2":null,"zip_code":null,"email":null,"first_name":null,"last_name":null,"full_name":null,"label":null,"phone_number":null,"status":"active"}],"contacts":[],"notes":[],"status":"active","is_default":false},{"id":528178852,"tenant_id":236571,"default_location_id":null,"created_on":"2024-09-05T07:27:34Z","modified_on":"2025-12-06T05:28:01Z","code":"LTENG","name":"LTENG","description":null,"email":null,"fax":null,"phone_number":null,"tax_number":null,"website":"lteng.jpg","supplier_group_id":3147763,"debt":-502157520.0000,"group_name":"ĐỘC QUYỀN","assignee_id":null,"default_payment_term_id":null,"default_payment_method_id":null,"default_tax_type_id":null,"default_discount_rate":null,"default_price_list_id":null,"tags":[],"addresses":[{"id":487129826,"created_on":"2024-09-05T07:27:34Z","modified_on":"2025-08-18T08:44:46Z","country":"Việt Nam","city":"Phú Yên","district":"Thành phố Tuy Hòa","ward":"Phường 1","address1":"Wenzhou City, Zhejiang Province, China","address2":null,"zip_code":null,"email":null,"first_name":null,"last_name":null,"full_name":"Wenzhou Latan Sanitary Ware Co., Ltd.","label":"ÔN CHÂU","phone_number":null,"status":"active"}],"contacts":[],"notes":[{"id":2373917,"tenant_id":0,"created_on":"2025-12-06T05:16:00Z","modified_on":"2025-12-06T05:16:00Z","account_id":319911,"content":"Ghi chú cho nhà cung cấp.Ghi chú cho nhà cung cấp.Ghi chú cho nhà cung cấp.Ghi chú cho nhà cung cấp.Ghi chú cho nhà cung cấp.","status":"deleted"}],"status":"active","is_default":false},{"id":465869681,"tenant_id":236571,"default_location_id":null,"created_on":"2024-05-20T05:07:36Z","modified_on":"2024-12-20T07:06:10Z","code":"DANLE","name":"DANLE","description":null,"email":null,"fax":null,"phone_number":null,"tax_number":null,"website":"ÔN CHÂU","supplier_group_id":2743130,"debt":0.0000,"group_name":"CONTAINER 60","assignee_id":null,"default_payment_term_id":null,"default_payment_method_id":null,"default_tax_type_id":null,"default_discount_rate":null,"default_price_list_id":null,"tags":[],"addresses":[{"id":427408839,"created_on":"2024-05-20T05:07:36Z","modified_on":"2024-05-20T05:07:36Z","country":"Việt Nam","city":null,"district":null,"ward":null,"address1":"x","address2":null,"zip_code":null,"email":null,"first_name":null,"last_name":null,"full_name":null,"label":null,"phone_number":null,"status":"active"}],"contacts":[],"notes":[],"status":"disable","is_default":false},{"id":283221466,"tenant_id":236571,"default_location_id":null,"created_on":"2023-07-26T04:25:10Z","modified_on":"2024-10-28T04:19:31Z","code":"HEISMAN","name":"HEISMAN","description":null,"email":null,"fax":null,"phone_number":null,"tax_number":null,"website":"SƠN TÂY","supplier_group_id":2743130,"debt":0,"group_name":"CONTAINER 60","assignee_id":null,"default_payment_term_id":null,"default_payment_method_id":null,"default_tax_type_id":null,"default_discount_rate":null,"default_price_list_id":null,"tags":[],"addresses":[{"id":252086038,"created_on":"2023-07-26T04:25:10Z","modified_on":"2023-07-26T04:25:10Z","country":"Việt Nam","city":null,"district":null,"ward":null,"address1":"z","address2":null,"zip_code":null,"email":null,"first_name":null,"last_name":null,"full_name":null,"label":null,"phone_number":null,"status":"active"}],"contacts":[],"notes":[],"status":"disable","is_default":false},{"id":283142623,"tenant_id":236571,"default_location_id":null,"created_on":"2023-07-26T01:26:21Z","modified_on":"2025-12-06T02:27:55Z","code":"HUANGYAN","name":"HUANGYAN","description":null,"email":null,"fax":null,"phone_number":null,"tax_number":null,"website":"THÁI CHÂU","supplier_group_id":2743130,"debt":0.0000,"group_name":"CONTAINER 60","assignee_id":null,"default_payment_term_id":null,"default_payment_method_id":null,"default_tax_type_id":null,"default_discount_rate":null,"default_price_list_id":null,"tags":[],"addresses":[{"id":252010551,"created_on":"2023-07-26T01:26:21Z","modified_on":"2024-03-13T07:58:27Z","country":"Việt Nam","city":"Quảng Bình","district":"Thành Phố Đồng Hới","ward":null,"address1":"Huangyan, Taizhou, Zhejiang","address2":null,"zip_code":null,"email":null,"first_name":null,"last_name":null,"full_name":"Taizhou Huangyan Shuangqing Plastic Mould Factory","label":null,"phone_number":null,"status":"active"}],"contacts":[],"notes":[],"status":"disable","is_default":false},{"id":277034007,"tenant_id":236571,"default_location_id":null,"created_on":"2023-07-13T14:14:06Z","modified_on":"2025-12-06T02:27:38Z","code":"GAOMI","name":"GAOMI","description":null,"email":null,"fax":null,"phone_number":null,"tax_number":null,"website":"SƠN ĐÔNG","supplier_group_id":2743130,"debt":-73674000.0000,"group_name":"CONTAINER 60","assignee_id":null,"default_payment_term_id":null,"default_payment_method_id":null,"default_tax_type_id":null,"default_discount_rate":null,"default_price_list_id":null,"tags":["GỬI ĐƠN SỚM"],"addresses":[{"id":246107904,"created_on":"2023-07-13T14:14:06Z","modified_on":"2024-03-13T08:00:19Z","country":"Việt Nam","city":"Quảng Bình","district":"Thành Phố Đồng Hới","ward":null,"address1":"zZhoucun, Zibo, Shandong","address2":null,"zip_code":null,"email":null,"first_name":null,"last_name":null,"full_name":"Zibo Dacheng Trading Co., Ltd","label":null,"phone_number":null,"status":"active"}],"contacts":[],"notes":[],"status":"disable","is_default":false},{"id":276852134,"tenant_id":236571,"default_location_id":null,"created_on":"2023-07-13T06:56:25Z","modified_on":"2025-12-06T02:27:25Z","code":"HEJIAN","name":"HEJIAN","description":null,"email":null,"fax":null,"phone_number":null,"tax_number":null,"website":"HÀ BẮC","supplier_group_id":3147762,"debt":-328824000.0000,"group_name":"PHÂN PHỐI","assignee_id":null,"default_payment_term_id":null,"default_payment_method_id":null,"default_tax_type_id":null,"default_discount_rate":null,"default_price_list_id":null,"tags":["GỬI ĐƠN SỚM"],"addresses":[{"id":245941393,"created_on":"2023-07-13T06:56:25Z","modified_on":"2024-03-13T08:00:09Z","country":"Việt Nam","city":"Quảng Bình","district":"Huyện Bố Trạch","ward":null,"address1":"Zhoucun, Zibo, Shandong","address2":null,"zip_code":null,"email":null,"first_name":null,"last_name":null,"full_name":"Zibo Dacheng Trading Co., Ltd","label":null,"phone_number":null,"status":"active"}],"contacts":[],"notes":[],"status":"active","is_default":false},{"id":275892642,"tenant_id":236571,"default_location_id":null,"created_on":"2023-07-11T08:08:47Z","modified_on":"2025-12-06T02:27:13Z","code":"LISSA","name":"LISSA","description":null,"email":null,"fax":null,"phone_number":null,"tax_number":null,"website":"THƯỢNG HẢI","supplier_group_id":3147762,"debt":0.0000,"group_name":"PHÂN PHỐI","assignee_id":null,"default_payment_term_id":null,"default_payment_method_id":null,"default_tax_type_id":null,"default_discount_rate":null,"default_price_list_id":null,"tags":[],"addresses":[{"id":245015839,"created_on":"2023-07-11T08:08:47Z","modified_on":"2024-03-13T08:00:21Z","country":"Việt Nam","city":"Quảng Bình","district":"Thành Phố Đồng Hới","ward":"Phường Đồng Phú","address1":"Zhoucun, Zibo, Shandong","address2":null,"zip_code":null,"email":null,"first_name":null,"last_name":null,"full_name":"Zibo Dacheng Trading Co., Ltd","label":null,"phone_number":null,"status":"active"}],"contacts":[],"notes":[],"status":"active","is_default":false},{"id":271332999,"tenant_id":236571,"default_location_id":null,"created_on":"2023-07-03T15:48:39Z","modified_on":"2025-12-06T02:27:03Z","code":"HOUDE","name":"HOUDE","description":"houde.jpg","email":null,"fax":null,"phone_number":null,"tax_number":null,"website":"SƠN ĐÔNG","supplier_group_id":3147762,"debt":-287866170.0000,"group_name":"PHÂN PHỐI","assignee_id":null,"default_payment_term_id":null,"default_payment_method_id":null,"default_tax_type_id":null,"default_discount_rate":null,"default_price_list_id":null,"tags":["CỌC SỚM"],"addresses":[{"id":240593132,"created_on":"2023-07-03T15:48:39Z","modified_on":"2024-03-13T08:00:24Z","country":"Việt Nam","city":"Quảng Bình","district":"Thành Phố Đồng Hới","ward":null,"address1":"Zhoucun, Zibo, Shandong","address2":null,"zip_code":null,"email":null,"first_name":null,"last_name":null,"full_name":"Zibo Dacheng Trading Co., Ltd","label":null,"phone_number":null,"status":"active"}],"contacts":[],"notes":[],"status":"active","is_default":false},{"id":261903923,"tenant_id":236571,"default_location_id":null,"created_on":"2023-06-13T09:49:00Z","modified_on":"2024-10-28T04:19:31Z","code":"PINMU","name":"PINMU","description":null,"email":null,"fax":null,"phone_number":null,"tax_number":null,"website":"NGHĨA Ô","supplier_group_id":2743130,"debt":0,"group_name":"CONTAINER 60","assignee_id":null,"default_payment_term_id":null,"default_payment_method_id":null,"default_tax_type_id":null,"default_discount_rate":null,"default_price_list_id":null,"tags":[],"addresses":[{"id":231556919,"created_on":"2023-06-13T09:49:00Z","modified_on":"2023-06-13T09:49:00Z","country":"Việt Nam","city":null,"district":null,"ward":null,"address1":"x","address2":null,"zip_code":null,"email":null,"first_name":null,"last_name":null,"full_name":null,"label":null,"phone_number":null,"status":"active"}],"contacts":[],"notes":[],"status":"disable","is_default":false},{"id":259488417,"tenant_id":236571,"default_location_id":null,"created_on":"2023-06-08T03:25:26Z","modified_on":"2024-10-28T04:19:31Z","code":"LIWEIDA","name":"LIWEIDA","description":"ermo.jpg","email":null,"fax":null,"phone_number":null,"tax_number":null,"website":"ÔN CHÂU","supplier_group_id":2743130,"debt":1000000.0000,"group_name":"CONTAINER 60","assignee_id":null,"default_payment_term_id":null,"default_payment_method_id":null,"default_tax_type_id":null,"default_discount_rate":null,"default_price_list_id":null,"tags":[],"addresses":[{"id":229261365,"created_on":"2023-06-08T03:25:26Z","modified_on":"2023-06-08T03:25:26Z","country":"Việt Nam","city":null,"district":null,"ward":null,"address1":"xxx","address2":null,"zip_code":null,"email":null,"first_name":null,"last_name":null,"full_name":null,"label":null,"phone_number":null,"status":"active"}],"contacts":[],"notes":[],"status":"disable","is_default":false},{"id":250138948,"tenant_id":236571,"default_location_id":null,"created_on":"2023-05-19T02:06:09Z","modified_on":"2025-12-06T02:26:53Z","code":"MEIHOUSE","name":"MEIHOUSE","description":null,"email":null,"fax":null,"phone_number":null,"tax_number":null,"website":null,"supplier_group_i

    3. Giải thích JSON và cách lưu các thuộc tính.
    {
      "id": 857154285,
      "tenant_id": 236571,
      "default_location_id": null,
      "created_on": "2025-12-05T03:23:14Z",
      "modified_on": "2025-12-06T02:28:18Z",
      "code": "NAIBEN", 
      "name": "NAIBEN", => Tên nhà cung cấp
      "description": null, => Thông tin mô tả
      "email": null,
      "fax": null,
      "phone_number": null,
      "tax_number": null,
      "website": null, => Lưu thông tin website. Lưu dưới dạng dict string -> vì có thể có nhiều website.
      "supplier_group_id": 3147762,
      "debt": 0,
      "group_name": "PHÂN PHỐI", => Có "ĐỘC QUYỀN" và "PHÂN PHỐI" 
      "assignee_id": null,
      "default_payment_term_id": null,
      "default_payment_method_id": null,
      "default_tax_type_id": null,
      "default_discount_rate": null,
      "default_price_list_id": null,
      "tags": [],
      "addresses": [
        {
          "id": 804131455,
          "created_on": "2025-12-05T03:23:14Z",
          "modified_on": "2025-12-05T03:23:14Z",
          "country": "Việt Nam",
          "city": null,
          "district": null,
          "ward": null,
          "address1": "HÀ BẮC",  => Lưu tỉnh của họ bên Trung Quốc: Hà Bắc, Đài Châu, Ôn Châu... để xem nhanh vị trí.
          "address2": null,
          "zip_code": null,
          "email": null,
          "first_name": null, => Lưu link logo vào đây (/static/suppliers/)
          "last_name": null,
          "full_name": null,
          "label": null,          => Lưu tên công ty
          "phone_number": null,  
          "status": "active"
        }
      ],
      "contacts": [],
      "notes": [],
      "status": "active",
      "is_default": false
    }


- Có các chức năng sau:
    - Hiển thị danh sách nhà cung cấp (đang hoạt động).
    - Tên - Logo - Vùng (Tỉnh) - Linkweb (Nếu là link 1688 thì hiển thị logo 1688 kèm link chứ ko hiển thị link).
    - Tags loại phân phối hay độc quyền.
    - Mô tả: Thông tin mô tả của NSX - Ví dụ: NSX đồ thuỷ tinh cho PHALEDO.
    - Số sản phẩm thuộc nhà cung cấp đó. (Xem ở products list)
    ....

-> Có thể thêm logo cho NSX -> nếu chưa có. (Dấu + nhỏ nhỏ ở phía trên logo để đổi hoặc thêm mới)
-> Thêm website: 1688, tmall, taobao, douyin (link tới logo: /static/1688_logo.png). Tự detect logo hiển thị.



# kho/views.py

from django.shortcuts import render
from core.sapo_client import get_sapo_client
from django.http import HttpResponse
from core.shopee_client import doi_shop, SHOPEE_SESSION

def dashboard(request):
    print("Hello")
    doi_shop(10925)  # hoặc "giadungplus_official"
    # Gọi API với session đã gắn header đúng shop
    resp = SHOPEE_SESSION.get("https://banhang.shopee.vn/api/v3/opt/mpsku/list/v2/search_product_list?SPC_CDS=8e6b674e-5f86-4980-b83d-d6017b61a7d2&SPC_CDS_VER=2&page_size=12&list_type=live_all&request_attribute=&operation_sort_by=recommend_v2&need_ads=true")
    print(resp.status_code, resp.text)

    return render(request, "kho/xx.html")

def order_list(request):
    return render(request, "kho/order_list.html")

def debug(request):
    sapo = get_sapo_client()

    # gọi thử 1 request thật đến Sapo
    res = sapo.get("orders.json", params={"limit": 1})

    # chỉ để kiểm tra, không cần parse json vội
    return HttpResponse(str(res.text))

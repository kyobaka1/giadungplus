# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.template import loader
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponse
from django.urls import reverse
from django.core.files.storage import FileSystemStorage
from django.http import Http404,  HttpResponseRedirect
import requests
import re
import xlrd
from py3dbp import Packer, Bin, Item
from lxml import html, etree
from .models import *
import gspread
from google.oauth2.service_account import Credentials
from oauth2client.service_account import ServiceAccountCredentials
from .apps import loginss, json_all, loginsp, logintmdt
import json
import datetime
import os.path
import calendar
import urllib
import time
from gzip import decompress
import qrcode
from barcode import Code128
import math
from bs4 import BeautifulSoup
import urllib.parse
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import sys
import secrets
import hashlib
import win32api, win32con
import PyPDF2
from fpdf import FPDF
from io import BytesIO
import win32print
import base64
from typing import Tuple
import threading
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from PyPDF2 import PdfReader, PdfWriter
import pdfplumber
from barcode.writer import ImageWriter
start_time = time.time()
import os
HOME_PARAM = os.environ.get('DJANGO_HOME', "HN")
# Printer set-up

existing_shop_map = {
    "giadungplus_official": 10925,  #GIADUNGPLUS_OFFICIAL
    "lteng": 155174,  #LTENG
    "phaledo": 134366, #PHALEDO_SHOPEE_MALL
    "phaledo_store": 155687,
    "lteng_hcm": 155938,
    "tiktok_giadungplus": 148291,
}

if "HN" in HOME_PARAM:
    GHOSTSCRIPT_PATH = "C:\\D\\Dropbox\\APP\\GHOSTSCRIPT\\bin\\gswin32.exe"
else:
    GHOSTSCRIPT_PATH = "D:\\Dropbox\\APP\\GHOSTSCRIPT\\bin\\gswin32.exe"

GSPRINT_PATH = "C:\\Program Files (x86)\\Ghostgum\\gsview\\gsprint.exe"
PRINTER = os.environ.get('PRINTER_DEFAULTS', None)
SERVER_ID = os.environ.get('SERVER_ID', None)

# YOU CAN PUT HERE THE NAME OF YOUR SPECIFIC PRINTER INSTEAD OF DEFAULT
if HOME_PARAM != "CSKH":
    win32print.SetDefaultPrinter(PRINTER)
    currentprinter = win32print.GetDefaultPrinter()
    PRINTER_DEFAULTS = {"DesiredAccess":win32print.PRINTER_ALL_ACCESS}
    level = 2
    handle = win32print.OpenPrinter(PRINTER,PRINTER_DEFAULTS)
    attributes = win32print.GetPrinter(handle, level)
    print(f"[+] Use printer: {PRINTER}")

    attributes['pDevMode'].DisplayFixedOutput = 2
    attributes['pDevMode'].Scale       = 98
    win32print.SetPrinter(handle, level, attributes, 0)


USERNAME = 'vuongdn@giadungplus.com'
PASSWORD = 'yeuMai1@'
LOGIN_USERNAME_FIELD = '//*[@id="login"]'
LOGIN_PASSWORD_FIELD = '//*[@id="Password"]'
LOGIN_BUTTON = '/html/body/div[1]/div/div/div/div/div/div/form/div[5]/button'
MAIN_URL = "https://sisapsan.mysapogo.com/admin"
HOME_PARAM = os.environ.get('DJANGO_HOME', None)

#Chrome options for SP46
chrome_options = webdriver.ChromeOptions()
settings = {
    "recentDestinations": [{
        "id": PRINTER,
        "origin": "local",
        "account": ""
    }],
    "selectedDestinationId": PRINTER,
    "version": 1,
    "isHeaderFooterEnabled": False,
    "mediaSize": {
        "height_microns": 150000,
        "name": "A6",
        "width_microns": 100000,
        "custom_display_name": "A6"
    },
    "customMargins": {},
    "isCssBackgroundEnabled": True,
    "marginsType": 2,    
    "scaling": 100,
    "scalingType": 2
}

chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
chrome_options.add_argument('--enable-print-browser')
prefs = {
    'printing.print_preview_sticky_settings.appState': json.dumps(settings),
    'savefile.default_directory': "C:\\Users\\Admin\\Dropbox\\KHO"
}
chrome_options.add_argument('--kiosk-printing')
chrome_options.add_experimental_option('prefs', prefs)

#Chrome options for XP350B
chrome_options_350 = webdriver.ChromeOptions()
settings_3 = {
    "recentDestinations": [{
        "id": "XP350B",
        "origin": "local",
        "account": ""   
    }],
    "selectedDestinationId": "XP350B",
    "version": 1,
    "isHeaderFooterEnabled": False,
    "isLandscapeEnabled": False,
    "mediaSize": {
        "name": "A7",
        "custom_display_name": "A7",
        "height_microns": 10500,
        "width_microns": 7500    
    },
    "customMargins": {},
    "isCssBackgroundEnabled": True,
    "marginsType": 2,    
    "scaling": 100,
    "scalingType": 2
}
chrome_options_350.add_experimental_option("excludeSwitches", ["enable-logging"])
chrome_options_350.add_argument('--enable-print-browser')
prefs_2 = {
    'printing.print_preview_sticky_settings.appState': json.dumps(settings_3),
    'savefile.default_directory': "C:\\Users\\Admin\\Dropbox\\APP"
}
chrome_options_350.add_argument('--kiosk-printing')
chrome_options_350.add_experimental_option('prefs', prefs_2)


#Chrome options for Canon
chrome_options_2 = webdriver.ChromeOptions()
settings_2 = {
    "recentDestinations": [{
        "id": "HP LaserJet Pro M12a",
        "origin": "local",
        "account": ""   
    }],
    "selectedDestinationId": "HP LaserJet Pro M12a",
    "version": 2,
    "isHeaderFooterEnabled": False,
    "isLandscapeEnabled": False,
    "mediaSize": {
        "name": "A5",
        "custom_display_name": "A5",
        "height_microns": 148500,
        "width_microns": 210000    
    },
    "customMargins": {},
    "isCssBackgroundEnabled": True,
    "marginsType": 2,    
    "scaling": 100,
    "scalingType": 2
}
chrome_options_2.add_experimental_option("excludeSwitches", ["enable-logging"])
chrome_options_2.add_argument('--enable-print-browser')
prefs_2 = {
    'printing.print_preview_sticky_settings.appState': json.dumps(settings_2),
    'savefile.default_directory': "C:\\Users\\Admin\\Dropbox\\APP"
}
chrome_options_2.add_argument('--kiosk-printing')
chrome_options_2.add_experimental_option('prefs', prefs_2)

MAIN_URL = "https://sisapsan.mysapogo.com/admin"

def readfile(fileName):
    jsonFile = open(fileName, "r", encoding="utf-8")
    return jsonFile.read()

def writefile(string,fileName):
    jsonFile = open(fileName, "w+", encoding="utf-8")
    jsonFile.write(string)
    jsonFile.close()

def writejsonfile(myjson, fileName):
    with open(fileName, "w", encoding="utf-8") as jsonFile:
        json.dump(myjson, jsonFile, ensure_ascii=False, indent=2)

def update_status(order_id, status_id,location_id):
    # Đã gói - 16698
    # Đã in - 16697

    URL = f"{MAIN_URL}/orders/{order_id}/updateProcessStatus/{status_id}.json"
    loginss.headers.update({'X-Sapo-Locationid': str(location_id)})
    rs = loginss.post(URL, json={})

def update_data_from_code(order_code,mydata):
    # Tìm cái shipment tương ứng với đơn hàng.
    URL = f"{MAIN_URL}/fulfillments.json?page=1&limit=20&query={order_code}&delivery_types=courier"
    rs = loginss.get(URL)
    if len(rs.text) > 200:
        fun = json.loads(rs.text)['fulfillments'][0]
        URL = f"{MAIN_URL}/shipments/update"
        data = {
            'id': fun['id'],
            'note': json.dumps(mydata)
        }
        rs = loginss.post(URL, data=data)

def update_data(fun_code,mydata):
        
    URL = f"{MAIN_URL}/shipments/update"
    data = {
        'id': fun_code,
        'note': json.dumps(mydata)
    }
    rs = loginss.post(URL, data=data)

def update_data_one(order_code,update_info):

    URL = f"{MAIN_URL}/fulfillments.json?page=1&limit=20&query={order_code}&delivery_types=courier"
    rs = loginss.get(URL)
    if len(rs.text) > 200:
        fun = json.loads(rs.text)['fulfillments'][0]
        if len(fun) > 0:
            save_data = {}
            # Nếu đã có data rồi.
            if fun['shipment'] != None:
                if fun['shipment']['note'] != None and "{" in fun['shipment']['note']:
                    save_data = json.loads(fun['shipment']['note'])

            for key, value in update_info.items():
                save_data[key] = value

            save_data = gopnhan_gon(save_data)
            fun['shipment']['note'] = json.dumps(save_data)
            
            URL = f"{MAIN_URL}/orders/{fun['order_id']}/fulfillments/{fun['id']}.json"
            data = {
                'fulfillment': fun
            }
            rs = loginss.put(URL, json=data)
        else:
            print(f"[-] UPDATE ERROR - NOT FOUND!")
            return 0

    else:
        return 0

def get_data_packing(order):
    #Xử lý data gói hàng đang lưu trên Sapo.
    if len(order['fulfillments']) > 0:
        if order['fulfillments'][-1]['shipment'] != None:
            if order['fulfillments'][-1]['shipment']['note'] != None and "}" in order['fulfillments'][-1]['shipment']['note']:
                data_save = mo_rong_gon(order['fulfillments'][-1]['shipment']['note'])
                for key, value in data_save.items():
                    order[key] = value

    if 'packing_status' not in order:
        order['packing_status'] = 0

    return order

def gopnhan_gon(json_data):
    key_mapping = {
        "packing_status": "pks",
        "nguoi_goi": "human",
        "time_packing": "tgoi",
        "dvvc": "vc",
        "shopee_id": "spid",
        "time_print": "tin",
        "split": "sp",
        "time_chia":"tc",
        "shipdate":"sd",
        "nguoi_chia":"nc"
    }

    gopnhan_gon_data = {}
    for key, value in json_data.items():
        new_key = key_mapping.get(key, key)
        gopnhan_gon_data[new_key] = value

    return gopnhan_gon_data

def mo_rong_gon(json_data):
    data = json.loads(json_data)
    reverse_key_mapping = {
        "pks": "packing_status",
        "human": "nguoi_goi",
        "tgoi": "time_packing",
        "vc": "dvvc",
        "spid": "shopee_id",
        "tin": "time_print",
        "sp": "split",
        "sd":"shipdate",
        "tc":"time_chia",
        "nc":"nguoi_chia"
    }

    mo_rong_gon_data = {}
    for key, value in data.items():
        new_key = reverse_key_mapping.get(key, key)
        mo_rong_gon_data[new_key] = value

    return mo_rong_gon_data

def convert_to_m_b(number):
    if isinstance(number, int):
        if number >= 1_000_000:
            return str(number // 1_000_000) + 'M'
        elif number >= 1_000:
            return str(number // 1_000) + 'K'
    return str(number)

def convert_int_in_obj(obj):
    for key, value in obj.items():
        if isinstance(value, dict):
            convert_int_in_obj(value)
        elif isinstance(value, int):
            obj[key] = convert_to_m_b(value)

def get_list_giavon():
    LGV = {}
    # ĐẦU TIÊN -> PHẢI LẤY GIÁ VỐN CÁI ĐÃ
    ALL_PA = js_get_url(f"https://sisapsan.mysapogo.com/admin/price_adjustments.json?query=SUPFINAL&page=1&limit=250")["price_adjustments"]
    for PA in ALL_PA:
        for line in PA["line_items"]:
            line['data'] = json.loads(line['note'])

            if line['variant_id'] not in LGV:
                LGV[line['variant_id']] = []
                LGV[line['variant_id']].append(line['data'])
            else:
                LGV[line['variant_id']].append(line['data'])

    for key in LGV.keys():
        LGV[key] = sorted(LGV[key], key=lambda x: datetime.datetime.strptime(x['date'].strip(), "%d/%m/%Y"))

    return LGV

def find_giavon(variant_id, created_on, location_id, LGV,line_amount):
    flag = 0
    if variant_id in LGV:
        for giavon_item in LGV[variant_id]:
            if giavon_item['li']:
                giavon_date = datetime.datetime.strptime(giavon_item['date'].strip(), "%d/%m/%Y")
                if created_on < giavon_date:
                    giavon = int(giavon_item['pu'])
                    flag = 1
                    break
                else:
                    giavon = int(giavon_item['pu'])
                    flag = 1
    else:
        giavon = int(line_amount * 0.35)  # Nếu không tìm thấy giá vốn, giả định giá vốn là 60% giá trị đơn hàng
    if flag == 0:
        giavon = int(line_amount * 0.35)


    return giavon

def js_get_url(request_url):
    if 'market-place' in request_url:
        rs = logintmdt.get(request_url).text
    else:
        rs = loginss.get(request_url).text
    if "{" in rs:
        return json.loads(rs)
    else:
        return {}


def updateFee(shipmentid,fee):
    url = "https://sisapsan.mysapogo.com/admin/shipments/updateFreightAmount"
    data = {'id': shipmentid, 'fee':abs(int(fee))}
    loginss.post(url,data=data)

def get_region(shipping_address, MIEN_NAM, MIEN_BAC):
    # Xác định vùng miền
    if shipping_address and shipping_address.get('city', None):
        if shipping_address['city'] in MIEN_NAM:
            vung_mien = "Miền Nam"
        elif shipping_address['city'] in MIEN_BAC:
            vung_mien = "Miền Bắc"
        else:
            vung_mien = "Miền Bắc"  # Mặc định là Miền Bắc nếu không nhận diện được thành phố
    else:
        vung_mien = "Miền Bắc"

def loc_brand(brands):
    new_brands = []
    for brand in brands:
        if brand['id'] not in [832828,981956,838100,1635941,1693497,833572,833594,833602,833612,1076219,1136933,1150675,1150680,1150681,1150682,1150683,1150684,1150685,1150686,1150687,1150688]:
            new_brands.append(brand)
    return new_brands

def sort_order(x):
    tang_order = {"T4":0, "T3":1, "T2":2, "T1":3}
    return (tang_order[x['tang']], str(x['ke']))

def parse_content_to_headers(content):
    header_dict = {}
    for line in content.splitlines():
        if line.strip():  # Ignore empty lines
            header_name, header_value = line.split(':', 1)  # Split at first colon
            header_dict[header_name.strip()] = header_value.strip()
    return header_dict

def get_json_note(TICKET_CUSTOMER_IDS):
    data_list = []
    for ticket_id in TICKET_CUSTOMER_IDS:
            url_notes = f"{MAIN_URL}/customers/{ticket_id}.json"
            res = loginss.get(url_notes)
            if res.status_code != 200:
                continue

            customer = res.json().get("customer", {})
            active_notes = [n for n in customer.get("notes", []) if n.get("status") == "active"]
            for note in active_notes:
                try:
                    content = json.loads(note.get("content", "{}"))
                    content['ticket_id'] = ticket_id
                    content['note_id'] = note['id']
                    data_list.append(content)
                except:
                    continue

    return data_list


def get_json_variants(TICKET_CUSTOMER_IDS):
    data_list = get_json_note(TICKET_CUSTOMER_IDS)

    for content in data_list:
        content["box_dai"] = float(content["box_dai"] )
        content["box_rong"] = float(content["box_rong"] )
        content["box_cao"] = float(content["box_cao"] )
        content["fullbox"] = int(float(content["fullbox"]))

    index = {}
    for vari in data_list:
        if 'vari_id' in vari:
            if vari['vari_id'] != "":
                index[str(int(vari['vari_id']))] = vari

    return index

def get_data_variant(vari_id):

    vari = js_get_url(f"{MAIN_URL}/variants/{vari_id}.json")['variant']
    product = js_get_url(f"{MAIN_URL}/products/{vari['product_id']}.json")['product']

    if product['description'] == None or product['description'] == '' :
        data = {'variant-data': {}}
    elif "###########" in product['description']:
        data = {'variant-data': {}}
        
    else:
        try:
            data = base64.b64decode(product['description'])
            data = json.loads(data)
        except Exception:
            data = {'variant-data': {}}

    if str(vari['id']) not in data['variant-data']:
        data_form = {'price_tq': 0, 'name_tq': '', 'sku_tq': '', '1_dai':0, '1_rong':0, '1_cao':0, '1_nang':0, '1_nang_qd':0, 'fullbox':0,
         'box_dai':0, 'box_rong':0, 'box_cao':0, 'sku_nhapkhau': '', 'check_done':0}
    else:
        data_form = data['variant-data'][str(vari['id'])]
        data_form['price_tq'] = float(data_form['price_tq'])
        data_form['1_dai'] = float(data_form['1_dai'])
        data_form['1_rong'] = float(data_form['1_rong'])
        data_form['1_cao'] = float(data_form['1_cao'])
        data_form['1_nang_qd'] = float(data_form['1_nang_qd'])
        data_form['fullbox'] = int(data_form['fullbox'])
        data_form['box_dai'] = float(data_form['box_dai'])
        data_form['box_rong'] = float(data_form['box_rong'])
        data_form['box_cao'] = float(data_form['box_cao'])
        if 'check_done' in data_form:
            data_form['check_done'] = float(data_form['check_done'])
        else:
            data_form['check_done'] = 0
    
    data_form["stock_hn"] =  vari["inventories"][0]["on_hand"]
    data_form["stock_sg"] =  vari["inventories"][1]["on_hand"] 

    return data_form



def all_xnk_data():
    TICKET_CUSTOMER_ID = '759930912'
    # STEP 3 - Load dữ liệu render ra giao diện
    data_list = []
    url_notes = f"{MAIN_URL}/customers/{TICKET_CUSTOMER_ID}.json"
    res = loginss.get(url_notes)
    if res.status_code != 200:
        return JsonResponse({"status": "error", "msg": "Không lấy được notes"}, status=500)

    customer = res.json().get("customer", {})
    active_notes = [n for n in customer.get("notes", []) if n.get("status") == "active"]
    for note in active_notes:
        try:
            content = json.loads(note.get("content", "{}"))
            data_list.append(content)
        except:
            continue

    return data_list

def doi_shop(shop_connect, loginsp):
    directory_path = 'logs/cookie/'

    shop_name = name = next((k for k, v in existing_shop_map.items() if v == shop_connect), None)
    if not shop_name:
        return 0  # Shop not found

    filename = f"{shop_name}.log"
    file_path = os.path.join(directory_path, filename)
    if os.path.isfile(file_path):
        try:
            with open(file_path, 'r') as file:
                content = file.read()
            new_headers = parse_content_to_headers(content)
            loginsp.headers.update(new_headers)
            return 1  # Success
        except Exception as e:
            print(f"Error updating headers: {e}")
            return 0  # Error
    else:
        return 0  # File not found

def search_order_shopee(search_key):
    #
    MADONHANG = ""
    list_shop = [10925,134366]

    for shop in list_shop:
        if doi_shop(shop,loginsp) == 1:
            URL_SEARCH = f"https://banhang.shopee.vn/api/v3/order/get_order_list_search_bar_hint?SPC_CDS=dd1e2956-003c-47ed-8af4-1ba50738c666&SPC_CDS_VER=2&keyword={search_key}&category=3&order_list_tab=100"    
            load_data = loginsp.get(URL_SEARCH).text
            load_data = json.loads(load_data)
            shipping_trace = load_data["data"].get("shipping_trace_numbers_result")
            if shipping_trace is not None:
                MADONHANG = load_data["data"]["shipping_trace_numbers_result"]["list"][0]["order_sn"]
            else:
                pass

    return MADONHANG

def print_shopee(order,prints):

    xtmdt_order = js_get_url(f"https://market-place.sapoapps.vn/v2/orders?page=1&limit=1&connectionIds=155938,155687,155174,134366,10925&query={order['reference_number']}")
    
    if "orders" in xtmdt_order:
        tmdt_order = xtmdt_order['orders'][0]
    else:
        for i in range(3):
            xtmdt_order = js_get_url(f"https://market-place.sapoapps.vn/v2/orders?page={int(i+1)}&limit=250&connectionIds=155938,155687,155174,134366,10925&channelOrderStatus=PROCESSED&sortBy=ISSUED_AT&orderBy=desc")

            if "Không tìm thấy đơn hàng nào" not in xtmdt_order:
                for zorder in xtmdt_order["orders"]:
                    if zorder["channel_order_number"] == order['reference_number']:
                        tmdt_order = zorder
                        print("Find it!")
                        break

    logintmdt.put(f"https://market-place.sapoapps.vn/v2/orders/sync?ids={tmdt_order['id']}&accountId=3199")

    if "Nhanh" == tmdt_order['shipping_carrier_name']:
        time.sleep(3)
        xtmdt_order = js_get_url(f"https://market-place.sapoapps.vn/v2/orders?page=1&limit=1&connectionIds=155938,155687,155174,134366,10925&query={order['reference_number']}")
        if "orders" in xtmdt_order:
            tmdt_order = xtmdt_order['orders'][0]
        else:
            for i in range(3):
                xtmdt_order = js_get_url(f"https://market-place.sapoapps.vn/v2/orders?page={int(i+1)}&limit=250&connectionIds=155938,155687,155174,134366,10925&channelOrderStatus=PROCESSED&sortBy=ISSUED_AT&orderBy=desc")

                if "Không tìm thấy đơn hàng nào" not in xtmdt_order:
                    for zorder in xtmdt_order["orders"]:
                        if zorder["channel_order_number"] == order['reference_number']:
                            tmdt_order = zorder
                            print("Find it!")
                            break


    directory_path = 'logs/print-cover'
    shop_name = name = next((k for k, v in existing_shop_map.items() if v == tmdt_order['connection_id']), None)
    link_to_cover = directory_path + "/" + shop_name + "/"
    DON_TACH_FLAG = 1

    if tmdt_order['channel_order_status'] in ['READY_TO_SHIP','RETRY_SHIP']:
        if shop_name=="giadungplus_official" and order["location_id"] == 241737:
            address_id = 29719283
            print("[+] Get packed giadungplus_official: Kho HN - GELEXIMCO!")
        elif shop_name=="giadungplus_official" and order["location_id"] == 548744:
            address_id = 200025624
            print("[+] Get packed giadungplus_official: Kho HCM - TOKY!")

        if shop_name=="phaledo" and order["location_id"] == 241737:
            address_id = 200033410
            print("[+] Get packed phaledo: Kho HN - GELEXIMCO!")

        elif shop_name=="phaledo" and order["location_id"] == 548744:
            address_id = 200086436
            print("[+] Get packed phaledo: Kho HCM - TOKY!")

        if shop_name=="lteng" and order["location_id"] == 241737:
            address_id = 200165433
            print("[+] Get packed lteng: Kho HN - GELEXIMCO!")

        elif shop_name=="lteng" and order["location_id"] == 548744:
            address_id = 200165433
            print("[+] Get packed lteng: Kho HCM - TOKY!")


        if shop_name=="lteng_hcm" and order["location_id"] == 241737:
            address_id = 200174020
            print("[+] Get packed lteng hcm: Kho HN - GELEXIMCO!")

        elif shop_name=="lteng_hcm" and order["location_id"] == 548744:
            address_id = 200174020
            print("[+] Get packed lteng hcm: Kho HCM - TOKY!")

        if shop_name=="phaledo_store" and order["location_id"] == 241737:
            address_id = 71071674
            print("[+] Get packed phaledo: Kho HN - GELEXIMCO!")

        elif shop_name=="phaledo_store" and order["location_id"] == 548744:
            address_id = 71071674
            print("[+] Get packed phaledo: Kho HCM - TOKY!")

        pick_up = js_get_url(f"https://market-place.sapoapps.vn/v2/orders/confirm/init?accountId=319911&ids={tmdt_order['id']}")

        if len(pick_up['data']['init_fail']['shopee'][0]['init_confirms']) == 0:
            if len(pick_up['data']['init_success']['shopee'][0]['init_confirms'][0]['pick_up_shopee_models']) > 0:
                STRING_TIME = pick_up['data']['init_success']['shopee'][0]['init_confirms'][0]['pick_up_shopee_models'][0]['time_slot_list'][0]['pickup_time_id']
            else:
                STRING_TIME = 0

            put_info = {
                "confirm_order_request_model": [
                    {
                        "connection_id": tmdt_order['connection_id'],
                        "order_models": [
                            {
                                "order_id": tmdt_order['id'],
                                "pickup_time_id": STRING_TIME,
                            }
                        ],
                        "shopee_logistic": {
                            "pick_up_type": 1,
                            "address_id": address_id
                        }
                    }]}

            #Nếu là đơn SPX ở kho Hà Nội -> chọn gửi tại bưu cục.
            if "SPX Express" in tmdt_order['shipping_carrier_name'] and order["location_id"] == 241737:
                put_info = {
                "confirm_order_request_model": [
                    {
                        "connection_id": tmdt_order['connection_id'],
                        "order_models": [
                            {
                                "order_id": tmdt_order['id'],
                                "pickup_time_id": STRING_TIME,
                            }
                        ],
                        "shopee_logistic": {
                            "pick_up_type": 2,
                            "address_id": address_id
                        }
                    }]}

            pick_up = "https://market-place.sapoapps.vn/v2/orders/confirm?accountId=319911"
            rs = logintmdt.put(pick_up, json=put_info)

            time.sleep(4)
    
    if doi_shop(tmdt_order['connection_id'],loginsp) == 1:
        print(f"[+] Print order shop: {shop_name}")
        if shop_name == 'giadungplus_official':
            shop_id = 241961702
        elif shop_name == 'phaledo':
            shop_id = 1009027554
        elif shop_name == 'lteng':
            shop_id = 1612223456
        elif shop_name == 'lteng_hcm':
            shop_id = 1638634407
        elif shop_name == 'phaledo_store':
            shop_id = 15064699

        try:
            URL = f"https://banhang.shopee.vn/api/v3/order/get_order_list_search_bar_hint?keyword={order['reference_number']}&&category=1&order_list_tab=100&SPC_CDS=a2c0b37e-fa4d-420d-a821-dc94b4265519&SPC_CDS_VER=2"
            load_data = loginsp.get(URL).text
            #Sẽ trả về order_id, nếu không có order_id tức là request thất bại.

            SHOPEE_ID =json.loads(load_data)['data']['order_sn_result']['list'][0]['order_id']
            print("Shopee ID:" + str(SHOPEE_ID))
            today = datetime.datetime.now().date()
            
            FLAGSHIP = 1
            SHIPBYDATE = today.strftime('%d/%m')
            SHIP_DAY = today.strftime('%d/%m')

            #Thông tin kiện hàng
            URL = f"https://banhang.shopee.vn/api/v3/order/get_package?SPC_CDS=a45333f0-5de3-4869-b134-460db3e8ea09&SPC_CDS_VER=2&order_id={SHOPEE_ID}"
            RS = json.loads(loginsp.get(URL).text)
            
            
            # Nếu nó là đơn tách
            if RS["data"]["order_info"]["split_up"] == 1:
                print("[+] Đơn tách!")
                
                URL = f"https://market-place.sapoapps.vn/v2/orders?page=1&limit=20&connectionIds=155938,155687,155174,134366,10925&query={order['reference_number']}&sortBy=ISSUED_AT&orderBy=desc"
                ORDER_TMDT = js_get_url(URL)["orders"][0]
                for x in order['real_items']:
                    x["item_id_shopee"] = 0
                for pr in ORDER_TMDT["products"]:
                    for x in order['real_items']:
                        if int(pr["sapo_variant_id"]) == int(x["id"]) or int(pr["sapo_variant_id"]) == int(x["old_id"]):
                            x["item_id_shopee"] = pr["variation_id"]

            LIST_PACK =RS['data']['order_info']["package_list"]
            DON_TACH_FLAG = len(LIST_PACK)
            
            PACK_1 = 0
            for PACKEDD in LIST_PACK:
                PACKED = PACKEDD['package_number']
                URL = "https://banhang.shopee.vn/api/v3/logistics/create_sd_jobs?SPC_CDS=8ff879e2-3346-42c6-988b-5ed1adc23da9&SPC_CDS_VER=2&async_sd_version=0.2"
                JSON_POST = {"group_list":[
                    {"primary_package_number":PACKED,
                    "group_shipment_id":0,
                    "package_list":[{"order_id":SHOPEE_ID,"package_number":PACKED}]}],"region_id":"VN","shop_id":shop_id,"channel_id":50021,"record_generate_schema":False,"generate_file_details":[{"file_type":"THERMAL_PDF","file_name":"Phiếu gửi hàng","file_contents":[3]}]
                }
                result = json.loads(loginsp.post(URL, json=JSON_POST).text)

                print(result)
                
                PRINT_URL = result['data']['list'][0]['job_id']
                PRINT_URL = f"https://banhang.shopee.vn/api/v3/logistics/download_sd_job?SPC_CDS=8dcc64a8-5308-476d-948d-9825a3610549&SPC_CDS_VER=2&job_id={PRINT_URL}&is_first_time=1"
                
                print("GET PHIEU GUI HANG!")
                r = loginsp.get(PRINT_URL)    
                while len(r.content) < 1000:
                    r = loginsp.get(PRINT_URL)
                    time.sleep(2)    
                    print("Repair Loading!")

                xpdfReader = PyPDF2.PdfReader(BytesIO(r.content),strict=False)
                pdfWriter2 = PyPDF2.PdfWriter()
                for page in range(len(xpdfReader.pages)):
                    pageObj = xpdfReader.pages[page]
                    pdfWriter2.add_page(pageObj)
              
                # pdfplumber xử lý saudonahngf
                try:
                    with pdfplumber.open(BytesIO(r.content)) as pdf:
                        page = pdf.pages[0]
                        lines = page.extract_text().split("\n")
                        ten_khach_hang = lines[3].replace("Gia Dụng Plus +","").replace("Gia Dụng Plus Store ","").replace("Gia Dụng Plus Official ","").replace("Phaledo Official ","").replace("Gia Dụng Plus HCM ","").replace("Gia Dụng Plus HN ","").replace("Gia Dụng Plus ","").replace("Phaledo Offcial ","").replace("lteng_vn ","").replace("LTENG VIETNAM ","").replace("PHALEDO ® ","").replace("LTENG ","").replace("LTENG HCM ","")

                        print(ten_khach_hang)
                        all_data = js_get_url(f"{MAIN_URL}/customers/{order['customer_id']}.json")["customer"]
                        all_data["name"] = ten_khach_hang

                        if "Lô C21 Ô 2, Khu đô thị Geleximco" not in ten_khach_hang or "B76a Tô Ký (Hẻm đối diện" not in ten_khach_hang:
                            rs = loginss.put(f"{MAIN_URL}/customers/{order['customer_id']}.json",json=all_data)
                                           
                except Exception as e:
                    print(f"Lỗi khi mở bằng pdfplumber: {e}")

                pdf = FPDF('P', 'mm', (100, 150))
                # Add a page
                pdf.add_page()
                pdf.set_font("Arial",'B', size = 34)
                # create a cell
                pdfWriter = PyPDF2.PdfWriter()
                pdfmetrics.registerFont(TTFont('UTM Avo', 'assets/font/micross.ttf'))
                pdfmetrics.registerFont(TTFont('UTM Avo Bold', 'assets/font/UTM_AvoBold.ttf'))

                pdfmetrics.registerFont(TTFont('Arial', 'assets/font/arial.ttf'))
                pdfmetrics.registerFont(TTFont('ArialI', 'assets/font/ariali.ttf'))

                list_kemkeo = []
                all_kemkeo = js_get_url(f"{MAIN_URL}/products.json?tags=add_keo_dan&page=1&litmit=250")["products"]
                for pr in all_kemkeo:
                    for vari in pr['variants']:
                        list_kemkeo.append(vari['id'])
                flagkemkeo = 0

                if "SPX Express" in tmdt_order['shipping_carrier_name']:
                    print("[+] Ben van chuyen: Shopee Xpress")
                    watermark = PyPDF2.PdfReader(f'{link_to_cover}shopee-express-cover.pdf')
                
                    c = canvas.Canvas("logs/MVD.pdf")
                    c.setPageSize((4.1*inch, 5.8*inch))
                    c.translate(inch, inch)
                    c.rotate(90)
                    
                    c.setFont('UTM Avo Bold', 33)
                    c.drawString(-45, 42, str(tmdt_order['channel_order_number']))
                    c.rotate(270)
                    
                    y_value = 168

                    count_line = 0
                    for x in order['real_items']:
                        count_line += 1

                    line_spacing = 12 if count_line > 6 else int(60 / max(1, count_line))
                    if line_spacing < 11:
                        line_spacing = 10
                    if line_spacing > 30:
                        line_spacing = 20

                    chuthich = []
                    count = 0
                    sokeo = 0

                    
                    if DON_TACH_FLAG > 1:
                        flag = 0
                        for s_item in PACKEDD["items"]:
                            for x in order['real_items']:
                                if str(x["item_id_shopee"]) == str(s_item["model_id"]):
                                    if x['id'] in list_kemkeo:
                                        if x['id'] not in [220497520,220497571]:
                                            sokeo += x['quantity']
                                        else:
                                            sokeo += int(x['quantity']/3)

                                        flagkemkeo = 1

                                    if count < 10:
                                        line_order = f"** {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                        line_order = line_order[:53]
                                        c.setFont('Arial', 8)
                                        c.drawString(-32, y_value, line_order)
                                        # In tên của sản phẩm
                                        if count_line <= 6:
                                            y_value -= 10
                                            c.setFont('ArialI', 7)
                                            c.drawString(-32, y_value, x['pr_name'])
                                        y_value -= line_spacing

                                    count += 1
                                    flag = 1

                        # Sản phẩm chưa có trong danh mục.
                        if flag == 0:
                            for x in order['real_items']:
                                if x["item_id_shopee"] == 0:
                                    if count < 10:
                                        line_order = f"* {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                        line_order = line_order[:53]
                                        c.setFont('Arial', 8)
                                        c.drawString(-32, y_value, line_order)
                                        y_value -= line_spacing  
                                    count += 1
                            
                    else:
                        for x in order['real_items']:
                            if x['id'] in list_kemkeo:
                                if x['id'] not in [220497520,220497571]:
                                    sokeo += x['quantity']
                                else:
                                    sokeo += int(x['quantity']/3)
                                flagkemkeo = 1

                            if count < 10:
                                line_order = f"** {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                line_order = line_order[:53]
                                c.setFont('Arial', 8)
                                c.drawString(-32, y_value, line_order)
                                
                                # In tên của sản phẩm
                                if count_line <= 5:
                                    y_value -= 10
                                    c.setFont('ArialI', 7)
                                    c.drawString(-32, y_value, x['pr_name'])

                                y_value -= line_spacing
                            count += 1

                    if count > 10:
                        c.setFont('UTM Avo Bold', 8)
                        c.drawString(-32, y_value, "** ĐƠN DÀI - QUÉT SAPO để xem thêm.")
                        y_value -= 10


                    if flagkemkeo == 1:
                        sokeo = int(sokeo)
                        y_value -= 10
                        c.setFont('UTM Avo Bold', 8)
                        c.setFillColor(colors.black)
                        c.rect(-32, y_value, 150, 14, stroke=1, fill=1)
                        c.setFillColor(colors.white)  # Đặt lại màu văn bản
                        y_value += 4
                        c.drawString(-32, y_value, f"  * TẶNG KÈM KEO /// SL: {sokeo} LỌ")

                    c.setFillColor(colors.black)  # Đặt lại màu văn bản
                    if order["note"] and order["note"] != "" and PACK_1==0:
                        if flagkemkeo == 1:
                            y_value -= 20
                        else:
                            y_value -= 5
                        c.setFont('UTM Avo Bold', 9)

                        max_length = 28  # Chiều dài tối đa cho mỗi dòng
                        note = "*** LƯU Ý: "+ order["note"]

                        PACK_1 = 1
                        note = note.strip()  # Loại bỏ các khoảng trắng đầu và cuối
                        
                        while note:
                            if len(note) > max_length:
                                c.drawString(-32, y_value, f"{note[:max_length]}")
                                note = note[max_length:]
                            else:
                                c.drawString(-32, y_value, f"{note}")
                                note = ""
                            y_value -= 12  # Điều chỉnh khoảng cách dòng tùy theo yêu cầu của bạn

                    c.setFont('UTM Avo Bold', 15)
                    if DON_TACH_FLAG > 1:
                        c.drawString(-25, 23, f"- Tách đơn: {PACKEDD['parcel_no']}/{DON_TACH_FLAG} -")
                    else:
                        c.drawString(0, 23, f"- Tổng: {int(order['total_quantity'])} -")
     
                    if order["location_id"] == 241737:
                        c.setFont('UTM Avo', 8)
                        c.drawString(-35, 255, f"C21-02 Geleximco, Dương Nội")
                        c.drawString(-35, 245, f"Hà Đông, Hà Nội")
                        c.setFont('UTM Avo Bold', 10)
                        c.drawString(-35, 213, f"KHO HÀ NỘI: GELE")

                    else:
                        c.setFont('UTM Avo', 8)
                        c.drawString(-35, 255, f"B76a Tô Ký, Quận 12")
                        c.drawString(-35, 245, f"Thành phố Hồ Chí Minh")

                        c.setFont('UTM Avo Bold', 10)
                        c.drawString(-35, 213, f"KHO SÀI GÒN: TOKY")

                    if FLAGSHIP == 1:
                        SHIP_CONTENT = f"GẤP >> HÔM NAY: {SHIP_DAY}"
                    else:
                        SHIP_CONTENT = f"GỬI TRƯỚC NGÀY: {SHIP_DAY}"

                    c.setFillColorRGB(1, 1, 1)
                    c.setFont('UTM Avo Bold', 9)
                    c.drawString(87, 210, SHIP_CONTENT)  

                    c.save()
                    mavandon = PyPDF2.PdfReader('logs/MVD.pdf')
                
                elif "J&T" in tmdt_order['shipping_carrier_name']:
                    print("[+] Ben van chuyen: J&T Express")
                    watermark = PyPDF2.PdfReader(f'{link_to_cover}jat-express-cover.pdf')
                    c = canvas.Canvas("logs/MVD.pdf")
                    c.setPageSize((4.1*inch, 5.8*inch))
                    c.translate(inch, inch)
                    c.rotate(90)
                    pdfmetrics.registerFont(TTFont('UTM Avo', 'assets/font/UTM_Avo.ttf'))
                    pdfmetrics.registerFont(TTFont('UTM Avo Bold', 'assets/font/UTM_AvoBold.ttf'))
                    c.setFont('UTM Avo Bold', 34)
                    c.drawString(0, 42, str(tmdt_order['channel_order_number']))

                    date_time = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                    c.rotate(270)
                    c.setFont('UTM Avo', 8)
                    c.drawString(118, 21, date_time)
                    c.setFont('UTM Avo', 8)
                    y_value = 182
                    count = 0
                    sokeo = 0
                    if DON_TACH_FLAG > 1:
                        flag = 0
                        for s_item in PACKEDD["items"]:
                            for x in order['real_items']:
                                if str(x["item_id_shopee"]) == str(s_item["model_id"]):
                                    if x['id'] in list_kemkeo:
                                        if x['id'] not in [220497520,220497571]:
                                            sokeo += x['quantity']
                                        else:
                                            sokeo += int(x['quantity']/3)

                                        flagkemkeo = 1

                                    if count < 10:
                                        line_order = f"* {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                        line_order = line_order[:53]
                                        c.drawString(-32, y_value, line_order)
                                        y_value -= 10
                                    count += 1
                                    flag = 1

                        if flag == 0:
                            for x in order['real_items']:
                                if x["item_id_shopee"] == 0:
                                    if count < 10:
                                        line_order = f"* {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                        line_order = line_order[:53]
                                        c.drawString(-32, y_value, line_order)
                                        y_value -= 10
                                    count += 1
                            
                    else:
                        for x in order['real_items']:
                            if x['id'] in list_kemkeo:
                                if x['id'] not in [220497520,220497571]:
                                    sokeo += x['quantity']
                                else:
                                    sokeo += int(x['quantity']/3)
                                flagkemkeo = 1

                            if count < 10:
                                line_order = f"* {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                line_order = line_order[:53]
                                c.drawString(-32, y_value, line_order)
                                y_value -= 10
                            count += 1

                    if flagkemkeo == 1:
                        sokeo = int(sokeo)
                        y_value -= 10
                        c.setFont('UTM Avo Bold', 8)
                        c.setFillColor(colors.black)
                        c.rect(-32, y_value, 150, 14, stroke=1, fill=1)
                        c.setFillColor(colors.white)  # Đặt lại màu văn bản
                        y_value += 4
                        c.drawString(-32, y_value, f"  * TẶNG KÈM KEO /// SL: {sokeo} LỌ")

                    c.setFillColor(colors.black)  # Đặt lại màu văn bản
                    if flagkemkeo == 1:
                        y_value -= 20
                    else:
                        y_value -= 5
                    c.setFont('UTM Avo Bold', 10)

                    max_length = 28  # Chiều dài tối đa cho mỗi dòng
                    note = "*** LƯU Ý: "+ order["note"]

                    if order["note"] and order["note"] != "" and PACK_1==0:
                        PACK_1 = 1
                        note = note.strip()  # Loại bỏ các khoảng trắng đầu và cuối
                        while note:
                            if len(note) > max_length:
                                c.drawString(-32, y_value, f"{note[:max_length]}")
                                note = note[max_length:]
                            else:
                                c.drawString(-32, y_value, f"{note}")
                                note = ""
                            y_value -= 12  # Điều chỉnh khoảng cách dòng tùy theo yêu cầu của bạn
                            
                    c.setFont('UTM Avo Bold', 20)
                    if DON_TACH_FLAG > 1:
                        c.drawString(0, 92, f"- Đ.TÁCH {PACKEDD['parcel_no']} -")
                    else:
                        c.drawString(25, 92, f"- {int(order['total_quantity'])} -")
                    c.setFont('UTM Avo Bold', 10)
                    c.drawString(10, -16, f"Anh/chị {order['shipping_address']['full_name']} ơi <3")
                    
                    if FLAGSHIP == 1:
                        SHIP_CONTENT = f"GẤP >> HÔM NAY: {SHIP_DAY}"
                    else:
                        SHIP_CONTENT = f"GỬI TRƯỚC NGÀY: {SHIP_DAY}"

                    c.setFont('UTM Avo Bold', 9)
                    c.drawString(-15, 80, SHIP_CONTENT)

                    c.save()

                    mavandon = PyPDF2.PdfReader('logs/MVD.pdf')

                elif "Ninja" in tmdt_order['shipping_carrier_name']:
                    print("[+] Ben van chuyen: Ninja Van")
                    watermark = PyPDF2.PdfReader(f'{link_to_cover}ninja-cover.pdf')
                   
                    c = canvas.Canvas("logs/MVD.pdf")
                    c.setPageSize((4.1*inch, 5.8*inch))
                    c.translate(inch, inch)
                    c.rotate(90)
                    pdfmetrics.registerFont(TTFont('UTM Avo', 'assets/font/UTM_Avo.ttf'))
                    pdfmetrics.registerFont(TTFont('UTM Avo Bold', 'assets/font/UTM_AvoBold.ttf'))
                    c.setFont('UTM Avo Bold', 33)
                    c.drawString(-45, 42, str(tmdt_order['channel_order_number']))

                    date_time = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
                    c.rotate(270)
                    c.setFont('UTM Avo', 8)
                    c.drawString(152, 80, date_time)
                    c.setFont('UTM Avo', 8)
                    y_value = 172
                    count = 0
                    sokeo = 0
                    if DON_TACH_FLAG > 1:
                        flag = 0
                        for s_item in PACKEDD["items"]:
                            for x in order['real_items']:
                                if str(x["item_id_shopee"]) == str(s_item["model_id"]):
                                    if x['id'] in list_kemkeo:
                                        if x['id'] not in [220497520,220497571]:
                                            sokeo += x['quantity']
                                        else:
                                            sokeo += int(x['quantity']/3)

                                        flagkemkeo = 1

                                    if count < 10:
                                        line_order = f"* {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                        line_order = line_order[:53]
                                        c.drawString(-32, y_value, line_order)
                                        y_value -= 10
                                    count += 1
                                    flag = 1

                        if flag == 0:
                            for x in order['real_items']:
                                if x["item_id_shopee"] == 0:
                                    if count < 10:
                                        line_order = f"* {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                        line_order = line_order[:53]
                                        c.drawString(-32, y_value, line_order)
                                        y_value -= 10
                                    count += 1
                            
                    else:
                        for x in order['real_items']:
                            if x['id'] in list_kemkeo:
                                if x['id'] not in [220497520,220497571]:
                                    sokeo += x['quantity']
                                else:
                                    sokeo += int(x['quantity']/3)
                                flagkemkeo = 1

                            if count < 10:
                                line_order = f"* {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                line_order = line_order[:53]
                                c.drawString(-32, y_value, line_order)
                                y_value -= 10
                            count += 1

                    if flagkemkeo == 1:
                        sokeo = int(sokeo)
                        y_value -= 10
                        c.setFont('UTM Avo Bold', 8)
                        c.setFillColor(colors.black)
                        c.rect(-32, y_value, 150, 14, stroke=1, fill=1)
                        c.setFillColor(colors.white)  # Đặt lại màu văn bản
                        y_value += 4
                        c.drawString(-32, y_value, f"  * TẶNG KÈM KEO /// SL: {sokeo} LỌ")

                    c.setFillColor(colors.black)  # Đặt lại màu văn bản
                    if flagkemkeo == 1:
                        y_value -= 20
                    else:
                        y_value -= 5
                    c.setFont('UTM Avo Bold', 10)

                    max_length = 28  # Chiều dài tối đa cho mỗi dòng
                    note = "*** LƯU Ý: "+ order["note"]

                    if order["note"] and order["note"] != "" and PACK_1==0:
                        PACK_1 = 1
                        note = note.strip()  # Loại bỏ các khoảng trắng đầu và cuối
                        while note:
                            if len(note) > max_length:
                                c.drawString(-32, y_value, f"{note[:max_length]}")
                                note = note[max_length:]
                            else:
                                c.drawString(-32, y_value, f"{note}")
                                note = ""
                            y_value -= 12  # Điều chỉnh khoảng cách dòng tùy theo yêu cầu của bạn
                            
                    c.setFont('UTM Avo Bold', 20)
                    if DON_TACH_FLAG > 1:
                        c.drawString(10, 62, f"- Đ.TÁCH {PACKEDD['parcel_no']} -")
                    else:
                        c.drawString(25, 62, f"- {int(order['total_quantity'])} -")

                    c.setFont('UTM Avo Bold', 10)
                    c.drawString(10, -16, f"Anh/chị {order['shipping_address']['full_name']} ơi <3")

                    if FLAGSHIP == 1:
                        SHIP_CONTENT = f"GẤP >> HÔM NAY: {SHIP_DAY}"
                    else:
                        SHIP_CONTENT = f"GỬI TRƯỚC NGÀY: {SHIP_DAY}"

                    c.setFont('UTM Avo Bold', 9)
                    c.drawString(-5, 50, SHIP_CONTENT)

                    c.save()
                    mavandon = PyPDF2.PdfReader('logs/MVD.pdf')

                elif "Giao Hàng Nhanh" in tmdt_order['shipping_carrier_name']:
                    print("[+] Ben van chuyen: Giao Hang Nhanh")
                    watermark = PyPDF2.PdfReader(f'{link_to_cover}ghn-cover.pdf')
                    c = canvas.Canvas("logs/MVD.pdf")
                    c.setPageSize((4.1*inch, 5.8*inch))
                    c.translate(inch, inch)
                    c.rotate(90)
                    c.setFont('UTM Avo Bold', 33)
                    c.drawString(-45, 42, str(tmdt_order['channel_order_number']))
                    
                    c.rotate(270)
                    c.setFont('UTM Avo', 8)
                    y_value = 185
                    
                    count_line = 0
                    for x in order['real_items']:
                        count_line += 1

                    line_spacing = 12 if count_line > 6 else int(60 / max(1, count_line))
                    if line_spacing < 11:
                        line_spacing = 10
                    if line_spacing > 30:
                        line_spacing = 20

                    chuthich = []
                    count = 0
                    sokeo = 0

                    if DON_TACH_FLAG > 1:
                        flag = 0
                        for s_item in PACKEDD["items"]:
                            for x in order['real_items']:
                                if str(x["item_id_shopee"]) == str(s_item["model_id"]):
                                    if x['id'] in list_kemkeo:
                                        if x['id'] not in [220497520,220497571]:
                                            sokeo += x['quantity']
                                        else:
                                            sokeo += int(x['quantity']/3)

                                        flagkemkeo = 1

                                    if count < 10:
                                        line_order = f"** {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                        line_order = line_order[:53]
                                        c.setFont('Arial', 8)
                                        c.drawString(-32, y_value, line_order)
                                        # In tên của sản phẩm
                                        if count_line <= 6:
                                            y_value -= 10
                                            c.setFont('ArialI', 7)
                                            c.drawString(-32, y_value, x['pr_name'])
                                        y_value -= line_spacing

                                    count += 1
                                    flag = 1

                        # Sản phẩm chưa có trong danh mục.
                        if flag == 0:
                            for x in order['real_items']:
                                if x["item_id_shopee"] == 0:
                                    if count < 10:
                                        line_order = f"* {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                        line_order = line_order[:53]
                                        c.setFont('Arial', 8)
                                        c.drawString(-32, y_value, line_order)
                                        y_value -= line_spacing  
                                    count += 1
                            
                    else:
                        for x in order['real_items']:
                            if x['id'] in list_kemkeo:
                                if x['id'] not in [220497520,220497571]:
                                    sokeo += x['quantity']
                                else:
                                    sokeo += int(x['quantity']/3)
                                flagkemkeo = 1

                            if count < 10:
                                line_order = f"** {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                line_order = line_order[:53]
                                c.setFont('Arial', 8)
                                c.drawString(-32, y_value, line_order)
                                
                                # In tên của sản phẩm
                                if count_line <= 5:
                                    y_value -= 10
                                    c.setFont('ArialI', 7)
                                    c.drawString(-32, y_value, x['pr_name'])

                                y_value -= line_spacing
                            count += 1

                    if count > 10:
                        c.setFont('UTM Avo Bold', 8)
                        c.drawString(-32, y_value, "** ĐƠN DÀI - QUÉT SAPO để xem thêm.")
                        y_value -= 10


                    if flagkemkeo == 1:
                        sokeo = int(sokeo)
                        y_value -= 10
                        c.setFont('UTM Avo Bold', 8)
                        c.setFillColor(colors.black)
                        c.rect(-32, y_value, 150, 14, stroke=1, fill=1)
                        c.setFillColor(colors.white)  # Đặt lại màu văn bản
                        y_value += 4
                        c.drawString(-32, y_value, f"  * TẶNG KÈM KEO /// SL: {sokeo} LỌ")

                    c.setFillColor(colors.black)  # Đặt lại màu văn bản
                    if order["note"] and order["note"] != "" and PACK_1==0:
                        
                        if flagkemkeo == 1:
                            y_value -= 20
                        else:
                            y_value -= 5
                        c.setFont('UTM Avo Bold', 9)

                        max_length = 28  # Chiều dài tối đa cho mỗi dòng
                        note = "*** LƯU Ý: "+ order["note"]

                        PACK_1 = 1
                        note = note.strip()  # Loại bỏ các khoảng trắng đầu và cuối
                        
                        while note:
                            if len(note) > max_length:
                                c.drawString(-32, y_value, f"{note[:max_length]}")
                                note = note[max_length:]
                            else:
                                c.drawString(-32, y_value, f"{note}")
                                note = ""
                            y_value -= 12  # Điều chỉnh khoảng cách dòng tùy theo yêu cầu của bạn

                    c.setFont('UTM Avo Bold', 15)
                    if DON_TACH_FLAG > 1:
                        c.drawString(-25, 15, f"- Tách đơn: {PACKEDD['parcel_no']}/{DON_TACH_FLAG} -")
                    else:
                        c.drawString(0, 15, f"- Tổng: {int(order['total_quantity'])} -")
                    
                    if order["location_id"] == 241737:
                        c.setFont('UTM Avo', 8)
                        c.drawString(-35, 265, f"C21-02 Geleximco,Dương Nội")
                        c.drawString(-35, 255, f"Hà Đông, Hà Nội")
                        c.setFont('UTM Avo Bold', 10)
                        c.drawString(-35, 230, f"KHO HÀ NỘI: GELE")

                    else:
                        c.setFont('UTM Avo', 8)
                        c.drawString(-35, 265, f"B76a Tô Ký, Quận 12")
                        c.drawString(-35, 230, f"Thành phố Hồ Chí Minh")

                        c.setFont('UTM Avo Bold', 10)
                        c.drawString(-35, 213, f"KHO SÀI GÒN: TOKY")

                    if FLAGSHIP == 1:
                        SHIP_CONTENT = f"GẤP >> HÔM NAY: {SHIP_DAY}"
                    else:
                        SHIP_CONTENT = f"GỬI TRƯỚC NGÀY: {SHIP_DAY}"

                    c.setFillColorRGB(1, 1, 1)
                    c.setFont('UTM Avo Bold', 9)
                    c.drawString(87, 228, SHIP_CONTENT)

                    c.save()
                    mavandon = PyPDF2.PdfReader('logs/MVD.pdf')

                elif "GrabExpress" in tmdt_order['shipping_carrier_name'] or "beDelivery" in tmdt_order['shipping_carrier_name'] or "AhaMove" in tmdt_order['shipping_carrier_name'] or "Instant" in tmdt_order['shipping_carrier_name']:
                    print("[+] Ben van chuyen: HOA TOC")
                    watermark = PyPDF2.PdfReader(f'{link_to_cover}hoatoc.pdf')
                
                    c = canvas.Canvas("logs/MVD.pdf")
                    c.setPageSize((4.1*inch, 5.8*inch))
                    c.translate(inch, inch)
                    c.setFont('UTM Avo', 8)
                    y_value = 170
                    count_line = 0
                    for x in order['real_items']:
                        count_line += 1

                    line_spacing = 12 if count_line > 6 else int(60 / max(1, count_line))
                    if line_spacing < 11:
                        line_spacing = 10
                    if line_spacing > 30:
                        line_spacing = 20

                    chuthich = []
                    count = 0
                    sokeo = 0
                    
                    if DON_TACH_FLAG > 1:
                        flag = 0
                        for s_item in PACKEDD["items"]:
                            for x in order['real_items']:
                                if str(x["item_id_shopee"]) == str(s_item["model_id"]):
                                    if x['id'] in list_kemkeo:
                                        if x['id'] not in [220497520,220497571]:
                                            sokeo += x['quantity']
                                        else:
                                            sokeo += int(x['quantity']/3)

                                        flagkemkeo = 1

                                    if count < 10:
                                        line_order = f"** {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                        line_order = line_order[:53]
                                        c.setFont('Arial', 8)
                                        c.drawString(-32, y_value, line_order)
                                        # In tên của sản phẩm
                                        if count_line <= 6:
                                            y_value -= 10
                                            c.setFont('ArialI', 7)
                                            c.drawString(-32, y_value, x['pr_name'])
                                        y_value -= line_spacing

                                    count += 1
                                    flag = 1

                        # Sản phẩm chưa có trong danh mục.
                        if flag == 0:
                            for x in order['real_items']:
                                if x["item_id_shopee"] == 0:
                                    if count < 10:
                                        line_order = f"* {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                        line_order = line_order[:53]
                                        c.setFont('Arial', 8)
                                        c.drawString(-32, y_value, line_order)
                                        y_value -= line_spacing  
                                    count += 1
                            
                    else:
                        for x in order['real_items']:
                            if x['id'] in list_kemkeo:
                                if x['id'] not in [220497520,220497571]:
                                    sokeo += x['quantity']
                                else:
                                    sokeo += int(x['quantity']/3)
                                flagkemkeo = 1

                            if count < 10:
                                line_order = f"** {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                line_order = line_order[:53]
                                c.setFont('Arial', 8)
                                c.drawString(-32, y_value, line_order)
                                
                                # In tên của sản phẩm
                                if count_line <= 5:
                                    y_value -= 10
                                    c.setFont('ArialI', 7)
                                    c.drawString(-32, y_value, x['pr_name'])

                                y_value -= line_spacing
                            count += 1

                    if count > 10:
                        c.setFont('UTM Avo Bold', 8)
                        c.drawString(-32, y_value, "** ĐƠN DÀI - QUÉT SAPO để xem thêm.")
                        y_value -= 10


                    if flagkemkeo == 1:
                        sokeo = int(sokeo)
                        y_value -= 10
                        c.setFont('UTM Avo Bold', 8)
                        c.setFillColor(colors.black)
                        c.rect(-32, y_value, 150, 14, stroke=1, fill=1)
                        c.setFillColor(colors.white)  # Đặt lại màu văn bản
                        y_value += 4
                        c.drawString(-32, y_value, f"  * TẶNG KÈM KEO /// SL: {sokeo} LỌ")

                    c.setFillColor(colors.black)  # Đặt lại màu văn bản
                    if order["note"] and order["note"] != "" and PACK_1==0:
                        
                        if flagkemkeo == 1:
                            y_value -= 20
                        else:
                            y_value -= 5
                        c.setFont('UTM Avo Bold', 9)

                        max_length = 28  # Chiều dài tối đa cho mỗi dòng
                        note = "*** LƯU Ý: "+ order["note"]

                        PACK_1 = 1
                        note = note.strip()  # Loại bỏ các khoảng trắng đầu và cuối
                        
                        while note:
                            if len(note) > max_length:
                                c.drawString(-32, y_value, f"{note[:max_length]}")
                                note = note[max_length:]
                            else:
                                c.drawString(-32, y_value, f"{note}")
                                note = ""
                            y_value -= 12  # Điều chỉnh khoảng cách dòng tùy theo yêu cầu của bạn
                    

                    c.setFont('UTM Avo Bold', 15)
                    if DON_TACH_FLAG > 1:
                        c.drawString(-25, 15, f"- Tách đơn: {PACKEDD['parcel_no']}/{DON_TACH_FLAG} -")
                    else:
                        c.drawString(0, 15, f"- Tổng: {int(order['total_quantity'])} -")

                    c.save()
                    mavandon = PyPDF2.PdfReader('logs/MVD.pdf')


                else:
                    print("[+] Ben van chuyen: Khac")
                    watermark = PyPDF2.PdfReader(f'{link_to_cover}khac.pdf')
                
                    c = canvas.Canvas("logs/MVD.pdf")
                    c.setPageSize((4.1*inch, 5.8*inch))
                    c.translate(inch, inch)
                    c.setFont('UTM Avo', 8)
                    y_value = 170
                    count_line = 0
                    for x in order['real_items']:
                        count_line += 1

                    line_spacing = 12 if count_line > 6 else int(60 / max(1, count_line))
                    if line_spacing < 11:
                        line_spacing = 10
                    if line_spacing > 30:
                        line_spacing = 20

                    chuthich = []
                    count = 0
                    sokeo = 0
                    
                    if DON_TACH_FLAG > 1:
                        flag = 0
                        for s_item in PACKEDD["items"]:
                            for x in order['real_items']:
                                if str(x["item_id_shopee"]) == str(s_item["model_id"]):
                                    if x['id'] in list_kemkeo:
                                        if x['id'] not in [220497520,220497571]:
                                            sokeo += x['quantity']
                                        else:
                                            sokeo += int(x['quantity']/3)

                                        flagkemkeo = 1

                                    if count < 10:
                                        line_order = f"** {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                        line_order = line_order[:53]
                                        c.setFont('Arial', 8)
                                        c.drawString(-32, y_value, line_order)
                                        # In tên của sản phẩm
                                        if count_line <= 6:
                                            y_value -= 10
                                            c.setFont('ArialI', 7)
                                            c.drawString(-32, y_value, x['pr_name'])
                                        y_value -= line_spacing

                                    count += 1
                                    flag = 1

                        # Sản phẩm chưa có trong danh mục.
                        if flag == 0:
                            for x in order['real_items']:
                                if x["item_id_shopee"] == 0:
                                    if count < 10:
                                        line_order = f"* {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                        line_order = line_order[:53]
                                        c.setFont('Arial', 8)
                                        c.drawString(-32, y_value, line_order)
                                        y_value -= line_spacing  
                                    count += 1
                            
                    else:
                        for x in order['real_items']:
                            if x['id'] in list_kemkeo:
                                if x['id'] not in [220497520,220497571]:
                                    sokeo += x['quantity']
                                else:
                                    sokeo += int(x['quantity']/3)
                                flagkemkeo = 1

                            if count < 10:
                                line_order = f"** {int(x['quantity'])} cái - {x['sku']} - {x['variant_options']}"
                                line_order = line_order[:53]
                                c.setFont('Arial', 8)
                                c.drawString(-32, y_value, line_order)
                                
                                # In tên của sản phẩm
                                if count_line <= 5:
                                    y_value -= 10
                                    c.setFont('ArialI', 7)
                                    c.drawString(-32, y_value, x['pr_name'])

                                y_value -= line_spacing
                            count += 1

                    if count > 10:
                        c.setFont('UTM Avo Bold', 8)
                        c.drawString(-32, y_value, "** ĐƠN DÀI - QUÉT SAPO để xem thêm.")
                        y_value -= 10


                    if flagkemkeo == 1:
                        sokeo = int(sokeo)
                        y_value -= 10
                        c.setFont('UTM Avo Bold', 8)
                        c.setFillColor(colors.black)
                        c.rect(-32, y_value, 150, 14, stroke=1, fill=1)
                        c.setFillColor(colors.white)  # Đặt lại màu văn bản
                        y_value += 4
                        c.drawString(-32, y_value, f"  * TẶNG KÈM KEO /// SL: {sokeo} LỌ")

                    c.setFillColor(colors.black)  # Đặt lại màu văn bản
                    if order["note"] and order["note"] != "" and PACK_1==0:
                        y_value -= 5
                        c.setFont('UTM Avo Bold', 9)

                        max_length = 28  # Chiều dài tối đa cho mỗi dòng
                        note = "*** LƯU Ý: "+ order["note"]

                        PACK_1 = 1
                        note = note.strip()  # Loại bỏ các khoảng trắng đầu và cuối

                        while note:
                            if len(note) > max_length:
                                c.drawString(-32, y_value, f"{note[:max_length]}")
                                note = note[max_length:]
                            else:
                                c.drawString(-32, y_value, f"{note}")
                                note = ""
                            y_value -= 12  # Điều chỉnh khoảng cách dòng tùy theo yêu cầu của bạn
                    
                    c.setFont('UTM Avo Bold', 15)
                    if DON_TACH_FLAG > 1:
                        c.drawString(-25, 15, f"- Tách đơn: {PACKEDD['parcel_no']}/{DON_TACH_FLAG} -")
                    else:
                        c.drawString(0, 15, f"- Tổng: {int(order['total_quantity'])} -")

                    c.save()
                    mavandon = PyPDF2.PdfReader('logs/MVD.pdf')


                watermark_page = watermark.pages[0]
                for page in range(len(xpdfReader.pages)):
                    pdf_page = xpdfReader.pages[page]
                    pdf_page.merge_page(watermark_page)

                watermark_page = mavandon.pages[0]
                for page in range(len(xpdfReader.pages)):
                    pdf_page = xpdfReader.pages[page]
                    pdf_page.merge_page(watermark_page)
                    pdfWriter.add_page(pdf_page)

                newFile = open('logs/print.pdf', 'wb')
                pdfWriter.write(newFile)
                newFile.close()

                time.sleep(2)
                x = update_data_one(order['code'], {'dvvc': tmdt_order['shipping_carrier_name'],'shopee_id': SHOPEE_ID,'split':DON_TACH_FLAG, 'shipdate':SHIPBYDATE})
                if x == 0:
                    print("Rewrite 1!")
                    time.sleep(2)
                    x = update_data_one(order['code'], {'dvvc': tmdt_order['shipping_carrier_name'], 'shopee_id': SHOPEE_ID,'split':DON_TACH_FLAG, 'shipdate':SHIPBYDATE})
                if x == 0:
                    print("Rewrite 2!")
                    time.sleep(2)
                    x = update_data_one(order['code'], {'dvvc': tmdt_order['shipping_carrier_name'], 'shopee_id': SHOPEE_ID,'split':DON_TACH_FLAG, 'shipdate':SHIPBYDATE})
                if x == 0:
                    print("Rewrite 3!")
                    time.sleep(2)
                    x = update_data_one(order['code'], {'dvvc': tmdt_order['shipping_carrier_name'], 'shopee_id': SHOPEE_ID,'split':DON_TACH_FLAG, 'shipdate':SHIPBYDATE})
                
                if x == 0:
                    tmdt_order = js_get_url(f"https://market-place.sapoapps.vn/v2/orders?page=1&limit=1&connectionIds=155938,155687,155174,134366,10925&query={order['reference_number']}")['orders'][0]
                    logintmdt.put(f"https://market-place.sapoapps.vn/v2/orders/sync?ids={tmdt_order['id']}&accountId=3199")
                    time.sleep(3)
                    x = update_data_one(order["code"],{'packing_status':order['packing_status']})
                    print("Rewrite put 1!") 
                if x == 0:
                    print("Rewrite put 2!")
                    time.sleep(3)
                    x = update_data_one(order['code'], {'dvvc': tmdt_order['shipping_carrier_name'], 'shopee_id': SHOPEE_ID,'split':DON_TACH_FLAG, 'shipdate':SHIPBYDATE})
                if x == 0:
                    tmdt_order = js_get_url(f"https://market-place.sapoapps.vn/v2/orders?page=1&limit=1&connectionIds=155938,155687,155174,134366,10925&query={order['reference_number']}")['orders'][0]
                    logintmdt.put(f"https://market-place.sapoapps.vn/v2/orders/sync?ids={tmdt_order['id']}&accountId=3199")
                    print("Rewrite put 3!")
                    time.sleep(5)
                    x = update_data_one(order['code'], {'dvvc': tmdt_order['shipping_carrier_name'], 'shopee_id': SHOPEE_ID,'split':DON_TACH_FLAG, 'shipdate':SHIPBYDATE})
                
                if x == 0:
                    tmdt_order = js_get_url(f"https://market-place.sapoapps.vn/v2/orders?page=1&limit=1&connectionIds=155938,155687,155174,134366,10925&query={order['reference_number']}")['orders'][0]
                    logintmdt.put(f"https://market-place.sapoapps.vn/v2/orders/sync?ids={tmdt_order['id']}&accountId=3199")
                    print("Rewrite put 4!")
                    time.sleep(5)
                    x = update_data_one(order['code'], {'dvvc': tmdt_order['shipping_carrier_name'], 'shopee_id': SHOPEE_ID,'split':DON_TACH_FLAG, 'shipdate':SHIPBYDATE})
                if x == 0:
                    print("ERROR PRINT WHEN UPDATE DATA!")
                else:
                    if prints == 'yes':
                        #mayin = readfile('logs/mayin.log')
                        #win32print.SetDefaultPrinter(mayin)
                        currentprinter = win32print.GetDefaultPrinter()
                        print(currentprinter)
                        x = win32api.ShellExecute(0, 'open', GSPRINT_PATH, '-ghostscript "'+GHOSTSCRIPT_PATH+'" -dFitPage -pMargins=0 -dHalftone=5 -r80 -dImageIntent=0 -dImageBlackPt=0 -printer "'+currentprinter+'" "logs/print.pdf"', '.', 0)
                        if x < 0:
                            time.sleep(1)
                            update_data_one(order['code'], {'dvvc': tmdt_order['shipping_carrier_name'], 'spid': SHOPEE_ID, 'shipdate':SHIPBYDATE})
                            return 1


        except Exception as e:
            print(f"Error print: {e}")
            return 0
    else:
        print("Error when doishop!")
        return 0

    

    return 1

def print_sapo(order_id):
    order = js_get_url(f"{MAIN_URL}/orders/{order_id}.json")["order"]
    flag = ""
    if "Shopee Xpress" in order["fulfillments"][-1]["shipment"]["service_name"]:
        flag = "Shopee"
    else:
        flag = "Khac"
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--kiosk-printing')
    chrome_options.add_argument('executable_path=chromedriver.exe')

    if flag == "Khac":
        try:
            
            DRIVER_CR = webdriver.Chrome(options=chrome_options)
            DRIVER_CR.get(f"https://127.0.0.1:8000/quantri/kho_indonsapo?order_id={order_id}")
            # Định nghĩa cấu hình in (khổ giấy, lề, đầu trang/chân trang)
            print_options = {
                'paperWidth': 4.13,  # Khổ giấy A6 có chiều rộng 4.13 inch
                'paperHeight': 5.83,  # Khổ giấy A6 có chiều cao 5.83 inch
                'marginTop': 0,  # Lề trên 0
                'marginBottom': 0,  # Lề dưới 0
                'marginLeft': 0,  # Lề trái 0
                'marginRight': 0,  # Lề phải 0
                'printBackground': True,  # In cả phần nền (nếu có)
                'displayHeaderFooter': False  # Tắt hiển thị đầu trang và chân trang
            }

            # Sử dụng DevTools Protocol để tùy chỉnh in
            driver = DRIVER_CR.execute_cdp_cmd('Page.printToPDF', print_options)

            # Gọi lệnh in
            DRIVER_CR.execute_script('window.print();')

            time.sleep(2)
            DRIVER_CR.quit()
        except Exception as e:
            print(f"An error occurred: {e}")

    if flag == "Shopee":
        json_post = {"shopee_xpress_lable_request": {"setracking_nos": [order['fulfillments'][-1]['shipment']['tracking_code']], "mktracking_nos": []}}

        file_print = loginss.post("https://sisapsan.mysapogo.com/admin/shipping_services/shopee_xpress/batch_get_shipping_label.json", json=json_post)

        if len(file_print.text) > 5000:
            base64_pdf = json.loads(file_print.text)["awb_link"]

            pdf_file_path = "assets/temp_print_spx.pdf"
            # Giải mã Base64 và lưu vào file
            with open(pdf_file_path, "wb") as pdf_file:
                pdf_file.write(base64.b64decode(base64_pdf))

            # Tạo WebDriver
            DRIVER_CR = webdriver.Chrome(options=chrome_options)

            try:
                # Mở file PDF bằng URL file://
                DRIVER_CR.get(f"https://127.0.0.1:8000/static/temp_print_spx.pdf")

                # Định nghĩa cấu hình in (khổ giấy, lề, đầu trang/chân trang)
                print_options = {
                    'paperWidth': 4.13,  # Khổ giấy A6 có chiều rộng 4.13 inch
                    'paperHeight': 5.83,  # Khổ giấy A6 có chiều cao 5.83 inch
                    'marginTop': 0,  # Lề trên 0
                    'marginBottom': 0,  # Lề dưới 0
                    'marginLeft': 0,  # Lề trái 0
                    'marginRight': 0,  # Lề phải 0
                    'printBackground': True,  # In cả phần nền (nếu có)
                    'displayHeaderFooter': False  # Tắt hiển thị đầu trang và chân trang
                }

                # Sử dụng DevTools Protocol để tùy chỉnh in
                driver = DRIVER_CR.execute_cdp_cmd('Page.printToPDF', print_options)


                # Gửi lệnh in (Ctrl+P)
                DRIVER_CR.execute_script('window.print();')
                time.sleep(2)

            finally:
                # Đóng trình duyệt
                DRIVER_CR.quit()

def generate_code_verifier(length: int = 128) -> str:
    if not 43 <= length <= 128:
        msg = 'Parameter `length` must verify `43 <= length <= 128`.'
        raise ValueError(msg)
    code_verifier = secrets.token_urlsafe(96)[:length]
    return code_verifier

def generate_pkce_pair(code_verifier_length: int = 128) -> Tuple[str, str]:
    if not 43 <= code_verifier_length <= 128:
        msg = 'Parameter `code_verifier_length` must verify '
        msg += '`43 <= code_verifier_length <= 128`.'
        raise ValueError(msg)
    code_verifier = generate_code_verifier(code_verifier_length)
    code_challenge = get_code_challenge(code_verifier)
    return code_verifier, code_challenge

def get_code_challenge(code_verifier: str) -> str:
    if not 43 <= len(code_verifier) <= 128:
        msg = 'Parameter `code_verifier` must verify '
        msg += '`43 <= len(code_verifier) <= 128`.'
        raise ValueError(msg)
    hashed = hashlib.sha256(code_verifier.encode('ascii')).digest()
    encoded = base64.urlsafe_b64encode(hashed)
    code_challenge = encoded.decode('ascii')[:-1]
    return code_challenge

def send_zns_xacnhan(template_id, order, mode):
    print("Send zns!")
    ZALO_LOGIN = requests.session()

    # TEST MODE
    if mode == 1:
        #GET ACCESS TOKEN 
        code = "oJD6hfR1NZNc2ZQr_vKGAQK0886_h3WBwW1MYPgu3NpzUGFJkxyVS9eX1FNvZ3PSw2eImfEoUd3pFXQ6dF0VATqxSxtwdLo1l0fiDAshSQJt2WOIaz5xnD5hB2RDz1ppocSTVxZJIutr8Wr4wfOQbPeJTtdrts_1a3C5GOErKilb07CHjkKsoeqK3GIqr7_ps1HfM9l77QVxDIXMvOK9eQzxHJ-4Yd_HknS2K8oILQMSJZWZXSOttVSFCnMr_7lPiCWGNE5SFvwEwwqEoI71ZD2-smMmOikUfzVt8Sj7ZgVR_zDjf0_eWFWiqHJMYlxlZJ_kTAwgn-kJVibDXkx6ger7fnIjdhA8oX7DPTZQxxlV7UDHNbacYfJUIfs96sm"
        code_verifier = generate_code_verifier(length=43)
        code_challenge = get_code_challenge(code_verifier)
        oa_id=1611688979718320843
        ZALO_LOGIN.headers.update({'secret_key': 'Ip67F3Sml77A1bDIKXjn'})
        mdata = {
            'code': code,
            'app_id': 1883883921644192603,
            'grant_type': 'authorization_code',
            'code_verifier': code_verifier,
        }
        URL = 'https://oauth.zaloapp.com/v4/oa/access_token'
        RS = json.loads(ZALO_LOGIN.post(URL,data=mdata).text)
        print(RS)
        if 'access_token' in RS:
            writejsonfile(RS,'logs/zalo_token.txt') 
        ZALO_TOKEN = json.loads(readfile('logs/zalo_token.txt'))
        TOKEN = ZALO_TOKEN['access_token']
        ZALO_LOGIN.headers.update({'access_token': TOKEN})
        ZALO_LOGIN.headers.update({'Content-Type': 'application/json'})
        URL = "https://business.openapi.zalo.me/message/template"
        ZNS_TEMP = {
                "mode": "development",
                "phone": '+84988700162',
                "template_id": template_id,
                "template_data": {
                    "total": order['total'],
                    "kho": "Hà Đông, Hà Nội",
                    "code": order['code'],
                    "channel": "Shopee",
                    "name": order["customer_data"]["name"],
                    "ship_day": "1-2",
                },
                "tracking_id":"tracking_id"
        }
        result = ZALO_LOGIN.post(URL, json=ZNS_TEMP).text

    else:
        NHOM_3 =  "Bình Phước, Bình Dương, Đồng Nai,Long An, Đồng Tháp, Tiền Giang, An Giang, Bến Tre, Vĩnh Long, Trà Vinh, Hậu Giang, Kiên Giang, Sóc Trăng, Bạc Liêu, Cà Mau và Thành phố Cần Thơ,  Kon Tum, Gia Lai, Đắk Lắk, Đắk Nông và Lâm Đồng, Bình Định, Phú Yên, Khánh Hòa, Ninh Thuận và Bình Thuận"
        NHOM_2 = "TP Hồ Chí Minh,Tây Ninh, Bà Rịa Vũng Tàu,Bà Rịa-Vũng Tàu, Thanh Hóa, Nghệ An, Hà Tĩnh, Quảng Bình, Quảng Trị và Thừa Thiên Huế, Đà Nẵng, Quảng Nam, Quảng Ngãi,"
        NHOM_1 = "Hà Nội, Hải Phòng, Tỉnh Lào Cai, Yên Bái, Điện Biên, Hòa Bình, Lai Châu, Sơn La; Tỉnh Hà Giang, Cao Bằng, Bắc Kạn, Lạng Sơn, Tuyên Quang, Thái Nguyên, Phú Thọ, Bắc Giang, Quảng Ninh; Tỉnh Bắc Ninh, Hà Nam, Hải Dương,, Hưng Yên, Nam Định, Ninh Bình, Thái Bình, Vĩnh Phúc."

        ZALO_LOGIN = requests.Session()
        ZALO_TOKEN = json.loads(readfile('logs/zalo_token.txt'))
        TOKEN = ZALO_TOKEN['access_token']
        ZALO_LOGIN.headers.update({'access_token': TOKEN})
        ZALO_LOGIN.headers.update({'Content-Type': 'application/json'})
        URL = "https://business.openapi.zalo.me/message/template"

        if "*" not in str(order['phone_number']) and order['phone_number'] != None:
            # Đơn Shopee
            if order["source_id"] in [1880152,1880150,1880149,6510687] and order['channel'] != None and order['reference_number'] != None:
                orders = js_get_url(f"https://market-place.sapoapps.vn/v2/orders?page=1&limit=20&connectionIds=155938,155687,155174,134366,10925&query={order['reference_number']}&sortBy=ISSUED_AT&orderBy=desc")
                if len(orders) > 100:
                    if orders['metadata']['total'] > 0:
                        order['total'] = orders['orders'][0]['total_amount']

            if order['phone_number'].startswith("0"):
                order['phone_number'] = "84" + order['phone_number'][1:]

            if order['source_id'] in [1880152,1880150,1880149,6510687] and order['channel'] != None and order['reference_number'] != None:
                order_code = order['reference_number']
            else:
                order_code = order['code']

            order_sources = js_get_url(f"{MAIN_URL}/order_sources.json?page=1&limit=100")["order_sources"]
            for source in order_sources:
                if source['id'] == order['source_id']:
                    order['source_name'] = source['name']
                    break

            shipping_date = "3-5"
            if order['location_id'] == 241737:
                # Kho Hà Nội
                kho_gui = "Geleximco, Hà Nội"

                if order['shipping_address'] != None:
                    if order['shipping_address']['city'] in NHOM_1:
                        shipping_date = "1-2"
                    elif order['shipping_address']['city'] in NHOM_2:
                        shipping_date = "3-5"
                    elif order['shipping_address']['city'] in NHOM_3:
                        shipping_date = "4-6"   


            elif order['location_id'] == 548744:
                # Kho Sài Gòn
                kho_gui = "Tô Ký, Hồ Chí Minh"
                if order['shipping_address'] != None:
                    if order['shipping_address']['city'] in NHOM_1:
                        shipping_date = "4-6"
                    elif order['shipping_address']['city'] in NHOM_2:
                        shipping_date = "3-5"
                    elif order['shipping_address']['city'] in NHOM_3:
                        shipping_date = "1-2"
            
            
            ZNS_TEMP = {
                "phone": order['phone_number'],
                "template_id": template_id,
                "template_data": {
                    "total": order['total'],
                    "kho": kho_gui,
                    "code": order_code,
                    "channel": order['source_name'],
                    "name": order["customer_data"]["name"],
                    "ship_day": shipping_date,
                },
                "tracking_id":"tracking_id"
            }
            result = ZALO_LOGIN.post(URL, json=ZNS_TEMP).text
            if "-124" in result:
                print("Lấy lại token!")
                # Lấy lại access token từ refresh token
                RS_TOKEN = ZALO_TOKEN['refresh_token']
                ZALO_LOGIN.headers.update({'secret_key': 'Ip67F3Sml77A1bDIKXjn'})
                ZALO_LOGIN.headers.update({'Content-Type': 'application/x-www-form-urlencoded'})
                mdata = {
                    'app_id': 1883883921644192603,
                    'grant_type': 'refresh_token',
                    'refresh_token': RS_TOKEN
                }
                URL = 'https://oauth.zaloapp.com/v4/oa/access_token'
                RS = json.loads(ZALO_LOGIN.post(URL,data=mdata).text)
                if 'access_token' in RS:
                    writejsonfile(RS,'logs/zalo_token.txt')
            else:
                Order_Packing.objects.using("packing").filter(id=order['id']).update(send_zns=1)


def check_login_sapo():
    order = loginss.get('https://sisapsan.mysapogo.com/admin/orders/522971327.json')

    if '84976613760' not in order.text:
        print("Relogin!")
        url = 'https://sisapsan.mysapogo.com/admin/login/authorization/login'
        json_all = {"a":1}
        r = loginss.get(url)
        sessionCookies = r.cookies
        tree = html.fromstring(r.text)
        input1 = {
            '_csrf': tree.xpath("/html/body/div[2]/div/div[6]/form/input/@value")[0],
            'clientId': tree.xpath('//*[@id="client-id"]/@value')[0],
            'LoginToken': '', 
            'relativeContextPath': '/admin',
            'countryCode': 84,
            'Product': 'pos',
            'domain': 'sisapsan',
            'suffix-domain': 'mysapogo.com',
            'phoneNumber': '0988700162',
            'password': '123122aC@',
            'g-recaptcha-response':'', 
            'isFixedDomain': False
        }
        r = loginss.post('https://accounts.sapo.vn/login',data=input1,headers={'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9','Accept-Encoding':'gzip, deflate, br'},cookies=sessionCookies)

    return 1


def get_cookie_tmdt(json_order):
    USERNAME = 'vuongdn@giadungplus.com'
    PASSWORD = 'yeuMai1@'
    LOGIN_USERNAME_FIELD = '//*[@id="login"]'
    LOGIN_PASSWORD_FIELD = '//*[@id="Password"]'
    LOGIN_BUTTON = '/html/body/div[1]/div/div/div/div/div/div/form/div[5]/button'

    if "orders" not in json_order:
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('executable_path=chromedriver.exe')

        DRIVER_CR = webdriver.Chrome(options=chrome_options)
        DRIVER_CR.get(f"{MAIN_URL}/authorization/login")
        login = WebDriverWait(DRIVER_CR, 0.5).until(
                EC.presence_of_element_located((By.XPATH, LOGIN_USERNAME_FIELD))
        )
        password = WebDriverWait(DRIVER_CR, 0.5).until(
                EC.presence_of_element_located((By.XPATH, LOGIN_PASSWORD_FIELD))
        )
        login_button = WebDriverWait(DRIVER_CR, 0.5).until(
                EC.presence_of_element_located((By.XPATH, LOGIN_BUTTON))
        )
        login.send_keys(USERNAME)
        password.send_keys(PASSWORD)
        login_button.click()

        DRIVER_CR.get(f"{MAIN_URL}/apps/market-place/home/overview")
        time.sleep(10)
        for request in DRIVER_CR.requests:
            if request.url == "https://market-place.sapoapps.vn/api/staffs/677448/scopes":
                loginss.headers.update({'x-market-token': request.headers['x-market-token']})
                loginss.headers.update({'authorization': request.headers['x-market-token']})
                loginss.headers.update({'x-market-account-id': request.headers['x-market-account-id']})

                writefile(request.headers['x-market-token'], 'logs/loginss_token.txt')
                writefile(request.headers['x-market-account-id'], 'logs/loginss2_token.txt')
        
        DRIVER_CR.quit()

def get_list_process():
    list_source = {}
    url_search = 'https://sisapsan.mysapogo.com/admin/statuses.json?limit=250'
    json_load = json.loads(loginss.get(url_search).text)['status_list']
    for sr in json_load:
        list_source[str(sr['id'])] = sr['name']
    
    return list_source

def real_time_report(report_all,start_time,end_time,array_sanpham_ds, array_sanpham_sl, list_nhan_vien,list_gia_von,array_donhang,list_time):

    url = "https://banhang.shopee.vn/api/report/miscellaneous/upload_router_info?SPC_CDS=8aef6607-03a6-48da-9c65-d3751f82533f&SPC_CDS_VER=2"
    data_route = '{"route_pattern":"/^\\/portal\\/sale\\/order(?:\\/(?=$))?$/i","region":"vn","is_cn":false,"nav_type":2}'
    loginsp.post(url,data=data_route)

    END_TIME_REAL = end_time - datetime.timedelta(days=1)
    END_TIME_0 = end_time

    CUNG_KI = (start_time - end_time).days
    if CUNG_KI == 0:
        CUNG_KI = 1
    END_CUNG_KI = END_TIME_REAL - datetime.timedelta(days=CUNG_KI)

    START_TIME_STR = start_time.strftime("%Y-%m-%d")
    END_TIME_STR = END_TIME_REAL.strftime("%Y-%m-%d")
    END_TIME_0_STR = END_TIME_0.strftime("%Y-%m-%d")
    END_CUNG_KI_STR = END_CUNG_KI.strftime("%Y-%m-%d")
    END_TIME = end_time.strftime("%Y-%m-%d")\

    print(f"Ads tinh tu {START_TIME_STR} den {END_TIME_0_STR}")

    now_time = datetime.datetime.now() - datetime.timedelta(days=1)
    now_time = now_time - datetime.timedelta(hours=7)
    now_time = now_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    url_query = "https://sisapsan.mysapogo.com/admin/orders.json?created_on_max="+str(START_TIME_STR)+"T16%3A59%3A59Z&created_on_min="+str(END_TIME_STR)+"T17%3A00%3A00Z"
    url_search = url_query + "&page=1&litmit=1"
    json_order_list = json.loads(loginss.get(url_search).text)
    if json_order_list["metadata"]["total"] > 0:    
        ROUND = math.ceil(json_order_list["metadata"]["total"]/250)
        for i in range(ROUND):
            url_search = url_query + "&limit=250&page=" + str(i+1)
            json_order_list = json.loads(loginss.get(url_search).text)

            for order in json_order_list["orders"]:
                report_all["sum_all"]["doanh_so_ao"] += order["total"]
                report_all["sum_all"]["c_doanh_so_ao"] += 1

                if order["status"] == "cancelled":
                    report_all["sum_all"]["da_huy"] += order["total"]
                    report_all["sum_all"]["c_da_huy"] += 1
                else:
                    report_all["sum_all"]["doanh_so_thuc"] += order["total"]
                    report_all["sum_all"]["c_doanh_so_thuc"] += 1

                    if order['order_returns'] != None:
                        for xreturn in order['order_returns']:
                            report_all["sum_all"]["doanh_so_thuc"] -= int(xreturn['total_amount'])
                            report_all["sum_all"]["tra_hang"] += int(xreturn['total_amount'])
                            report_all["sum_all"]["c_tra_hang"] += 1

                    date_create = datetime.datetime.strptime(order["created_on"], "%Y-%m-%dT%H:%M:%SZ") + datetime.timedelta(hours=7)
                    order["hours"] = date_create.hour

                    if order["hours"] < 10:
                        order["hours"] = '0' + str(order["hours"])
                    list_time[str(order["hours"])] += order['total']
                    order["real_time_create"] = date_create.strftime("%Y-%m-%dT%H:%M:%SZ")

                    comback_time =     str(order["created_on"])[:17]+'01Z'

                    URL = "https://sisapsan.mysapogo.com/admin/orders.json?limit=2&composite_fulfillment_status=received%2Cfulfilled%2Cretry_delivery&created_on_max="+comback_time+"&customer_ids="+str(order['customer_id'])
                    comback = js_get_url(URL)
                    if 'metadata' in comback:
                        comback = comback['metadata']['total']
                        if comback > 0:
                            report_all['khach']['cu'] += order['total']
                            report_all['khach']['c_cu'] += 1
                            # Facebook
                            if order["source_id"] == 1880147:
                                report_all['facebook']['dt_comback'] += order['total']
                                report_all['facebook']['tl_comback'] += 1
                            # Shopee
                            elif order["source_id"] == 1880152:
                                report_all['shopee']['dt_comback'] += order['total']
                                report_all['shopee']['tl_comback'] += 1
                            #Lazada
                            elif order["source_id"] == 1880149 or order["source_id"] == 1880150:
                                report_all['lazada']['dt_comback'] += order['total']
                                report_all['lazada']['tl_comback'] += 1
                            #Zalo, Web
                            elif order["source_id"] == 1880148 or order["source_id"] == 1880146 or order["source_id"] == 5483992:
                                report_all['zalo']['dt_comback'] += order['total']
                                report_all['zalo']['tl_comback'] += 1
                        
                        else:
                            report_all['khach']['moi'] += order['total']
                            report_all['khach']['c_moi'] += 1
                    else:
                        print(URL)

                    if len(order['fulfillments']) > 0 and order['fulfillments'][-1]['status'] != "cancelled":
                        if order['fulfillments'][-1]["shipment"] != None:
                            if order["source_id"] == 1880147 or order["source_id"] == 1880148 or order["source_id"] == 1880146 or order["source_id"] == 5483992 or order["source_id"] == 1880147:
                                report_all["ship"]["ds_ship"] += int(order['total'])
                                report_all["ship"]["cp_ship"] += int(order['fulfillments'][-1]["shipment"]["freight_amount"])
                                report_all["ship"]["thu_khach"] += int(order['fulfillments'][-1]["shipment"]["delivery_fee"])

                    for nv in list_nhan_vien:
                        if nv["id"] == order["assignee_id"]:
                            nv["doanh_so"] += order["total"]
                            order['nhanvien'] = nv['full_name']

                    for vari in order["order_line_items"]:
                        if len(vari['sku']) > 0:
                            if str("b_"+vari['sku']) in list_gia_von:
                                report_all["sum_all"]["gia_von"] += list_gia_von["b_"+str(vari['sku'])] * vari['quantity']
                            else:
                                report_all["sum_all"]["gia_von"] += vari["line_amount"] * 0.6

                        report_all["sum_all"]["san_pham"] += int(vari["quantity"])

                        if str(vari["variant_id"]) in array_sanpham_ds:
                            array_sanpham_sl[str(vari["variant_id"])] += vari["quantity"]
                            array_sanpham_ds[str(vari["variant_id"])] += vari["line_amount"]
                        else:
                            array_sanpham_sl[str(vari["variant_id"])] = vari["quantity"]
                            array_sanpham_ds[str(vari["variant_id"])] = vari["line_amount"]                        

                        if order["source_id"] == 1880147:
                            if str("SI_"+str(vari["variant_id"])) in array_sanpham_sl:
                                array_sanpham_sl["SI_"+str(vari["variant_id"])] += vari["quantity"]
                            else:
                                array_sanpham_sl["SI_"+str(vari["variant_id"])] = vari["quantity"]
                        elif order["source_id"] == 1880147 or order["source_id"] == 1880148 or order["source_id"] == 1880146 or order["source_id"] == 1880151:
                            if str("FB_"+str(vari["variant_id"])) in array_sanpham_sl:
                                array_sanpham_sl["FB_"+str(vari["variant_id"])] += vari["quantity"]
                            else:
                                array_sanpham_sl["FB_"+str(vari["variant_id"])] = vari["quantity"]                            
                        elif order["source_id"] == 1880152:
                            if str("SP_"+str(vari["variant_id"])) in array_sanpham_sl:
                                array_sanpham_sl["SP_"+str(vari["variant_id"])] += vari["quantity"]
                            else:
                                array_sanpham_sl["SP_"+str(vari["variant_id"])] = vari["quantity"]                                                    
                        elif order["source_id"] == 1880149 or order["source_id"] == 1880150:
                            if str("LZ_"+str(vari["variant_id"])) in array_sanpham_sl:
                                array_sanpham_sl["LZ_"+str(vari["variant_id"])] += vari["quantity"]
                            else:
                                array_sanpham_sl["LZ_"+str(vari["variant_id"])] = vari["quantity"]                            
                    
                    # Facebook
                    if order["source_id"] == 1880147:
                        report_all["facebook"]["doanh_so"] += int(order["total"])
                        report_all["facebook"]["don_hang"] += 1
                        order['nguon'] = "Facebook"

                    # Shopee
                    elif order["source_id"] == 1880152:
                        order['nguon'] = "Shopee"
                        report_all["shopee"]["doanh_so"] += order["total"]
                        report_all["shopee"]["don_hang"] += 1
                        if len(order["tags"]) < 2:
                            report_all["shopee"]["official"] += order["total"]
                        elif "Shopee_Gia Dụng Plus Official" in order["tags"][1]:
                            report_all["shopee"]["official"] += order["total"]
                        elif "Shopee_Vimora.vn" in order["tags"][1]:
                            report_all["shopee"]["vimora"] += order["total"]
                        elif "Đồ Sứ" in order["tags"][1] or "HaoChi" in order["tags"][1]:
                            report_all["shopee"]["do_su"] += order["total"]
                        else:
                            report_all["shopee"]["mall"] += order["total"]


                        if order['total'] > 0 and order['total'] <= 150000:
                            report_all["shopee"]["m1"] += 1
                        elif order['total'] > 150000 and order['total'] <= 300000:
                            report_all["shopee"]["m2"] += 1
                        elif order['total'] > 300000 and order['total'] <= 500000:
                            report_all["shopee"]["m3"] += 1
                        elif order['total'] > 500000  and order['total'] <= 1000000:
                            report_all["shopee"]["m4"] += 1
                        else:
                            report_all["shopee"]["m5"] += 1

                        file_log = 'logs/log_shopee/'+str(order['id'])+'.log'
                        print(file_log)
                        if len(order["tags"]) >= 2 and "Shopee_Gia Dụng Plus Official" in order["tags"][1] and order['reference_url'] != None and order['channel']=="Sàn TMĐT - Shopee":
                            # Đã có order id
                            if os.path.exists(file_log) == False:
                                url = "https://banhang.shopee.vn/api/v3/order/search_order_hint?SPC_CDS=8aef6607-03a6-48da-9c65-d3751f82533f&SPC_CDS_VER=2&category=1&keyword="+str(order['reference_number'])
                                result = json.loads(loginsp.get(url).text)
                                order['shopee_id'] = result['data']['order_sn_result']['list'][0]['order_id']

                                shopee_info = {
                                    "order_id":0,
                                    "tien_ve":0,
                                    "phi_vc_thuc_te":0, #shipping_fee_paid_by_shopee_on_your_behalf 
                                    "phi_vc_tro_gia":0, #shipping_rebate_from_shopee
                                    "phi_vc_ng_mua_tra":0, #shipping_fee_paid_by_buyer
                                    "tro_gia_sp":0, #product_discount_rebate_from_shopee
                                    "tro_gia_voucher":0, #voucher_code
                                    "tro_gia_coin":0,    #seller_absorbed_coin_cash_back
                                    "tro_gia_cho_khach": 0 , #shopee_voucher
                                    "shipping_carrier": "", #shipping_carrier
                                    "shop_voucher": 0, #shipping_carrier
                                    "phi_tt":0,
                                    "phi_dv":0,
                                    "order_items": [],
                                    "discount_combo":0
                                }

                                url = "https://banhang.shopee.vn/api/v3/finance/income_transaction_history_detail/?SPC_CDS=8aef6607-03a6-48da-9c65-d3751f82533f&SPC_CDS_VER=2&order_id="+str(order['shopee_id'])
                                all_info_sp = json.loads(loginsp.get(url).text)['data']
                                
                                shopee_info['order_id'] = order['shopee_id']
                                shopee_info['tien_ve'] = int(all_info_sp['amount'])
                                shopee_info['phi_vc_ng_mua_tra'] =  int(all_info_sp['payment_info']['shipping_subtotal']['shipping_fee_paid_by_buyer'])
                                shopee_info['tro_gia_sp'] =  int(all_info_sp['payment_info']['rebate_and_voucher']['product_discount_rebate_from_shopee'])
                                shopee_info['tro_gia_voucher'] =  int(all_info_sp['payment_info']['rebate_and_voucher']['voucher_code'])
                                shopee_info['tro_gia_coin'] = int(all_info_sp['payment_info']['rebate_and_voucher']['seller_absorbed_coin_cash_back'])
                                shopee_info['tro_gia_cho_khach'] =  int(all_info_sp['buyer_payment_info']['shopee_voucher'])
                                shopee_info['shipping_carrier'] =  all_info_sp['shipping_carrier']

                                shopee_info['phi_tt'] =  int(abs(all_info_sp['payment_info']['fees_and_charges']['transaction_fee']))
                                shopee_info['phi_dv'] =  int(abs(all_info_sp['payment_info']['fees_and_charges']['service_fee']))
                                shopee_info['phi_all'] =  shopee_info['phi_tt'] + shopee_info['phi_dv']

                                url = 'https://banhang.shopee.vn/api/v3/order/get_package?SPC_CDS=8aef6607-03a6-48da-9c65-d3751f82533f&SPC_CDS_VER=2&order_id='+str(order['shopee_id'])
                                all_info_sp = json.loads(loginsp.get(url).text)['data']['order_info']
                                print(all_info_sp)
                                shopee_info['phi_vc_thuc_te'] =  int(all_info_sp['package_list'][0]['shipping_fee']/100000)
                                shopee_info['phi_vc_tro_gia'] =  int(all_info_sp['package_list'][0]['shipping_fee_discount']/100000)

                                url = 'https://banhang.shopee.vn/api/v3/finance/get_one_order?SPC_CDS=2cf2ffdf-2e6f-4c53-8c21-1ee48ac80476&SPC_CDS_VER=2&order_id='+str(order['shopee_id'])
                                all_info_sp = json.loads(loginsp.get(url).text)['data']

                                for line in all_info_sp['order_items']:
                                    if line['bundle_deal_id'] == 0:
                                        new_line = {"price": int(line['item_price'].replace('.00','')),"sp_id":line['model_id'],"qty":line['amount']}
                                        shopee_info['order_items'].append(new_line)
                                    else:
                                        for pr in line['item_list']:
                                            new_line = {"price": int(pr['item_price'].replace('.00','')),"sp_id":pr['model_id'],"qty":pr['amount']}
                                            shopee_info['order_items'].append(new_line)
                                        shopee_info['discount_combo'] = int(line['price_before_bundle'].replace('.00','')) - int(line['item_price'].replace('.00',''))

                                url = 'https://market-place.sapoapps.vn/v2/orders?page=1&limit=20&connectionIds=155938,155687,155174,134366,10925&sortBy=ISSUED_AT&orderBy=desc&query='+str(order['reference_number'])
                                all_info_sp = json.loads(loginss.get(url).text)['orders'][0]

                                for pr in all_info_sp['products']:
                                    for x in shopee_info['order_items']:
                                        if str(x['sp_id']) == str(pr['variation_id']):
                                            x['vari_id'] = str(pr['sapo_variant_id'])

                                writejsonfile(shopee_info, file_log)

                        if len(order["tags"]) >= 2 and "Shopee_Gia Dụng Plus Official" in order["tags"][1] and order['reference_url'] != None and order['channel'] == "Sàn TMĐT - Shopee":

                            shopee_info = json.loads(readfile(file_log))

                            report_all["shopee"]["phi_san"] += shopee_info['phi_all']
                            report_all["shopee"]["phi_dv"] += shopee_info['phi_dv']
                            report_all["shopee"]["phi_tt"] += shopee_info['phi_tt']

                            report_all["shopee"]["tong_ship"] += shopee_info['phi_vc_thuc_te']
                            report_all["shopee"]["ship_shopee_tra"] += shopee_info['phi_vc_tro_gia']
                            report_all["shopee"]["ship_khach_tra"] += shopee_info['phi_vc_ng_mua_tra']
                            if(report_all["shopee"]["ship_shopee_tra"] > 0):
                                report_all["shopee"]["don_duoc_tro_ship"] += 1

                            report_all["shopee"]["mgg_shopee"] += shopee_info['tro_gia_cho_khach']
                            report_all["shopee"]["tro_gia"] += abs(shopee_info['tro_gia_cho_khach']) + abs(shopee_info['tro_gia_sp']) + abs(shopee_info['tro_gia_voucher'])
                            report_all["shopee"]["gui_shopee"] += order['total']

                        elif  order['channel'] == "Sàn TMĐT - Shopee" and  order['reference_url'] != None:
                            report_all["shopee"]["phi_san"] += order['total']*0.105
                            report_all["shopee"]["phi_dv"] += order['total']*0.025
                            report_all["shopee"]["phi_tt"] += order['total']*0.085
                            report_all["shopee"]["tong_ship"] += 25000
                            report_all["shopee"]["ship_shopee_tra"] += 0
                            report_all["shopee"]["ship_khach_tra"] += 15000
                            report_all["shopee"]["mgg_shopee"] += 10000
                            report_all["shopee"]["tro_gia"] += 0
                            report_all["shopee"]["gui_shopee"] += order['total']
                        else:
                            if order['fulfillments'] != [] and order['fulfillments'][-1]['shipment'] != None:
                                report_all["shopee"]["phi_san"] += order['fulfillments'][-1]['shipment']['freight_amount'] - order['fulfillments'][-1]['shipment']['delivery_fee']
                                report_all["shopee"]["cp_gui_ngoai"] += order['fulfillments'][-1]['shipment']['freight_amount'] - order['fulfillments'][-1]['shipment']['delivery_fee']
                                report_all["shopee"]["tong_ship"] +=  order['fulfillments'][-1]['shipment']['freight_amount']
                            else:
                                report_all["shopee"]["phi_san"] += 35000
                                report_all["shopee"]["tong_ship"] +=  35000
                                report_all["shopee"]["cp_gui_ngoai"] += 35000
                            
                            report_all["shopee"]["gui_ngoai"] += order['total']
                            report_all["shopee"]["c_gui_ngoai"] += 1

                    # Lazada
                    elif order["source_id"] == 1880149 or order["source_id"] == 1880150:
                        order['nguon'] = "Lazada"
                        report_all["lazada"]["doanh_so"] += order["total"]
                        report_all["lazada"]["don_hang"] += 1
                        if order["source_id"] == 1880149:
                            report_all["lazada"]["lazada"] += order["total"]
                        else:
                            report_all["lazada"]["tiki"] += order["total"]

                    #Zalo
                    elif order["source_id"] == 1880148 or order["source_id"] == 1880146 or order["source_id"] == 5483992:
                        order['nguon'] = "Zalo/Web"
                        report_all["zalo"]["doanh_so"] += order["total"]
                        report_all["zalo"]["don_hang"] += 1
                    # Sỉ /đại lý
                    elif order["source_id"] == 4893087:
                        order['nguon'] = "Sỉ"
                        report_all["daily"]["doanh_so"] += order["total"]
                        report_all["daily"]["don_hang"] += 1
                    
                    array_donhang.append(order)

    #Tỉ lệ chuyển đổi
    url_search = "https://socials.sapoapps.vn/api/report-v2/interactive/messages?store_alias=sisapsan&facebook_page_ids=2290891804562178,106808424116731&group_by=day&accountId=5ce8999d00cfeb00012501bc&language=vi&from="+str(END_TIME_STR)+"&to="+str(START_TIME_STR)
    json_order_list = json.loads(loginss.get(url_search).text)["interactive_message_report"]["interactive_details"]
    
    report_all["facebook"]["tin_nhan_yes"] = json_order_list[0]["total_user_inbox"]
    report_all["facebook"]["tin_nhan"] = json_order_list[1]["total_user_inbox"]
    if report_all["facebook"]["tin_nhan_yes"] > 0:
        report_all["facebook"]["ss_tin_nhan"] = "%.2f" % float(((report_all["facebook"]["tin_nhan"] - report_all["facebook"]["tin_nhan_yes"])/report_all["facebook"]["tin_nhan_yes"])*100)
    report_all["facebook"]["ti_le_chuyen_doi_yes"] = json_order_list[0]["conversion_rate"]
    report_all["facebook"]["ti_le_chuyen_doi"] = json_order_list[1]["conversion_rate"]
    if report_all["facebook"]["ti_le_chuyen_doi_yes"] > 0:
        report_all["facebook"]["ss_ti_le_chuyen_doi"] = "%.2f" % float(((report_all["facebook"]["ti_le_chuyen_doi"] - report_all["facebook"]["ti_le_chuyen_doi_yes"])/report_all["facebook"]["ti_le_chuyen_doi_yes"])*100)
    report_all["facebook"]["ti_le_chuyen_doi_yes"] = "%.2f" % float(json_order_list[0]["conversion_rate"])
    report_all["facebook"]["ti_le_chuyen_doi"] = "%.2f" % float(json_order_list[1]["conversion_rate"])
    #QUảng cáo FB
    url = 'https://socials.sapoapps.vn/api/facebook/ad_accounts/442035716365629/insights?store_alias=sisapsan&order_status=NEW&filter_level=CAMPAIGN&campaign_ids=&ad_set_ids=&query=&sort_by=FB_COMMENT&type_sort=DESC&facebook_page_ids=2290891804562178,106808424116731&accountId=5ce8999d00cfeb00012501bc&language=vi&to='+START_TIME_STR+'&from='+ END_TIME_0_STR
    report_all["facebook"]["ads"] = json.loads(loginss.get(url).text)['data']
    # Shopee
    report_all["facebook"]["ti_le_doanh_thu"] = "%.2f" % float(report_all["facebook"]["doanh_so"]*100 / report_all["sum_all"]["doanh_so_thuc"])
    report_all["shopee"]["ti_le_doanh_thu"] = "%.2f" % float(report_all["shopee"]["doanh_so"]*100 / report_all["sum_all"]["doanh_so_thuc"])
    report_all["lazada"]["ti_le_doanh_thu"] = "%.2f" % float(report_all["lazada"]["doanh_so"]*100 / report_all["sum_all"]["doanh_so_thuc"])
    report_all["zalo"]["ti_le_doanh_thu"] = "%.2f" % float(report_all["zalo"]["doanh_so"]*100 / report_all["sum_all"]["doanh_so_thuc"])
    report_all["daily"]["ti_le_doanh_thu"] = "%.2f" % float(report_all["daily"]["doanh_so"]*100 / report_all["sum_all"]["doanh_so_thuc"])    

    report_all["shopee"]["trung_binh_don"] = int(report_all["shopee"]["doanh_so"]/report_all["shopee"]["don_hang"])
    if report_all["lazada"]["don_hang"] > 0:
        report_all["lazada"]["trung_binh_don"] = int(report_all["lazada"]["doanh_so"]/report_all["lazada"]["don_hang"])    
    if report_all["facebook"]["don_hang"] > 0:
        report_all["facebook"]["trung_binh_don"] = int(report_all["facebook"]["doanh_so"]/report_all["facebook"]["don_hang"])    
    if report_all["zalo"]["don_hang"] > 0:
        report_all["zalo"]["trung_binh_don"] = int(report_all["zalo"]["doanh_so"]/report_all["zalo"]["don_hang"])    
    

    report_all["sum_all"]["ti_le_gia_von"] = "%.2f" % float((report_all["sum_all"]["gia_von"]/report_all["sum_all"]["doanh_so_thuc"])*100)

    return report_all

def get_list_nhan_vien():
    list_nhan_vien = []
    url_search = "https://sisapsan.mysapogo.com/admin/accounts.json?page=1&limit=200&status=active"
    result_rq = json.loads(loginss.get(url_search).text)
    for nv in result_rq["accounts"]:
        nv["doanh_so"] = 0
        if nv["id"] == 713355:
            nv["image"] = "2.png"
        elif nv["id"] == 707777:
            nv["image"] = "loan.jpg"
        elif nv["id"] == 692589:
            nv["image"] = "9.png" 
        elif nv["id"] == 638138:
            nv["image"] = "3.png"
        elif nv["id"] == 553697:
            nv["image"] = "12.png" 
        elif nv["id"] == 551947:
            nv["image"] = "5.png" 
        elif nv["id"] == 518175:
            nv["image"] = "13.png"             
        elif nv["id"] == 340290:
            nv["image"] = "giap.jpg"
        elif nv["id"] == 319911:
            nv["image"] = "1.png" 
        elif nv["id"] == 828281:
            nv["image"] = "pdnguyen.png" 
        list_nhan_vien.append(nv)
    return list_nhan_vien

def get_list_gia_goc():
    list_gia_goc = {}
    loc = ("logs/ALL-PRODUCT.xlsx")
    wb = xlrd.open_workbook(loc)
    sheet = wb.sheet_by_index(0)
    sheet.cell_value(0, 0)

    for i in range(sheet.nrows):
        if i != 0:
            array_pr = sheet.row_values(i)
            if array_pr[11]:
                if int(array_pr[11]) > 0:
                    list_gia_goc["b_"+str(array_pr[1])] = int(array_pr[11])
                    list_gia_goc["s_"+str(array_pr[1])] = int(array_pr[11])

    return list_gia_goc

def human_format(num):
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    # add more suffixes if you need them
    return '%.2f%s' % (num, ['', 'K', 'M', 'B', 'T', 'P'][magnitude])


from collections import defaultdict
import glob

def count_handler_kpi(date_str: str):  # "YYYY-MM-DD"
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    log_dir = "logs/comment"
    pattern = f"{dt.month}_{dt.year}-*.jsonl"  # gom tất cả file log trong tháng đó
    files = glob.glob(os.path.join(log_dir, pattern))

    result = defaultdict(lambda: {
        "today": {"good": 0, "bad": 0},
        "thismonth": {"good": 0, "bad": 0}
    })

    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    timestamp = entry.get("timestamp", "")
                    handler = entry.get("handler", "Unknown")
                    rate = int(entry.get("rate_star", 0))

                    if not timestamp:
                        continue

                    # Lọc trong tháng
                    if timestamp.startswith(f"{dt.year}-{dt.month:02}"):
                        if rate >= 4:
                            result[handler]["thismonth"]["good"] += 1
                        else:
                            result[handler]["thismonth"]["bad"] += 1

                    # Lọc trong ngày
                    if timestamp.startswith(date_str):
                        if rate >= 4:
                            result[handler]["today"]["good"] += 1
                        else:
                            result[handler]["today"]["bad"] += 1
                except (json.JSONDecodeError, ValueError):
                    continue
    for nv in result:
        if 'CSKH: Dương' in nv:
             result[nv]['image'] = 'duong-cskh.png'
        elif 'CSKH: Mai' in nv:
             result[nv]['image'] = 'mai-cskh.png'

    return dict(result)


def get_reviews_list(shop_name, rate):
    connection_id = existing_shop_map[shop_name]
    reviews = []
    URLs = [
    f"https://banhang.shopee.vn/api/v3/settings/search_shop_rating_comments_new/?SPC_CDS=4044a386-9ee1-4d4b-9227-b3536170695d&SPC_CDS_VER=2&rating_star={rate}&page_number=1&page_size=20&cursor=44555077169&from_page_number=1&reply_status=1&language=vi",
    f"https://banhang.shopee.vn/api/v3/settings/search_shop_rating_comments_new/?SPC_CDS=d5bd45b3-2d49-4801-b02e-6abe897baf95&SPC_CDS_VER=2&rating_star={rate}&page_number=2&page_size=20&cursor=45105897341&from_page_number=1&reply_status=1&language=vi"
    ]
    if doi_shop(connection_id,loginsp) == 1:
        for URL in URLs:
            comment_list = json.loads(loginsp.get(URL).text)["data"]["list"]

            for comment in comment_list:
                order = js_get_url(f"{MAIN_URL}/orders.json?page=1&limit=250&query={comment['order_sn']}")["orders"][0]
                ten_khach_hang = order["customer_data"]["name"]

                if "Store" in ten_khach_hang:
                    all_data = js_get_url(f"{MAIN_URL}/customers/{order['customer_id']}.json")["customer"]
                    ten_khach_hang = ten_khach_hang.replace("Store ", "")
                    all_data["name"] = ten_khach_hang

                    if "Lô C21 Ô 2, Khu đô thị Geleximco" not in ten_khach_hang or "B76a Tô Ký (Hẻm đối diện" not in ten_khach_hang:
                        rs = loginss.put(f"{MAIN_URL}/customers/{order['customer_id']}.json",json=all_data)

                json_comment = {
                    'comment_id': comment['comment_id'],
                    'user_name':comment['user_name'],
                    'customer_name':ten_khach_hang,
                    'rating':comment['rating_star'],
                    'review_content':comment['comment'],
                    'product_name':comment['product_name'],
                    "order_sn": comment['order_sn'],
                    'shop_name': shop_name,
                    'image':comment['images']
                }

                if '5' in rate:
                    if comment["comment"] != "":
                        reviews.append(json_comment)
                else:
                    reviews.append(json_comment)

    return reviews


def build_prompt_from_reviews(reviews):
    prompt = ""
    prompt += "\nDưới đây là danh sách đánh giá cần phản hồi:\n"
    for r in reviews:
        if r['images'] != None:
            co_anh = "Có"
        else:
            co_anh = "Không"

        prompt += f"comment_id: {r['comment_id']}\n"
        prompt += f"Tên tài khoản: {r['user_name']}\n"
        prompt += f"Tên khách hàng: {r['order_info']['customer_data']['name']}\n"
        prompt += f"rating_star: {r['rating_star']}\n"
        prompt += f"review_content: {r['comment'] or '[không có nội dung]'}\n"
        prompt += f"Tên sản phẩm: {r['product_name']}\n"
        prompt += f"Tên shop: {r['order_info']['tags']}\n"
        prompt += f"Ảnh kèm theo: {co_anh}\n"
        prompt += f"\n----\n"

    prompt += "\nTrả lời kết quả theo định dạng JSON như hướng dẫn."

    return prompt

# ---------- Tiện ích nhỏ linh tinh ----------

def get_shop_name(request, default='giadungplus_official'):
    # Ưu tiên lấy từ GET, rồi đến session, cuối cùng là default
    shop_name = request.GET.get('shop_name')
    if shop_name:
        request.session['shop_name'] = shop_name
    elif 'shop_name' in request.session:
        shop_name = request.session['shop_name']
    else:
        shop_name = default
    return shop_name

def get_connection_id(shop_name, existing_shop_map):
    return existing_shop_map.get(shop_name, None)

def get_connection_name(shop_id, existing_shop_map):
    for key, value in existing_shop_map.items():
        if value == shop_id:
            return key
    return "noname"

def find_chat_id_connect(connection_id, all_connect):
    for c in all_connect:
        if c['connection_id'] == connection_id:
            return c['id']
    return 0

def find_cover_id(username, chat_id_connect):
    if not username:
        return 0
    cover = js_get_url(
        f"https://market-place.sapoapps.vn/search/conversation/filter?sortType=desc&connectionIds={chat_id_connect}&queryType=account&query={username}&page=0&limit=20"
    )
    if cover['metadata']['total'] > 0:
        return cover['conversations'][0]['id']
    return 0

def get_handler(request):
    handler = request.GET.get('handler')
    if handler:
        request.session['handler'] = handler
    elif 'handler' in request.session:
        handler = request.session['handler']
    else:
        handler = None
    return handler

def get_order_comment_rep(all_data, comment_id):
    order_comment_rep = 0
    comment = {}
    for cmt in all_data:
        if str(cmt['comment_id']) == str(comment_id):
            comment = cmt
        if cmt['reply'] is not None:
            order_comment_rep = 1
    return order_comment_rep, comment

# ---------- Lấy gợi ý đánh giá ----------

def load_goi_y_danh_gia(excel_file_path, shop_name, rate_star, male, name):
    wb = xlrd.open_workbook(excel_file_path)
    sheet = wb.sheet_by_index(0)
    headers = sheet.row_values(0)
    listgoiy = []
    for i in range(1, sheet.nrows):
        row_values = sheet.row_values(i)
        x = {header: value for header, value in zip(headers, row_values)}
        if shop_name == x['shop']:
            if rate_star >= 4 and int(x['for_rate']) == rate_star:
                listgoiy.append(x)
            elif rate_star < 4 and '1,2,3' in x['for_rate']:
                listgoiy.append(x)
    for goiy in listgoiy:
        goiyx = goiy["goiydanhgia"].replace("[male]", male, 5)
        goiyx = goiyx.replace("[Male]", male.capitalize(), 5)
        goiyx = goiyx.replace("[name]", name.title(), 5)
        goiy["goiydanhgia"] = goiyx
    random.shuffle(listgoiy)
    all_tags_set = set(x['tags'] for x in listgoiy if x['tags'])
    return listgoiy, sorted(all_tags_set)

# ---------- Log phản hồi ----------

def log_rep_comment(log_path, log_entry):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

# ---------- Gửi tin nhắn qua Sapo Messenger ----------

def send_messages_to_customer(COVER_ID, messages, logintmdt):
    for mess in messages:
        url = f"https://market-place.sapoapps.vn/go/messenger/conversations/{COVER_ID}/messages"
        data = {
            "id": None,
            "id_fake": "119bc2bc-48f2-4ac0-843a-75d93996256e",
            "conversation_id": COVER_ID,
            "sapo_staff_id": 319911,
            "status": 2,
            "message_type": 0,
            "content": str(mess),
            "send_from_customer": False,
            "channel_created_at": 1748345443,
            "text": str(mess)
        }
        files = {
            'message': ('blob', json.dumps(data), 'application/json')
        }
        response = logintmdt.post(url, files=files)
        time.sleep(3)

# ---------- Main view ----------

def crawl_shopee_ratings(base_url, max_pages=100, page_size=50, delay=0.5, rate_type="new"):
    """
    rate_type:
      - "new": giữ thứ tự API (mới -> cũ)
      - "old": sắp xếp lại theo thời gian tăng dần (cũ -> mới)
              nếu không tìm thấy timestamp thì đảo ngược list như fallback
    """
    cursor = 0
    page_number = 1
    from_page_number = 1
    all_ratings = []
    all_ratings_final = []

    for i in range(max_pages):
        url = (f"{base_url}"
               f"&page_number={page_number}"
               f"&page_size={page_size}"
               f"&cursor={cursor}"
               f"&from_page_number={from_page_number}")

        print(f"Page {page_number} | Cursor {cursor} | FromPage {from_page_number}")

        resp = loginsp.get(url)
        if resp.status_code != 200:
            print("Lỗi:", resp.status_code)
            break

        data = resp.json()
        page_data = data.get("data", {}).get("list", [])
        if not page_data:
            print("Hết dữ liệu.")
            break

        all_ratings.extend(page_data)

        # Lấy comment_id cuối làm cursor cho trang tiếp theo
        cursor = page_data[-1].get("comment_id", cursor)

        page_number += 1
        from_page_number = page_number - 1

        time.sleep(delay)

    # Map qua orders + enrich
    for cmt in all_ratings:
        all_ratings_final.append(cmt)

    # --- Sắp xếp theo rate_type ---
    if rate_type == "old":
        # Cố gắng sort theo timestamp; nếu không có thì đảo list làm fallback
        def _extract_ts(x):
            src = x.get("cmt_save", {})
            # Thử các key thường gặp của Shopee rating
            for k in ("comment_time", "ctime", "create_time", "rating_ctime", "mtime"):
                v = src.get(k)
                if isinstance(v, int):
                    return v
                # đôi khi trả về string epoch
                if isinstance(v, str) and v.isdigit():
                    return int(v)
            return None

        has_ts = any(_extract_ts(x) is not None for x in all_ratings_final)
        if has_ts:
            all_ratings_final.sort(key=lambda x: (_extract_ts(x) or 0))  # tăng dần: cũ -> mới
        else:
            # fallback: API vốn là mới->cũ, ta đảo lại thành cũ->mới
            all_ratings_final.reverse()

    # Ngược lại "new": giữ nguyên thứ tự API (mới -> cũ)
    return all_ratings_final



def get_region_from_order(order, region_filter):
    city = ""
    if isinstance(order, dict):
        shipping_address = order.get("shipping_address")
        if isinstance(shipping_address, dict):
            city = (shipping_address.get("city") or "").strip()

    for region, provinces in region_filter.items():
        province_list = [p.strip() for p in provinces.split(",")]
        if any(city.startswith(p) or p in city for p in province_list):
            return region
    return "MIEN_BAC"

def extract_order_stats(order, variant_id, heso=1, region_filter=None):
    now = datetime.datetime.utcnow()
    order_time = datetime.datetime.strptime(order["created_on"], "%Y-%m-%dT%H:%M:%SZ")
    age_days = (now - order_time).days
    region = get_region_from_order(order, region_filter) if region_filter and order else "ALL"

    result = []
    for line in order.get("order_line_items", []):
        if line["variant_id"] != variant_id:
            continue
        quantity = line["quantity"] * heso
        amount = line["line_amount"] * heso
        result.append({
            "variant_id": variant_id,
            "order_id": order["id"],
            "quantity": quantity,
            "line_amount": amount,
            "created_on": order_time,
            "age_days": age_days,
            "region": region
        })
    return result

import pandas as pd

def calc_suggest_import(
    raw_data,
    available_dict=None,
    incoming_dict=None,
    days_plan=60,
    lead_time=20,
    boost_if_growth_15d=True,
    boost_ratio_15d=0.15,
    boost_if_growth_7d=True,
    boost_ratio_7d=0.10,
    enable_dynamic_boost=True,
    boost_limit=2.0,
    reduce_if_decline=True,
    reduce_ratio=0.05
):
    import datetime
    import pandas as pd

    df = pd.DataFrame(raw_data).copy()

    if df.empty:
        return pd.DataFrame([{
            "variant_id": None,
            "suggest_import": 0,
            "suggest_boost": 1,
            "boosted_15d": False,
            "boosted_7d": False,
            "suggest_mien_bac": 0,
            "suggest_mien_nam": 0,
            "days_cover_mienbac": 0,
            "days_cover_miennam": 0,
            "days_cover_total": 0,
            "inventory_turnover_days": 0,
            "suggest_action": "Không đủ dữ liệu"
        }])

    df["date"] = pd.to_datetime(df["created_on"])
    df["qty"] = df["quantity"]
    df["amount"] = df["line_amount"]
    df["age_days"] = (datetime.datetime.utcnow() - df["date"]).dt.days

    def segment(days):
        if days <= 7: return "0_7"
        elif days <= 15: return "7_15"
        elif days <= 30: return "15_30"
        elif days <= 60: return "30_60"
        else: return "old"

    df["segment"] = df["age_days"].apply(segment)

    # Tổng theo segment
    segment_agg = df.groupby("segment").agg(qty=("qty", "sum"), amount=("amount", "sum")).to_dict()
    qty_0_7 = segment_agg["qty"].get("0_7", 0)
    qty_7_15 = segment_agg["qty"].get("7_15", 0)
    qty_15_30 = segment_agg["qty"].get("15_30", 0)
    qty_30_60 = segment_agg["qty"].get("30_60", 0)
    rev_0_7 = segment_agg["amount"].get("0_7", 0)
    rev_7_15 = segment_agg["amount"].get("7_15", 0)
    rev_15_30 = segment_agg["amount"].get("15_30", 0)
    rev_30_60 = segment_agg["amount"].get("30_60", 0)

    sum_qty_30 = qty_0_7 + qty_7_15 + qty_15_30
    sum_rev_30 = rev_0_7 + rev_7_15 + rev_15_30
    sum_qty_15 = qty_0_7 + qty_7_15
    sum_rev_15 = rev_0_7 + rev_7_15

    def safe_growth(now, prev):
        if prev == 0: return 100.0 if now > 0 else 0.0
        return round((now - prev) / prev * 100, 2)

    growth_30d = safe_growth(sum_qty_30, qty_30_60)
    growth_15d = safe_growth(sum_qty_15, qty_15_30)
    growth_7d = safe_growth(qty_0_7, qty_7_15)

    speed_30d = sum_qty_30 / 30 if sum_qty_30 > 0 else 0.1
    speed_15d = sum_qty_15 / 15 if sum_qty_15 > 0 else 0.1
    avg_speed = speed_30d

    # Tồn kho hiện tại
    stock_bac = (available_dict.get("MIEN_BAC", 0) + incoming_dict.get("MIEN_BAC", 0)) if available_dict else 0
    stock_nam = (available_dict.get("MIEN_NAM", 0) + incoming_dict.get("MIEN_NAM", 0)) if available_dict else 0
    total_stock = stock_bac + stock_nam

    # Số ngày đủ bán
    days_cover_mienbac = stock_bac / avg_speed if avg_speed > 0 else 0
    days_cover_miennam = stock_nam / avg_speed if avg_speed > 0 else 0
    days_cover_total = total_stock / avg_speed if avg_speed > 0 else 0

    # Vòng xoay hàng hóa
    inventory_turnover_days = total_stock / avg_speed if avg_speed > 0 else 0

    # Đề xuất nhập cơ bản
    suggest_import_raw = round(avg_speed * (days_plan + lead_time))
    suggest_import = suggest_import_raw

    # Áp boost
    suggest_boost = 1
    boosted_15d = False
    boosted_7d = False

    if enable_dynamic_boost and speed_30d > 0:
        speed_ratio = speed_15d / speed_30d
        if speed_ratio > 1:
            suggest_boost = min(round(speed_ratio, 2), boost_limit)
        elif reduce_if_decline:
            suggest_boost = max(1 - reduce_ratio, 0.5)

    if boost_if_growth_15d and growth_15d > 10:
        boosted_15d = True

    if boost_if_growth_7d and growth_7d > 10:
        boosted_7d = True

    # Sau boost mới trừ tồn kho
    suggest_import = max(0, round(suggest_import - total_stock))

    # Phân bổ theo miền
    speed_bac = df[df["region"] == "MIEN_BAC"]["qty"].sum() / 30 if not df[df["region"] == "MIEN_BAC"].empty else 0.1
    speed_nam = df[df["region"] == "MIEN_NAM"]["qty"].sum() / 30 if not df[df["region"] == "MIEN_NAM"].empty else 0.1
    total_speed = speed_bac + speed_nam

    ratio_bac = speed_bac / total_speed if total_speed > 0 else 0.5
    ratio_nam = speed_nam / total_speed if total_speed > 0 else 0.5
    suggest_mien_bac = round(suggest_import * ratio_bac)
    suggest_mien_nam =  round(suggest_import * ratio_nam)

    # Gợi ý hành động mới
    if days_cover_total < (lead_time + 10) and total_stock < suggest_import_raw:
        suggest_action = 0  # Nên nhập gấp
    elif (lead_time + 10) <= days_cover_total < (lead_time + 30):
        suggest_action = 1  # Cần nhập
    elif (lead_time + 30) <= days_cover_total < (days_plan + lead_time):
        suggest_action = 4  # Nhập thêm ít
    elif inventory_turnover_days > 120 or days_cover_total > (days_plan + lead_time):
        suggest_action = 2  # Bán chậm
    else:
        suggest_action = 3  # Ổn định

    # Hàm format tiền
    def shorten_vnd(x):
        try:
            x = float(x)
            if x >= 1e9:
                return f"{round(x/1e9,1)}B"
            elif x >= 1e6:
                return f"{round(x/1e6,1)}M"
            elif x >= 1e3:
                return f"{round(x/1e3,1)}K"
            return str(int(x))
        except:
            return "0"

    return pd.DataFrame([{
        "qty_0_7": qty_0_7,
        "qty_7_15": qty_7_15,
        "qty_15_30": qty_15_30,
        "qty_30_60": qty_30_60,
        "revenue_0_7": shorten_vnd(rev_0_7),
        "revenue_7_15": shorten_vnd(rev_7_15),
        "revenue_15_30": shorten_vnd(rev_15_30),
        "revenue_30_60": shorten_vnd(rev_30_60),
        "sum_qty_30": sum_qty_30,
        "sum_rev_30": shorten_vnd(sum_rev_30),
        "sum_qty_15": sum_qty_15,
        "sum_rev_15": shorten_vnd(sum_rev_15),
        "sum_qty_60": qty_30_60,
        "sum_rev_60": shorten_vnd(rev_30_60),
        "growth_qty_30d": growth_30d,
        "growth_qty_15d": growth_15d,
        "growth_qty_7d": growth_7d,
        "speed_15d": speed_15d,
        "speed_30d": speed_30d,
        "avg_speed": avg_speed,
        "suggest_import": suggest_import,
        "suggest_boost": suggest_boost,
        "boosted_15d": boosted_15d,
        "boosted_7d": boosted_7d,
        "suggest_mien_bac": suggest_mien_bac,
        "suggest_mien_nam": suggest_mien_nam,
        "days_cover_mienbac": int(days_cover_mienbac),
        "days_cover_miennam": int(days_cover_miennam),
        "days_cover_total": int(days_cover_total),
        "inventory_turnover_days": round(inventory_turnover_days, 1),
        "suggest_action": suggest_action
    }])


def shorten_vnd(value):
    try:
        num = float(value)
    except (ValueError, TypeError):
        return "0"

    if num >= 1_000_000_000:
        return f"{round(num / 1_000_000_000, 1)}B"
    elif num >= 1_000_000:
        return f"{round(num / 1_000_000, 1)}M"
    elif num >= 1_000:
        return f"{round(num / 1_000, 0)}K"
    else:
        return str(int(num))


def extract_total_onhand(html):
    match = re.search(r'<td[^>]*nametd="total"[^>]*>\s*([\d,\.]+)\s*</td>', html)
    if match:
        return int(match.group(1).replace(",", ""))
    else:
        print("❌ No match found.")

    return 0

from collections import defaultdict

def calculate_onhand_60_days(vari_id, stock_nam, stock_bac, end_date=None):

    URL = f"{MAIN_URL}/reports/inventories/variants/{vari_id}.json?page=1&limit=500&location_ids=241737,548744"
    logs = js_get_url(URL)["variant_inventories"]

    # Nếu không truyền ngày thì mặc định là hôm nay
    if end_date is None:
        end_date = datetime.datetime.now(datetime.timezone.utc)
    else:
        end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    
    # Cố định giờ cuối ngày
    end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=0)
    start_date = end_date - datetime.timedelta(days=59)

    daily_change = defaultdict(int)

    for log in logs:
        try:
            date = datetime.datetime.fromisoformat(log["issued_at_utc"].replace("Z", "+00:00")).replace(hour=23, minute=59, second=59, microsecond=0)
           
        except:
            continue
        if not (start_date <= date <= end_date):
            break
        if log["location_id"] not in [241737, 548744]:
            continue
        daily_change[date.date()] += log["onhand_adj"]


    stock_by_day = {}
    stock_total = stock_nam + stock_bac

    for i in range(60):
        date = (end_date - datetime.timedelta(days=i)).date()
        stock_by_day[date.strftime("%Y-%m-%d")] = stock_total
        stock_total -= daily_change.get(date, 0)

    return dict(sorted(stock_by_day.items()))


def export_giao_excel(obj, ss_day, filename="logs/giao_san.xlsx"):
    rows = []
    all_categories = set()

    # Lọc ra tất cả loại phân loại từng xuất hiện (cột header)
    for kho in ['gele', 'toky']:
        for nguoi_goi in obj.get(kho, {}):
            for cato in obj[kho][nguoi_goi].get('cato', {}):
                all_categories.add(cato)

    all_categories = sorted(all_categories)  # Sắp xếp tên cột cho đẹp

    # Đổ dữ liệu
    for aday in ss_day:
        for kho in ['gele', 'toky']:
            for nguoi_goi in obj.get(kho, {}):
                row = {
                    "Ngày": aday.strftime("%Y-%m-%d"),
                    "Kho": kho.upper(),
                    "Người Gói": nguoi_goi
                }
                for cat in all_categories:
                    row[cat] = obj[kho][nguoi_goi]['cato'].get(cat, 0)
                rows.append(row)

    df = pd.DataFrame(rows)

    # Sắp xếp cột: Ngày - Kho - Người Gói - các phân loại
    columns_order = ["Ngày", "Kho", "Người Gói"] + all_categories
    df = df[columns_order]

    df.to_excel(filename, index=False)
    print(f"Đã xuất file: {filename}")


def classify_type(title):
    """Gán loại cho từng block theo tiêu đề"""
    title = title.lower()
    if "tính năng" in title:
        return "tinh-nang"
    elif "ưu việt" in title or "khác biệt" in title:
        return "uu-viet"
    elif "hướng dẫn" in title:
        return "huong-dan"
    else:
        return "default"

def transform_description(raw_html):
    # 1. Cắt bỏ phần sau ###########
    if "###########" in raw_html:
        raw_html = raw_html.split("###########")[0]

    # 2. Dùng BeautifulSoup để parse HTML
    soup = BeautifulSoup(raw_html, "html.parser")

    # 3. Duyệt theo thẻ và gom theo nhóm <hr> + <h2> + nội dung
    blocks = []
    current_block = []

    for tag in soup.contents:
        if tag.name == "hr":
            if current_block:
                blocks.append(current_block)
                current_block = []
        else:
            current_block.append(tag)

    if current_block:
        blocks.append(current_block)

    # 4. Tạo HTML từng block
    output = ""
    for block in blocks:
        header = None
        content = ""
        for el in block:
            if el.name == "h2":
                header = el.text.strip()
            else:
                content += str(el)

        if header:
            type_class = classify_type(header)
            block_html = f"""
            <div class="dropdown-block" data-type="{type_class}">
              <div class="dropdown-header" onclick="toggleDropdown(this)"><div>
                {header}
                <span class="icon">▶</span></div>
              </div>
              <div class="dropdown-content">
                {content}
              </div>
            </div>
            """
            output += block_html
        else:
            output += content

    return output

def build_image_block(images):
    soup = BeautifulSoup("", "html.parser")

    wrapper = soup.new_tag("div")
    wrapper['class'] = 'dropdown-block'
    wrapper['data-type'] = 'hinh-anh'

    header = soup.new_tag("div", **{
        'class': 'dropdown-header',
        'onclick': 'toggleDropdown(this)'
    })
    header.string = "Hình ảnh sản phẩm ▶"


    content = soup.new_tag("div", **{'class': 'dropdown-content'})

    for img in images:
        img_tag = soup.new_tag("img", src=img['full_path'])
        img_tag['style'] = 'max-width: 48%; margin-bottom: 10px; margin-left:6px; border-radius: 6px;'
        content.append(img_tag)

    wrapper.append(header)
    wrapper.append(content)

    return str(wrapper)



def extract_table(description: str):
    if not description:
        return "", description

    table_match = re.search(r'<table.*?</table>', description, re.DOTALL | re.IGNORECASE)
    
    if not table_match:
        return "", description.strip()

    table_html = table_match.group(0)
    rest_description = description.replace(table_html, '', 1).strip()

    # Xử lý với BeautifulSoup
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(table_html, "html.parser")

    for li in soup.find_all("li"):
        text = li.get_text(strip=True)
        match = re.search(r"(Shopee|Website|Link)[:：]?\s*(https?://\S+)", text, re.IGNORECASE)
        if match:
            label = match.group(1).strip()
            url = match.group(2).strip()

            if "shopee.vn" in url:
                link_text = "Shopee"
            elif "giadungplus.com" in url:
                link_text = "Website"
            else:
                link_text = "Truy cập"

            # Gán lại bằng thẻ a HTML thật
            li.clear()
            li.append(BeautifulSoup(f'{label}: <a href="{url}" target="_blank" rel="noopener noreferrer">{link_text}</a>', 'html.parser'))

    return str(soup), rest_description


def split_description(pr_description):
    parts = pr_description.split("###########")

    main_desc = parts[0].strip() if len(parts) > 0 else ""
    extra_info = parts[1].strip() if len(parts) > 1 else ""
    print_info = parts[2].strip() if len(parts) > 2 else ""

    key_search = ""
    product_replace = []
    product_recommend = []

    # Lấy dòng chứa "Cách tìm kiếm"
    search_match = re.search(r"Cách tìm kiếm:\s*(.+?)</p>", extra_info, re.DOTALL)
    if search_match:
        key_search = search_match.group(1).strip()

    # Lấy dòng chứa "Sản phẩm thay thế"
    replace_match = re.search(r"Sản phẩm thay thế:\s*([\d, ]+)", extra_info)
    if replace_match:
        product_replace = [x.strip() for x in replace_match.group(1).split(',')]

    # Lấy dòng chứa "Sản phẩm mua cùng"
    recommend_match = re.search(r"Sản phẩm mua cùng:\s*([\d, ]+)", extra_info)
    if recommend_match:
        product_recommend = [x.strip() for x in recommend_match.group(1).split(',')]


    # Dùng BeautifulSoup để parse HTML
    soup = BeautifulSoup(print_info, "html.parser")

    print_info_all = {}

    for li in soup.find_all("li"):
        if "=" in li.text:
            key, value = li.text.split("=", 1)
            print_info_all[key.strip()] = value.strip()

    return {
        "description": main_desc,
        "key_search": key_search,
        "product_replace": product_replace,
        "product_recommend": product_recommend,
        "print_data": print_info_all
    }

CACHE_TTL   = 10  

def read_nhanvien_pwd(read_new):
    all_nhanvien = []
    data = json.loads(readfile('logs/log excel/all_google_api.json'))
    now = datetime.datetime.utcnow()
    last = datetime.datetime.fromisoformat(data["time_read_nhanvien"])
    data["time_read_nhanvien"] = now.isoformat()
    if (now - last).total_seconds() > CACHE_TTL:
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        creds = Credentials.from_service_account_file("logs/app-project-sapo-plus-eb0edec5c0dc.json", scopes=SCOPES)
        client = gspread.authorize(creds)
        sheet_url = "https://docs.google.com/spreadsheets/d/1SNRlyLJqKCg5C0sRg75r23SO_Yqxdl8pHP2E0z55o94/edit?usp=sharing"
        worksheet = client.open_by_url(sheet_url).worksheet("NHAN_VIEN")  # Hoặc tên sheet cụ thể
        rows = worksheet.get_all_values()
        for i, row in enumerate(rows[1:], start=1):  # bỏ dòng tiêu đề
            try:
                # Bỏ qua dòng rỗng
                if not any(row):  
                    continue

                kho = str(row[0]).strip()
                name = str(row[1]).strip()
                vitri = str(row[2]).strip()
                pwd = str(row[3]).strip()
                status = str(row[4]).strip()

                # Bỏ dòng nếu thiếu câu hỏi hoặc câu trả lời chính
                if not kho or not name or status=='Đã nghỉ việc':
                    continue

                all_nhanvien.append({
                    "kho": kho,
                    "name": name,
                    "vitri": vitri,
                    "pwd": pwd,
                    "status": status
                })

            except Exception as e:
                print(f"[!] Lỗi tại dòng {i}: {e}")
                continue
        
        writejsonfile(all_nhanvien,'logs/log excel/all_nhanvien.json')
        writejsonfile(data,'logs/log excel/all_google_api.json')

        return all_nhanvien
    else:
        print("[+] Read from cache")
        all_ngaycong = json.loads(readfile('logs/log excel/all_nhanvien.json'))
        return all_ngaycong

def read_nhanvien_bangchamcong(read_new):
    all_ngaycong = []
    data = json.loads(readfile('logs/log excel/all_google_api.json'))
    now = datetime.datetime.utcnow()
    last = datetime.datetime.fromisoformat(data["time_read_ngaycong"])
    data["time_read_nhanvien"] = now.isoformat()
    if (now - last).total_seconds() > CACHE_TTL:
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        creds = Credentials.from_service_account_file("logs/app-project-sapo-plus-eb0edec5c0dc.json", scopes=SCOPES)
        client = gspread.authorize(creds)
        sheet_url = "https://docs.google.com/spreadsheets/d/1SNRlyLJqKCg5C0sRg75r23SO_Yqxdl8pHP2E0z55o94/edit?usp=sharing"
        worksheet = client.open_by_url(sheet_url).worksheet("CHAM_CONG")  # Hoặc tên sheet cụ thể
        # ==== BƯỚC 4: CHUYỂN DỮ LIỆU VÀO obj["qa"] ====

        rows = worksheet.get_all_values()

        for i, row in enumerate(rows[1:], start=1):  # bỏ dòng tiêu đề
            try:
                # Bỏ qua dòng rỗng
                if not any(row):  
                    continue

                date = str(row[1]).strip()
                kho = str(row[2]).strip()
                name = str(row[3]).strip()
                cong = float(row[4])

                # Bỏ dòng nếu thiếu câu hỏi hoặc câu trả lời chính
                if not kho or not name or not date:
                    continue

                all_ngaycong.append({
                    "date": date,
                    "kho": kho,
                    "name": name,
                    "cong": cong
                })

            except Exception as e:
                print(f"[!] Lỗi tại dòng {i}: {e}")
                continue
        writejsonfile(all_ngaycong,'logs/log excel/all_ngaycong.json')
        writejsonfile(data,'logs/log excel/all_google_api.json')

        return all_ngaycong
    else:
        all_ngaycong = json.loads(readfile('logs/log excel/all_ngaycong.json'))
        return all_ngaycong


def spapi_edit_note(ticket_customer_id, note_id, obj_data):
    try:
        # 1. Lấy nội dung note hiện tại
        url_get = f"{MAIN_URL}/customers/{ticket_customer_id}/notes/{note_id}.json"
        res_get = loginss.get(url_get)

        if res_get.status_code != 200:
            return {"status": "error", "msg": f"Không tìm thấy note ID {note_id}"}

        note_obj = res_get.json().get("note", {})
        note_obj["content"] = json.dumps(obj_data, ensure_ascii=False)

        # 2. Gửi PUT để cập nhật
        url_put = f"{MAIN_URL}/customers/{ticket_customer_id}/notes/{note_id}.json"
        res_put = loginss.put(url_put, json={"note": note_obj})

        if res_put.status_code == 200:
            return {"status": "success", "msg": "Cập nhật thành công", "note_id": note_id}
        else:
            return {"status": "error", "msg": f"Lỗi khi cập nhật: {res_put.text}"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}
        
def spapi_new_note(ticket_customer_id, obj_data):
    try:
        url_post = f"{MAIN_URL}/customers/{ticket_customer_id}/notes.json"
        payload = {
            "content": json.dumps(obj_data, ensure_ascii=False)
        }
        res = loginss.post(url_post, json=payload)

        if res.status_code == 201:
            new_id = res.json().get("note", {}).get("id")
            msg = {"status": "success", "msg": "Tạo mới thành công", "note_id": new_id}
        else:
            msg = {"status": "error", "msg": f"Lỗi khi tạo note: {res.text}"}
    except Exception as e:
        msg = {"status": "error", "msg": str(e)}
    print(msg)


from bs4 import BeautifulSoup, NavigableString, Tag
import re

NBSP = u'\xa0'

def _strip_nbsp(s: str) -> str:
    if s is None:
        return ''
    # Chuẩn hóa &nbsp; về khoảng trắng thường, rồi strip
    return re.sub(r'\s+', ' ', s.replace('&nbsp;', ' ').replace(NBSP, ' ')).strip()

def _is_meaningful_tag(tag: Tag) -> bool:
    """Một node được coi là 'có nội dung' nếu:
       - có text (sau khi bỏ &nbsp;) hoặc
       - chứa thẻ mang ý nghĩa trực quan: img, iframe, video, svg, source, picture, audio, canvas
       - chứa anchor có href
    """
    if isinstance(tag, NavigableString):
        return _strip_nbsp(str(tag)) != ''
    if not isinstance(tag, Tag):
        return False

    # Có text?
    if _strip_nbsp(tag.get_text(separator=' ', strip=True)) != '':
        return True

    # Có phần tử media/hyperlink?
    meaningful = tag.find(['img', 'iframe', 'video', 'svg', 'source', 'picture', 'audio', 'canvas'])
    if meaningful:
        return True
    a = tag.find('a', href=True)
    if a:
        return True

    # Không có gì đáng kể
    return False

def _is_empty_html_fragment(nodes) -> bool:
    """Kiểm tra một danh sách node HTML có rỗng (chỉ gồm rác &nbsp;/space) không."""
    for node in nodes:
        if isinstance(node, NavigableString):
            if _strip_nbsp(str(node)) != '':
                return False
        elif isinstance(node, Tag):
            if _is_meaningful_tag(node):
                return False
    return True

def _inner_html(tag: Tag) -> str:
    return ''.join(str(child) for child in tag.contents)

def _serialize_nodes_join_br(nodes) -> str:
    """Ghép các node HTML (đã lọc rỗng) bằng <br>."""
    pieces = []
    for node in nodes:
        if isinstance(node, NavigableString):
            txt = _strip_nbsp(str(node))
            if txt:
                pieces.append(txt)
        elif isinstance(node, Tag):
            if _is_meaningful_tag(node):
                pieces.append(str(node))
    # Loại bỏ phần tử rỗng còn sót và nối bằng <br>
    pieces = [p for p in pieces if _strip_nbsp(BeautifulSoup(p, 'html.parser').get_text()) or re.search(r'<(img|iframe|video|svg|audio|canvas)\b', p, re.I)]
    return ''.join(pieces)

def _parse_table_to_dict(table: Tag) -> dict:
    """Trả về dict {col1_text: col2_innerHTML}. Bỏ qua hàng rỗng.
       - Lấy 2 cột đầu tiên; nếu <th> xuất hiện ở hàng đầu coi như bình thường.
    """
    result = {}
    for tr in table.find_all('tr'):
        # Lấy cell theo thứ tự th/td
        cells = tr.find_all(['td', 'th'])
        if len(cells) < 2:
            continue
        key = _strip_nbsp(cells[0].get_text(separator=' ', strip=True))
        val_nodes = cells[1].contents
        # Bỏ các giá trị rỗng dạng <ul><li>&nbsp;</li></ul>…
        if key and not _is_empty_html_fragment(val_nodes):
            val_html = _inner_html(cells[1]).strip()
            # Nếu value sau khi chuẩn hóa vẫn trống text và không có thẻ ý nghĩa thì bỏ
            if _is_empty_html_fragment(cells[1].contents):
                continue
            result[key] = val_html
    return result

def parse_product_description(html: str):
    """Trả về list[dict] với mỗi dict:
        {
          "header": <text trong h2>,
          "content": <HTML không gồm table, các khối được nối bằng <br>, đã bỏ rỗng>,
          "table_content": {col1: col2_html, ...}
        }
    """
    soup = BeautifulSoup(html or '', 'html.parser')

    sections = []
    h2_list = soup.find_all('h2')
    if not h2_list:
        # Không có h2: gom toàn bộ thành 1 section 'Nội dung'
        all_tables = soup.find_all('table')
        table_dict = {}
        for tb in all_tables:
            table_dict.update(_parse_table_to_dict(tb))
            tb.decompose()
        # Content còn lại sau khi bỏ table
        rest_nodes = list(soup.body.children) if soup.body else list(soup.children)
        # Lọc các node rỗng
        if _is_empty_html_fragment(rest_nodes):
            content_html = ''
        else:
            content_html = _serialize_nodes_join_br(rest_nodes)
        return [{
            'header': 'Nội dung',
            'content': content_html,
            'table_content': table_dict
        }]

    # Có h2: cắt theo từng h2 -> next h2
    for idx, h2 in enumerate(h2_list):
        header = _strip_nbsp(h2.get_text(separator=' ', strip=True))
        # Lấy siblings từ sau h2 tới trước h2 kế
        nodes = []
        cursor = h2.next_sibling
        while cursor and not (isinstance(cursor, Tag) and cursor.name == 'h2'):
            nodes.append(cursor)
            cursor = cursor.next_sibling

        # Clone fragment để xử lý bảng
        frag_soup = BeautifulSoup(''.join(str(n) for n in nodes), 'html.parser')

        # Gom bảng
        table_dict = {}
        for tb in frag_soup.find_all('table'):
            table_dict.update(_parse_table_to_dict(tb))
            tb.decompose()  # bỏ table khỏi content

        # Content: nối phần còn lại bằng <br>, đồng thời loại rỗng
        rest_nodes = list(frag_soup.children)
        content_html = '' if _is_empty_html_fragment(rest_nodes) else _serialize_nodes_join_br(rest_nodes)

        # Nếu cả content và table đều rỗng thì bỏ qua section này
        if not content_html and not table_dict:
            continue

        sections.append({
            'header': header,
            'content': content_html,
            'table_content': table_dict
        })

    return sections
    
def log_safe(msg):
    print(msg, flush=True)


def put_customer(loginss, url, payload):
    RETRY_MAX = 4
    """
    Gửi PUT cập nhật khách hàng, có retry + backoff.
    Trả về True/False.
    """
    for attempt in range(RETRY_MAX):
        try:
            # Nếu loginss là requests.Session đã đăng nhập sẵn
            res = loginss.put(url, json=payload, timeout=60)
            if 200 <= res.status_code < 300:
                return True
            else:
                log_safe(f"[PUT] {url} status {res.status_code}: {res.text[:200]}")
        except Exception as e:
            log_safe(f"[PUT] Lỗi attempt {attempt+1}/{RETRY_MAX} cho {url}: {e}")

        if attempt < RETRY_MAX - 1:
            retry_backoff_sleep(attempt)

    return False

import json
from collections import OrderedDict
from copy import deepcopy

# ====== 1) Ánh xạ khóa ngắn/đầy đủ ======
SHORT = {
    "comment_id":"i","order_sn":"osn","shopee_order_id":"oid","brand":"b","ctime":"t",
    "rating_star":"r","product_id":"pid","variant_id":"vid","comment":"c",
    "images":"im","label":"L","tags":"g","low_rating_reasons":"lr"
}
INV_SHORT = {v: k for k, v in SHORT.items()}

def _dedup_images(images):
    if not images: return []
    # Giữ nguyên thứ tự, loại trùng
    seen, out = set(), []
    for x in images:
        if x not in seen:
            out.append(x); seen.add(x)
    return out

def _clean_payload(p: dict) -> dict:
    """Dọn dữ liệu để rút ký tự nhưng không mất thông tin hữu ích."""
    q = deepcopy(p)

    # Dedup ảnh
    if "images" in q:
        q["images"] = _dedup_images(q.get("images") or [])

    # Nếu variant_id trùng product_id thì bỏ (giảm ký tự)
    if q.get("variant_id") == q.get("product_id"):
        q.pop("variant_id", None)

    # Loại các trường rỗng để tiết kiệm ký tự (không đụng 0/False)
    for k in list(q.keys()):
        v = q[k]
        if v is None or v == "" or v == [] or v == {}:
            # Giữ lại 'images' nếu muốn luôn có mảng (tuỳ anh):
            if k == "images": 
                continue
            q.pop(k, None)

    return q

# ====== 2) PACK: rút gọn khóa + (tuỳ chọn) rút gọn giá trị, rồi minify JSON ======
def pack_note(payload: dict, *, shorten_values: bool = True) -> str:
    """
    Trả về chuỗi JSON minify với khóa ngắn.
    - shorten_values=True: 'label' -> số (-1/0/1) để giảm ký tự; có thể mở rộng thêm brand/tags nếu anh muốn.
    """
    cleaned = _clean_payload(payload)

    # Map khóa → ngắn; các khóa không nằm trong SHORT sẽ bị loại (tiết kiệm ký tự)
    compact = {}
    for k, v in cleaned.items():
        sk = SHORT.get(k)
        if sk:
            compact[sk] = v

    # Minify JSON (giữ Unicode, bỏ khoảng trắng)
    return json.dumps(compact, ensure_ascii=False, separators=(',', ':'))

# ====== 3) UNPACK: khôi phục về dict đầy đủ ======
def unpack_note(content: str, *, restore_values: bool = True) -> dict:
    """
    Nhận chuỗi JSON minify khóa ngắn → dict khóa đầy đủ.
    - restore_values=True: chuyển 'label' từ mã (-1/0/1) về chuỗi.
    """
    data = json.loads(content)
    out = {}
    for sk, v in data.items():
        k = INV_SHORT.get(sk, sk)
        out[k] = v

    if restore_values and "label" in out:
        lbl = out["label"]
        if isinstance(lbl, int) and lbl in CODE_TO_LABEL:
            out["label"] = CODE_TO_LABEL[lbl]

    # Bảo đảm kiểu dữ liệu/field cơ bản:
    if "ctime" in out:
        try: out["ctime"] = int(out["ctime"])
        except Exception: pass
    if "rating_star" in out:
        try: out["rating_star"] = int(out["rating_star"])
        except Exception: pass
    if "images" in out and out["images"] is None:
        out["images"] = []

    return out

def extract_brand_name(order: dict, default: str = "Gia Dụng Plus") -> str:
    """
    Lấy brand từ order['tags'][1] theo quy ước của anh.
    Có fallback: nếu không đủ phần tử, lấy tag nào KHÔNG thuộc nhóm marketplace.
    """
    tags = (order or {}).get("tags") or []
    if len(tags) >= 2 and isinstance(tags[1], str) and tags[1].strip():
        return tags[1].strip()

    # Fallback thông minh: loại bỏ các tag marketplace, lấy tag còn lại
    MARKETPLACE = {"Shopee", "Lazada", "Tiki", "TikTok", "TikTok Shop", "Sendo"}
    for t in tags:
        if 'Gia Dụng Plus' in t:
            t = "Gia Dụng Plus Official"

        if isinstance(t, str) and t.strip() and t.strip() not in MARKETPLACE:
            return t.strip()

    return default

def build_note_payload(comment: dict, order: dict) -> dict:
    """
    Chuẩn hoá payload JSON cho note:
    - Dedup images
    - variant_id lấy từ variant_id/model_id/product_id
    - low_rating_reasons chấp nhận list hoặc str
    - label theo rating_star: >=4 tích cực, 3 trung lập, <3 tiêu cực
    """
    if len(str(comment.get("low_rating_reasons"))) > 5:
        low_rating_reasons = comment["low_rating_reasons"][0]["low_rating_reasons"]["tag_name"]
    else:
        low_rating_reasons = ""

    if comment.get("reply") == None:
        reply_status = 0
    else:
        reply_status = 1
    payload = {
        "comment_id":       comment.get("comment_id"),
        "order_sn":         comment.get("order_sn"),
        "shopee_order_id":  comment.get("order_id"),
        "brand":            extract_brand_name(order),   # lấy từ order['tags'][1]
        "ctime":            int(comment.get("ctime", 0) or 0),
        "rating_star":      comment.get("rating_star"),
        "product_id":       comment.get("product_id"),
        "variant_id":       0,
        "comment":          (comment.get("comment") or "").strip(),
        "images":           comment.get("images"),
        "low_rating_reasons": low_rating_reasons,
        "reply": reply_status
        # cần thêm gì nữa thì bổ sung ở đây
    }

    return payload

#LẤY TOÀN BỘ VARIANTS
def get_all_variants(add_filter, return_type: str = "list"):
    all_vari = []
    for i in range(10):
        varis = js_get_url(f"{MAIN_URL}/variants.json?limit=250&page={int(i+1)}{add_filter}")["variants"]
        if len(varis) > 0:
            all_vari.extend(varis)
        else:
            break
    if return_type == "list":
        return all_vari
    if return_type == "json":
        all_vari_json = {}
        for vari in all_vari:
            all_vari_json[str(vari['id'])] = vari
        return all_vari_json

def get_all_products(add_filter, return_type: str = "list"):
    all_vari = []
    for i in range(10):
        varis = js_get_url(f"{MAIN_URL}/products.json?limit=250&page={int(i+1)}{add_filter}")["products"]
        if len(varis) > 0:
            all_vari.extend(varis)
        else:
            break
    if return_type == "list":
        return all_vari
    if return_type == "json":
        all_vari_json = {}
        for vari in all_vari:
            all_vari_json[str(vari['id'])] = vari
        return all_vari_json

def get_list_brand(return_type: str = "list"):
    brand_all = []
    brands = js_get_url(f"{MAIN_URL}/brands.json?limit=250&page=1")["brands"]

    for brand in brands:
        brand_all.append(brand)

    if return_type == "list":    
        return brand_all
    else:
        all_vari_json = {}
        for vari in brand_all:
            all_vari_json[str(vari['id'])] = vari
        return all_vari_json
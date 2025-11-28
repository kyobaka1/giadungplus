# products/management/commands/push_xnk_from_html.py
"""
Management command để push dữ liệu XNK từ file HTML cũ lên customer mới.
Usage: python manage.py push_xnk_from_html oldxnkmodel.html
"""

import json
import os
from django.core.management.base import BaseCommand
from bs4 import BeautifulSoup
from products.services.xnk_model_service import XNKModelService

# Import loginss từ thamkhao (thử nhiều cách)
loginss = None
try:
    # Thử import từ thamkhao.views hoặc thamkhao.functions
    from thamkhao.views import loginss
except ImportError:
    try:
        from thamkhao.functions import loginss
    except ImportError:
        # Fallback: dùng SapoClient
        from core.sapo_client import get_sapo_client
        sapo_client = get_sapo_client()
        # Gọi _ensure_logged_in để init session (nếu cần)
        try:
            sapo_client._ensure_logged_in()
        except:
            pass  # Nếu không login được, vẫn dùng session hiện tại
        loginss = sapo_client.core_session


class Command(BaseCommand):
    help = 'Push dữ liệu XNK từ file HTML lên customer mới'

    def add_arguments(self, parser):
        parser.add_argument('html_file', type=str, help='Đường dẫn đến file HTML chứa dữ liệu')
        parser.add_argument(
            '--customer-id',
            type=str,
            default='851379103',
            help='Customer ID để push dữ liệu (default: 851379103)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chạy thử không push dữ liệu thực tế'
        )

    def handle(self, *args, **options):
        html_file = options['html_file']
        customer_id = options['customer_id']
        dry_run = options['dry_run']

        if not os.path.exists(html_file):
            self.stdout.write(self.style.ERROR(f'File không tồn tại: {html_file}'))
            return

        self.stdout.write(f'Đang đọc file: {html_file}')
        self.stdout.write(f'Customer ID: {customer_id}')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - Không push dữ liệu thực tế'))

        # Đọc file HTML
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')

        # Tìm tất cả các row trong table
        rows = soup.find_all('tr', class_='js-xnk-row')
        self.stdout.write(f'Tìm thấy {len(rows)} rows trong HTML')

        if not rows:
            self.stdout.write(self.style.WARNING('Không tìm thấy dữ liệu trong HTML'))
            return

        # Tạo service với customer ID mới
        # Tạm thời override customer_id
        xnk_service = XNKModelService(loginss)
        xnk_service.customer_id = customer_id

        success_count = 0
        error_count = 0
        skipped_count = 0

        for idx, row in enumerate(rows, 1):
            try:
                # Lấy SKU từ data attribute
                sku = row.get('data-sku', '').strip()
                if not sku:
                    self.stdout.write(self.style.WARNING(f'Row {idx}: Không có SKU, bỏ qua'))
                    skipped_count += 1
                    continue

                # Lấy tất cả các cell trong row
                cells = row.find_all('td')
                if len(cells) < 11:
                    self.stdout.write(self.style.WARNING(f'Row {idx} (SKU: {sku}): Không đủ cột, bỏ qua'))
                    skipped_count += 1
                    continue

                # Parse dữ liệu từ các cell
                model_data = {
                    'sku': sku,
                }

                # Cell 0: SKU (đã có)
                # Cell 1: HS Code (ưu tiên lấy từ input trong edit mode)
                hs_code_cell = cells[1] if len(cells) > 1 else None
                if hs_code_cell:
                    hs_code_input = hs_code_cell.find('input', class_='xnk-input')
                    if hs_code_input:
                        hs_code = hs_code_input.get('value', '').strip()
                        if hs_code:
                            model_data['hs_code'] = hs_code
                    else:
                        hs_code_display = hs_code_cell.find(class_='xnk-display')
                        if hs_code_display:
                            hs_code = hs_code_display.get_text(strip=True)
                            if hs_code and hs_code != '-':
                                model_data['hs_code'] = hs_code

                # Cell 2: English Name (ưu tiên lấy từ input trong edit mode)
                en_name_cell = cells[2] if len(cells) > 2 else None
                if en_name_cell:
                    en_name_input = en_name_cell.find('input', class_='xnk-input')
                    if en_name_input:
                        en_name = en_name_input.get('value', '').strip()
                        if en_name:
                            model_data['en_name'] = en_name
                    else:
                        en_name_display = en_name_cell.find(class_='xnk-display')
                        if en_name_display:
                            en_name = en_name_display.get_text(strip=True)
                            if en_name and en_name != '-':
                                model_data['en_name'] = en_name

                # Cell 3: Vietnam Name (có thể bị truncate, lấy từ textarea trong edit mode)
                vn_name_cell = cells[3] if len(cells) > 3 else None
                if vn_name_cell:
                    # Ưu tiên lấy từ textarea trong edit mode (đầy đủ)
                    vn_name_edit = vn_name_cell.find('textarea', class_='xnk-input')
                    if vn_name_edit:
                        vn_name = vn_name_edit.get_text(strip=True)
                        if vn_name:
                            model_data['vn_name'] = vn_name
                    else:
                        # Fallback: lấy từ display (có thể bị truncate)
                        vn_name_display = vn_name_cell.find(class_='xnk-display')
                        if vn_name_display:
                            vn_name = vn_name_display.get_text(strip=True)
                            if vn_name and vn_name != '-' and not vn_name.endswith('…'):
                                model_data['vn_name'] = vn_name

                # Cell 4: USD Price (ưu tiên lấy từ input trong edit mode)
                usd_price_cell = cells[4] if len(cells) > 4 else None
                if usd_price_cell:
                    usd_price_input = usd_price_cell.find('input', class_='xnk-input')
                    if usd_price_input:
                        usd_price_value = usd_price_input.get('value', '').strip()
                        if usd_price_value:
                            try:
                                model_data['usd_price'] = float(usd_price_value)
                            except ValueError:
                                pass
                    else:
                        usd_price_display = usd_price_cell.find(class_='xnk-display')
                        if usd_price_display:
                            usd_price_text = usd_price_display.get_text(strip=True)
                            if usd_price_text and usd_price_text != '-':
                                # Remove $ sign and parse
                                usd_price_text = usd_price_text.replace('$', '').strip()
                                try:
                                    model_data['usd_price'] = float(usd_price_text)
                                except ValueError:
                                    pass

                # Cell 5: Unit (ưu tiên lấy từ input trong edit mode)
                unit_cell = cells[5] if len(cells) > 5 else None
                if unit_cell:
                    unit_input = unit_cell.find('input', class_='xnk-input')
                    if unit_input:
                        unit = unit_input.get('value', '').strip()
                        if unit:
                            model_data['unit'] = unit
                    else:
                        unit_display = unit_cell.find(class_='xnk-display')
                        if unit_display:
                            unit = unit_display.get_text(strip=True)
                            if unit and unit != '-':
                                model_data['unit'] = unit

                # Cell 6: NSX Name (có thể bị truncate, lấy từ input trong edit mode)
                nsx_name_cell = cells[6] if len(cells) > 6 else None
                if nsx_name_cell:
                    # Ưu tiên lấy từ input trong edit mode (đầy đủ)
                    nsx_name_input = nsx_name_cell.find('input', class_='xnk-input')
                    if nsx_name_input:
                        nsx_name = nsx_name_input.get('value', '').strip()
                        if nsx_name:
                            model_data['nsx_name'] = nsx_name
                    else:
                        # Fallback: lấy từ display
                        nsx_name_display = nsx_name_cell.find(class_='xnk-display')
                        if nsx_name_display:
                            nsx_name = nsx_name_display.get_text(strip=True)
                            if nsx_name and nsx_name != '-' and not nsx_name.endswith('…'):
                                model_data['nsx_name'] = nsx_name
                    
                    # NSX Address (nếu có trong data attributes hoặc từ nguồn khác)
                    # Có thể cần parse thêm từ các field khác

                # Cell 7: Tax VAT (ưu tiên lấy từ input trong edit mode)
                tax_vat_cell = cells[7] if len(cells) > 7 else None
                if tax_vat_cell:
                    tax_vat_input = tax_vat_cell.find('input', class_='xnk-input')
                    if tax_vat_input:
                        tax_vat_value = tax_vat_input.get('value', '').strip()
                        if tax_vat_value:
                            try:
                                model_data['tax_vat'] = float(tax_vat_value)
                            except ValueError:
                                pass
                    else:
                        tax_vat_display = tax_vat_cell.find(class_='xnk-display')
                        if tax_vat_display:
                            tax_vat_text = tax_vat_display.get_text(strip=True)
                            if tax_vat_text and tax_vat_text != '-':
                                # Remove % sign and parse
                                tax_vat_text = tax_vat_text.replace('%', '').strip()
                                try:
                                    tax_vat = float(tax_vat_text) / 100  # Convert from percentage to decimal
                                    model_data['tax_vat'] = tax_vat
                                except ValueError:
                                    pass

                # Cell 8: Tax NK (ưu tiên lấy từ input trong edit mode)
                tax_nk_cell = cells[8] if len(cells) > 8 else None
                if tax_nk_cell:
                    tax_nk_input = tax_nk_cell.find('input', class_='xnk-input')
                    if tax_nk_input:
                        tax_nk_value = tax_nk_input.get('value', '').strip()
                        if tax_nk_value:
                            try:
                                model_data['tax_nk'] = float(tax_nk_value)
                            except ValueError:
                                pass
                    else:
                        tax_nk_display = tax_nk_cell.find(class_='xnk-display')
                        if tax_nk_display:
                            tax_nk_text = tax_nk_display.get_text(strip=True)
                            if tax_nk_text and tax_nk_text != '-':
                                # Remove % sign and parse
                                tax_nk_text = tax_nk_text.replace('%', '').strip()
                                try:
                                    tax_nk = float(tax_nk_text) / 100  # Convert from percentage to decimal
                                    model_data['tax_nk'] = tax_nk
                                except ValueError:
                                    pass

                # Cell 9: China Name (ưu tiên lấy từ input trong edit mode)
                china_name_cell = cells[9] if len(cells) > 9 else None
                if china_name_cell:
                    china_name_input = china_name_cell.find('input', class_='xnk-input')
                    if china_name_input:
                        china_name = china_name_input.get('value', '').strip()
                        if china_name:
                            model_data['china_name'] = china_name
                    else:
                        china_name_display = china_name_cell.find(class_='xnk-display')
                        if china_name_display:
                            china_name = china_name_display.get_text(strip=True)
                            if china_name and china_name != '-':
                                model_data['china_name'] = china_name

                # Cell 10: Material (ưu tiên lấy từ input trong edit mode)
                material_cell = cells[10] if len(cells) > 10 else None
                if material_cell:
                    material_input = material_cell.find('input', class_='xnk-input')
                    if material_input:
                        material = material_input.get('value', '').strip()
                        if material:
                            model_data['material'] = material
                    else:
                        material_display = material_cell.find(class_='xnk-display')
                        if material_display:
                            material = material_display.get_text(strip=True)
                            if material and material != '-':
                                model_data['material'] = material

                # Kiểm tra xem model đã tồn tại chưa
                existing = xnk_service.get_model_by_sku(sku)
                if existing:
                    self.stdout.write(self.style.WARNING(f'Row {idx} (SKU: {sku}): Đã tồn tại, bỏ qua'))
                    skipped_count += 1
                    continue

                if dry_run:
                    self.stdout.write(f'[DRY RUN] Row {idx} (SKU: {sku}): Sẽ tạo với {len(model_data)} fields')
                    success_count += 1
                else:
                    # Push lên Sapo
                    result = xnk_service.create_model(model_data)
                    if result.get('status') == 'success':
                        self.stdout.write(self.style.SUCCESS(f'Row {idx} (SKU: {sku}): Tạo thành công'))
                        success_count += 1
                    else:
                        self.stdout.write(self.style.ERROR(f'Row {idx} (SKU: {sku}): Lỗi - {result.get("msg")}'))
                        error_count += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Row {idx}: Lỗi khi xử lý - {str(e)}'))
                error_count += 1

        # Tổng kết
        self.stdout.write('')
        self.stdout.write('=' * 50)
        self.stdout.write('TỔNG KẾT:')
        self.stdout.write(f'  - Thành công: {success_count}')
        self.stdout.write(f'  - Lỗi: {error_count}')
        self.stdout.write(f'  - Bỏ qua: {skipped_count}')
        self.stdout.write(f'  - Tổng: {len(rows)}')
        self.stdout.write('=' * 50)


# products/views_payment_spo.py
"""
Views cho quản trị thanh toán XNK (Payment SPO).
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpRequest
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods, require_POST
from django.db.models import Sum, Q, F
from django.db import transaction as db_transaction
from django.utils import timezone
from decimal import Decimal
from datetime import date, datetime
import logging

from kho.utils import admin_only
from products.models import (
    BalanceTransaction,
    PaymentPeriod,
    PaymentPeriodTransaction,
    PurchaseOrderPayment,
    SPOCost,
    PurchaseOrder,
    SumPurchaseOrder,
)

logger = logging.getLogger(__name__)


@admin_only
def payment_spo_list(request: HttpRequest):
    """
    Màn hình 1: Quản lý số dư và lịch sử giao dịch.
    - Hiển thị số dư hiện tại và tỷ giá hiện tại
    - Lịch sử các giao dịch nạp và rút
    - Có thể lọc theo loại (Nạp/Rút)
    - Có thể tích chọn các khoản nạp để tạo kỳ thanh toán
    """
    # Tính số dư hiện tại
    total_balance = BalanceTransaction.objects.aggregate(
        total=Sum('amount_cny')
    )['total'] or Decimal('0')
    
    # Tính tỷ giá hiện tại (tỷ giá trung bình của các giao dịch nạp gần nhất)
    recent_deposits = BalanceTransaction.objects.filter(
        transaction_type__in=['deposit_bank', 'deposit_black_market'],
        exchange_rate__isnull=False
    ).order_by('-transaction_date', '-created_at')[:10]
    
    current_exchange_rate = None
    if recent_deposits:
        total_cny = Decimal('0')
        weighted_rate = Decimal('0')
        for deposit in recent_deposits:
            if deposit.exchange_rate and deposit.amount_cny > 0:
                total_cny += deposit.amount_cny
                weighted_rate += deposit.amount_cny * deposit.exchange_rate
        if total_cny > 0:
            current_exchange_rate = weighted_rate / total_cny
    
    # Lấy lịch sử giao dịch
    filter_type = request.GET.get('type', '')  # 'deposit' hoặc 'withdraw'
    transactions = BalanceTransaction.objects.all().select_related().prefetch_related('payment_periods__payment_period')
    
    if filter_type == 'deposit':
        transactions = transactions.filter(transaction_type__in=['deposit_bank', 'deposit_black_market'])
    elif filter_type == 'withdraw':
        transactions = transactions.filter(transaction_type__in=['withdraw_po', 'withdraw_spo_cost'])
    
    # Lấy tất cả giao dịch và xác định KTT realtime cho từng giao dịch
    # Sắp xếp theo ngày giao dịch (transaction_date) - giao dịch gần nhất trước
    transactions_list = list(transactions)
    
    # Xác định KTT realtime cho từng giao dịch và lưu lại period để dùng cho hiển thị
    transactions_with_period = []
    for txn in transactions_list:
        # Xác định KTT realtime
        if txn.is_withdraw:
            # RÚT: xác định KTT realtime
            period = PaymentPeriod.find_period_for_transaction_datetime(txn.created_at, is_withdraw=True)
        else:
            # NẠP: lấy từ liên kết đã lưu
            period_txn = txn.payment_periods.first()
            period = period_txn.payment_period if period_txn else None
        
        # Lưu lại period để dùng cho hiển thị
        # Sử dụng transaction_date làm key chính, created_at làm key phụ (nếu cùng ngày)
        transactions_with_period.append((txn.transaction_date, txn.created_at, txn, period))
    
    # Sắp xếp theo ngày giao dịch: giao dịch gần nhất trước (transaction_date giảm dần)
    # Nếu cùng transaction_date thì sắp xếp theo created_at giảm dần
    transactions_with_period.sort(key=lambda x: (x[0], x[1]), reverse=True)
    
    # Lấy danh sách giao dịch đã sắp xếp cùng với period đã xác định
    sorted_transactions_with_period = [(txn, period) for _, _, txn, period in transactions_with_period]
    
    # Format transactions cho template
    transactions_data = []
    for txn, period in sorted_transactions_with_period:
        txn_data = {
            'id': txn.id,
            'transaction_type': txn.transaction_type,
            'transaction_type_display': txn.get_transaction_type_display(),
            'amount_cny': txn.amount_cny,
            'amount_vnd': txn.amount_vnd,
            'exchange_rate': txn.exchange_rate,
            'bank_name': txn.bank_name,
            'transaction_date': txn.transaction_date,
            'description': txn.description,
            'is_deposit': txn.is_deposit,
            'is_withdraw': txn.is_withdraw,
            'created_at': txn.created_at,  # Dùng để hiển thị giờ
        }
        
        # Sử dụng period đã xác định từ bước sắp xếp
        if period:
            txn_data['payment_period'] = {
                'id': period.id,
                'code': period.code,
                'name': period.name,
            }
            
            # Đối với giao dịch RÚT: đồng bộ lại liên kết trong DB (cập nhật nếu khác với liên kết cũ)
            if txn.is_withdraw:
                old_period_txn = txn.payment_periods.first()
                if not old_period_txn or old_period_txn.payment_period.id != period.id:
                    # Xóa liên kết cũ (nếu có)
                    if old_period_txn:
                        old_period_txn.delete()
                    # Tạo liên kết mới
                    PaymentPeriodTransaction.objects.get_or_create(
                        payment_period=period,
                        balance_transaction=txn
                    )
        
        # Thông tin chi tiết khi rút
        if txn.is_withdraw:
            if txn.purchase_order_payment:
                po_payment = txn.purchase_order_payment
                po = po_payment.purchase_order
                
                # Lấy supplier_name, nếu chưa có thì lấy từ Sapo API
                supplier_name = po.supplier_name
                if not supplier_name:
                    try:
                        from core.sapo_client import get_sapo_client
                        from products.services.spo_po_service import SPOPOService
                        sapo_client = get_sapo_client()
                        spo_po_service = SPOPOService(sapo_client)
                        po_data = spo_po_service.get_po_from_sapo(po.sapo_order_supplier_id)
                        supplier_name = po_data.get('supplier_name', '')
                        
                        # Cập nhật lại vào DB để lần sau không cần lấy lại
                        if supplier_name:
                            po.supplier_name = supplier_name
                            po.supplier_id = po_data.get('supplier_id', 0)
                            po.supplier_code = po_data.get('supplier_code', '')
                            po.save(update_fields=['supplier_name', 'supplier_id', 'supplier_code'])
                    except Exception as e:
                        logger.warning(f"[payment_spo_list] Error getting supplier name for PO {po.sapo_order_supplier_id}: {e}")
                        supplier_name = None
                
                txn_data['withdraw_info'] = {
                    'type': 'PO',
                    'po_id': po.id,
                    'po_code': po.sapo_order_supplier_id,
                    'spo_id': None,
                    'spo_code': None,
                    'supplier_name': supplier_name,
                    'payment_date': po_payment.payment_date,
                }
                # Tìm SPO chứa PO này (related_name là 'spo_relations')
                spo_po = po.spo_relations.first()
                if spo_po:
                    txn_data['withdraw_info']['spo_id'] = spo_po.sum_purchase_order.id
                    txn_data['withdraw_info']['spo_code'] = spo_po.sum_purchase_order.code
            elif txn.spo_cost:
                spo_cost = txn.spo_cost
                spo = spo_cost.sum_purchase_order
                txn_data['withdraw_info'] = {
                    'type': 'SPO Cost',
                    'spo_id': spo.id,
                    'spo_code': spo.code,
                    'cost_name': spo_cost.name,
                    'payment_date': spo_cost.created_at.date(),
                }
        
        transactions_data.append(txn_data)
    
    # Lấy danh sách kỳ thanh toán cho cột 2 - sắp xếp từ gần nhất đến xa nhất
    # Sắp xếp theo end_date (giảm dần), sau đó theo start_date (giảm dần), cuối cùng theo created_at (giảm dần)
    # Kỳ hiện tại = kỳ có end_date lớn nhất, nếu cùng end_date thì lấy kỳ có start_date lớn nhất, nếu vẫn cùng thì lấy kỳ tạo sau
    periods = PaymentPeriod.objects.all().order_by('-end_date', '-start_date', '-created_at')
    
    # Xác định kỳ hiện tại (kỳ gần đây nhất)
    # Logic: kỳ có end_date lớn nhất, nếu cùng end_date thì lấy kỳ có start_date lớn nhất, nếu vẫn cùng thì lấy kỳ tạo sau
    current_period_id = None
    if periods.exists():
        current_period = periods.first()  # Kỳ đầu tiên sau khi sắp xếp là kỳ gần nhất (hiện tại)
        current_period_id = current_period.id
    
    periods_data = []
    periods_data_json = []  # Dữ liệu cho JSON (chuyển date thành string)
    for period in periods:
        # Tỷ giá trung bình giờ tính realtime, không cần gọi calculate_avg_exchange_rate()
        
        period_dict = {
            'id': period.id,
            'code': period.code,
            'name': period.name,
            'start_date': period.start_date,
            'end_date': period.end_date,
            'opening_balance_cny': float(period.opening_balance_cny_realtime),  # Realtime từ kỳ trước
            'total_deposits_cny': float(period.total_deposits_cny_realtime),  # Realtime với datetime filter
            'total_withdraws_cny': float(period.total_withdraws_cny_realtime),  # Realtime với datetime filter
            'closing_balance_cny': float(period.closing_balance_cny_realtime),  # Realtime tính toán
            'avg_exchange_rate': float(period.avg_exchange_rate_realtime) if period.avg_exchange_rate_realtime else None,
            'note': period.note,
            'is_current': period.id == current_period_id,  # Đánh dấu kỳ hiện tại
        }
        periods_data.append(period_dict)
        
        # Tạo bản copy cho JSON (chuyển date thành string)
        period_dict_json = period_dict.copy()
        period_dict_json['start_date'] = period.start_date.isoformat() if period.start_date else None
        period_dict_json['end_date'] = period.end_date.isoformat() if period.end_date else None
        periods_data_json.append(period_dict_json)
    
    # Tính số tiền VNĐ quy đổi từ số dư hiện tại
    total_balance_vnd = None
    if current_exchange_rate and total_balance > 0:
        total_balance_vnd = int(float(total_balance * current_exchange_rate))
    
    # Chuyển periods_data sang JSON để dùng trong JavaScript
    import json
    periods_json = json.dumps(periods_data_json)
    
    context = {
        'total_balance': total_balance,
        'total_balance_vnd': total_balance_vnd,
        'current_exchange_rate': current_exchange_rate,
        'transactions': transactions_data,
        'filter_type': filter_type,
        'periods': periods_data,
        'periods_json': periods_json,  # JSON để dùng trong JavaScript
    }
    
    return render(request, 'products/payment_spo_list.html', context)


@admin_only
def payment_periods(request: HttpRequest):
    """
    Màn hình 2: Quản trị các kỳ thanh toán.
    Hiển thị đầy đủ thông tin các kỳ thanh toán.
    """
    periods = PaymentPeriod.objects.all().order_by('-start_date')
    
    periods_data = []
    for period in periods:
        # Tỷ giá trung bình giờ tính realtime, không cần gọi calculate_avg_exchange_rate()
        
        periods_data.append({
            'id': period.id,
            'code': period.code,
            'name': period.name,
            'start_date': period.start_date,
            'end_date': period.end_date,
            'opening_balance_cny': period.opening_balance_cny_realtime,  # Realtime từ kỳ trước
            'total_deposits_cny': period.total_deposits_cny,
            'total_withdraws_cny': period.total_withdraws_cny,
            'closing_balance_cny': period.closing_balance_cny_realtime,  # Realtime tính toán
            'avg_exchange_rate': period.avg_exchange_rate_realtime,
            'note': period.note,
        })
    
    context = {
        'periods': periods_data,
    }
    
    return render(request, 'products/payment_periods.html', context)


@admin_only
@require_POST
def add_balance_transaction(request: HttpRequest):
    """
    API endpoint để thêm giao dịch số dư (nạp).
    
    POST data:
    - transaction_type: 'deposit_bank' hoặc 'deposit_black_market'
    - amount_cny: float (bắt buộc)
    - amount_vnd: float (optional, nếu có thì tính tỷ giá)
    - exchange_rate: float (optional, nếu có thì tính amount_vnd)
    - bank_name: str (nếu là deposit_bank)
    - transaction_date: str (YYYY-MM-DD)
    - description: str (optional)
    """
    try:
        import json
        from datetime import datetime
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        transaction_type = data.get('transaction_type', '').strip()
        amount_cny = Decimal(str(data.get('amount_cny', 0)))
        amount_vnd = data.get('amount_vnd')
        exchange_rate = data.get('exchange_rate')
        bank_name = data.get('bank_name', '').strip()
        transaction_date_str = data.get('transaction_date', '').strip()
        description = data.get('description', '').strip()
        
        if transaction_type not in ['deposit_bank', 'deposit_black_market']:
            return JsonResponse({
                "status": "error",
                "message": "Loại giao dịch không hợp lệ"
            }, status=400)
        
        if amount_cny <= 0:
            return JsonResponse({
                "status": "error",
                "message": "Số tiền CNY phải lớn hơn 0"
            }, status=400)
        
        # Parse date
        transaction_date = None
        if transaction_date_str:
            try:
                transaction_date = datetime.strptime(transaction_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({
                    "status": "error",
                    "message": "Định dạng ngày không hợp lệ. Phải là YYYY-MM-DD"
                }, status=400)
        
        # Parse các giá trị số
        amount_vnd_decimal = Decimal(str(round(float(amount_vnd)))) if amount_vnd else None
        exchange_rate_decimal = Decimal(str(exchange_rate)) if exchange_rate else None
        
        # Tính giá trị còn lại nếu chưa có
        if amount_cny > 0 and exchange_rate_decimal and exchange_rate_decimal > 0 and (not amount_vnd_decimal or amount_vnd_decimal == 0):
            amount_vnd_decimal = Decimal(str(round(float(amount_cny * exchange_rate_decimal))))
        elif amount_cny > 0 and amount_vnd_decimal and amount_vnd_decimal > 0 and (not exchange_rate_decimal or exchange_rate_decimal == 0):
            exchange_rate_decimal = amount_vnd_decimal / amount_cny
        
        # Tạo giao dịch
        txn = BalanceTransaction.objects.create(
            transaction_type=transaction_type,
            amount_cny=amount_cny,
            amount_vnd=amount_vnd_decimal,
            exchange_rate=exchange_rate_decimal,
            bank_name=bank_name if transaction_type == 'deposit_bank' else '',
            transaction_date=transaction_date or timezone.now().date(),
            description=description,
            created_by=request.user if request.user.is_authenticated else None
        )
        
        # Tự động liên kết với PaymentPeriod nếu giao dịch nạp nằm trong khoảng thời gian của một kỳ
        # Logic mới: Chỉ tự động thêm vào KTT khi transaction_date nằm trong khoảng start_date -> end_date của KTT hiện có
        # Không tự động thêm vào KTT nếu ngoài thời gian các KTT hiện tại đang có
        from products.models import PaymentPeriod, PaymentPeriodTransaction
        
        # Kiểm tra xem transaction_date có nằm trong khoảng thời gian của một KTT nào không
        period = None
        transaction_date_to_check = txn.transaction_date or timezone.now().date()
        
        # Tìm KTT có transaction_date nằm trong khoảng start_date -> end_date
        matching_periods = PaymentPeriod.objects.filter(
            start_date__lte=transaction_date_to_check,
            end_date__gte=transaction_date_to_check
        ).order_by('-created_at')
        
        if matching_periods.exists():
            # Lấy KTT đầu tiên (gần nhất) nếu có nhiều KTT chồng lên nhau
            period = matching_periods.first()
        
        if period:
            # Tự động liên kết giao dịch nạp với kỳ thanh toán
            PaymentPeriodTransaction.objects.get_or_create(
                payment_period=period,
                balance_transaction=txn
            )
            
            # Sau khi thêm giao dịch mới, tự động thêm TẤT CẢ giao dịch nạp nằm trong khoảng transaction_date từ đầu đến cuối của KTT
            # Lấy tất cả giao dịch nạp trong kỳ (sau khi đã thêm giao dịch mới)
            period_deposits = period.period_transactions.filter(
                balance_transaction__transaction_type__in=['deposit_bank', 'deposit_black_market']
            ).select_related('balance_transaction').order_by('balance_transaction__transaction_date', 'balance_transaction__created_at')
            
            if period_deposits.exists():
                first_deposit = period_deposits.first().balance_transaction
                last_deposit = period_deposits.last().balance_transaction
                
                # Tìm TẤT CẢ giao dịch nạp nằm trong khoảng transaction_date từ first_deposit đến last_deposit
                start_date = first_deposit.transaction_date
                end_date = last_deposit.transaction_date
                
                # Lấy tất cả giao dịch nạp có transaction_date nằm trong khoảng [start_date, end_date]
                # Chỉ lấy các giao dịch nằm trong khoảng transaction_date, không dựa vào created_at
                all_deposits_in_range = BalanceTransaction.objects.filter(
                    transaction_type__in=['deposit_bank', 'deposit_black_market'],
                    transaction_date__gte=start_date,
                    transaction_date__lte=end_date
                )
                
                # Tự động thêm các giao dịch nạp chưa có trong KTT
                for deposit_txn in all_deposits_in_range:
                    PaymentPeriodTransaction.objects.get_or_create(
                        payment_period=period,
                        balance_transaction=deposit_txn
                    )
                
                # Cập nhật start_date và end_date của kỳ nếu cần
                new_start_date = first_deposit.transaction_date
                new_end_date = last_deposit.transaction_date
                
                update_needed = False
                if period.start_date != new_start_date:
                    period.start_date = new_start_date
                    update_needed = True
                if period.end_date != new_end_date:
                    period.end_date = new_end_date
                    update_needed = True
                
                if update_needed:
                    period.save(update_fields=['start_date', 'end_date'])
        
        return JsonResponse({
            "status": "success",
            "message": "Thêm giao dịch thành công",
            "transaction_id": txn.id
        })
        
    except Exception as e:
        logger.error(f"Error in add_balance_transaction: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def create_payment_period(request: HttpRequest):
    """
    API endpoint để tạo kỳ thanh toán từ các giao dịch nạp được chọn.
    
    POST data:
    - code: str (mã kỳ, ví dụ: KTT2025-001)
    - name: str (tên kỳ, optional)
    - start_date: str (YYYY-MM-DD)
    - end_date: str (YYYY-MM-DD)
    - transaction_ids: list[int] (danh sách ID các giao dịch nạp)
    - opening_balance_cny: float (số dư đầu kỳ, từ kỳ trước)
    - note: str (optional)
    """
    try:
        import json
        from datetime import datetime
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        name = data.get('name', '').strip()
        transaction_ids = data.get('transaction_ids', [])
        opening_balance_cny = Decimal(str(data.get('opening_balance_cny', 0)))
        note = data.get('note', '').strip()
        
        if not transaction_ids:
            return JsonResponse({
                "status": "error",
                "message": "Vui lòng chọn ít nhất một giao dịch nạp"
            }, status=400)
        
        # Lấy các giao dịch nạp từ danh sách transaction_ids đã chọn
        # Xác định giao dịch đầu và cuối (theo transaction_date) để lấy tất cả giao dịch ở giữa
        selected_transactions = BalanceTransaction.objects.filter(
            id__in=transaction_ids,
            transaction_type__in=['deposit_bank', 'deposit_black_market']
        ).order_by('transaction_date', 'created_at')
        
        if not selected_transactions.exists():
            return JsonResponse({
                "status": "error",
                "message": "Không tìm thấy giao dịch nạp nào trong danh sách đã chọn"
            }, status=400)
        
        # Lấy giao dịch đầu tiên và cuối cùng từ các giao dịch đã chọn (theo transaction_date)
        first_selected = selected_transactions.first()
        last_selected = selected_transactions.last()
        
        # start_date và end_date lấy từ transaction_date của giao dịch
        start_date = first_selected.transaction_date
        end_date = last_selected.transaction_date
        
        # Lấy TẤT CẢ các giao dịch nạp nằm trong khoảng transaction_date từ đầu đến cuối
        # Chỉ lấy các giao dịch có transaction_date nằm trong khoảng [start_date, end_date]
        # Bao gồm cả các giao dịch chưa được chọn nhưng nằm trong khoảng thời gian này
        deposit_transactions = BalanceTransaction.objects.filter(
            transaction_type__in=['deposit_bank', 'deposit_black_market'],
            transaction_date__gte=start_date,
            transaction_date__lte=end_date
        ).order_by('transaction_date', 'created_at')
        
        # Tự động tạo mã kỳ: KTT<năm>-STT
        year = start_date.year
        prefix = f"KTT{year}-"
        
        # Tìm số thứ tự cuối cùng trong năm
        last_period = PaymentPeriod.objects.filter(
            code__startswith=prefix
        ).order_by('-code').first()
        
        if last_period:
            try:
                # Extract số từ code (ví dụ: KTT2025-001 -> 001)
                last_num_str = last_period.code.split('-')[-1]
                last_num = int(last_num_str)
                new_num = last_num + 1
            except (ValueError, IndexError):
                new_num = 1
        else:
            new_num = 1
        
        # Tạo mã kỳ mới
        code = f"{prefix}{new_num:03d}"
        
        # Kiểm tra không có kỳ thanh toán nào chồng lên nhau
        # Logic theo MAKE.md: 2 kỳ thanh toán không thể có thời gian chồng lên nhau
        # Kỳ A: ngày 1 -> ngày 10, thì Kỳ B phải từ ngày 11 trở đi
        # Sử dụng transaction_date từ giao dịch nạp đầu tiên và cuối cùng
        existing_periods = PaymentPeriod.objects.all().prefetch_related('period_transactions__balance_transaction')
        for existing_period in existing_periods:
            existing_deposits = existing_period.period_transactions.filter(
                balance_transaction__transaction_type__in=['deposit_bank', 'deposit_black_market']
            ).select_related('balance_transaction').order_by('balance_transaction__transaction_date', 'balance_transaction__created_at')
            
            if existing_deposits.exists():
                existing_first_date = existing_deposits.first().balance_transaction.transaction_date
                existing_last_date = existing_deposits.last().balance_transaction.transaction_date
                
                # Kiểm tra chồng lên nhau: nếu có giao nhau về thời gian (transaction_date)
                # Kỳ mới: start_date -> end_date
                # Kỳ cũ: existing_first_date -> existing_last_date
                if not (end_date < existing_first_date or start_date > existing_last_date):
                    return JsonResponse({
                        "status": "error",
                        "message": f"Kỳ thanh toán '{existing_period.code}' đã tồn tại trong khoảng thời gian này. Hai kỳ thanh toán không thể có thời gian chồng lên nhau."
                    }, status=400)
        
        # Xác định số dư đầu kỳ:
        # - Nếu là kỳ đầu tiên: dùng opening_balance_cny từ input
        # - Nếu không phải kỳ đầu tiên: tự động tính từ kỳ trước (không cần input)
        previous_period = PaymentPeriod.objects.filter(
            created_at__lt=timezone.now()  # Tạm thời, sẽ được tính realtime
        ).order_by('-created_at').first()
        
        if previous_period:
            # Kỳ sau: tự động tính từ kỳ trước, bỏ qua opening_balance_cny từ input
            opening_balance_cny = Decimal('0')  # Không dùng, sẽ tính realtime
        # else: Kỳ đầu tiên: dùng opening_balance_cny từ input
        
        # Tạo kỳ thanh toán
        with db_transaction.atomic():
            period = PaymentPeriod.objects.create(
                code=code,
                name=name,
                start_date=start_date,
                end_date=end_date,
                opening_balance_cny=opening_balance_cny,  # Chỉ dùng cho kỳ đầu tiên
                note=note,
                created_by=request.user if request.user.is_authenticated else None
            )
            
            # Liên kết các giao dịch với kỳ
            for txn in deposit_transactions:
                PaymentPeriodTransaction.objects.create(
                    payment_period=period,
                    balance_transaction=txn
                )
            
            # Tỷ giá trung bình giờ tính realtime, không cần gọi calculate_avg_exchange_rate()
        
        return JsonResponse({
            "status": "success",
            "message": "Tạo kỳ thanh toán thành công",
            "period_id": period.id
        })
        
    except Exception as e:
        logger.error(f"Error in create_payment_period: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def edit_balance_transaction(request: HttpRequest, txn_id: int):
    """
    API endpoint để sửa giao dịch số dư.
    """
    try:
        import json
        from datetime import datetime
        
        txn = get_object_or_404(BalanceTransaction, id=txn_id)
        
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        transaction_type = data.get('transaction_type', '').strip()
        amount_cny = Decimal(str(data.get('amount_cny', 0)))
        amount_vnd = data.get('amount_vnd')
        exchange_rate = data.get('exchange_rate')
        bank_name = data.get('bank_name', '').strip()
        transaction_date_str = data.get('transaction_date', '').strip()
        description = data.get('description', '').strip()
        
        if transaction_type not in ['deposit_bank', 'deposit_black_market', 'withdraw_po', 'withdraw_spo_cost']:
            return JsonResponse({
                "status": "error",
                "message": "Loại giao dịch không hợp lệ"
            }, status=400)
        
        if amount_cny <= 0:
            return JsonResponse({
                "status": "error",
                "message": "Số tiền CNY phải lớn hơn 0"
            }, status=400)
        
        # Parse date
        transaction_date = None
        if transaction_date_str:
            try:
                transaction_date = datetime.strptime(transaction_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({
                    "status": "error",
                    "message": "Định dạng ngày không hợp lệ. Phải là YYYY-MM-DD"
                }, status=400)
        
        # Parse các giá trị số
        amount_vnd_decimal = Decimal(str(round(float(amount_vnd)))) if amount_vnd else None
        exchange_rate_decimal = Decimal(str(exchange_rate)) if exchange_rate else None
        
        # Tính giá trị còn lại nếu chưa có
        if amount_cny > 0 and exchange_rate_decimal and exchange_rate_decimal > 0 and (not amount_vnd_decimal or amount_vnd_decimal == 0):
            amount_vnd_decimal = Decimal(str(round(float(amount_cny * exchange_rate_decimal))))
        elif amount_cny > 0 and amount_vnd_decimal and amount_vnd_decimal > 0 and (not exchange_rate_decimal or exchange_rate_decimal == 0):
            exchange_rate_decimal = amount_vnd_decimal / amount_cny
        
        # Cập nhật giao dịch
        txn.transaction_type = transaction_type
        txn.amount_cny = amount_cny
        txn.amount_vnd = amount_vnd_decimal
        txn.exchange_rate = exchange_rate_decimal
        txn.bank_name = bank_name if transaction_type == 'deposit_bank' else ''
        if transaction_date:
            txn.transaction_date = transaction_date
        txn.description = description
        txn.save()
        
        return JsonResponse({
            "status": "success",
            "message": "Cập nhật giao dịch thành công",
            "transaction_id": txn.id
        })
        
    except Exception as e:
        logger.error(f"Error in edit_balance_transaction: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_http_methods(["DELETE"])
def delete_balance_transaction(request: HttpRequest, txn_id: int):
    """
    API endpoint để xóa giao dịch số dư.
    """
    try:
        txn = get_object_or_404(BalanceTransaction, id=txn_id)
        
        # Kiểm tra xem giao dịch đã thuộc kỳ thanh toán chưa
        if txn.payment_periods.exists():
            return JsonResponse({
                "status": "error",
                "message": "Không thể xóa giao dịch đã thuộc kỳ thanh toán"
            }, status=400)
        
        # Xóa giao dịch
        txn.delete()
        
        return JsonResponse({
            "status": "success",
            "message": "Xóa giao dịch thành công"
        })
        
    except Exception as e:
        logger.error(f"Error in delete_balance_transaction: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_http_methods(["DELETE"])
def delete_payment_period(request: HttpRequest, period_id: int):
    """
    Xóa kỳ thanh toán.
    
    Logic:
    - Xóa tất cả PaymentPeriodTransaction liên quan (bỏ liên kết với giao dịch)
    - Xóa PaymentPeriod
    - Các giao dịch (BalanceTransaction) không bị xóa, chỉ bỏ liên kết với kỳ
    
    Returns:
        JSON: {status, message}
    """
    try:
        period = get_object_or_404(PaymentPeriod, id=period_id)
        
        # Xóa tất cả PaymentPeriodTransaction liên quan
        PaymentPeriodTransaction.objects.filter(payment_period=period).delete()
        
        # Xóa kỳ thanh toán
        period_code = period.code
        period.delete()
        
        logger.info(f"Deleted payment period {period_code} (ID: {period_id}) by user {request.user}")
        
        return JsonResponse({
            "status": "success",
            "message": f"Xóa kỳ thanh toán '{period_code}' thành công"
        })
        
    except Exception as e:
        logger.error(f"Error in delete_payment_period: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


@admin_only
@require_POST
def add_transaction_to_period(request: HttpRequest, txn_id: int):
    """
    API endpoint để thêm giao dịch vào kỳ thanh toán theo mã kỳ.
    
    POST /payment-spo/transactions/<txn_id>/add-to-period/
    Body: {"period_code": "KTT2025-001"}
    """
    try:
        import json
        data = json.loads(request.body)
        period_code = data.get('period_code', '').strip()
        
        if not period_code:
            return JsonResponse({
                "status": "error",
                "message": "Mã kỳ thanh toán không được để trống"
            }, status=400)
        
        # Lấy giao dịch
        txn = get_object_or_404(BalanceTransaction, id=txn_id)
        
        # Kiểm tra xem giao dịch đã có kỳ thanh toán chưa
        existing_period_txn = PaymentPeriodTransaction.objects.filter(balance_transaction=txn).first()
        if existing_period_txn:
            return JsonResponse({
                "status": "error",
                "message": f"Giao dịch này đã thuộc kỳ thanh toán {existing_period_txn.payment_period.code}"
            }, status=400)
        
        # Tìm kỳ thanh toán theo mã
        period = PaymentPeriod.objects.filter(code=period_code).first()
        if not period:
            return JsonResponse({
                "status": "error",
                "message": f"Không tìm thấy kỳ thanh toán với mã: {period_code}"
            }, status=404)
        
        # Kiểm tra xem có thể thêm giao dịch này vào kỳ không
        # Nếu là giao dịch nạp, cần kiểm tra xem có nằm trong khoảng thời gian của kỳ không
        # (hoặc có thể mở rộng khoảng thời gian)
        is_deposit = txn.transaction_type in ['deposit_bank', 'deposit_black_market']
        added_count = 0  # Số lượng giao dịch được tự động thêm
        
        with db_transaction.atomic():
            # Tạo liên kết
            PaymentPeriodTransaction.objects.create(
                payment_period=period,
                balance_transaction=txn
            )
            
            # Nếu là giao dịch nạp, cần:
            # 1. Tự động thêm TẤT CẢ giao dịch nạp nằm trong khoảng transaction_date từ đầu đến cuối của KTT
            # 2. Cập nhật start_date/end_date của kỳ nếu cần
            if is_deposit:
                # Lấy tất cả giao dịch nạp trong kỳ (sau khi đã thêm giao dịch mới)
                period_deposits = period.period_transactions.filter(
                    balance_transaction__transaction_type__in=['deposit_bank', 'deposit_black_market']
                ).select_related('balance_transaction').order_by('balance_transaction__transaction_date', 'balance_transaction__created_at')
                
                if period_deposits.exists():
                    first_deposit = period_deposits.first().balance_transaction
                    last_deposit = period_deposits.last().balance_transaction
                    
                    # Tìm TẤT CẢ giao dịch nạp nằm trong khoảng transaction_date từ first_deposit đến last_deposit
                    # Chỉ lấy các giao dịch có transaction_date nằm trong khoảng [start_date, end_date]
                    start_date = first_deposit.transaction_date
                    end_date = last_deposit.transaction_date
                    
                    # Lấy tất cả giao dịch nạp có transaction_date nằm trong khoảng [start_date, end_date]
                    # Không dựa vào created_at
                    all_deposits_in_range = BalanceTransaction.objects.filter(
                        transaction_type__in=['deposit_bank', 'deposit_black_market'],
                        transaction_date__gte=start_date,
                        transaction_date__lte=end_date
                    )
                    
                    # Tự động thêm các giao dịch nạp chưa có trong KTT
                    for deposit_txn in all_deposits_in_range:
                        # Kiểm tra xem giao dịch đã có trong KTT chưa
                        existing_link = PaymentPeriodTransaction.objects.filter(
                            payment_period=period,
                            balance_transaction=deposit_txn
                        ).first()
                        
                        if not existing_link:
                            # Tự động thêm vào KTT
                            PaymentPeriodTransaction.objects.create(
                                payment_period=period,
                                balance_transaction=deposit_txn
                            )
                            added_count += 1
                    
                    # Cập nhật start_date và end_date dựa trên transaction_date
                    new_start_date = first_deposit.transaction_date
                    new_end_date = last_deposit.transaction_date
                    
                    update_needed = False
                    if period.start_date != new_start_date:
                        period.start_date = new_start_date
                        update_needed = True
                    if period.end_date != new_end_date:
                        period.end_date = new_end_date
                        update_needed = True
                    
                    if update_needed:
                        period.save(update_fields=['start_date', 'end_date'])
                    
                    # Thông báo nếu có giao dịch được tự động thêm
                    if added_count > 0:
                        logger.info(f"Auto-added {added_count} deposit transactions to period {period_code}")
        
        # Tạo message response
        if added_count > 0:
            message = f"Đã thêm giao dịch vào kỳ thanh toán {period_code}. Tự động thêm {added_count} giao dịch nạp khác nằm trong khoảng thời gian."
        else:
            message = f"Đã thêm giao dịch vào kỳ thanh toán {period_code}"
        
        return JsonResponse({
            "status": "success",
            "message": message,
            "period_id": period.id,
            "period_code": period.code,
            "period_name": period.name
        })
        
    except Exception as e:
        logger.error(f"Error in add_transaction_to_period: {e}", exc_info=True)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)


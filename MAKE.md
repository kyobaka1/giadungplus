Hãy cập nhật LOGIC cho payment-spo

-----TRƯỚC ĐÓ ĐÃ THỰC HIỆN-----------
**Quản trị kỳ thanh toán: Nạp**
- Tổng toàn bộ số tiền nạp vào trong thời điểm start-end (từ giao dịch cũ nhất -> giao dịch mới nhất).
- Nếu phát sinh giao dịch mới trong thời điểm này thì tự động cho vào KTT đó.
* Ví dụ: KTT từ ngày 1 đến ngày 15, hiện có 5 giao dịch nạp trong database, tổng là 10,000 rmb.
-> Thêm 1 giao dịch Nạp vào ngày 10 -> tự động giao dịch ngày 10 này sẽ được add vào KTT này. 
-> Nạp sẽ là tổng + tiền nạp của giao dịch mới thêm.

*Logic* Kì thanh toán là tất cả giao dịch trong 1 khoảng thời gian, từ lúc phát sinh giao dịch đầu tiên tới giao dịch cuối cùng. Trong khoảng thời gian đó đều là kì thanh toán đã tạo.
- 2 kì thanh toán không thể có thời gian chồng lên nhau. Không thể có 1 khoảng thời gian có 2 kì giao dịch.
- Tức là ngày 1-> 10h ngày 10 (Kì A) thì Kì B là phải 10:01 ngày 10 trở đi -> ngày xx. Vì tất cả giao dịch từ ngày 1 -> giao dịch cuối cùng của kì A ngày 10 -> thì đều là tự động thuộc về kì A.



**Quản trị kỳ thanh toán: Rút**
- Rút là những khoản giao dịch đã dùng tiền của kỳ thanh toán này. Tức là những khoản giao dịch phát sinh từ thời điểm start của KTT và có thể là sau cả enddate của kì thanh toán. (Chứ ko phải chỉ ở giữa start->end).
- Rút là việc xác định khoản thanh toán đó dùng số tiền của kỳ thanh toán nào. Chứ không phải là số tiền đã thanh toán trong thời gian kì thanh toán đó.

*Ví dụ* Nạp vào từ ngày 1 -> 10 số tiền là 10,000 rmb. Đến ngày 11 rút 2,000 rmb -> Giao dịch này đã dùng tiền của KTT từ ngày 1-> ngày 10.
Tức là khoảng trống giữa:
KTT A : Ngày 1-> 10
KTT B:  Ngày 13 -> ngày 15.

Thì nếu phát sinh giao dịch giữa khoảng trống giữa ngày 10 -> ngày 13. Thì số tiền đã dùng đó là của kì nạp KTT A. 
Nguyên tắc là có NẠP thì mới RÚT ra được.


**Tỷ giá TB của kỳ thanh toán (KTT)**
- Tỷ giá là realtime chứ không phải cố định.
- Tỷ giá của kì thanh toán được tính là: bình quân gia quyền của đầu kỳ thanh toán & tỷ giá trước đó + các giao dịch và tỷ giá trong kì hiện tại.

-> Cái muốn xác định là tỷ giá của số tiền đang có trong kì thanh toán đó, chứ ko phải là tỷ giá NẠP. Vì có thể còn tồn lại tiền của kì trước.

14/12/2025 12:23
Nạp qua ngân hàng
+2,000,000 CNY
(Tỷ giá: 2,000)
Kỳ: KTT2025-002 -> Thêm tên của kỳ thanh toán cho dễ nhận biết.

# Sửa lại phần chỗ KTT2025-002 -> thành nút bấm vào.
-> bấm vào KTT2025-002 sẽ hiên thị lên pannel với thông tin của KT2025-002
-> Như vậy sẽ dễ thấy hơn so với việc phải tìm kiếm thông tin kì thanh toán.


*Phát triển* Tính năng sửa giao dịch đang được phát triển
*Thêm tính năg* Nút thêm -> có thể vào KTT theo mã kì thanh toán. Nếu thêm vào -> tính toán lại kì thanh toán.


-----YÊU CẦU MỚI-----------
Kiểm tra đoạn HTML bên dưới và sửa lại logic:

Hôm nay 12:40
Rút - Thanh toán PO
--20,000,000 CNY

-> Khoản giao dịch này phát sinh ra trong KTT KTT2025-002
-> Nhưng lại ghi nhận RÚT trong KTT2025-003
-> Trong khi kì 3 là giao dịch từ cuối cùng cho đến giao dịch Mua chợ đen 3000 CNY. Hôm nay 10:55




<div class="divide-y divide-slate-100 max-h-[600px] overflow-y-auto">
                    
                    <div class="p-3 hover:bg-slate-50 transition group/item border-b border-slate-100 last:border-b-0 bg-blue-50/20">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <!-- Hàng 1: Ngày giờ + Loại + Số tiền (gộp thành 1 hàng) -->
                                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 timeline-date" data-date="2025-12-14" data-time="12:23"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-500">14/12/2025</span> <span class="text-[10px] text-slate-400 ml-1">12:23</span></span>
                                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold 
                                        bg-blue-100 text-blue-700
                                        ">
                                        Nạp qua ngân hàng
                                    </span>
                                    <span class="text-sm font-bold text-emerald-700">
                                        +2,000,000 CNY
                                    </span>
                                    
                                    <span class="text-[10px] text-slate-500">
                                        (Tỷ giá: 2,000)
                                    </span>
                                    
                                </div>
                                
                                <!-- Hàng 2: Thông tin chi tiết -->
                                <div class="text-[10px] text-slate-500 space-y-0.5">
                                    
                                    
                                    
                                    <div class="flex items-center gap-1">
                                        <span class="text-slate-500 text-[10px]">Kỳ:</span>
                                        <button onclick="showPeriodDetail(8)" class="text-indigo-600 hover:text-indigo-800 font-medium text-[10px] underline decoration-dotted hover:decoration-solid transition">
                                            KTT2025-002 - Kì 2
                                        </button>
                                    </div>
                                    
                                    
                                </div>
                            </div>
                            <div class="flex items-center gap-1 flex-shrink-0">
                                
                                
                                <button onclick="editTransaction(12)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Sửa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                    </svg>
                                </button>
                                <button onclick="deleteTransaction(12)" class="p-1 text-slate-400 hover:text-red-600 opacity-0 group-hover/item:opacity-100 transition" title="Xóa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="p-3 hover:bg-slate-50 transition group/item border-b border-slate-100 last:border-b-0 bg-red-50/20">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <!-- Hàng 1: Ngày giờ + Loại + Số tiền (gộp thành 1 hàng) -->
                                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 timeline-date" data-date="2025-12-13" data-time="12:40"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700">Hôm nay</span> <span class="text-[10px] text-slate-400 ml-1">12:40</span></span>
                                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold 
                                        bg-red-100 text-red-700">
                                        Rút - Thanh toán PO
                                    </span>
                                    <span class="text-sm font-bold text-red-700">
                                        --20,000,000 CNY
                                    </span>
                                    
                                </div>
                                
                                <!-- Hàng 2: Thông tin chi tiết -->
                                <div class="text-[10px] text-slate-500 space-y-0.5">
                                    
                                    
                                    <p class="truncate">Thanh toán PO 515159</p>
                                    
                                    
                                    
                                    <div class="mt-1 p-1.5 bg-slate-100 rounded text-[10px]">
                                        <p class="font-semibold mb-0.5">Rút để thanh toán:</p>
                                        
                                        <p>PO: <a href="/products/sum-purchase-orders/1/" class="text-indigo-600 hover:underline">515159</a></p>
                                        <p>NSX: LOGSHEG</p>
                                        <p>SPO: <a href="/products/sum-purchase-orders/1/" class="text-indigo-600 hover:underline">SPO-2025-001</a></p>
                                        
                                    </div>
                                    
                                </div>
                            </div>
                            <div class="flex items-center gap-1 flex-shrink-0">
                                
                                
                                <button onclick="openAddToPeriodModal(13)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Thêm vào KTT">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
                                    </svg>
                                </button>
                                
                                <button onclick="editTransaction(13)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Sửa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                    </svg>
                                </button>
                                <button onclick="deleteTransaction(13)" class="p-1 text-slate-400 hover:text-red-600 opacity-0 group-hover/item:opacity-100 transition" title="Xóa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="p-3 hover:bg-slate-50 transition group/item border-b border-slate-100 last:border-b-0 bg-blue-50/20">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <!-- Hàng 1: Ngày giờ + Loại + Số tiền (gộp thành 1 hàng) -->
                                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 timeline-date" data-date="2025-12-13" data-time="12:16"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700">Hôm nay</span> <span class="text-[10px] text-slate-400 ml-1">12:16</span></span>
                                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold 
                                        bg-blue-100 text-blue-700
                                        ">
                                        Nạp qua ngân hàng
                                    </span>
                                    <span class="text-sm font-bold text-emerald-700">
                                        +2,000 CNY
                                    </span>
                                    
                                    <span class="text-[10px] text-slate-500">
                                        (Tỷ giá: 3,600)
                                    </span>
                                    
                                </div>
                                
                                <!-- Hàng 2: Thông tin chi tiết -->
                                <div class="text-[10px] text-slate-500 space-y-0.5">
                                    
                                    
                                    
                                    <div class="flex items-center gap-1">
                                        <span class="text-slate-500 text-[10px]">Kỳ:</span>
                                        <button onclick="showPeriodDetail(8)" class="text-indigo-600 hover:text-indigo-800 font-medium text-[10px] underline decoration-dotted hover:decoration-solid transition">
                                            KTT2025-002 - Kì 2
                                        </button>
                                    </div>
                                    
                                    
                                </div>
                            </div>
                            <div class="flex items-center gap-1 flex-shrink-0">
                                
                                
                                <button onclick="editTransaction(11)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Sửa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                    </svg>
                                </button>
                                <button onclick="deleteTransaction(11)" class="p-1 text-slate-400 hover:text-red-600 opacity-0 group-hover/item:opacity-100 transition" title="Xóa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="p-3 hover:bg-slate-50 transition group/item border-b border-slate-100 last:border-b-0 bg-red-50/20">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <!-- Hàng 1: Ngày giờ + Loại + Số tiền (gộp thành 1 hàng) -->
                                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 timeline-date" data-date="2025-12-13" data-time="11:52"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700">Hôm nay</span> <span class="text-[10px] text-slate-400 ml-1">11:52</span></span>
                                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold 
                                        bg-red-100 text-red-700">
                                        Rút - Thanh toán PO
                                    </span>
                                    <span class="text-sm font-bold text-red-700">
                                        --14,117 CNY
                                    </span>
                                    
                                </div>
                                
                                <!-- Hàng 2: Thông tin chi tiết -->
                                <div class="text-[10px] text-slate-500 space-y-0.5">
                                    
                                    
                                    <p class="truncate">Thanh toán PO 515159</p>
                                    
                                    
                                    
                                    <div class="mt-1 p-1.5 bg-slate-100 rounded text-[10px]">
                                        <p class="font-semibold mb-0.5">Rút để thanh toán:</p>
                                        
                                        <p>PO: <a href="/products/sum-purchase-orders/1/" class="text-indigo-600 hover:underline">515159</a></p>
                                        <p>NSX: LOGSHEG</p>
                                        <p>SPO: <a href="/products/sum-purchase-orders/1/" class="text-indigo-600 hover:underline">SPO-2025-001</a></p>
                                        
                                    </div>
                                    
                                </div>
                            </div>
                            <div class="flex items-center gap-1 flex-shrink-0">
                                
                                
                                <button onclick="openAddToPeriodModal(10)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Thêm vào KTT">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
                                    </svg>
                                </button>
                                
                                <button onclick="editTransaction(10)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Sửa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                    </svg>
                                </button>
                                <button onclick="deleteTransaction(10)" class="p-1 text-slate-400 hover:text-red-600 opacity-0 group-hover/item:opacity-100 transition" title="Xóa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="p-3 hover:bg-slate-50 transition group/item border-b border-slate-100 last:border-b-0 bg-red-50/20">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <!-- Hàng 1: Ngày giờ + Loại + Số tiền (gộp thành 1 hàng) -->
                                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 timeline-date" data-date="2025-12-13" data-time="11:02"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700">Hôm nay</span> <span class="text-[10px] text-slate-400 ml-1">11:02</span></span>
                                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold 
                                        bg-red-100 text-red-700">
                                        Rút - Thanh toán PO
                                    </span>
                                    <span class="text-sm font-bold text-red-700">
                                        --20,000 CNY
                                    </span>
                                    
                                </div>
                                
                                <!-- Hàng 2: Thông tin chi tiết -->
                                <div class="text-[10px] text-slate-500 space-y-0.5">
                                    
                                    
                                    <p class="truncate">Thanh toán PO 515159</p>
                                    
                                    
                                    
                                    <div class="mt-1 p-1.5 bg-slate-100 rounded text-[10px]">
                                        <p class="font-semibold mb-0.5">Rút để thanh toán:</p>
                                        
                                        <p>PO: <a href="/products/sum-purchase-orders/1/" class="text-indigo-600 hover:underline">515159</a></p>
                                        <p>NSX: LOGSHEG</p>
                                        <p>SPO: <a href="/products/sum-purchase-orders/1/" class="text-indigo-600 hover:underline">SPO-2025-001</a></p>
                                        
                                    </div>
                                    
                                </div>
                            </div>
                            <div class="flex items-center gap-1 flex-shrink-0">
                                
                                
                                <button onclick="openAddToPeriodModal(9)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Thêm vào KTT">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
                                    </svg>
                                </button>
                                
                                <button onclick="editTransaction(9)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Sửa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                    </svg>
                                </button>
                                <button onclick="deleteTransaction(9)" class="p-1 text-slate-400 hover:text-red-600 opacity-0 group-hover/item:opacity-100 transition" title="Xóa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="p-3 hover:bg-slate-50 transition group/item border-b border-slate-100 last:border-b-0 bg-blue-50/20">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <!-- Hàng 1: Ngày giờ + Loại + Số tiền (gộp thành 1 hàng) -->
                                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 timeline-date" data-date="2025-12-13" data-time="10:55"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700">Hôm nay</span> <span class="text-[10px] text-slate-400 ml-1">10:55</span></span>
                                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold 
                                        bg-blue-100 text-blue-700
                                        ">
                                        Nạp qua ngân hàng
                                    </span>
                                    <span class="text-sm font-bold text-emerald-700">
                                        +5,000 CNY
                                    </span>
                                    
                                    <span class="text-[10px] text-slate-500">
                                        (Tỷ giá: 2,000)
                                    </span>
                                    
                                </div>
                                
                                <!-- Hàng 2: Thông tin chi tiết -->
                                <div class="text-[10px] text-slate-500 space-y-0.5">
                                    
                                    
                                    
                                    <div class="flex items-center gap-1">
                                        <span class="text-slate-500 text-[10px]">Kỳ:</span>
                                        <button onclick="showPeriodDetail(8)" class="text-indigo-600 hover:text-indigo-800 font-medium text-[10px] underline decoration-dotted hover:decoration-solid transition">
                                            KTT2025-002 - Kì 2
                                        </button>
                                    </div>
                                    
                                    
                                </div>
                            </div>
                            <div class="flex items-center gap-1 flex-shrink-0">
                                
                                
                                <button onclick="editTransaction(8)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Sửa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                    </svg>
                                </button>
                                <button onclick="deleteTransaction(8)" class="p-1 text-slate-400 hover:text-red-600 opacity-0 group-hover/item:opacity-100 transition" title="Xóa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="p-3 hover:bg-slate-50 transition group/item border-b border-slate-100 last:border-b-0 bg-slate-900/3">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <!-- Hàng 1: Ngày giờ + Loại + Số tiền (gộp thành 1 hàng) -->
                                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 timeline-date" data-date="2025-12-13" data-time="10:55"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700">Hôm nay</span> <span class="text-[10px] text-slate-400 ml-1">10:55</span></span>
                                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold 
                                        bg-slate-800 text-white
                                        ">
                                        Mua chợ đen
                                    </span>
                                    <span class="text-sm font-bold text-emerald-700">
                                        +3,000 CNY
                                    </span>
                                    
                                    <span class="text-[10px] text-slate-500">
                                        (Tỷ giá: 4,000)
                                    </span>
                                    
                                </div>
                                
                                <!-- Hàng 2: Thông tin chi tiết -->
                                <div class="text-[10px] text-slate-500 space-y-0.5">
                                    
                                    
                                    
                                    <div class="flex items-center gap-1">
                                        <span class="text-slate-500 text-[10px]">Kỳ:</span>
                                        <button onclick="showPeriodDetail(9)" class="text-indigo-600 hover:text-indigo-800 font-medium text-[10px] underline decoration-dotted hover:decoration-solid transition">
                                            KTT2025-003 - Kì 1
                                        </button>
                                    </div>
                                    
                                    
                                </div>
                            </div>
                            <div class="flex items-center gap-1 flex-shrink-0">
                                
                                
                                <button onclick="editTransaction(7)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Sửa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                    </svg>
                                </button>
                                <button onclick="deleteTransaction(7)" class="p-1 text-slate-400 hover:text-red-600 opacity-0 group-hover/item:opacity-100 transition" title="Xóa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="p-3 hover:bg-slate-50 transition group/item border-b border-slate-100 last:border-b-0 bg-slate-900/3">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <!-- Hàng 1: Ngày giờ + Loại + Số tiền (gộp thành 1 hàng) -->
                                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 timeline-date" data-date="2025-12-13" data-time="10:54"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700">Hôm nay</span> <span class="text-[10px] text-slate-400 ml-1">10:54</span></span>
                                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold 
                                        bg-slate-800 text-white
                                        ">
                                        Mua chợ đen
                                    </span>
                                    <span class="text-sm font-bold text-emerald-700">
                                        +2,000 CNY
                                    </span>
                                    
                                    <span class="text-[10px] text-slate-500">
                                        (Tỷ giá: 3,900)
                                    </span>
                                    
                                </div>
                                
                                <!-- Hàng 2: Thông tin chi tiết -->
                                <div class="text-[10px] text-slate-500 space-y-0.5">
                                    
                                    
                                    
                                    <div class="flex items-center gap-1">
                                        <span class="text-slate-500 text-[10px]">Kỳ:</span>
                                        <button onclick="showPeriodDetail(9)" class="text-indigo-600 hover:text-indigo-800 font-medium text-[10px] underline decoration-dotted hover:decoration-solid transition">
                                            KTT2025-003 - Kì 1
                                        </button>
                                    </div>
                                    
                                    
                                </div>
                            </div>
                            <div class="flex items-center gap-1 flex-shrink-0">
                                
                                
                                <button onclick="editTransaction(6)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Sửa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                    </svg>
                                </button>
                                <button onclick="deleteTransaction(6)" class="p-1 text-slate-400 hover:text-red-600 opacity-0 group-hover/item:opacity-100 transition" title="Xóa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="p-3 hover:bg-slate-50 transition group/item border-b border-slate-100 last:border-b-0 bg-blue-50/20">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <!-- Hàng 1: Ngày giờ + Loại + Số tiền (gộp thành 1 hàng) -->
                                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 timeline-date" data-date="2025-12-13" data-time="10:36"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700">Hôm nay</span> <span class="text-[10px] text-slate-400 ml-1">10:36</span></span>
                                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold 
                                        bg-blue-100 text-blue-700
                                        ">
                                        Nạp qua ngân hàng
                                    </span>
                                    <span class="text-sm font-bold text-emerald-700">
                                        +20,000,000 CNY
                                    </span>
                                    
                                    <span class="text-[10px] text-slate-500">
                                        (Tỷ giá: 4,000)
                                    </span>
                                    
                                </div>
                                
                                <!-- Hàng 2: Thông tin chi tiết -->
                                <div class="text-[10px] text-slate-500 space-y-0.5">
                                    
                                    
                                    
                                    <div class="flex items-center gap-1">
                                        <span class="text-slate-500 text-[10px]">Kỳ:</span>
                                        <button onclick="showPeriodDetail(9)" class="text-indigo-600 hover:text-indigo-800 font-medium text-[10px] underline decoration-dotted hover:decoration-solid transition">
                                            KTT2025-003 - Kì 1
                                        </button>
                                    </div>
                                    
                                    
                                </div>
                            </div>
                            <div class="flex items-center gap-1 flex-shrink-0">
                                
                                
                                <button onclick="editTransaction(5)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Sửa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                    </svg>
                                </button>
                                <button onclick="deleteTransaction(5)" class="p-1 text-slate-400 hover:text-red-600 opacity-0 group-hover/item:opacity-100 transition" title="Xóa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="p-3 hover:bg-slate-50 transition group/item border-b border-slate-100 last:border-b-0 bg-slate-900/3">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <!-- Hàng 1: Ngày giờ + Loại + Số tiền (gộp thành 1 hàng) -->
                                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 timeline-date" data-date="2025-12-13" data-time="10:35"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700">Hôm nay</span> <span class="text-[10px] text-slate-400 ml-1">10:35</span></span>
                                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold 
                                        bg-slate-800 text-white
                                        ">
                                        Mua chợ đen
                                    </span>
                                    <span class="text-sm font-bold text-emerald-700">
                                        +16,000 CNY
                                    </span>
                                    
                                    <span class="text-[10px] text-slate-500">
                                        (Tỷ giá: 4,000)
                                    </span>
                                    
                                </div>
                                
                                <!-- Hàng 2: Thông tin chi tiết -->
                                <div class="text-[10px] text-slate-500 space-y-0.5">
                                    
                                    
                                    
                                    <div class="flex items-center gap-1">
                                        <span class="text-slate-500 text-[10px]">Kỳ:</span>
                                        <button onclick="showPeriodDetail(9)" class="text-indigo-600 hover:text-indigo-800 font-medium text-[10px] underline decoration-dotted hover:decoration-solid transition">
                                            KTT2025-003 - Kì 1
                                        </button>
                                    </div>
                                    
                                    
                                </div>
                            </div>
                            <div class="flex items-center gap-1 flex-shrink-0">
                                
                                
                                <button onclick="editTransaction(4)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Sửa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                    </svg>
                                </button>
                                <button onclick="deleteTransaction(4)" class="p-1 text-slate-400 hover:text-red-600 opacity-0 group-hover/item:opacity-100 transition" title="Xóa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="p-3 hover:bg-slate-50 transition group/item border-b border-slate-100 last:border-b-0 bg-blue-50/20">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <!-- Hàng 1: Ngày giờ + Loại + Số tiền (gộp thành 1 hàng) -->
                                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 timeline-date" data-date="2025-12-13" data-time="10:33"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700">Hôm nay</span> <span class="text-[10px] text-slate-400 ml-1">10:33</span></span>
                                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold 
                                        bg-blue-100 text-blue-700
                                        ">
                                        Nạp qua ngân hàng
                                    </span>
                                    <span class="text-sm font-bold text-emerald-700">
                                        +2,000 CNY
                                    </span>
                                    
                                    <span class="text-[10px] text-slate-500">
                                        (Tỷ giá: 3,200)
                                    </span>
                                    
                                </div>
                                
                                <!-- Hàng 2: Thông tin chi tiết -->
                                <div class="text-[10px] text-slate-500 space-y-0.5">
                                    
                                    
                                    
                                    <div class="flex items-center gap-1">
                                        <span class="text-slate-500 text-[10px]">Kỳ:</span>
                                        <button onclick="showPeriodDetail(9)" class="text-indigo-600 hover:text-indigo-800 font-medium text-[10px] underline decoration-dotted hover:decoration-solid transition">
                                            KTT2025-003 - Kì 1
                                        </button>
                                    </div>
                                    
                                    
                                </div>
                            </div>
                            <div class="flex items-center gap-1 flex-shrink-0">
                                
                                
                                <button onclick="editTransaction(3)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Sửa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                    </svg>
                                </button>
                                <button onclick="deleteTransaction(3)" class="p-1 text-slate-400 hover:text-red-600 opacity-0 group-hover/item:opacity-100 transition" title="Xóa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="p-3 hover:bg-slate-50 transition group/item border-b border-slate-100 last:border-b-0 bg-blue-50/20">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <!-- Hàng 1: Ngày giờ + Loại + Số tiền (gộp thành 1 hàng) -->
                                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 timeline-date" data-date="2025-12-13" data-time="10:33"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700">Hôm nay</span> <span class="text-[10px] text-slate-400 ml-1">10:33</span></span>
                                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold 
                                        bg-blue-100 text-blue-700
                                        ">
                                        Nạp qua ngân hàng
                                    </span>
                                    <span class="text-sm font-bold text-emerald-700">
                                        +20,000,000 CNY
                                    </span>
                                    
                                    <span class="text-[10px] text-slate-500">
                                        (Tỷ giá: 3,800)
                                    </span>
                                    
                                </div>
                                
                                <!-- Hàng 2: Thông tin chi tiết -->
                                <div class="text-[10px] text-slate-500 space-y-0.5">
                                    
                                    
                                    
                                    <div class="flex items-center gap-1">
                                        <span class="text-slate-500 text-[10px]">Kỳ:</span>
                                        <button onclick="showPeriodDetail(9)" class="text-indigo-600 hover:text-indigo-800 font-medium text-[10px] underline decoration-dotted hover:decoration-solid transition">
                                            KTT2025-003 - Kì 1
                                        </button>
                                    </div>
                                    
                                    
                                </div>
                            </div>
                            <div class="flex items-center gap-1 flex-shrink-0">
                                
                                
                                <button onclick="editTransaction(2)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Sửa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                    </svg>
                                </button>
                                <button onclick="deleteTransaction(2)" class="p-1 text-slate-400 hover:text-red-600 opacity-0 group-hover/item:opacity-100 transition" title="Xóa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="p-3 hover:bg-slate-50 transition group/item border-b border-slate-100 last:border-b-0 bg-blue-50/20">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <!-- Hàng 1: Ngày giờ + Loại + Số tiền (gộp thành 1 hàng) -->
                                <div class="flex items-center gap-2 mb-1.5 flex-wrap">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 timeline-date" data-date="2025-12-13" data-time="10:33"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700">Hôm nay</span> <span class="text-[10px] text-slate-400 ml-1">10:33</span></span>
                                    <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold 
                                        bg-blue-100 text-blue-700
                                        ">
                                        Nạp qua ngân hàng
                                    </span>
                                    <span class="text-sm font-bold text-emerald-700">
                                        +100,000 CNY
                                    </span>
                                    
                                    <span class="text-[10px] text-slate-500">
                                        (Tỷ giá: 3,920)
                                    </span>
                                    
                                </div>
                                
                                <!-- Hàng 2: Thông tin chi tiết -->
                                <div class="text-[10px] text-slate-500 space-y-0.5">
                                    
                                    
                                    
                                    <div class="flex items-center gap-1">
                                        <span class="text-slate-500 text-[10px]">Kỳ:</span>
                                        <button onclick="showPeriodDetail(9)" class="text-indigo-600 hover:text-indigo-800 font-medium text-[10px] underline decoration-dotted hover:decoration-solid transition">
                                            KTT2025-003 - Kì 1
                                        </button>
                                    </div>
                                    
                                    
                                </div>
                            </div>
                            <div class="flex items-center gap-1 flex-shrink-0">
                                
                                
                                <button onclick="editTransaction(1)" class="p-1 text-slate-400 hover:text-indigo-600 opacity-0 group-hover/item:opacity-100 transition" title="Sửa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                    </svg>
                                </button>
                                <button onclick="deleteTransaction(1)" class="p-1 text-slate-400 hover:text-red-600 opacity-0 group-hover/item:opacity-100 transition" title="Xóa">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                </div>
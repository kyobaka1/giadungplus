# kho/views.py
from django.shortcuts import render

def dashboard(request):
    return render(request, "kho/dashboard.html")

def order_list(request):
    return render(request, "kho/order_list.html")

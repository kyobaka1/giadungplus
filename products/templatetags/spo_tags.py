from django import template
from datetime import datetime, date
from django.utils import timezone
import dateutil.parser

register = template.Library()

@register.simple_tag
def calculate_date_status(planned_str, actual_str):
    """
    Compares actual date vs planned date.
    Returns dict with status info.
    """
    if not actual_str or not planned_str:
        return {}
    
    try:
        # Handle ISO strings
        if isinstance(planned_str, str):
            planned = dateutil.parser.parse(planned_str).date()
        else:
            planned = planned_str
            
        if isinstance(actual_str, str):
            actual = dateutil.parser.parse(actual_str).date()
        else:
            actual = actual_str
            
        days_diff = (actual - planned).days
        
        if days_diff <= 0:
            return {
                'is_late': False,
                'days_diff': abs(days_diff),
                'status_label': 'Đúng hẹn' if days_diff == 0 else f'Sớm {abs(days_diff)} ngày',
                'color_class': 'text-emerald-600 bg-emerald-50 border-emerald-100',
                'icon_class': 'text-emerald-500'
            }
        else:
            return {
                'is_late': True,
                'days_diff': days_diff,
                'status_label': f'Trễ {days_diff} ngày',
                'color_class': 'text-red-600 bg-red-50 border-red-100',
                'icon_class': 'text-red-500'
            }
    except Exception as e:
        return {'error': str(e)}

@register.simple_tag
def calculate_deadline_status(planned_str):
    """
    Compares planned date vs today (for pending steps).
    """
    if not planned_str:
        return {}
    
    try:
        if isinstance(planned_str, str):
            planned = dateutil.parser.parse(planned_str).date()
        else:
            planned = planned_str
            
        today = date.today()
        days_diff = (planned - today).days
        
        if days_diff < 0:
            return {
                'is_overdue': True,
                'days_left': abs(days_diff),
                'status_label': f'Trễ {abs(days_diff)} ngày',
                'color_class': 'text-red-600 font-bold',
                'bg_class': 'bg-red-50 border-red-100'
            }
        elif days_diff == 0:
             return {
                'is_overdue': False,
                'days_left': 0,
                'status_label': 'Hôm nay',
                'color_class': 'text-orange-600 font-bold',
                 'bg_class': 'bg-orange-50 border-orange-100'
            }
        else:
             return {
                'is_overdue': False,
                'days_left': days_diff,
                'status_label': f'Còn {days_diff} ngày',
                'color_class': 'text-blue-600',
                 'bg_class': 'bg-blue-50 border-blue-100'
            }
    except Exception as e:
        return {'error': str(e)}

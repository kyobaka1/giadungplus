"""
Forms cho Campaigns module.
"""
from django import forms
from django.core.exceptions import ValidationError
from marketing.models import Campaign, CampaignProduct, CampaignCreator, Brand, Product, Creator


class CampaignForm(forms.ModelForm):
    """Form cho create/edit Campaign."""
    
    class Meta:
        model = Campaign
        fields = [
            'code', 'name', 'brand', 'channel', 'objective',
            'description', 'start_date', 'end_date',
            'budget_planned', 'kpi_view', 'kpi_order', 'kpi_revenue',
            'status', 'owner'
        ]
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'VD: CAM-2025-001'
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Tên campaign'
            }),
            'brand': forms.Select(attrs={'class': 'form-select'}),
            'channel': forms.Select(attrs={'class': 'form-select'}),
            'objective': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 10,
                'placeholder': 'Brief tổng (markdown được hỗ trợ)'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'budget_planned': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.01',
                'min': '0'
            }),
            'kpi_view': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '0'
            }),
            'kpi_order': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '0'
            }),
            'kpi_revenue': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.01',
                'min': '0'
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'owner': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active brands
        self.fields['brand'].queryset = Brand.objects.filter(is_active=True).order_by('name')
        # Filter active users (có thể thêm filter theo group)
        from django.contrib.auth.models import User
        self.fields['owner'].queryset = User.objects.filter(is_active=True).order_by('username')
        self.fields['owner'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        status = cleaned_data.get('status')
        
        # Validate dates
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError({
                    'end_date': 'Ngày kết thúc phải sau ngày bắt đầu'
                })
        
        # Validate status transitions
        if self.instance and self.instance.pk:
            old_status = self.instance.status
            if old_status in ['finished', 'canceled'] and status != old_status:
                raise ValidationError({
                    'status': f'Không thể thay đổi status từ {self.instance.get_status_display()}'
                })
        
        # Validate required fields for planned/running
        if status in ['planned', 'running']:
            if not start_date or not end_date:
                raise ValidationError({
                    'start_date' if not start_date else 'end_date': 
                    'Campaign planned/running phải có ngày bắt đầu và kết thúc'
                })
        
        return cleaned_data


class CampaignProductForm(forms.ModelForm):
    """Form để thêm/sửa product trong campaign."""
    
    class Meta:
        model = CampaignProduct
        fields = ['product', 'priority', 'note']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '1',
                'value': '1'
            }),
            'note': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Ghi chú về sản phẩm trong campaign này'
            }),
        }
    
    def __init__(self, *args, campaign=None, **kwargs):
        super().__init__(*args, **kwargs)
        if campaign:
            self.campaign = campaign
            # Filter products theo brand của campaign
            self.fields['product'].queryset = Product.objects.filter(
                brand=campaign.brand,
                is_active=True
            ).order_by('name')
    
    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        
        if self.campaign and product:
            # Check unique constraint
            existing = CampaignProduct.objects.filter(
                campaign=self.campaign,
                product=product,
                is_active=True
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                raise ValidationError({
                    'product': 'Sản phẩm này đã được thêm vào campaign'
                })
        
        return cleaned_data


class CampaignCreatorForm(forms.ModelForm):
    """Form để thêm/sửa creator trong campaign."""
    
    class Meta:
        model = CampaignCreator
        fields = ['creator', 'role', 'note']
        widgets = {
            'creator': forms.Select(attrs={'class': 'form-select'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'note': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Ghi chú về creator trong campaign này'
            }),
        }
    
    def __init__(self, *args, campaign=None, **kwargs):
        super().__init__(*args, **kwargs)
        if campaign:
            self.campaign = campaign
            # Filter active creators
            self.fields['creator'].queryset = Creator.objects.filter(
                is_active=True
            ).order_by('name')
    
    def clean(self):
        cleaned_data = super().clean()
        creator = cleaned_data.get('creator')
        
        if self.campaign and creator:
            # Check unique constraint
            existing = CampaignCreator.objects.filter(
                campaign=self.campaign,
                creator=creator,
                is_active=True
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                raise ValidationError({
                    'creator': 'Creator này đã được thêm vào campaign'
                })
        
        return cleaned_data


class BulkAddProductsForm(forms.Form):
    """Form để bulk add products."""
    products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.none(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '10'}),
        required=True
    )
    priority = forms.IntegerField(
        initial=1,
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': '1'})
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 3,
            'placeholder': 'Ghi chú chung cho tất cả sản phẩm'
        })
    )
    
    def __init__(self, *args, campaign=None, **kwargs):
        super().__init__(*args, **kwargs)
        if campaign:
            self.fields['products'].queryset = Product.objects.filter(
                brand=campaign.brand,
                is_active=True
            ).exclude(
                id__in=campaign.campaign_products.filter(is_active=True).values_list('product_id', flat=True)
            ).order_by('name')


class BulkAddCreatorsForm(forms.Form):
    """Form để bulk add creators."""
    creators = forms.ModelMultipleChoiceField(
        queryset=Creator.objects.none(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '10'}),
        required=True
    )
    role = forms.ChoiceField(
        choices=CampaignCreator.ROLE_CHOICES,
        initial='main',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 3,
            'placeholder': 'Ghi chú chung cho tất cả creators'
        })
    )
    
    def __init__(self, *args, campaign=None, **kwargs):
        super().__init__(*args, **kwargs)
        if campaign:
            self.fields['creators'].queryset = Creator.objects.filter(
                is_active=True
            ).exclude(
                id__in=campaign.campaign_creators.filter(is_active=True).values_list('creator_id', flat=True)
            ).order_by('name')


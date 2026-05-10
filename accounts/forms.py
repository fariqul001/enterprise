from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser, InvestorKYC, Fund, Investment, Payment

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

class ProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'email')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

class InvestorKYCForm(forms.ModelForm):
    date_of_birth = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}), required=False)

    class Meta:
        model = InvestorKYC
        exclude = ('user', 'status', 'admin_note', 'requested_documents', 'submitted_at', 'reviewed_at')
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.TextInput(attrs={'class': 'form-control'}),
            'address_line': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control'}),
            'passport_number': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_account': forms.TextInput(attrs={'class': 'form-control'}),
            'income_source': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'id_proof': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'bank_statement': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'wealth_declaration': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field.widget.attrs.get('class') is None:
                field.widget.attrs.update({'class': 'form-control'})

class FundForm(forms.ModelForm):
    class Meta:
        model = Fund
        fields = [
            'name',
            'description',
            'minimum_investment',
            'expected_return',
            'duration',
            'total_capacity',
            'status'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'minimum_investment': forms.NumberInput(attrs={'class': 'form-control'}),
            'expected_return': forms.TextInput(attrs={'class': 'form-control'}),
            'duration': forms.TextInput(attrs={'class': 'form-control'}),
            'total_capacity': forms.NumberInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

class InvestmentForm(forms.ModelForm):
    class Meta:
        model = Investment
        fields = ('amount',)
        widgets = {
            
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ('amount',)
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
        }

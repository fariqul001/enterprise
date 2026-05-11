from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, InvestorKYC, InvestorAgreement, Fund, Investment, Payment

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Role Information', {'fields': ('role', 'email_verified')}),
    )
    list_display = ('username', 'email', 'role', 'is_staff', 'is_superuser')
    list_filter = ('role', 'is_staff', 'is_superuser', 'email_verified')

@admin.register(InvestorKYC)
class InvestorKYCAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'submitted_at', 'reviewed_at')
    list_filter = ('status', 'submitted_at', 'reviewed_at')
    search_fields = ('user__username', 'full_name', 'national_id')

@admin.register(InvestorAgreement)
class InvestorAgreementAdmin(admin.ModelAdmin):
    list_display = ('kyc', 'generated_at')
    search_fields = ('kyc__user__username',)

@admin.register(Fund)
class FundAdmin(admin.ModelAdmin):
    list_display = ('name', 'minimum_investment', 'invested_amount')
    search_fields = ('name',)

@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = ('investor', 'fund', 'amount', 'invested_date', 'status')
    list_filter = ('fund', 'status', 'invested_date')
    search_fields = ('investor__username',)

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('investor', 'amount', 'payment_date', 'status')
    list_filter = ('status', 'payment_date')
    search_fields = ('investor__username',)

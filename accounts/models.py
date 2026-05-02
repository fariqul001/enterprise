from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('viewer', 'Viewer'),
        ('investor', 'Investor'),
        ('admin', 'Admin'),
    ]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='viewer')
    email_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.username

class InvestorKYC(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_ADDITIONAL = 'additional_docs'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_ADDITIONAL, 'Additional Documents Required'),
    ]

    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='kyc')
    full_name = models.CharField(max_length=255)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=50, blank=True)
    address_line = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    national_id = models.CharField(max_length=100)
    passport_number = models.CharField(max_length=100, blank=True)
    bank_name = models.CharField(max_length=150)
    bank_account = models.CharField(max_length=100)
    income_source = models.CharField(max_length=255)
    id_proof = models.FileField(upload_to='kyc/id_proof/', null=True, blank=True)
    bank_statement = models.FileField(upload_to='kyc/bank_statement/', null=True, blank=True)
    wealth_declaration = models.FileField(upload_to='kyc/wealth_declaration/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    admin_note = models.TextField(blank=True)
    requested_documents = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"KYC application for {self.user.username} ({self.get_status_display()})"

class InvestorAgreement(models.Model):
    kyc = models.OneToOneField(InvestorKYC, on_delete=models.CASCADE, related_name='agreement')
    pdf = models.FileField(upload_to='agreements/')
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Agreement for {self.kyc.user.username}"

class Fund(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    minimum_investment = models.DecimalField(max_digits=10, decimal_places=2)
    expected_return = models.CharField(max_length=100)
    duration = models.CharField(max_length=100)
    total_capacity = models.DecimalField(max_digits=15, decimal_places=2)
    invested_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Investment(models.Model):
    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='investments')
    fund = models.ForeignKey(Fund, on_delete=models.CASCADE, related_name='investments')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    invested_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, default='active')

    def __str__(self):
        return f"{self.investor.username} invested in {self.fund.name}"

class Installment(models.Model):
    investment = models.ForeignKey(Investment, on_delete=models.CASCADE, related_name='installments')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    due_date = models.DateField()
    paid = models.BooleanField(default=False)
    paid_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Installment for {self.investment} - Due {self.due_date}"

class Payment(models.Model):
    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='payments')
    installment = models.ForeignKey(Installment, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, default='pending')

    def __str__(self):
        return f"Payment by {self.investor.username} - {self.status}"

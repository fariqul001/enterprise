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
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_INACTIVE, 'Inactive'),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField()
    minimum_investment = models.DecimalField(max_digits=10, decimal_places=2)
    expected_return = models.CharField(max_length=100)
    duration = models.CharField(max_length=100)
    total_capacity = models.DecimalField(max_digits=15, decimal_places=2)
    invested_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Investment(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACTIVE = 'active'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_FAILED, 'Failed'),
    ]

    investor = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='investments'
    )

    fund = models.ForeignKey(
        Fund,
        on_delete=models.CASCADE,
        related_name='investments'
    )

    amount = models.DecimalField(max_digits=15, decimal_places=2)

    invested_date = models.DateTimeField(auto_now_add=True)

    # PAYMENT STATUS (IMPORTANT FOR REAL SYSTEM)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )

    #  TRANSACTION TRACKING (VERY IMPORTANT)
    transaction_id = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True
    )

    payment_method = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )  # e.g. sslcommerz, bkash, nagad

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.investor.username} - {self.fund.name} (${self.amount}) [{self.status}]"

class Installment(models.Model):
    investment = models.ForeignKey(Investment, on_delete=models.CASCADE, related_name='installments')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    due_date = models.DateField()
    paid = models.BooleanField(default=False)
    paid_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Installment for {self.investment} - Due {self.due_date}"

class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]
    
    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='payments')
    installment = models.ForeignKey(Installment, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    bank_slip = models.ImageField(upload_to='payment_slips/', null=True, blank=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    admin_note = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Payment by {self.investor.username} - {self.status}"
    


class Transaction(models.Model):
    investment = models.ForeignKey(Investment, on_delete=models.CASCADE)
    tran_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=20, default='initiated')
    created_at = models.DateTimeField(auto_now_add=True)
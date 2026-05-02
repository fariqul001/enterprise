import os
from pathlib import Path
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, FileResponse
from django.contrib import messages
from django.db import models
import json
from .forms import CustomUserCreationForm, InvestorKYCForm, ProfileForm, FundForm, InvestmentForm, PaymentForm
from .models import CustomUser, InvestorKYC, InvestorAgreement, Fund, Investment, Installment, Payment
from fpdf import FPDF

def home(request):
    return render(request, 'accounts/home.html')

def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful!')
            return redirect('accounts:user_dashboard')
    else:
        form = CustomUserCreationForm()
    return render(request, 'accounts/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if user.role == 'admin':
                return redirect('accounts:admin_dashboard')
            return redirect('accounts:user_dashboard')
        else:
            messages.error(request, 'Invalid credentials')
    return render(request, 'accounts/login.html')

def logout_view(request):
    logout(request)
    return redirect('accounts:home')

@login_required
def user_dashboard(request):
    if request.user.role == 'admin':
        return redirect('accounts:admin_dashboard')

    kyc = getattr(request.user, 'kyc', None)
    agreement = getattr(kyc, 'agreement', None) if kyc else None

    # Dynamic data for dashboard
    total_invested = Investment.objects.filter(investor=request.user).aggregate(total=models.Sum('amount'))['total'] or 0
    new_funds = Fund.objects.order_by('-created_at')[:5]
    existing_investments = Investment.objects.filter(investor=request.user).select_related('fund')

    # Data for pie chart: investments by fund
    investment_data = []
    labels = []
    for inv in existing_investments:
        labels.append(inv.fund.name)
        investment_data.append(float(inv.amount))

    return render(request, 'accounts/user_dashboard.html', {
        'kyc': kyc,
        'agreement': agreement,
        'total_invested': total_invested,
        'new_funds': new_funds,
        'existing_investments': existing_investments,
        'investment_labels_json': json.dumps(labels),
        'investment_data_json': json.dumps(investment_data),
    })

@login_required
def apply_kyc(request):
    if request.user.role != 'viewer':
        messages.info(request, 'You already have access to investor features.')
        return redirect('accounts:user_dashboard')

    kyc = getattr(request.user, 'kyc', None)
    if request.method == 'POST':
        form = InvestorKYCForm(request.POST, request.FILES, instance=kyc)
        if form.is_valid():
            kyc = form.save(commit=False)
            kyc.user = request.user
            kyc.status = InvestorKYC.STATUS_PENDING
            kyc.save()
            messages.success(request, 'KYC application submitted successfully. Admin will review it shortly.')
            return redirect('accounts:kyc_status')
    else:
        form = InvestorKYCForm(instance=kyc)
    return render(request, 'accounts/kyc_apply.html', {'form': form, 'kyc': kyc})

@login_required
def kyc_status(request):
    if request.user.role == 'admin':
        return redirect('accounts:admin_dashboard')

    kyc = getattr(request.user, 'kyc', None)
    if not kyc:
        return redirect('accounts:apply_kyc')

    agreement = getattr(kyc, 'agreement', None)
    return render(request, 'accounts/kyc_status.html', {
        'kyc': kyc,
        'agreement': agreement,
    })

@login_required
def admin_dashboard(request):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')

    pending_kyc = InvestorKYC.objects.filter(status=InvestorKYC.STATUS_PENDING)
    approved_kyc = InvestorKYC.objects.filter(status=InvestorKYC.STATUS_APPROVED)

    # Dynamic data
    total_funds = Fund.objects.count()
    total_investors = CustomUser.objects.filter(role='investor').count()
    total_money_raised = Investment.objects.aggregate(total=models.Sum('amount'))['total'] or 0

    # Data for pie chart: funds by invested amount
    funds = Fund.objects.all()
    fund_labels = [fund.name for fund in funds]
    fund_data = [float(fund.invested_amount) for fund in funds]

    context = {
        'active_users': InvestorKYC.objects.count(),
        'pending_kyc': pending_kyc.count(),
        'open_funds': total_funds,
        'pending_payments': Payment.objects.filter(status='pending').count(),
        'pending_investors': total_investors,
        'total_money_raised': total_money_raised,
        'kyc_requests': pending_kyc.select_related('user'),
        'recent_activities': [
            {'title': 'Platform audit completed', 'time': '1 hour ago'},
            {'title': 'New investor application received', 'time': '2 hours ago'},
            {'title': 'Agreement archive updated', 'time': '6 hours ago'},
        ],
        'fund_requests': [
            {'fund': 'Emerging Markets', 'status': 'Open', 'capacity': '250K'},
            {'fund': 'Capital Preservation', 'status': 'Closed', 'capacity': '500K'},
        ],
        'payment_requests': [
            {'investor': 'alex', 'amount': '$12,000', 'status': 'Awaiting Approval'},
            {'investor': 'nina', 'amount': '$5,600', 'status': 'Verified'},
        ],
        'fund_labels_json': json.dumps(fund_labels),
        'fund_data_json': json.dumps(fund_data),
    }
    return render(request, 'accounts/admin_dashboard.html', context)

@login_required
def kyc_review_detail(request, pk):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')

    kyc = get_object_or_404(InvestorKYC, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        admin_note = request.POST.get('admin_note', '').strip()
        if action == 'approve':
            kyc.status = InvestorKYC.STATUS_APPROVED
            kyc.admin_note = admin_note or 'Approved by admin.'
            kyc.user.role = 'investor'
            kyc.user.save()
            kyc.reviewed_at = timezone.now()
            kyc.save()
            create_agreement_pdf(kyc)
            messages.success(request, 'KYC approved and investor agreement generated.')
            return redirect('accounts:admin_dashboard')
        if action == 'reject':
            kyc.status = InvestorKYC.STATUS_REJECTED
            kyc.admin_note = admin_note or 'KYC rejected. Please review the documents.'
            kyc.reviewed_at = timezone.now()
            kyc.save()
            messages.success(request, 'KYC application rejected.')
            return redirect('accounts:admin_dashboard')
        if action == 'request_docs':
            kyc.status = InvestorKYC.STATUS_ADDITIONAL
            kyc.admin_note = admin_note or 'Additional documents required.'
            kyc.reviewed_at = timezone.now()
            kyc.save()
            messages.success(request, 'Requested additional documents from the investor.')
            return redirect('accounts:admin_dashboard')
    return render(request, 'accounts/kyc_review_detail.html', {'kyc': kyc})

@login_required
def agreement_list(request):
    if request.user.role == 'admin':
        return redirect('accounts:admin_dashboard')

    agreements = InvestorAgreement.objects.filter(kyc__user=request.user)
    return render(request, 'accounts/agreement_list.html', {'agreements': agreements})

@login_required
def agreement_download(request, pk):
    agreement = get_object_or_404(InvestorAgreement, pk=pk, kyc__user=request.user)
    file_path = agreement.pdf.path
    if not os.path.exists(file_path):
        messages.error(request, 'Agreement file is not available.')
        return redirect('accounts:agreement_list')
    return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=os.path.basename(file_path))

def create_agreement_pdf(kyc):
    agreement_dir = Path(settings.MEDIA_ROOT) / 'agreements'
    agreement_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"investor_agreement_{kyc.user.username}_{timezone.now().strftime('%Y%m%d%H%M%S')}.pdf"
    file_path = agreement_dir / file_name

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 12, 'Investor Agreement', ln=True, align='C')
    pdf.ln(10)
    pdf.set_font('Arial', '', 12)
    pdf.multi_cell(0, 8, f"Investor: {kyc.user.get_full_name() or kyc.user.username}")
    pdf.multi_cell(0, 8, f"Email: {kyc.user.email}")
    pdf.multi_cell(0, 8, f"Role: {kyc.user.get_role_display()}")
    pdf.ln(4)
    pdf.multi_cell(0, 8, 'Agreement Summary:')
    pdf.multi_cell(0, 8, 'This agreement outlines the legal relationship between the investor and Enterprise Fund. The investor agrees to the company terms and acknowledges that investment products are subject to risk.')
    pdf.ln(4)
    pdf.multi_cell(0, 8, f"KYC Status: {kyc.get_status_display()}")
    pdf.multi_cell(0, 8, f"Date Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
    pdf.ln(10)
    pdf.multi_cell(0, 8, 'By signing below, the investor agrees to the fund terms and acknowledges that they have provided accurate documents.')
    pdf.ln(20)
    pdf.cell(0, 8, 'Investor Signature: ____________________________', ln=True)
    pdf.cell(0, 8, 'Admin Signature: ______________________________', ln=True)

    pdf.output(str(file_path))

    agreement, _ = InvestorAgreement.objects.get_or_create(kyc=kyc)
    agreement.pdf.name = f'agreements/{file_name}'
    agreement.save()
    return agreement

# INVESTOR VIEWS

@login_required
def profile(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts:profile')
    else:
        form = ProfileForm(instance=request.user)
    return render(request, 'accounts/profile.html', {'form': form})

@login_required
def fund_list(request):
    funds = Fund.objects.all()
    return render(request, 'accounts/fund_list.html', {'funds': funds})

@login_required
def invest_in_fund(request, pk):
    if request.user.role == 'viewer':
        messages.error(request, 'Please complete KYC to invest in funds.')
        return redirect('accounts:apply_kyc')

    fund = get_object_or_404(Fund, pk=pk)
    if request.method == 'POST':
        form = InvestmentForm(request.POST)
        if form.is_valid():
            investment = form.save(commit=False)
            investment.investor = request.user
            investment.fund = fund
            investment.save()
            fund.invested_amount += investment.amount
            fund.save()
            messages.success(request, f'Successfully invested ${investment.amount} in {fund.name}!')
            return redirect('accounts:active_investments')
    else:
        form = InvestmentForm()
        form.fields['fund'].queryset = Fund.objects.filter(pk=pk)
    return render(request, 'accounts/invest_in_fund.html', {'form': form, 'fund': fund})

@login_required
def active_investments(request):
    investments = Investment.objects.filter(investor=request.user)
    return render(request, 'accounts/active_investments.html', {'investments': investments})

@login_required
def payment(request):
    installments = Installment.objects.filter(investment__investor=request.user, paid=False)
    if request.method == 'POST':
        installment_id = request.POST.get('installment_id')
        installment = get_object_or_404(Installment, id=installment_id, investment__investor=request.user)
        installment.paid = True
        installment.paid_date = timezone.now().date()
        installment.save()
        Payment.objects.create(investor=request.user, installment=installment, amount=installment.amount, status='completed')
        messages.success(request, f'Payment of ${installment.amount} completed successfully!')
        return redirect('accounts:payment')
    return render(request, 'accounts/payment.html', {'installments': installments})

# ADMIN VIEWS

@login_required
def admin_investors(request):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')
    investors = CustomUser.objects.filter(role='investor')
    return render(request, 'accounts/admin_investors.html', {'investors': investors})

@login_required
def admin_funds(request):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')
    funds = Fund.objects.all()
    return render(request, 'accounts/admin_funds.html', {'funds': funds})

@login_required
def admin_add_fund(request):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')
    if request.method == 'POST':
        form = FundForm(request.POST)
        if form.is_valid():
            fund = form.save()
            messages.success(request, f'Fund {fund.name} created successfully!')
            return redirect('accounts:admin_funds')
    else:
        form = FundForm()
    return render(request, 'accounts/admin_add_fund.html', {'form': form})

@login_required
def admin_fund_applications(request):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')
    applications = Investment.objects.all()
    return render(request, 'accounts/admin_fund_applications.html', {'applications': applications})

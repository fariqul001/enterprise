import os
from io import BytesIO
import csv
import calendar
from datetime import datetime, timedelta
from pathlib import Path
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, FileResponse, HttpResponse
from django.contrib import messages
from django.db import models
from django.utils import timezone
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
    active_funds = Fund.objects.filter(status=Fund.STATUS_ACTIVE).count()
    inactive_funds = Fund.objects.filter(status=Fund.STATUS_INACTIVE).count()
    total_investors = CustomUser.objects.filter(role='investor').count()
    total_money_raised = Investment.objects.aggregate(total=models.Sum('amount'))['total'] or 0

    # Data for pie chart: funds by invested amount
    funds = Fund.objects.all()
    fund_labels = [fund.name for fund in funds]
    fund_data = [float(fund.invested_amount) for fund in funds]
    total_capacity = Fund.objects.aggregate(total=models.Sum('total_capacity'))['total'] or 0
    total_remaining = sum(max(float(fund.total_capacity - fund.invested_amount), 0) for fund in funds)

    context = {
        'active_users': InvestorKYC.objects.count(),
        'pending_kyc': pending_kyc.count(),
        'open_funds': total_funds,
        'active_funds': active_funds,
        'inactive_funds': inactive_funds,
        'pending_payments': Payment.objects.filter(status='pending').count(),
        'pending_investors': total_investors,
        'total_money_raised': total_money_raised,
        'total_capacity': total_capacity,
        'total_remaining': total_remaining,
        'kyc_requests': pending_kyc.select_related('user'),
        'recent_activities': [
            {'title': 'Platform audit completed', 'time': '1 hour ago'},
            {'title': 'New investor application received', 'time': '2 hours ago'},
            {'title': 'Agreement archive updated', 'time': '6 hours ago'},
        ],
        'fund_requests': funds.order_by('-created_at')[:4],
        'payment_requests': Payment.objects.select_related('investor').order_by('-payment_date')[:4],
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
    funds = Fund.objects.all().order_by('-created_at')
    return render(request, 'accounts/admin_funds.html', {'funds': funds})

@login_required
def admin_toggle_fund(request, pk):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')
    fund = get_object_or_404(Fund, pk=pk)
    if request.method == 'POST':
        fund.status = Fund.STATUS_INACTIVE if fund.status == Fund.STATUS_ACTIVE else Fund.STATUS_ACTIVE
        fund.save()
        messages.success(request, f'Fund "{fund.name}" status updated to {fund.status}.')
    return redirect('accounts:admin_funds')

@login_required
def admin_delete_fund(request, pk):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')
    fund = get_object_or_404(Fund, pk=pk)
    if request.method == 'POST':
        fund.delete()
        messages.success(request, f'Fund "{fund.name}" was deleted successfully.')
    return redirect('accounts:admin_funds')

def build_admin_report_context(period='this_month'):
    now = timezone.now()
    selected_period_label = 'This Month'
    members = CustomUser.objects.filter(role='investor')

    if period == 'previous_month':
        first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = first_of_this_month - timedelta(seconds=1)
        start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        selected_period_label = 'Previous Month'
    elif period == 'this_year':
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
        selected_period_label = 'This Year'
    elif period == 'all':
        start = None
        end = None
        selected_period_label = 'All Time'
    else:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now

    if start is not None:
        members = members.filter(date_joined__gte=start, date_joined__lte=end)

    funds = Fund.objects.all().order_by('-created_at')
    fund_summary = []
    for fund in funds:
        remaining = max(float(fund.total_capacity - fund.invested_amount), 0)
        fund_summary.append({
            'name': fund.name,
            'invested': float(fund.invested_amount),
            'remaining': remaining,
            'status': fund.status,
            'badge_color': 'success' if fund.status == Fund.STATUS_ACTIVE else 'secondary',
        })

    month_labels = []
    month_counts = []
    for offset in range(5, -1, -1):
        year = now.year
        month = now.month - offset
        while month <= 0:
            month += 12
            year -= 1
        start_month = datetime(year, month, 1, tzinfo=timezone.get_current_timezone())
        if month == 12:
            next_month = datetime(year + 1, 1, 1, tzinfo=timezone.get_current_timezone())
        else:
            next_month = datetime(year, month + 1, 1, tzinfo=timezone.get_current_timezone())
        count = CustomUser.objects.filter(role='investor', date_joined__gte=start_month, date_joined__lt=next_month).count()
        month_labels.append(start_month.strftime('%b %Y'))
        month_counts.append(count)

    return {
        'selected_period': period,
        'selected_period_label': selected_period_label,
        'fund_summary': fund_summary,
        'total_invested': sum(float(fund.invested_amount) for fund in funds),
        'total_capacity': sum(float(fund.total_capacity) for fund in funds),
        'total_remaining': sum(item['remaining'] for item in fund_summary),
        'active_funds': Fund.objects.filter(status=Fund.STATUS_ACTIVE).count(),
        'total_funds': funds.count(),
        'total_investors': CustomUser.objects.filter(role='investor').count(),
        'members_count': members.count(),
        'joined_members': members.order_by('-date_joined')[:12],
        'month_labels_json': json.dumps(month_labels),
        'month_counts_json': json.dumps(month_counts),
    }

@login_required
def admin_reports(request):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')
    context = build_admin_report_context(request.GET.get('period', 'this_month'))
    return render(request, 'accounts/admin_reports.html', context)

@login_required
def admin_reports_download(request):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')

    download_type = request.GET.get('type', 'csv')
    period = request.GET.get('period', 'this_month')
    report_data = build_admin_report_context(period)

    if download_type == 'pdf':
        buffer = BytesIO()
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, 'Admin Reports & Analytics', ln=True)
        pdf.set_font('Arial', '', 12)
        pdf.cell(0, 8, f'Period: {report_data.get("selected_period_label")}', ln=True)
        pdf.ln(4)
        pdf.cell(0, 8, f'Total Invested: ${report_data.get("total_invested"):.2f}', ln=True)
        pdf.cell(0, 8, f'Total Capacity: ${report_data.get("total_capacity"):.2f}', ln=True)
        pdf.cell(0, 8, f'Total Remaining: ${report_data.get("total_remaining"):.2f}', ln=True)
        pdf.cell(0, 8, f'Active Funds: {report_data.get("active_funds")}', ln=True)
        pdf.cell(0, 8, f'Total Investors: {report_data.get("total_investors")}', ln=True)
        pdf.ln(6)
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 8, 'Fund Summary', ln=True)
        pdf.set_font('Arial', '', 11)
        for fund in report_data.get('fund_summary', []):
            pdf.multi_cell(0, 7, f"{fund['name']}: Invested ${fund['invested']:.2f}, Remaining ${fund['remaining']:.2f}, Status {fund['status']}")
        buffer.write(pdf.output(dest='S').encode('latin-1'))
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="admin_report.pdf"'
        return response

    csv_buffer = BytesIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(['Report Type', report_data.get('selected_period_label')])
    writer.writerow([])
    writer.writerow(['Total Invested', f'${report_data.get("total_invested"):.2f}'])
    writer.writerow(['Total Capacity', f'${report_data.get("total_capacity"):.2f}'])
    writer.writerow(['Total Remaining', f'${report_data.get("total_remaining"):.2f}'])
    writer.writerow(['Active Funds', report_data.get('active_funds')])
    writer.writerow(['Total Investors', report_data.get('total_investors')])
    writer.writerow([])
    writer.writerow(['Fund Name', 'Invested', 'Remaining', 'Status'])
    for fund in report_data.get('fund_summary', []):
        writer.writerow([fund['name'], f"${fund['invested']:.2f}", f"${fund['remaining']:.2f}", fund['status']])
    writer.writerow([])
    writer.writerow(['Investor Username', 'Email', 'Joined'])
    for member in report_data.get('joined_members', []):
        writer.writerow([member.username, member.email, member.date_joined.strftime('%Y-%m-%d')])

    response = HttpResponse(csv_buffer.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="admin_report.csv"'
    return response

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

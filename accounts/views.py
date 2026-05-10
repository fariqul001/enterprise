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
from .models import CustomUser, InvestorKYC, InvestorAgreement, Fund, Investment, Installment, Payment, Transaction
from fpdf import FPDF
from django.core.mail import EmailMessage
from .sslcommerz import initiate_payment
from django.views.decorators.csrf import csrf_exempt


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

        user_email = kyc.user.email
        user_name = kyc.user.username

        # ================= APPROVE =================
        if action == 'approve':
            kyc.status = InvestorKYC.STATUS_APPROVED
            kyc.admin_note = admin_note or 'Approved by admin.'
            kyc.user.role = 'investor'
            kyc.user.save()
            kyc.reviewed_at = timezone.now()
            kyc.save()

            create_agreement_pdf(kyc)

            #  Email
            subject = "KYC Application Approved - Welcome Investor"
            message = f"""
Dear {user_name},

We are pleased to inform you that your KYC (Know Your Customer) application has been successfully approved.

You are now officially registered as an investor in our platform and can start participating in investment opportunities.

If you have any questions or need assistance, feel free to contact our support team.

Best regards,  
Enterprise Fund & Investment Management Team
            """

            email = EmailMessage(subject, message, settings.EMAIL_HOST_USER, [user_email])
            email.send()

            messages.success(request, 'KYC approved and email sent.')
            return redirect('accounts:admin_dashboard')

        # ================= REJECT =================
        if action == 'reject':
            kyc.status = InvestorKYC.STATUS_REJECTED
            kyc.admin_note = admin_note or 'KYC rejected. Please review the documents.'
            kyc.reviewed_at = timezone.now()
            kyc.save()

            #  Email
            subject = "KYC Application Status Update"
            message = f"""
Dear {user_name},

Thank you for submitting your KYC application.

After careful review, we regret to inform you that your application has not been approved at this time.

Reason:
{kyc.admin_note}

You are welcome to review your documents and submit a new application.

Best regards,  
Enterprise Fund & Investment Management Team
            """

            email = EmailMessage(subject, message, settings.EMAIL_HOST_USER, [user_email])
            email.send()

            messages.success(request, 'KYC rejected and email sent.')
            return redirect('accounts:admin_dashboard')

        # ================= REQUEST DOCUMENTS =================
        if action == 'request_docs':
            kyc.status = InvestorKYC.STATUS_ADDITIONAL
            kyc.admin_note = admin_note or 'Additional documents required.'
            kyc.reviewed_at = timezone.now()
            kyc.save()

            #  Email
            subject = "Additional Documents Required for KYC"
            message = f"""
Dear {user_name},

Your KYC application has been reviewed.

However, additional documents are required to proceed further.

Details:
{kyc.admin_note}

Please log in to your account and upload the requested documents.

Best regards,  
Enterprise Fund & Investment Management Team
            """

            email = EmailMessage(subject, message, settings.EMAIL_HOST_USER, [user_email])
            email.send()

            messages.success(request, 'Requested documents and email sent.')
            return redirect('accounts:admin_dashboard')

    return render(request, 'accounts/kyc_review_detail.html', {'kyc': kyc})






@login_required
def send_monthly_reminder(request):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')

    investors = InvestorKYC.objects.filter(status=InvestorKYC.STATUS_APPROVED)

    for kyc in investors:
        user_email = kyc.user.email
        user_name = kyc.user.username

        subject = "Monthly Investment Payment Reminder"

        message = f"""
Dear {user_name},

This is a friendly reminder to complete your monthly investment payment.

Please ensure that your payment is submitted before the 25th of this month to remain compliant with your investment plan.

Timely payments help us maintain smooth operations and maximize investment opportunities for all members.

Thank you for your continued trust and cooperation.

Best regards,  
Enterprise Fund & Investment Management Team
        """

        email = EmailMessage(subject, message, settings.EMAIL_HOST_USER, [user_email])
        email.send()

    messages.success(request, "Monthly reminder emails sent to all investors.")
    return redirect('accounts:admin_dashboard')



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
    user = request.user
    kyc = getattr(user, 'kyc', None)

    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts:profile')
    else:
        form = ProfileForm(instance=user)

    total_invested = Investment.objects.filter(
        investor=user
    ).aggregate(total=models.Sum('amount'))['total'] or 0

    total_funds = Investment.objects.filter(investor=user).count()

    total_payments = Payment.objects.filter(
        investor=user,
        status='completed'
    ).aggregate(total=models.Sum('amount'))['total'] or 0

    context = {
        'form': form,
        'kyc': kyc,
        'total_invested': total_invested,
        'total_funds': total_funds,
        'total_payments': total_payments,
    }

    return render(request, 'accounts/profile.html', context)
@login_required
def fund_list(request):
    # Only show active funds
    funds = Fund.objects.filter(status=Fund.STATUS_ACTIVE)
    
    # Get user's existing investments
    user_investments = Investment.objects.filter(investor=request.user).values_list('fund_id', flat=True)
    
    # Add enrollment status to each fund
    funds_with_status = []
    for fund in funds:
        funds_with_status.append({
            'fund': fund,
            'is_enrolled': fund.id in user_investments
        })
    
    return render(request, 'accounts/fund_list.html', {'funds_with_status': funds_with_status})

def invest_in_fund(request, pk):
    if request.user.role == 'viewer':
        messages.error(request, 'Please complete KYC to invest in funds.')
        return redirect('accounts:apply_kyc')

    fund = get_object_or_404(Fund, pk=pk)
    
    # Check if fund is active
    if fund.status != Fund.STATUS_ACTIVE:
        messages.error(request, 'This fund is no longer accepting investments.')
        return redirect('accounts:fund_list')
    
    # Check if user already invested in this fund
    existing_investment = Investment.objects.filter(investor=request.user, fund=fund).exists()
    if existing_investment:
        messages.warning(request, 'You are already enrolled in this fund. You can make monthly payments instead.')
        return redirect('accounts:fund_list')

    if request.method == 'POST':
        form = InvestmentForm(request.POST)

        if form.is_valid():
            investment = form.save(commit=False)

            # assign from URL (NOT FORM)
            investment.investor = request.user
            investment.fund = fund
            investment.status = 'pending'

            # validation
            if investment.amount < fund.minimum_investment:
                messages.error(
                    request,
                    f'Minimum investment for this fund is ${fund.minimum_investment}'
                )
                return redirect('accounts:invest_in_fund', pk=fund.pk)

            investment.save()

            messages.success(
                request,
                f'Investment created. Proceed to payment.'
            )

            return redirect('accounts:ssl_payment', pk=investment.pk)

        else:
            print(form.errors)  # DEBUG

    else:
        form = InvestmentForm()

    return render(request, 'accounts/invest_in_fund.html', {
        'form': form,
        'fund': fund
    })

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

    investor_data = []

    for investor in investors:
        total_invested = Investment.objects.filter(
            investor=investor
        ).aggregate(total=models.Sum('amount'))['total'] or 0

        total_payments = Payment.objects.filter(
            investor=investor,
            status='completed'
        ).aggregate(total=models.Sum('amount'))['total'] or 0

        total_funds = Investment.objects.filter(
            investor=investor
        ).count()

        investor_data.append({
            'user': investor,
            'total_invested': total_invested,
            'total_payments': total_payments,
            'total_funds': total_funds,
        })

    return render(request, 'accounts/admin_investors.html', {
        'investor_data': investor_data
    })


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



@login_required
def investment_history(request):
    investments = Investment.objects.filter(
        investor=request.user
    ).select_related('fund').order_by('-invested_date')

    return render(request, 'accounts/investment_history.html', {
        'investments': investments
    })


# NEW: Investor Pending Monthly Payments
@login_required
def investor_pending_payments(request):
    if request.user.role == 'admin':
        return redirect('accounts:admin_dashboard')
    
    # Get active investments for this investor
    active_investments = Investment.objects.filter(
        investor=request.user, 
        status='active'
    ).select_related('fund')
    
    return render(request, 'accounts/investor_pending_payments.html', {
        'active_investments': active_investments
    })


# NEW: Submit monthly payment with bank slip
@login_required
def submit_monthly_payment(request, investment_id):
    if request.user.role == 'admin':
        return redirect('accounts:admin_dashboard')
    
    investment = get_object_or_404(Investment, id=investment_id, investor=request.user)
    
    if request.method == 'POST':
        amount = request.POST.get('amount')
        bank_slip = request.FILES.get('bank_slip')
        
        if not amount or not bank_slip:
            messages.error(request, 'Please provide amount and bank slip image.')
            return redirect('accounts:investor_pending_payments')
        
        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError("Amount must be greater than 0")
        except (ValueError, TypeError):
            messages.error(request, 'Invalid amount.')
            return redirect('accounts:investor_pending_payments')
        
        # Get or create pending installment
        pending_installment = Installment.objects.filter(
            investment=investment,
            paid=False
        ).first()
        
        if pending_installment:
            # Create or update payment record
            payment = Payment.objects.create(
                investor=request.user,
                installment=pending_installment,
                amount=amount,
                bank_slip=bank_slip,
                status='pending'
            )
            messages.success(request, 'Monthly payment submitted successfully. Admin will review and approve it.')
        else:
            messages.error(request, 'No pending installments for this investment.')
        
        return redirect('accounts:investor_pending_payments')
    
    return render(request, 'accounts/submit_monthly_payment.html', {'investment': investment})


# NEW: Admin Pending Payments Management
@login_required
def admin_pending_payments(request):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')
    
    # Get all pending payments
    pending_payments = Payment.objects.filter(status='pending').select_related(
        'investor', 'installment__investment__fund'
    ).order_by('-payment_date')
    
    # Handle approval/rejection
    if request.method == 'POST':
        payment_id = request.POST.get('payment_id')
        action = request.POST.get('action')
        admin_note = request.POST.get('admin_note', '')
        
        payment = get_object_or_404(Payment, id=payment_id)
        
        if action == 'approve':
            payment.status = 'approved'
            payment.installment.paid = True
            payment.installment.paid_date = timezone.now().date()
            payment.installment.save()
            payment.reviewed_at = timezone.now()
            payment.admin_note = admin_note or 'Payment approved by admin.'
            payment.save()
            
            # Send approval email to investor
            subject = "Monthly Payment Approved"
            message = f"""
Dear {payment.investor.username},

Your monthly installment payment of {payment.amount} for {payment.installment.investment.fund.name} has been approved.

Your account has been updated accordingly.

Thank you for your commitment to your investment.

Best regards,
Enterprise Fund & Investment Management Team
            """
            email = EmailMessage(subject, message, settings.EMAIL_HOST_USER, [payment.investor.email])
            email.send()
            
            messages.success(request, 'Payment approved successfully.')
        
        elif action == 'reject':
            payment.status = 'rejected'
            payment.reviewed_at = timezone.now()
            payment.admin_note = admin_note or 'Payment rejected. Please check and resubmit.'
            payment.save()
            
            # Send rejection email to investor
            subject = "Monthly Payment Status - Action Required"
            message = f"""
Dear {payment.investor.username},

Your monthly installment payment submission for {payment.installment.investment.fund.name} could not be approved.

Reason: {payment.admin_note}

Please review and resubmit your payment with the correct details.

Best regards,
Enterprise Fund & Investment Management Team
            """
            email = EmailMessage(subject, message, settings.EMAIL_HOST_USER, [payment.investor.email])
            email.send()
            
            messages.success(request, 'Payment rejected.')
        
        return redirect('accounts:admin_pending_payments')
    
    return render(request, 'accounts/admin_pending_payments.html', {
        'pending_payments': pending_payments,
        'pending_count': pending_payments.count()
    })


# NEW: Investor Investment Report Detail
@login_required
def investment_report_detail(request, investment_id):

    if request.user.role == 'admin':
        return redirect('accounts:admin_dashboard')

    investment = get_object_or_404(
        Investment,
        id=investment_id,
        investor=request.user
    )

    installments = Installment.objects.filter(
        investment=investment
    ).order_by('due_date')

    payment_history = []
    total_paid = 0
    paid_count = 0

    # Installments
    for installment in installments:
        if installment.paid:
            paid_count += 1
            total_paid += float(installment.amount)

            payment_history.append({
                'type': 'Monthly Installment',
                'amount': installment.amount,
                'date': installment.paid_date,
                'status': 'Completed'
            })

    # Down payment
    payment_history.insert(0, {
        'type': 'Down Payment',
        'amount': investment.amount,
        'date': investment.paid_at or investment.invested_date,
        'status': 'Completed' if investment.status == 'active' else investment.status
    })

    total_paid += float(investment.amount)

    total_due = float(investment.amount) + sum(
        float(i.amount) for i in installments
    )

    remaining_installments = len(installments) - paid_count

    context = {
        'investment': investment,
        'payment_history': payment_history,
        'total_due': total_due,
        'total_paid': total_paid,
        'paid_count': paid_count,
        'installments': installments,
        'remaining_installments': remaining_installments,
    }

    return render(request, 'accounts/investment_report_detail.html', context)

# NEW: Admin Investor Funds Overview
@login_required
def admin_investor_funds_overview(request):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')
    
    # Get all investors
    investors = CustomUser.objects.filter(role='investor').select_related('kyc')
    
    investor_cards = []
    
    for investor in investors:
        # Get KYC info
        kyc = getattr(investor, 'kyc', None)
        joined_date = kyc.submitted_at if kyc else investor.date_joined
        
        # Get all investments
        investments = Investment.objects.filter(investor=investor)
        
        # Calculate metrics
        total_funds = investments.filter(status='active').count()
        total_amount_paid = investments.aggregate(total=models.Sum('amount'))['total'] or 0
        
        # Count transactions
        total_transactions = Installment.objects.filter(
            investment__investor=investor, paid=True
        ).count() + investments.filter(status='active').count()
        
        # Check current monthly installment status
        pending_monthly = Installment.objects.filter(
            investment__investor=investor,
            investment__status='active',
            paid=False,
            due_date__lte=timezone.now().date()
        ).exists()
        
        investor_cards.append({
            'user': investor,
            'kyc': kyc,
            'joined_date': joined_date,
            'total_funds': total_funds,
            'total_amount_paid': total_amount_paid,
            'total_transactions': total_transactions,
            'pending_monthly': pending_monthly,
            'kyc_status': kyc.get_status_display() if kyc else 'Not Applied',
        })
    
    return render(request, 'accounts/admin_investor_funds_overview.html', {
        'investor_cards': investor_cards
    })

from django.db.models import Sum
# NEW: Admin View Investor Fund Details
@login_required
def admin_investor_detail(request, investor_id):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')
    
    investor = get_object_or_404(CustomUser, id=investor_id, role='investor')
    kyc = getattr(investor, 'kyc', None)
    
    # Get all investments
    active_investments = Investment.objects.filter(
        investor=investor, status='active'
    ).select_related('fund')
    
    # Prepare investment details
    investment_details = []
    for inv in active_investments:
        installments = Installment.objects.filter(investment=inv)

        paid_installments = installments.filter(paid=True).count()
        total_installments = installments.count()

        total_amount = installments.aggregate(
            total=Sum('amount')
        )['total'] or 0

        total_paid = Installment.objects.filter(
            investment=inv,
            paid=True
        ).aggregate(
            total=Sum('amount')
        )['total'] or 0

        investment_details.append({
            'investment': inv,
            'paid_installments': paid_installments,
            'total_installments': total_installments,
            'total_amount': inv.amount + total_amount,
            'total_paid': inv.amount + total_paid,
        })
    
    context = {
        'investor': investor,
        'kyc': kyc,
        'investment_details': investment_details,
        'total_funds': active_investments.count(),
    }
    
    return render(request, 'accounts/admin_investor_detail.html', context)



@csrf_exempt
def payment_success(request):
    if request.method == "POST":
        tran_id = request.POST.get("tran_id")
        val_id = request.POST.get("val_id")

        if not tran_id:
            return HttpResponse("Transaction ID missing")

        transaction = get_object_or_404(Transaction, tran_id=tran_id)

        #  VALIDATE WITH SSLCommerz
        validation_url = f"https://sandbox.sslcommerz.com/validator/api/validationserverAPI.php?val_id={val_id}&store_id={settings.SSLCOMMERZ_STORE_ID}&store_passwd={settings.SSLCOMMERZ_STORE_PASSWORD}&format=json"

        res = requests.get(validation_url)
        result = res.json()

        if result.get("status") == "VALID":
            transaction.status = "success"
            transaction.save()

            investment = transaction.investment
            investment.status = "active"
            investment.transaction_id = tran_id
            investment.save()
            monthly_amount = investment.amount / 12

            for i in range(1, 13):
                Installment.objects.create(
                     investment=investment,
                     amount=monthly_amount,
                     due_date=timezone.now().date() + timedelta(days=30 * i),
                     paid=False
                 )
            

            fund = investment.fund
            fund.invested_amount += investment.amount
            fund.save()

            messages.success(request, "Payment successful!")
        else:
            transaction.status = "failed"
            transaction.save()
            messages.error(request, "Payment validation failed!")

        return redirect("accounts:active_investments")

    return HttpResponse("Invalid request")
@csrf_exempt
def payment_fail(request):
    tran_id = request.POST.get("tran_id")
    if tran_id:
        Transaction.objects.filter(tran_id=tran_id).update(status="failed")
    return redirect('accounts:fund_list')


@csrf_exempt
def payment_cancel(request):
    tran_id = request.POST.get("tran_id")
    if tran_id:
        Transaction.objects.filter(tran_id=tran_id).update(status="cancelled")
    return redirect('accounts:fund_list')


import requests

def ssl_payment(request, pk):
    investment = get_object_or_404(Investment, pk=pk)

    tran_id = f"INV{investment.id}{int(timezone.now().timestamp())}"

    transaction = Transaction.objects.create(
        investment=investment,
        tran_id=tran_id,
        amount=investment.amount,
        status='initiated'
    )

    store_id = settings.SSLCOMMERZ_STORE_ID
    store_pass = settings.SSLCOMMERZ_STORE_PASSWORD

    payload = {
        'store_id': store_id,
        'store_passwd': store_pass,
        'total_amount': float(investment.amount),
        'currency': "BDT",
        'tran_id': tran_id,

        'success_url': request.build_absolute_uri('/accounts/payment/success/'),
        'fail_url': request.build_absolute_uri('/accounts/payment/fail/'),
        'cancel_url': request.build_absolute_uri('/accounts/payment/cancel/'),

        'cus_name': request.user.username,
        'cus_email': request.user.email,
        'cus_add1': "Dhaka",
        'cus_phone': "01700000000",
        'shipping_method': "NO",
        'product_name': investment.fund.name,
        'product_category': "Investment",
        'product_profile': "general",
    }

    response = requests.post(
        "https://sandbox.sslcommerz.com/gwprocess/v4/api.php",
        data=payload
    )

    data = response.json()

    if data.get("status") == "SUCCESS":
        return redirect(data["GatewayPageURL"])
    else:
        messages.error(request, "Payment gateway error")
        return redirect("accounts:fund_list")
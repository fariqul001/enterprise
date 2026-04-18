from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

@login_required
def user_dashboard(request):
    if request.user.role == 'admin':
        return redirect('dashboard:admin_dashboard')
    return render(request, 'dashboard/user_dashboard.html')

@login_required
def admin_dashboard(request):
    if request.user.role != 'admin':
        return HttpResponseForbidden('Access denied')

    context = {
        'active_users': 1824,
        'pending_kyc': 14,
        'open_funds': 8,
        'pending_payments': 6,
        'pending_investors': 21,
        'recent_activities': [
            {'title': 'KYC approved for user: alice', 'time': '30 minutes ago'},
            {'title': 'New fund added: Global Growth Fund', 'time': '2 hours ago'},
            {'title': 'Payment received: TXN-9085', 'time': '6 hours ago'},
            {'title': 'Investor request pending: bob', 'time': '1 day ago'},
        ],
        'kyc_requests': [
            {'user': 'alice', 'status': 'Pending', 'submitted': '2 hours ago'},
            {'user': 'maria', 'status': 'Pending', 'submitted': '4 hours ago'},
            {'user': 'david', 'status': 'Review', 'submitted': '1 day ago'},
        ],
        'fund_requests': [
            {'fund': 'Emerging Markets', 'status': 'Open', 'capacity': '250K'},
            {'fund': 'Capital Preservation', 'status': 'Closed', 'capacity': '500K'},
        ],
        'payment_requests': [
            {'investor': 'alex', 'amount': '$12,000', 'status': 'Awaiting Approval'},
            {'investor': 'nina', 'amount': '$5,600', 'status': 'Verified'},
        ],
    }
    return render(request, 'dashboard/admin_dashboard.html', context)

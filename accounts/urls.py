from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.user_dashboard, name='user_dashboard'),
    path('profile/', views.profile, name='profile'),
    path('funds/', views.fund_list, name='fund_list'),
    path('invest/<int:pk>/', views.invest_in_fund, name='invest_in_fund'),
    path('investments/', views.active_investments, name='active_investments'),
    path('payments/', views.payment, name='payment'),
    path('kyc/apply/', views.apply_kyc, name='apply_kyc'),
    path('kyc/status/', views.kyc_status, name='kyc_status'),
    path('kyc/review/<int:pk>/', views.kyc_review_detail, name='kyc_review_detail'),
    path('agreements/', views.agreement_list, name='agreement_list'),
    path('agreements/<int:pk>/download/', views.agreement_download, name='agreement_download'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/', views.admin_dashboard, name='admin_dashboard_alias'),
    path('admin/investors/', views.admin_investors, name='admin_investors'),
    path('admin/funds/', views.admin_funds, name='admin_funds'),
    path('admin/funds/<int:pk>/toggle/', views.admin_toggle_fund, name='admin_toggle_fund'),
    path('admin/funds/<int:pk>/delete/', views.admin_delete_fund, name='admin_delete_fund'),
    path('admin/add-fund/', views.admin_add_fund, name='admin_add_fund'),
    path('admin/fund-applications/', views.admin_fund_applications, name='admin_fund_applications'),
    path('admin/reports/', views.admin_reports, name='admin_reports'),
    path('admin/reports/download/', views.admin_reports_download, name='admin_reports_download'),
]
print("ACCOUNTS URLS LOADED")
import requests
from django.conf import settings

SSLCOMMERZ_URL = "https://sandbox.sslcommerz.com/gwprocess/v4/api.php"


def initiate_payment(investment):
    data = {
        "store_id": settings.SSLCOMMERZ_STORE_ID,
        "store_passwd": settings.SSLCOMMERZ_STORE_PASSWORD,
        "total_amount": float(investment.amount),
        "currency": "BDT",
        "tran_id": f"INV{investment.id}",

        "success_url": "http://127.0.0.1:8000/accounts/payment/success/",
        "fail_url": "http://127.0.0.1:8000/accounts/payment/fail/",
        "cancel_url": "http://127.0.0.1:8000/accounts/payment/cancel/",

        "cus_name": investment.investor.username,
        "cus_email": investment.investor.email,
        "cus_phone": "0000000000",

        "product_name": investment.fund.name,
        "product_category": "Investment",
    }

    response = requests.post(SSLCOMMERZ_URL, data=data)

    return response.json()
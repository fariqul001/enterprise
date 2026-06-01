import requests
import time
from django.conf import settings
from django.utils import timezone

SSLCOMMERZ_URL = "https://sandbox.sslcommerz.com/gwprocess/v4/api.php"


def initiate_payment(investment=None, amount=None, success_url=None, fail_url=None, cancel_url=None, tran_id=None):
    # Build payload using provided values; fall back to investment data when available
    total_amount = float(amount) if amount is not None else (float(investment.amount) if investment is not None else 0)
    # Use provided tran_id or build one
    tran_id = tran_id or (f"INV{investment.id}{int(timezone.now().timestamp())}" if investment is not None else f"TRX{int(time.time())}")

    # Use KYC fields if available, otherwise fallback to defaults.
    cus_city = ''
    cus_country = 'Bangladesh'
    cus_postcode = '1207'
    cus_address = ''
    if investment is not None:
        kyc = getattr(investment.investor, 'kyc', None)
        if kyc:
            cus_city = kyc.city or cus_city
            cus_country = kyc.country or cus_country
            cus_postcode = kyc.postal_code or cus_postcode
            cus_address = kyc.address_line or ''

    data = {
        "store_id": settings.SSLCOMMERZ_STORE_ID,
        "store_passwd": settings.SSLCOMMERZ_STORE_PASSWORD,
        "total_amount": total_amount,
        "currency": "BDT",
        "tran_id": tran_id,
        "success_url": success_url,
        "fail_url": fail_url,
        "cancel_url": cancel_url,
        "cus_name": investment.investor.username if investment is not None else '',
        "cus_email": investment.investor.email if investment is not None else '',
        "cus_phone": "0000000000",
        "cus_add1": cus_address or "Dhaka",
        "cus_add2": cus_address or "Dhaka",
        "cus_city": cus_city or "Dhaka",
        "cus_state": cus_city or "Dhaka",
        "cus_postcode": cus_postcode,
        "cus_country": cus_country,
        "shipping_method": "NO",
        "product_name": investment.fund.name if investment is not None else 'Payment',
        "product_category": "Investment",
        "product_profile": "general",
    }

    try:
        response = requests.post(SSLCOMMERZ_URL, data=data, timeout=30)
    except Exception as e:
        return {"status": "FAILED", "error": f"Request failed: {str(e)}"}

    if response.status_code != 200:
        return {
            "status": "FAILED",
            "error": f"HTTP {response.status_code}: {response.text[:300]}"
        }

    try:
        return response.json()
    except ValueError:
        return {
            "status": "FAILED",
            "error": f"Invalid JSON response: {response.text[:300]}"
        }
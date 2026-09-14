"""Smoke test for the rebuilt backend API. Run from backend/: python smoke_test.py"""
import os
import sys
from decimal import Decimal

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.conf import settings  # noqa: E402

if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append("testserver")

from rest_framework.test import APIClient  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
import uuid  # noqa: E402

FAIL = []
TEST_EMAIL = f"test-{uuid.uuid4().hex[:8]}@student.edu"

# Tiny but valid enough for the upload validators (PNG magic bytes).
TEST_PNG = SimpleUploadedFile(
    "aadhar.png",
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
    content_type="image/png",
)


def check(name, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" {extra}" if not cond and extra else ""))
    if not cond:
        FAIL.append(name)


# ---- anonymous catalog
anon = APIClient()
r = anon.get("/api/v1/shifts/")
check("GET shifts 200", r.status_code == 200, r.status_code)
shifts = r.data if isinstance(r.data, list) else r.data.get("results", [])
check("shifts seeded (>=7)", len(shifts) >= 7, len(shifts))
shift_id = shifts[0]["id"]
check("shift has price", "price" in shifts[0], shifts[0])

# ---- register
anon.post("/api/v1/auth/logout/")
reg = anon.post("/api/v1/auth/register/", {
    "name": "Test Student", "email": TEST_EMAIL,
    "phone": "+91 9999999999", "gender": "female",
    "wifi_device_name": "Test-Laptop", "password": "TestPass1!",
    "confirm_password": "TestPass1!",
    "aadhar_document": TEST_PNG,
}, format="multipart")
check("register 201", reg.status_code == 201, (reg.status_code, reg.data))
token = reg.data.get("access", "")

# ---- login
login = anon.post("/api/v1/auth/login/", {"email": TEST_EMAIL, "password": "TestPass1!"})
check("login 200", login.status_code == 200, (login.status_code, login.data))

# ---- member flow
member = APIClient()
member.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

r = member.get("/api/v1/seats/available/", {"shift": shift_id})
check("seats available 200", r.status_code == 200, (r.status_code, r.data))
seats_seen = r.data.get("seats", [])
female_seats = [s for s in seats_seen if s["section"] == "female"]
check("female sees only female seats", len(female_seats) > 0 and all(s["section"] == "female" for s in seats_seen))
free_seat = next((s for s in female_seats if s["available"]), None)
check("has free seat", free_seat is not None)

seat_id = free_seat["id"] if free_seat else None
r = member.post("/api/v1/memberships/", {"shift": shift_id, "seat": seat_id, "duration_months": 2})
check("create membership 201", r.status_code == 201, (r.status_code, r.data))
m_id = r.data.get("id")
check("membership status pending_payment", r.data.get("status") == "pending_payment")
check("duration_months echoed", r.data.get("duration_months") == 2, r.data)
expected_amount = str(Decimal(shifts[0]["price"]) * 2)
check("amount = monthly price × months", r.data.get("amount") == expected_amount, r.data)

r = member.post(f"/api/v1/memberships/{m_id}/create_payment_order/")
check("create payment order 200", r.status_code == 200, (r.status_code, r.data))
order_id = r.data.get("order_id", "")

r = member.post(f"/api/v1/memberships/{m_id}/verify_payment/", {
    "razorpay_payment_id": "pay_test_123", "razorpay_signature": "sig",
})
check("verify payment 200", r.status_code == 200, (r.status_code, r.data))
check("membership active after payment", r.data.get("membership", {}).get("status") == "active")
check("seat assigned", bool(r.data.get("membership", {}).get("seat")), r.data)

r = member.get("/api/v1/memberships/my/")
check("my memberships", r.status_code == 200 and len(r.data) >= 1, r.data)

# re-verifying after activation is guarded (no double activation, no 500)
r = member.post(f"/api/v1/memberships/{m_id}/verify_payment/", {
    "razorpay_payment_id": "pay_test_123", "razorpay_signature": "sig",
})
check("verify guarded after active", r.status_code in (200, 400), (r.status_code, r.data))

# seat conflict: same seat same shift should now be unavailable for a new membership
r = member.post("/api/v1/memberships/", {"shift": shift_id, "seat": seat_id})
check("seat conflict rejected", r.status_code == 400, (r.status_code, r.data))

# gender segregation: female member cannot hold a common-section seat
r = member.get("/api/v1/seats/map/", {"shift": shift_id})
common_seat = next((s for s in r.data.get("seats", []) if s["section"] == "common"), None)
if common_seat:
    r = member.post("/api/v1/bookings/hold/", {"seat": common_seat["id"], "shift": shift_id})
    check("female cannot hold common seat", r.status_code == 400, (r.status_code, r.data))
else:
    check("female cannot hold common seat", False, "no common seat found")

# ---- admin
admin = APIClient()
r = admin.post("/api/v1/auth/login/", {"email": "admin@library.app", "password": "Admin@123"})
check("admin login", r.status_code == 200, (r.status_code, r.data))
admin.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")

r = admin.get("/api/v1/admin/dashboard/")
check("admin dashboard", r.status_code == 200 and "revenue" in r.data, (r.status_code, r.data))
check("dashboard seats keys", "seats" in r.data and "free" in r.data["seats"], r.data)

r = admin.get("/api/v1/admin/memberships/")
check("admin memberships list", r.status_code == 200, (r.status_code, r.data))

r = admin.get("/api/v1/admin/seats/")
check("admin seats list", r.status_code == 200, (r.status_code, r.data))

r = admin.get("/api/v1/admin/memberships/export/")
check("CSV export", r.status_code == 200 and "text/csv" in r.get("Content-Type", ""), r.get("Content-Type"))

r = admin.get("/api/v1/admin/dashboard/revenue/")
check("revenue series", r.status_code == 200 and isinstance(r.data, list), r.status_code)

# member cannot access admin
r = member.get("/api/v1/admin/dashboard/")
check("member denied admin", r.status_code == 403, r.status_code)

print()
if FAIL:
    print("FAILED:", ", ".join(FAIL))
    sys.exit(1)
print("ALL CHECKS PASSED")


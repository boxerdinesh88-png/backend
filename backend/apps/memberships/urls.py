from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CouponListView,
    CouponPromoView,
    CouponValidateView,
    DurationDiscountView,
    MembershipViewSet,
    PaymentSettingsView,
    RazorpayWebhookView,
)

router = DefaultRouter()
router.register("", MembershipViewSet, basename="membership")

urlpatterns = [
    # Must precede the router so "webhooks"/"payment-settings"/"coupons" are
    # never swallowed as a pk.
    path("webhooks/razorpay/", RazorpayWebhookView.as_view(), name="razorpay-webhook"),
    path("discounts/", DurationDiscountView.as_view(), name="duration-discounts"),
    path("payment-settings/", PaymentSettingsView.as_view(), name="payment-settings"),
    path("coupons/", CouponListView.as_view(), name="coupon-list"),
    path("coupons/promo/", CouponPromoView.as_view(), name="coupon-promo"),
    path("coupons/validate/", CouponValidateView.as_view(), name="coupon-validate"),
    path("", include(router.urls)),
]

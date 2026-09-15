from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DurationDiscountView,
    MembershipViewSet,
    PaymentSettingsView,
    RazorpayWebhookView,
)

router = DefaultRouter()
router.register("", MembershipViewSet, basename="membership")

urlpatterns = [
    # Must precede the router so "webhooks"/"payment-settings" are never
    # swallowed as a pk.
    path("webhooks/razorpay/", RazorpayWebhookView.as_view(), name="razorpay-webhook"),
    path("discounts/", DurationDiscountView.as_view(), name="duration-discounts"),
    path("payment-settings/", PaymentSettingsView.as_view(), name="payment-settings"),
    path("", include(router.urls)),
]

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AdminDiscountViewSet, AdminMembershipViewSet

router = DefaultRouter()
router.register("memberships", AdminMembershipViewSet, basename="admin-membership")
router.register("discounts", AdminDiscountViewSet, basename="admin-discount")

urlpatterns = [
    path("", include(router.urls)),
]

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AdminSeatViewSet, AdminShiftViewSet

router = DefaultRouter()
router.register("seats", AdminSeatViewSet, basename="admin-seat")
router.register("shifts", AdminShiftViewSet, basename="admin-shift")

urlpatterns = [
    path("", include(router.urls)),
]

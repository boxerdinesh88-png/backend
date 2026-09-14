from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AvailableSeatsView, SeatMapView, ShiftViewSet

router = DefaultRouter()
router.register("shifts", ShiftViewSet, basename="shift")

urlpatterns = [
    path("", include(router.urls)),
    path("seats/available/", AvailableSeatsView.as_view(), name="seats-available"),
    path("seats/map/", SeatMapView.as_view(), name="seats-map"),
]

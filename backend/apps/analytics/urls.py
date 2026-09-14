from django.urls import path

from .views import DashboardViewSet

view = DashboardViewSet.as_view

urlpatterns = [
    path("dashboard/", view({"get": "summary"}), name="admin-dashboard"),
    path("dashboard/revenue/", view({"get": "revenue"}), name="admin-revenue"),
    path("dashboard/recent/", view({"get": "recent"}), name="admin-recent"),
    path("dashboard/members/", view({"get": "members"}), name="admin-members"),
]

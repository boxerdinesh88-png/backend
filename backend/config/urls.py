"""Root URL configuration."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

API = "api/v1/"

urlpatterns = [
    path("admin/", admin.site.urls),
    # ---- API v1 ----
    path(f"{API}auth/", include("apps.accounts.urls")),
    # Public catalog: day-pass shifts, available seats
    path(f"{API}", include("apps.library.urls")),
    # Member memberships (create / pay / verify / seat)
    path(f"{API}memberships/", include("apps.memberships.urls")),
    # Seat booking holds (3D seat-map flow)
    path(f"{API}", include("apps.seats.urls")),
    # Public visitor reviews (anonymous survey shown on the landing page)
    path(f"{API}reviews/", include("apps.reviews.urls")),
    # Admin: CRUD + dashboard
    path(f"{API}admin/", include("apps.library.admin_urls")),
    path(f"{API}admin/", include("apps.memberships.admin_urls")),
    path(f"{API}admin/", include("apps.analytics.urls")),
    # ---- Docs ----
    path(f"{API}schema/", SpectacularAPIView.as_view(), name="schema"),
    path(f"{API}docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

# Serve uploaded media via Django as well, so profile / ID photos do not 404
# even when the PythonAnywhere static-file mapping for /media/ is missing.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

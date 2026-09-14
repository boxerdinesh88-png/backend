"""Public catalog + admin CRUD APIs for shifts and seats."""
from datetime import date

from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import error_response
from apps.core.permissions import IsAdmin

from .models import Seat, Section, Shift
from .serializers import (
    SeatAdminSerializer,
    SeatSerializer,
    SectionSerializer,
    ShiftSerializer,
)


class ShiftViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (AllowAny,)
    serializer_class = ShiftSerializer
    queryset = Shift.objects.filter(is_active=True)

    def list(self, request):
        """Cache the (rarely changing) shift catalog for 120 s.

        Every page load fetches this endpoint, so under 30-40 concurrent
        users it would otherwise hit the DB on every request for identical
        data. A short TTL keeps it fresh while cutting the DB load to ~1
        query per minute. Increased to 120s for FREE plan efficiency.
        """
        from django.core.cache import cache

        key = "api:shifts:list"
        data = cache.get(key)
        if data is None:
            data = ShiftSerializer(self.queryset, many=True).data
            cache.set(key, data, 120)  # Increased from 60s for FREE plan
        return Response(data)


class AvailableSeatsView(APIView):
    """GET /api/seats/available/?shift=&gender=&start_date=&end_date=

    Returns every active seat in the member's allowed sections with an
    `available` flag computed against overlapping active memberships for the
    requested shift and date range. `gender`/`start_date`/`end_date` are
    optional and default to the authenticated member's values.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        from apps.core.maintenance import run_light_maintenance
        from apps.memberships.services import seats_availability

        run_light_maintenance()
        shift_id = request.query_params.get("shift")
        shift = Shift.objects.filter(pk=shift_id, is_active=True).first()
        if not shift:
            return error_response("A valid shift is required.", code="shift_required")

        user = request.user
        gender = request.query_params.get("gender") or user.gender
        sections = {
            "male": ["male", "common"],
            "female": ["female"],
        }.get(gender, ["common"])

        start_date = request.query_params.get("start_date") or date.today().isoformat()
        end_date = request.query_params.get("end_date") or start_date
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except ValueError:
            return error_response("Invalid start_date/end_date.", code="invalid_date")
        if end < start:
            return error_response("end_date must be on or after start_date.", code="invalid_date")

        seats = Seat.objects.filter(is_active=True, section__in=sections).select_related("zone")
        available, _ = seats_availability(seats, shift, start, end, user=user)
        data = SeatSerializer(
            seats, many=True, context={"available": available}
        ).data
        return Response({"shift": ShiftSerializer(shift).data, "seats": data})


class SeatMapView(APIView):
    """GET /api/seats/map/?shift=&start_date=&end_date=

    Returns ALL active seats (the full physical hall, sections A–D) for the
    3D seat map, regardless of the member's section. Each seat carries
    ``available`` (free for this shift + range) and ``selectable`` (the member
    may legally pick it, e.g. not a girls-only seat for a male member).
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        from apps.core.maintenance import run_light_maintenance
        from apps.memberships.services import seats_availability

        run_light_maintenance()
        shift_id = request.query_params.get("shift")
        shift = Shift.objects.filter(pk=shift_id, is_active=True).first()
        if not shift:
            return error_response("A valid shift is required.", code="shift_required")

        start_date = request.query_params.get("start_date") or date.today().isoformat()
        end_date = request.query_params.get("end_date") or start_date
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except ValueError:
            return error_response("Invalid start_date/end_date.", code="invalid_date")
        if end < start:
            return error_response("end_date must be on or after start_date.", code="invalid_date")

        user = request.user
        allowed_sections = set(user.allowed_sections)
        seats = Seat.objects.filter(is_active=True).select_related("zone")
        available, held = seats_availability(seats, shift, start, end, user=user)
        selectable = {
            str(seat.id): seat.section in allowed_sections
            for seat in seats
        }
        data = SeatSerializer(
            seats, many=True,
            context={"available": available, "selectable": selectable, "held": held},
        ).data
        return Response(
            {
                "shift": ShiftSerializer(shift).data,
                "sections": SectionSerializer(Section.objects.all(), many=True).data,
                "seats": data,
            }
        )


class AdminSeatViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAdmin,)
    serializer_class = SeatAdminSerializer
    queryset = Seat.objects.all()


class AdminShiftViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAdmin,)
    serializer_class = ShiftSerializer
    queryset = Shift.objects.all()

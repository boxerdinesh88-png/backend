"""Member-facing booking lifecycle: hold, confirm, cancel, list mine."""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import error_response
from apps.library.models import Seat, Shift

from .models import Booking
from .serializers import BookingSerializer, HoldSerializer
from .services import SeatHoldError, cancel_booking, confirm_booking, hold_seat


class BookingViewSet(viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = BookingSerializer

    def get_queryset(self):
        return (
            Booking.objects.filter(user=self.request.user)
            .select_related("seat", "seat__zone", "shift")
        )

    @action(detail=False, methods=["get"])
    def my(self, request):
        bookings = self.get_queryset()
        return Response(BookingSerializer(bookings, many=True).data)

    @action(detail=False, methods=["post"])
    def hold(self, request):
        serializer = HoldSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Please fix the highlighted fields.",
                code="validation_error",
                fields=serializer.errors,
            )
        data = serializer.validated_data
        try:
            booking = hold_seat(
                request.user,
                data["seat"],
                data["shift"],
                data.get("start_date"),
                data.get("end_date"),
            )
        except SeatHoldError as exc:
            return error_response(str(exc), code=exc.code)
        return Response(
            BookingSerializer(booking).data, status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=["post"])
    def confirm(self, request):
        booking = self._own_booking(request)
        if not booking:
            return error_response("Booking not found.", code="not_found", status_code=status.HTTP_404_NOT_FOUND)
        try:
            confirm_booking(request.user, booking)
        except SeatHoldError as exc:
            return error_response(str(exc), code=exc.code)
        return Response(BookingSerializer(booking).data)

    @action(detail=False, methods=["post"])
    def cancel(self, request):
        booking = self._own_booking(request)
        if not booking:
            return error_response("Booking not found.", code="not_found", status_code=status.HTTP_404_NOT_FOUND)
        try:
            cancel_booking(request.user, booking)
        except SeatHoldError as exc:
            return error_response(str(exc), code=exc.code)
        return Response(BookingSerializer(booking).data)

    def _own_booking(self, request):
        booking_id = request.data.get("booking_id")
        return self.get_queryset().filter(pk=booking_id).first()

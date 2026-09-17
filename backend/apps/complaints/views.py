import logging

from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.core.exceptions import error_response

from .models import Complaint
from .serializers import ComplaintSerializer

logger = logging.getLogger("libseat.complaints")


class ComplaintViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Public complaint form: anyone can raise a complaint without an account.

    Complaints are private — there is no public list. Each submission gets a
    short reference returned to the member as confirmation; the library picks
    it up in Django admin and resolves it within one week. Abuse is contained
    by the scoped `complaints` throttle plus field length caps.
    """

    queryset = Complaint.objects.all()
    serializer_class = ComplaintSerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()
    pagination_class = None
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "complaints"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Please fix the highlighted fields.",
                code="validation_error",
                fields=serializer.errors,
            )
        complaint = serializer.save()
        logger.info(
            "complaint_created reference=%s category=%s name=%s",
            complaint.reference, complaint.category, complaint.display_name,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

import logging

from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.core.exceptions import error_response

from .models import Review
from .serializers import ReviewSerializer

logger = logging.getLogger("libseat.reviews")

MAX_LIST = 60


class ReviewViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    """Public reviews: anyone can read approved ones and submit new ones.

    Fully anonymous by design — no login wall on a public survey. Abuse is
    contained by the scoped `reviews` throttle plus field length caps; the
    `is_approved` flag lets the library hide any review from Django admin.
    """

    queryset = Review.objects.filter(is_approved=True)[:MAX_LIST]
    serializer_class = ReviewSerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()
    pagination_class = None
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "reviews"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Please fix the highlighted fields.",
                code="validation_error",
                fields=serializer.errors,
            )
        review = serializer.save()
        logger.info(
            "review_created id=%s rating=%s name=%s",
            review.id, review.rating, review.display_name,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

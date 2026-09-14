import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler

logger = logging.getLogger("libseat")


def custom_exception_handler(exc, context):
    """Normalise DRF / Django / unexpected errors into a stable envelope.

    Shape: {"detail": "...", "fields": {...}, "code": "..."}
    """
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(dict(exc) if hasattr(exc, "error_dict") else exc.messages)

    response = exception_handler(exc, context)

    if response is None:
        logger.exception("Unhandled exception", exc_info=exc)
        return Response(
            {
                "detail": "An unexpected server error occurred. Please try again.",
                "fields": {},
                "code": "internal_error",
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    detail = response.data
    if isinstance(detail, dict) and "detail" in detail:
        message = detail["detail"]
    else:
        message = " ".join(
            f"{k}: {', '.join(v) if isinstance(v, list) else v}"
            for k, v in detail.items()
        ) if isinstance(detail, dict) else detail

    response.data = {
        "detail": message,
        "fields": detail if isinstance(detail, dict) else {},
        "code": exc.get_codes() if hasattr(exc, "get_codes") else None,
        "status": response.status_code,
    }
    return response


def error_response(message, code="error", status_code=status.HTTP_400_BAD_REQUEST, fields=None):
    payload = {"detail": message, "code": code}
    if fields:
        payload["fields"] = fields
    return Response(payload, status=status_code)

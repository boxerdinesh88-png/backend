import uuid

from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator


def _star_validators():
    return [MinValueValidator(1), MaxValueValidator(5)]


class Review(models.Model):
    """Public visitor review captured by the short on-site survey.

    Anyone can submit without an account. Reviews are auto-published so they
    appear on the live site immediately; `is_approved` gives the library a
    one-click hide switch in Django admin if something inappropriate slips
    through (set the model default to False for full moderation mode).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=60, blank=True, default="")

    # The short survey: three star questions + two optional text answers.
    rating = models.PositiveSmallIntegerField(validators=_star_validators())
    atmosphere = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=_star_validators()
    )
    facilities = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=_star_validators()
    )
    liked_most = models.TextField(blank=True, default="")
    suggestion = models.TextField(blank=True, default="")

    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["is_approved", "-created_at"]),
        ]

    @property
    def display_name(self) -> str:
        return self.name.strip() or "Anonymous"

    def __str__(self):
        return f"{self.display_name} · {self.rating}★"

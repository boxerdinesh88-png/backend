import uuid

from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator


def _star_validators():
    return [MinValueValidator(1), MaxValueValidator(5)]


SATISFACTION_CHOICES = (
    ("yes", "Yes"),
    ("partially", "Partially"),
    ("no", "No"),
)

RECOMMEND_CHOICES = (
    ("definitely", "Definitely"),
    ("maybe", "Maybe"),
    ("no", "No"),
)


class Review(models.Model):
    """Student feedback form captured by the on-site survey.

    Anyone can submit without an account. Reviews are auto-published so they
    appear on the live site immediately; `is_approved` gives the library a
    one-click hide switch in Django admin if something inappropriate slips
    through (set the model default to False for full moderation mode).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=60, blank=True, default="")

    # The survey: star questions + satisfaction questions + text answers.
    rating = models.PositiveSmallIntegerField(validators=_star_validators())

    # Star ratings (1–5).
    atmosphere = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=_star_validators()
    )
    cleanliness = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=_star_validators()
    )
    power_backup = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=_star_validators()
    )
    safety = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=_star_validators()
    )
    facilities = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=_star_validators()
    )
    sports = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=_star_validators()
    )

    # Yes / Partially / No questions.
    ac_ventilation = models.CharField(
        max_length=10, choices=SATISFACTION_CHOICES, blank=True, default=""
    )
    separate_seating = models.CharField(
        max_length=10, choices=SATISFACTION_CHOICES, blank=True, default=""
    )
    refreshment_area = models.CharField(
        max_length=10, choices=SATISFACTION_CHOICES, blank=True, default=""
    )
    focused_study = models.CharField(
        max_length=10, choices=SATISFACTION_CHOICES, blank=True, default=""
    )

    # Would you recommend…?
    recommend = models.CharField(
        max_length=12, choices=RECOMMEND_CHOICES, blank=True, default=""
    )

    # Open text answers.
    liked_most = models.TextField(blank=True, default="")
    suggestion = models.TextField(blank=True, default="")
    message = models.TextField(blank=True, default="")

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

"""Public review survey: anonymous submission + approved-only listing."""
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Review

# Generous throttle so tests never trip the 10/hour spam guard.
NO_THROTTLE = {"DEFAULT_THROTTLE_RATES": {
    "anon": "1000/minute", "user": "1000/minute",
    "auth": "1000/minute", "otp": "1000/minute", "reviews": "1000/hour",
}}


def review_payload(**over):
    payload = {
        "name": "Ravi Kumar",
        "rating": 5,
        "atmosphere": 4,
        "cleanliness": 5,
        "power_backup": 4,
        "safety": 5,
        "facilities": 5,
        "sports": 3,
        "ac_ventilation": "yes",
        "separate_seating": "partially",
        "refreshment_area": "yes",
        "focused_study": "yes",
        "recommend": "definitely",
        "liked_most": "Quiet hall and a fixed window seat.",
        "suggestion": "More power sockets would help.",
        "message": "Keep the campus green.",
    }
    payload.update(over)
    return payload


@override_settings(**NO_THROTTLE)
class ReviewAPITests(APITestCase):
    def test_anonymous_submit_and_list(self):
        res = self.client.post("/api/v1/reviews/", review_payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["display_name"], "Ravi Kumar")

        listed = self.client.get("/api/v1/reviews/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)
        self.assertEqual(listed.data[0]["rating"], 5)

    def test_blank_name_displays_anonymous(self):
        res = self.client.post(
            "/api/v1/reviews/", review_payload(name="   "), format="json"
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["display_name"], "Anonymous")

    def test_rating_bounds_enforced(self):
        for bad in (0, 6, -1):
            res = self.client.post(
                "/api/v1/reviews/", review_payload(rating=bad), format="json"
            )
            self.assertEqual(res.status_code, 400)
        self.assertEqual(Review.objects.count(), 0)

    def test_text_length_cap(self):
        res = self.client.post(
            "/api/v1/reviews/",
            review_payload(liked_most="x" * 401),
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_hidden_reviews_are_not_public(self):
        Review.objects.create(rating=1, is_approved=False)
        Review.objects.create(rating=4, is_approved=True)
        listed = self.client.get("/api/v1/reviews/")
        self.assertEqual(len(listed.data), 1)
        self.assertEqual(listed.data[0]["rating"], 4)

    def test_full_feedback_roundtrip(self):
        res = self.client.post("/api/v1/reviews/", review_payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.data
        self.assertEqual(data["cleanliness"], 5)
        self.assertEqual(data["power_backup"], 4)
        self.assertEqual(data["safety"], 5)
        self.assertEqual(data["sports"], 3)
        self.assertEqual(data["ac_ventilation"], "yes")
        self.assertEqual(data["separate_seating"], "partially")
        self.assertEqual(data["refreshment_area"], "yes")
        self.assertEqual(data["focused_study"], "yes")
        self.assertEqual(data["recommend"], "definitely")
        self.assertEqual(data["message"], "Keep the campus green.")

    def test_satisfaction_choices_enforced(self):
        bad = Review(ac_ventilation="maybe", separate_seating="ok",
                     refreshment_area="fine", focused_study="sure",
                     recommend="perhaps", rating=3)
        from django.core.exceptions import ValidationError
        from django.db.models.fields import Field
        try:
            bad.full_clean()
        except ValidationError as exc:
            self.assertIn("ac_ventilation", exc.message_dict)
            self.assertIn("recommend", exc.message_dict)
        else:
            self.fail("expected ValidationError for bad choice values")

    def test_latest_first_and_capped_at_60(self):
        for i in range(65):
            Review.objects.create(rating=3 + (i % 3))
        listed = self.client.get("/api/v1/reviews/")
        self.assertEqual(len(listed.data), 60)
        newest = Review.objects.order_by("-created_at").first()
        self.assertEqual(listed.data[0]["id"], str(newest.id))


@override_settings(**NO_THROTTLE)
class ReviewModelTests(TestCase):
    def test_display_name_fallback(self):
        r = Review.objects.create(rating=2)
        self.assertEqual(r.display_name, "Anonymous")

    def test_str(self):
        r = Review.objects.create(name="Neha", rating=5)
        self.assertIn("Neha", str(r))

    def test_reverse_name(self):
        self.assertTrue(reverse("review-list").endswith("/reviews/"))

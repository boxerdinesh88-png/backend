"""Public complaint form: anonymous submission + confirmation reference."""
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Complaint
from .views import ComplaintViewSet


class NoThrottleMixin:
    """Disable the scoped throttle so tests never trip the spam guard."""

    def setUp(self):
        super().setUp()
        self._orig_throttle = ComplaintViewSet.throttle_classes
        ComplaintViewSet.throttle_classes = ()

    def tearDown(self):
        ComplaintViewSet.throttle_classes = self._orig_throttle
        super().tearDown()


def complaint_payload(**over):
    payload = {
        "name": "Ravi Kumar",
        "contact": "ravi@example.com",
        "category": "ac",
        "subject": "AC not cooling in the morning block",
        "description": "The AC in the morning block has not been cooling for a few days.",
    }
    payload.update(over)
    return payload


class ComplaintAPITests(NoThrottleMixin, APITestCase):
    def test_anonymous_submit_returns_reference(self):
        res = self.client.post("/api/v1/complaints/", complaint_payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data["reference"].startswith("PBL-"))
        self.assertFalse(res.data["is_resolved"])
        self.assertEqual(Complaint.objects.count(), 1)

    def test_reference_is_unique(self):
        refs = {
            self.client.post(
                "/api/v1/complaints/", complaint_payload(), format="json"
            ).data["reference"]
            for _ in range(5)
        }
        self.assertEqual(len(refs), 5)

    def test_subject_required(self):
        res = self.client.post(
            "/api/v1/complaints/", complaint_payload(subject="   "), format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_description_min_length(self):
        res = self.client.post(
            "/api/v1/complaints/", complaint_payload(description="help"), format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_contact_accepts_email_and_phone(self):
        for contact in ("ravi@example.com", "+91 90861 62854", "9086162854"):
            res = self.client.post(
                "/api/v1/complaints/", complaint_payload(contact=contact), format="json"
            )
            self.assertEqual(res.status_code, 201, contact)

    def test_invalid_contact_rejected(self):
        res = self.client.post(
            "/api/v1/complaints/", complaint_payload(contact="not-a-contact"), format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_blank_contact_allowed(self):
        res = self.client.post(
            "/api/v1/complaints/", complaint_payload(contact=""), format="json"
        )
        self.assertEqual(res.status_code, 201)

    def test_complaints_are_not_publicly_listed(self):
        self.client.post("/api/v1/complaints/", complaint_payload(), format="json")
        listed = self.client.get("/api/v1/complaints/")
        self.assertIn(listed.status_code, (404, 405))


class ComplaintModelTests(TestCase):
    def test_display_name_fallback(self):
        c = Complaint.objects.create(subject="x", description="y")
        self.assertEqual(c.display_name, "Anonymous")

    def test_str_and_reference(self):
        c = Complaint.objects.create(name="Neha", subject="x", description="y")
        self.assertTrue(c.reference.startswith("PBL-"))
        self.assertIn("Neha", c.display_name)
        self.assertIn(c.reference, str(c))

    def test_category_choices_enforced(self):
        bad = Complaint(category="nonsense", subject="x", description="y")
        with self.assertRaises(ValidationError) as ctx:
            bad.full_clean()
        self.assertIn("category", ctx.exception.message_dict)

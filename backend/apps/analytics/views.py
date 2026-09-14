"""Admin dashboard analytics: occupancy, membership counts, revenue."""
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.db.models.functions import ExtractMonth, ExtractYear
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.response import Response

from apps.accounts.models import User
from apps.core.permissions import IsAdmin
from apps.library.models import Seat
from apps.memberships.models import Membership, Payment

EXPIRING_SOON_DAYS = 7
SUMMARY_CACHE_TTL = 60  # Increased from 30s for FREE plan efficiency


def _paid_payments():
    return Payment.objects.filter(status="paid")


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = (IsAdmin,)

    def summary(self, request):
        today = timezone.localdate()
        cache_key = f"admin_dashboard_summary_{today.isoformat()}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        month_start = today.replace(day=1)

        # Optimize query by using values() instead of loading full objects
        active_memberships = Membership.objects.filter(status="active")
        occupied_seat_ids = set(
            active_memberships.exclude(seat_id=None).values_list("seat_id", flat=True)
        )

        seats = Seat.objects.all()
        total_seats = seats.count()
        occupied = len(occupied_seat_ids)

        section_totals = {
            row["section"]: row["total"]
            for row in seats.values("section").annotate(total=Count("id"))
        }
        section_occupied = {
            row["section"]: row["total"]
            for row in (
                seats.filter(id__in=occupied_seat_ids)
                .values("section")
                .annotate(total=Count("id"))
            )
        }

        paid = _paid_payments()
        revenue = paid.aggregate(
            today=Sum("amount", filter=Q(paid_at__date=today)),
            month=Sum("amount", filter=Q(paid_at__date__gte=month_start)),
            total=Sum("amount"),
        )

        payload = {
            "total_members": User.objects.filter(role="member").count(),
            "active_memberships": active_memberships.count(),
            "active_members": active_memberships.values("member").distinct().count(),
            "expiring_soon": active_memberships.filter(
                end_date__lte=today + timedelta(days=EXPIRING_SOON_DAYS)
            ).count(),
            "pending_payments": Membership.objects.filter(status="pending_payment").count(),
            "pending_cash_requests": Membership.objects.filter(status="pending_cash").count(),
            "seats": {
                "total": total_seats,
                "occupied": occupied,
                "free": total_seats - occupied,
                "male": {
                    "total": section_totals.get("male", 0),
                    "occupied": section_occupied.get("male", 0),
                },
                "female": {
                    "total": section_totals.get("female", 0),
                    "occupied": section_occupied.get("female", 0),
                },
                "common": {
                    "total": section_totals.get("common", 0),
                    "occupied": section_occupied.get("common", 0),
                },
            },
            "revenue": {
                "today": revenue["today"] or 0,
                "month": revenue["month"] or 0,
                "total": revenue["total"] or 0,
            },
            "memberships_by_status": {
                row["status"]: row["total"]
                for row in Membership.objects.values("status").annotate(total=Count("id"))
            },
        }
        cache.set(cache_key, payload, SUMMARY_CACHE_TTL)
        return Response(payload)

    def revenue(self, request):
        """Paid revenue aggregated by calendar month, last 12 months."""
        today = timezone.localdate()
        start = today.replace(day=1) - timedelta(days=365)
        rows = {
            (row["year"], row["month"]): row["amount"]
            for row in _paid_payments()
            .filter(paid_at__date__gte=start)
            .annotate(year=ExtractYear("paid_at"))
            .annotate(month=ExtractMonth("paid_at"))
            .values("year", "month")
            .annotate(amount=Sum("amount"))
        }

        series = []
        cursor = start
        while cursor <= today:
            key = (cursor.year, cursor.month)
            series.append(
                {
                    "month": f"{cursor.year}-{cursor.month:02d}",
                    "revenue": rows.get(key, 0),
                }
            )
            if cursor.month == 12:
                cursor = cursor.replace(year=cursor.year + 1, month=1)
            else:
                cursor = cursor.replace(month=cursor.month + 1)
        return Response(series)

    def members(self, request):
        """All registered members with their device details (IP + Wi-Fi name)."""
        qs = User.objects.filter(role="member")
        search = request.query_params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(email__icontains=search))
        qs = qs.order_by("-date_joined")
        # Optimize by using values() instead of loading full objects
        return Response(
            [
                {
                    "id": str(u["id"]),
                    "name": u["name"],
                    "email": u["email"],
                    "phone": u["phone"],
                    "gender": u["gender"],
                    "purpose": u["purpose"],
                    "class_name": u["class_name"],
                    "wifi_device_name": u["wifi_device_name"],
                    "ip_address": str(u["ip_address"]) if u["ip_address"] else None,
                    "is_email_verified": u["is_email_verified"],
                    "date_joined": u["date_joined"].isoformat(),
                }
                for u in qs.values(
                    "id", "name", "email", "phone", "gender", "purpose", "class_name",
                    "wifi_device_name", "ip_address", "is_email_verified", "date_joined"
                )
            ]
        )

    def recent(self, request):
        # Optimize by using values() with select_related for foreign keys
        memberships = (
            Membership.objects.select_related("member", "shift", "seat")
            .order_by("-created_at")[:10]
        )
        return Response(
            [
                {
                    "id": str(m.id),
                    "member_name": m.member.name,
                    "email": m.member.email,
                    "shift": m.shift.name,
                    "seat": m.seat.seat_number if m.seat else None,
                    "status": m.status,
                    "amount": float(m.amount),
                    "created_at": m.created_at.isoformat(),
                }
                for m in memberships
            ]
        )

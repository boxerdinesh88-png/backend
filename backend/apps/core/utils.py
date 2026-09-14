import random
import secrets
import string


def generate_otp(length=6):
    return "".join(secrets.choice("0123456789") for _ in range(length))


def generate_booking_id():
    return "LS-" + secrets.token_hex(3).upper()


def generate_ref_code():
    return "REF" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def haversine_km(lat1, lng1, lat2, lng2):
    """Distance between two lat/lng pairs in kilometres (Haversine)."""
    import math

    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))

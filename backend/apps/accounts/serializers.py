import base64
import re
import uuid
from pathlib import Path

from django.contrib.auth import authenticate
from django.core.files.base import ContentFile
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User

STRONG_PASSWORD = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$"
)

MAX_UPLOAD_BYTES = 3 * 1024 * 1024  # Reduced from 5MB to 3MB for FREE plan optimization
DOCUMENT_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "webp"}
PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
DOCUMENT_KINDS = {"pdf", "jpeg", "png", "webp"}
PHOTO_KINDS = {"jpeg", "png", "webp"}


def _sniff_kind(header: bytes):
    if header[:5] == b"%PDF-":
        return "pdf"
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if header[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    return None


def _validate_upload(value, extensions, kinds, message):
    ext = Path(value.name).suffix.lower().lstrip(".")
    if ext not in extensions:
        raise serializers.ValidationError(message)
    if value.size and value.size > MAX_UPLOAD_BYTES:
        raise serializers.ValidationError("File must be 3 MB or smaller.")
    kind = _sniff_kind(value.file.read(16))
    value.file.seek(0)
    if kind not in kinds:
        raise serializers.ValidationError(
            "The file doesn't look like a valid PDF or image."
        )
    return value


def validate_identity_document(value):
    return _validate_upload(
        value, DOCUMENT_EXTENSIONS, DOCUMENT_KINDS,
        "Only PDF, JPG, PNG or WebP documents are allowed.",
    )


def validate_photo(value):
    return _validate_upload(
        value, PHOTO_EXTENSIONS, PHOTO_KINDS,
        "Only JPG, PNG or WebP images are allowed.",
    )


def validate_password_strength(value):
    if not STRONG_PASSWORD.match(value or ""):
        raise serializers.ValidationError(
            "Password must be 8+ characters with at least one uppercase letter, "
            "one lowercase letter and one number."
        )
    return value


DATA_URL_MIME_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}


def _data_url_to_file(data):
    try:
        header, b64 = data.split(",", 1)
        mime = header[5:].split(";", 1)[0].strip().lower()
        ext = DATA_URL_MIME_EXT.get(mime)
        if not ext:
            return None
        raw = base64.b64decode(b64, validate=True)
        if not raw:
            return None
        return ContentFile(raw, name=f"upload_{uuid.uuid4().hex}.{ext}")
    except Exception:
        return None


class DataURLFileField(serializers.Field):
    """Accept either a normal multipart file upload or a JSON base64 data URL.

    Mobile browsers sometimes drop multipart POSTs mid-flight, so the app can
    send files as ``data:<mime>;base64,<payload>`` strings inside a plain JSON
    body. The decoded bytes go through the same validators as a real upload.
    """

    def to_internal_value(self, data):
        if isinstance(data, str) and data.startswith("data:"):
            f = _data_url_to_file(data)
            if f is None:
                raise serializers.ValidationError(
                    "The uploaded file is invalid or corrupt."
                )
            return f
        return data


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


class UserSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()
    aadhar_document_url = serializers.SerializerMethodField()
    aadhar_document_back_url = serializers.SerializerMethodField()
    photo = serializers.ImageField(
        required=False, allow_null=True, validators=[validate_photo]
    )
    aadhar_document = serializers.FileField(
        required=False, allow_null=True, validators=[validate_identity_document]
    )
    aadhar_document_back = serializers.FileField(
        required=False, allow_null=True, validators=[validate_identity_document]
    )

    class Meta:
        model = User
        fields = (
            "id", "name", "email", "phone", "gender",
            "aadhar_document", "aadhar_document_url", "aadhar_document_back", "aadhar_document_back_url",
            "photo", "photo_url",
            "purpose", "class_name",
            "wifi_device_name", "wifi_device_name_2", "ip_address", "role",
            "is_email_verified", "date_joined",
        )
        read_only_fields = (
            "id", "email", "role", "ip_address", "is_email_verified", "date_joined",
            "photo_url", "aadhar_document_url", "aadhar_document_back_url",
        )

    def get_photo_url(self, obj):
        request = self.context.get("request")
        if obj.photo and request:
            return request.build_absolute_uri(obj.photo.url)
        if obj.photo:
            return obj.photo.url
        return None

    def get_aadhar_document_url(self, obj):
        request = self.context.get("request")
        if obj.aadhar_document and request:
            return request.build_absolute_uri(obj.aadhar_document.url)
        if obj.aadhar_document:
            return obj.aadhar_document.url
        return None

    def get_aadhar_document_back_url(self, obj):
        request = self.context.get("request")
        if obj.aadhar_document_back and request:
            return request.build_absolute_uri(obj.aadhar_document_back.url)
        if obj.aadhar_document_back:
            return obj.aadhar_document_back.url
        return None


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, validators=[validate_password_strength]
    )
    confirm_password = serializers.CharField(write_only=True)
    aadhar_document = DataURLFileField(
        write_only=True, validators=[validate_identity_document]
    )
    aadhar_document_back = DataURLFileField(
        required=False, write_only=True, allow_null=True, validators=[validate_identity_document]
    )
    photo = DataURLFileField(
        required=False, write_only=True, allow_null=True, validators=[validate_photo]
    )

    class Meta:
        model = User
        fields = (
            "name", "email", "phone", "gender",
            "aadhar_document", "aadhar_document_back", "photo", "purpose", "class_name",
            "wifi_device_name", "wifi_device_name_2", "ip_address", "password", "confirm_password",
        )

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("confirm_password"):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        if attrs.get("gender") not in ("male", "female", "other"):
            raise serializers.ValidationError({"gender": "Invalid gender value."})
        if not attrs.get("aadhar_document"):
            raise serializers.ValidationError({"aadhar_document": "Please upload your Aadhaar card."})
        return attrs

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["email"],
            password=attrs["password"],
        )
        if not user or not user.is_active:
            raise serializers.ValidationError("Invalid credentials.")
        attrs["user"] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(validators=[validate_password_strength])


class OTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    gender = serializers.ChoiceField(
        choices=("male", "female", "other"), required=False, allow_null=True
    )


class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=10)
    purpose = serializers.ChoiceField(choices=("verify_email", "reset_password"))


class PhoneOTPRequestSerializer(serializers.Serializer):
    phone = serializers.RegexField(regex=r"^\+?[0-9\s\-]{10,15}$")


class PhoneOTPVerifySerializer(serializers.Serializer):
    phone = serializers.RegexField(regex=r"^\+?[0-9\s\-]{10,15}$")
    code = serializers.CharField(max_length=10)


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=10)
    new_password = serializers.CharField(validators=[validate_password_strength])

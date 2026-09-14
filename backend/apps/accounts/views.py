from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.exceptions import error_response
from apps.core.ip import client_ip as _client_ip

from .models import User
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    PasswordResetConfirmSerializer,
    PhoneOTPRequestSerializer,
    PhoneOTPVerifySerializer,
    RegisterSerializer,
    UserSerializer,
    get_tokens_for_user,
)
from .services import OTPCooldownError, issue_otp, send_otp_email, verify_otp


def _auth_payload(user, request=None):
    tokens = get_tokens_for_user(user)
    return {
        **tokens,
        "user": UserSerializer(user, context={"request": request}).data,
    }


def _user_by_email(email):
    """Case-insensitive lookup that never raises MultipleObjectsReturned.

    ``email`` has a case-sensitive UNIQUE constraint, so ``Name@x.com`` and
    ``name@x.com`` can coexist. Login/OTP lookups are case-insensitive and
    would otherwise crash with 500; always resolve to the oldest account.
    """
    return User.objects.filter(email__iexact=email).order_by("date_joined").first()


class RegisterView(APIView):
    permission_classes = (AllowAny,)
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Please fix the highlighted fields.",
                code="validation_error",
                status_code=status.HTTP_400_BAD_REQUEST,
                fields=serializer.errors,
            )
        user = serializer.save(ip_address=_client_ip(request))
        try:
            code = issue_otp(user, purpose="verify_email")
            send_otp_email(user, code, purpose="verify_email")
        except OTPCooldownError:
            pass
        return Response(
            {
                "message": "Account created. Verify your email with the code we sent.",
                **_auth_payload(user, request),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = (AllowAny,)
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return error_response(
                "Invalid email or password.", code="invalid_credentials",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        user = serializer.validated_data["user"]
        return Response(_auth_payload(user, request))


class RefreshView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return error_response("refresh token required", code="missing_refresh")
        try:
            token = RefreshToken(refresh)
            return Response({"access": str(token.access_token)})
        except Exception:
            return error_response("invalid refresh token", code="invalid_refresh",
                                  status_code=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            RefreshToken(request.data.get("refresh", "")).blacklist()
        except Exception:
            pass
        return Response({"message": "Logged out."})


class ProfileView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)

    def patch(self, request):
        data = request.data.copy()
        # Multipart forms can't send a true null. A cleared document/photo
        # arrives as an empty part -> normalise it to None so the fields are
        # actually removed from the profile.
        for field in ("aadhar_document", "aadhar_document_back", "photo"):
            if data.get(field) == "":
                data[field] = None
        serializer = UserSerializer(
            request.user, data=data, partial=True, context={"request": request}
        )
        if not serializer.is_valid():
            return error_response("Validation failed", fields=serializer.errors)
        serializer.save()
        return Response(UserSerializer(request.user, context={"request": request}).data)


class ChangePasswordView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return error_response("Current password is incorrect.", code="wrong_password")
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response({"message": "Password changed."})


class RequestOTPView(APIView):
    permission_classes = (AllowAny,)
    throttle_scope = "otp"

    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        gender = serializer.validated_data.get("gender")
        user = _user_by_email(email)
        if user is None:
            # Auto-create a stub account so the OTP has somewhere to land.
            # The gender picked at sign-in decides which seat sections the
            # member may use (female → girls-only / male → common).
            from django.contrib.auth import get_user_model
            User = get_user_model()
            stub_name = email.split("@")[0].replace(".", " ").replace("_", " ").title()
            user = User.objects.create_user(
                email=email,
                password=None,
                name=stub_name,
                gender=gender or "other",
            )
        elif gender and not user.is_admin and not (user.class_name and user.purpose):
            # First sign-in (before the profile form is filled) the gender
            # picked here decides the seat section. Once a member has completed
            # the profile form, the gender saved there is authoritative — a
            # later login must NOT silently overwrite what they chose in the
            # form ("you can change it here anytime").
            user.gender = gender
            user.save(update_fields=["gender"])
        try:
            code = issue_otp(user, purpose="verify_email")
            send_otp_email(user, code, purpose="verify_email")
        except OTPCooldownError:
            pass
        return Response({"message": "A code was sent to your email."})


class VerifyOTPView(APIView):
    permission_classes = (AllowAny,)
    throttle_scope = "otp"

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        purpose = serializer.validated_data["purpose"]
        user = _user_by_email(email)
        if user is None:
            return error_response("Invalid or expired code.", code="invalid_otp")
        if not verify_otp(user, purpose, serializer.validated_data["code"]):
            return error_response("Invalid or expired code.", code="invalid_otp")
        if purpose == "verify_email":
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified"])
        return Response({"message": "Verified successfully.", **_auth_payload(user, request)})


class PhoneRequestOTPView(APIView):
    permission_classes = (AllowAny,)
    throttle_scope = "otp"

    def post(self, request):
        serializer = PhoneOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        user = request.user if request.user.is_authenticated else None
        if user is None:
            return Response({"message": "If that number is registered, a code was sent."})
        try:
            code = issue_otp(user, purpose="verify_phone")
            from apps.notifications.channels import SmsChannel

            SmsChannel().send(user, "OTP", f"Your library verification code is: {code}")
        except OTPCooldownError:
            pass
        return Response({"message": "If that number is registered, a code was sent."})


class PhoneVerifyOTPView(APIView):
    permission_classes = (AllowAny,)
    throttle_scope = "otp"

    def post(self, request):
        serializer = PhoneOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        code = serializer.validated_data["code"]
        user = request.user if request.user.is_authenticated else None
        if user is None:
            return error_response("Invalid or expired code.", code="invalid_otp")
        if not verify_otp(user, "verify_phone", code):
            return error_response("Invalid or expired code.", code="invalid_otp")
        user.phone = phone
        user.save(update_fields=["phone"])
        return Response({"message": "Verified successfully.", "phone": phone})


class ForgotPasswordView(APIView):
    permission_classes = (AllowAny,)
    throttle_scope = "otp"

    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = _user_by_email(serializer.validated_data["email"])
        if user is None:
            return Response({"message": "If that email exists, a reset code was sent."})
        try:
            code = issue_otp(user, purpose="reset_password")
            send_otp_email(user, code, purpose="reset_password")
        except OTPCooldownError:
            pass
        return Response({"message": "If that email exists, a reset code was sent."})


class ResetPasswordView(APIView):
    permission_classes = (AllowAny,)
    throttle_scope = "otp"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = _user_by_email(serializer.validated_data["email"])
        if user is None:
            return error_response("Invalid or expired code.", code="invalid_otp")
        if not verify_otp(user, "reset_password", serializer.validated_data["code"]):
            return error_response("Invalid or expired code.", code="invalid_otp")
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response({"message": "Password reset successfully."})

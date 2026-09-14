from django.urls import path

from .views import (
    ChangePasswordView,
    ForgotPasswordView,
    LoginView,
    LogoutView,
    PhoneRequestOTPView,
    PhoneVerifyOTPView,
    ProfileView,
    RefreshView,
    RegisterView,
    RequestOTPView,
    ResetPasswordView,
    VerifyOTPView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("otp/request/", RequestOTPView.as_view(), name="auth-otp-request"),
    path("otp/verify/", VerifyOTPView.as_view(), name="auth-otp-verify"),
    path("otp/phone/request/", PhoneRequestOTPView.as_view(), name="auth-phone-otp-request"),
    path("otp/phone/verify/", PhoneVerifyOTPView.as_view(), name="auth-phone-otp-verify"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="auth-forgot"),
    path("reset-password/", ResetPasswordView.as_view(), name="auth-reset"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("profile/", ProfileView.as_view(), name="auth-profile"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
]

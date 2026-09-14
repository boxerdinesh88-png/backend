"""Authentication backends.

Emails are matched case-insensitively: registration preserves the local-part
case (Django's ``normalize_email`` only lowercases the domain), but users type
their address in any case at login. An exact-match lookup would reject
``Name@Example.com`` vs ``name@example.com``, so we look up by ``email__iexact``.
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

UserModel = get_user_model()


class EmailModelBackend(ModelBackend):
    """Authenticate by email, ignoring case (and any whitespace)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return
        try:
            user = UserModel._default_manager.get(
                email__iexact=username.strip()
            )
        except UserModel.DoesNotExist:
            UserModel().set_password(password)
            return
        except UserModel.MultipleObjectsReturned:
            return
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

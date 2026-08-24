"""
Auth endpoints for the React SPA (frontend/) - thin JSON wrappers
around the exact same logic RAG/auth_views.py's classic login_user()/
logout_user() already run (rate limiting, remember-me session expiry,
activity logging, the indistinguishable-from-wrong-password OTP-pending
branch). No authentication/authorization behavior is duplicated or
reimplemented here, only re-exposed as JSON instead of an HTML redirect.

OTP verification and signup are deliberately NOT ported to the SPA in
this increment - login_api redirects the browser to the existing
Django /verify-otp/ page (a real navigation, not an API call) for the
one case that needs it, so that flow keeps working unchanged.
"""

from django.contrib.auth import authenticate, login, logout
from django.conf import settings
from django.middleware.csrf import get_token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..models import User
from ..services import otp_service
from ..services.activity_log_service import log_activity
from ..services.geolocation_service import get_client_ip
from ..services.permission_service import get_user_access_snapshot, has_admin_area_access
from ..services.rate_limit_service import is_rate_limited

LOGIN_ATTEMPTS_PER_USERNAME = (5, 900)
LOGIN_ATTEMPTS_PER_IP = (20, 900)


def _session_payload(request):
    role, can_view_admin_area, user_permissions = get_user_access_snapshot(request.user)
    return {
        "authenticated": True,
        "user": {
            "id": request.user.id,
            "username": request.user.username,
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "email": request.user.email,
        },
        "role": role.name if role else None,
        "can_view_admin_area": can_view_admin_area,
        "permissions": user_permissions,
        "csrf_token": get_token(request),
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def session_view(request):
    """
    Bootstrap endpoint the SPA calls once on load - also the only
    reliable place to hand the CSRF token to JS (see api/permissions.py
    module docstring / settings.py's REST_FRAMEWORK comment on why the
    cookie itself is httponly). Anonymous callers still get a fresh
    token back (get_token() sets the cookie as a side effect) so the
    very first login POST already carries a valid one.
    """

    if not request.user.is_authenticated:
        return Response({"authenticated": False, "csrf_token": get_token(request)})

    return Response(_session_payload(request))


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""
    remember_me = bool(request.data.get("remember_me"))

    ip = get_client_ip(request)

    username_limited = username and is_rate_limited(f"login:user:{username.lower()}", *LOGIN_ATTEMPTS_PER_USERNAME)
    ip_limited = ip and is_rate_limited(f"login:ip:{ip}", *LOGIN_ATTEMPTS_PER_IP)

    if username_limited or ip_limited:
        return Response(
            {"error": "Too many login attempts. Please wait a few minutes and try again."},
            status=429,
        )

    user = authenticate(request, username=username, password=password)

    if user is None and username and password:
        candidate = User.objects.filter(username__iexact=username, is_active=False).first()
        if candidate and candidate.check_password(password) and otp_service.has_pending_verification(candidate):
            request.session["pending_verification_user_id"] = candidate.id
            return Response({"pending_verification": True, "redirect": "/verify-otp/"})

    if user is None:
        return Response({"error": "Invalid username or password."}, status=400)

    login(request, user)

    if remember_me:
        request.session.set_expiry(settings.REMEMBER_ME_SESSION_AGE)
    else:
        request.session.set_expiry(0)

    log_activity(
        actor=user,
        action="user.login",
        description=f"{user.username} logged in",
        request=request,
    )

    return Response(_session_payload(request))


@api_view(["POST"])
def logout_view(request):
    log_activity(
        actor=request.user,
        action="user.logout",
        description=f"{request.user.username} logged out",
        request=request,
    )
    logout(request)
    return Response({"authenticated": False, "csrf_token": get_token(request)})

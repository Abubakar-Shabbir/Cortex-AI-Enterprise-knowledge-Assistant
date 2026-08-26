"""
Profile endpoints for the React SPA - thin JSON wrappers around the
exact same section handlers RAG/views.py's profile_view() POST-dispatch
already runs (`_save_extended_profile_fields`, PasswordChangeForm,
notification preference toggling), split into one endpoint per section
instead of one view keyed by a hidden "form" field, since a JSON API
has no reason to keep that single-view-multiple-forms shape. No new
business logic - same helper functions, same models, same validation.
"""

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from ..models import User, UserProfile
from ..services import device_intelligence_service, notification_service
from ..services.activity_log_service import log_activity
from ..services.profile_completion_service import get_completion
from ..services.stats_service import get_activity_summary
from ..views import TOGGLEABLE_EMAIL_CATEGORIES, _save_extended_profile_fields


def _role_name(user):
    try:
        return user.role_assignment.role.name
    except AttributeError:
        return None


def _serialize_profile(user, session_key=None):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    completion = get_completion(user, profile)

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "date_joined": user.date_joined,
            "last_login": user.last_login,
            "role_name": _role_name(user),
        },
        "profile": {
            "avatar_url": profile.avatar.url if profile.avatar else None,
            "headline": profile.headline,
            "job_title": profile.job_title,
            "department": profile.department,
            "team": profile.team,
            "employee_id": profile.employee_id,
            "phone": profile.phone,
            "location": profile.location,
            "manager_id": profile.manager_id,
            "timezone": profile.timezone,
            "language": profile.language,
            "profile_visibility": profile.profile_visibility,
            "linkedin_url": profile.linkedin_url,
            "github_url": profile.github_url,
            "portfolio_url": profile.portfolio_url,
            "skills": profile.skills or [],
            "certifications": profile.certifications or [],
        },
        "completion": completion,
        "activity_summary": get_activity_summary(user),
        "is_online": device_intelligence_service.is_online(user),
        "account_health": device_intelligence_service.get_account_health(user),
        "last_active": device_intelligence_service.get_last_active(user),
        "manager_options": [
            {"id": u.id, "name": u.get_full_name() or u.username}
            for u in User.objects.exclude(id=user.id).order_by("username")
        ],
        "timezone_choices": UserProfile.COMMON_TIMEZONES,
        "language_choices": [{"code": code, "label": label} for code, label in UserProfile.LANGUAGE_CHOICES],
        "visibility_choices": [{"value": value, "label": label} for value, label in UserProfile.Visibility.choices],
        "notification_preferences": {
            "disabled_email_categories": notification_service.get_or_create_preferences(user).disabled_email_categories,
        },
        "toggleable_email_categories": [
            {"key": key, "label": label, "description": description}
            for key, label, description in TOGGLEABLE_EMAIL_CATEGORIES
        ],
        "current_device": device_intelligence_service.parse_device(""),  # overwritten below with the real request UA
        "login_history": device_intelligence_service.get_login_history(user),
        "active_sessions": device_intelligence_service.get_active_sessions(user, session_key),
    }


@api_view(["GET"])
def profile_view(request):
    data = _serialize_profile(request.user, request.session.session_key)
    data["current_device"] = device_intelligence_service.parse_device(request.META.get("HTTP_USER_AGENT", ""))
    return Response(data)


@api_view(["POST"])
def profile_personal_view(request):
    user = request.user
    user.first_name = (request.data.get("first_name") or "").strip()
    user.last_name = (request.data.get("last_name") or "").strip()
    user.email = (request.data.get("email") or "").strip()
    user.save()

    log_activity(actor=user, action="profile.updated", description=f"{user.username} updated their personal information", request=request)

    return Response(_serialize_profile(user, request.session.session_key))


@api_view(["POST"])
def profile_extended_view(request):
    """`skills`/`certifications` arrive as JSON arrays (request.data), unlike the classic view's request.POST.getlist() form fields - _save_extended_profile_fields only needs .get()/.getlist(), so a tiny dict-like shim bridges the two without touching that shared helper."""

    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    class _PostShim(dict):
        def getlist(self, key):
            value = self.get(key)
            return value if isinstance(value, list) else ([] if value is None else [value])

    post = _PostShim(request.data)
    _save_extended_profile_fields(profile, request.user, post)

    log_activity(actor=request.user, action="profile.updated", description=f"{request.user.username} updated their profile details", request=request)

    return Response(_serialize_profile(request.user, request.session.session_key))


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def profile_avatar_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if "avatar" not in request.FILES:
        return Response({"error": "No file provided."}, status=400)

    profile.avatar = request.FILES["avatar"]
    profile.save(update_fields=["avatar", "updated_at"])

    log_activity(actor=request.user, action="profile.updated", description=f"{request.user.username} updated their profile photo", request=request)

    return Response({"avatar_url": profile.avatar.url})


@api_view(["POST"])
def profile_notifications_view(request):
    preferences = notification_service.get_or_create_preferences(request.user)
    toggleable = {key for key, _, _ in TOGGLEABLE_EMAIL_CATEGORIES}
    enabled = set(request.data.get("email_categories") or []) & toggleable
    preferences.disabled_email_categories = sorted(toggleable - enabled)
    preferences.save(update_fields=["disabled_email_categories", "updated_at"])

    return Response({"disabled_email_categories": preferences.disabled_email_categories})


@api_view(["POST"])
def profile_password_view(request):
    form = PasswordChangeForm(request.user, {
        "old_password": request.data.get("old_password", ""),
        "new_password1": request.data.get("new_password1", ""),
        "new_password2": request.data.get("new_password2", ""),
    })

    if not form.is_valid():
        return Response({"errors": {field: list(messages) for field, messages in form.errors.items()}}, status=400)

    user = form.save()
    update_session_auth_hash(request, user)

    log_activity(actor=user, action="user.password_changed", description=f"{user.username} changed their password", request=request)

    notification_service.create_notification(
        recipient=user,
        notification_type="account.password_changed",
        title="Your password was changed",
        message="Your password was just changed. If this wasn't you, contact support immediately.",
    )

    return Response({"ok": True})

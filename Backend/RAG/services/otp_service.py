"""
Email OTP Verification (signup)

Generates, sends, and verifies the 6-digit code a new account must
enter before it's activated. The code is never stored in plaintext -
EmailOTP.code_hash uses Django's own password hasher (make_password/
check_password), and the plaintext value exists only as a local
variable in generate_and_send_otp() and as an argument to the
backgrounded email-send task - never logged, never returned in any
response (RAG.services.task_runner's exception logging only ever logs
a failed task's function name, never its arguments - see that
module's _run()).

Two independent abuse guards, deliberately layered:
- EmailOTP.attempt_count - a durable, per-row cap (MAX_OTP_ATTEMPTS),
  survives a process restart, auditable on the row itself.
- rate_limit_service - a cache-based cap across *all* of a user's OTP
  rows (resend cooldown/hourly cap, verify attempts/10min), so
  requesting a fresh OTP can't be used to reset the per-row counter
  and keep guessing indefinitely.
"""

import logging
import secrets
import string

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from ..models import EmailOTP
from .rate_limit_service import get_cooldown_remaining_seconds, is_rate_limited, start_cooldown

logger = logging.getLogger(__name__)

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 10
MAX_OTP_ATTEMPTS = 5

RESEND_COOLDOWN_SECONDS = 60
RESEND_HOURLY_LIMIT = (5, 3600)
VERIFY_ATTEMPTS_LIMIT = (10, 600)


def _generate_code() -> str:
    """Cryptographically secure, not random.choice - this gates account activation, same standard as a password reset token."""

    return "".join(secrets.choice(string.digits) for _ in range(OTP_LENGTH))


def generate_and_send_otp(user) -> None:
    """
    Invalidates any prior unused SIGNUP OTPs for `user` (so only the
    most recently sent code is ever valid - typing in an old email's
    code after requesting a new one should never work), creates a new
    one, and dispatches the email send in the background. Never raises
    - a dispatch failure is logged by task_runner itself; the caller
    (auth_views.signup/resend_otp) always proceeds to the "check your
    email" screen regardless, since a transient SMTP hiccup shouldn't
    be distinguishable to the user from a slow but working send.
    """

    EmailOTP.objects.filter(user=user, purpose=EmailOTP.Purpose.SIGNUP, is_used=False).update(is_used=True)

    code = _generate_code()

    otp = EmailOTP.objects.create(
        user=user,
        purpose=EmailOTP.Purpose.SIGNUP,
        code_hash=make_password(code),
        expires_at=timezone.now() + timezone.timedelta(minutes=OTP_EXPIRY_MINUTES),
    )

    start_cooldown(f"otp_resend_cd:{user.id}", RESEND_COOLDOWN_SECONDS)

    from . import task_runner
    from ..tasks import send_otp_email_task
    task_runner.submit(send_otp_email_task, user.id, code, otp.expires_at.isoformat())


def can_resend(user) -> tuple[bool, int]:
    """(allowed, seconds_remaining). Checked before generate_and_send_otp() is called again from resend_otp()."""

    cooldown_remaining = get_cooldown_remaining_seconds(f"otp_resend_cd:{user.id}")
    if cooldown_remaining > 0:
        return False, cooldown_remaining

    limit, window = RESEND_HOURLY_LIMIT
    if is_rate_limited(f"otp_resend_hr:{user.id}", limit, window):
        return False, window

    return True, 0


def verify_otp(user, submitted_code: str) -> tuple[bool, str]:
    """
    Returns (success, status) where status is one of:
    "" (success), "expired", "invalid", "max_attempts", "none_pending",
    "rate_limited" - the exact vocabulary verify_otp view needs to show
    a distinct message per state. On success: marks the OTP used,
    activates the account, marks the profile verified, and fires an
    "account.verified" notification. Does NOT call django.contrib.auth.login()
    - that needs `request`, so it stays the view's responsibility
    (services own data/state changes, views own request-scoped side
    effects, same split RAG.views.document_share already follows for
    notifications).
    """

    limit, window = VERIFY_ATTEMPTS_LIMIT
    if is_rate_limited(f"otp_verify:{user.id}", limit, window):
        return False, "rate_limited"

    otp = (
        EmailOTP.objects
        .filter(user=user, purpose=EmailOTP.Purpose.SIGNUP, is_used=False)
        .order_by("-created_at")
        .first()
    )

    if otp is None:
        return False, "none_pending"

    if otp.attempt_count >= MAX_OTP_ATTEMPTS:
        return False, "max_attempts"

    if otp.expires_at < timezone.now():
        return False, "expired"

    if not check_password(submitted_code, otp.code_hash):
        otp.attempt_count += 1
        otp.save(update_fields=["attempt_count"])
        if otp.attempt_count >= MAX_OTP_ATTEMPTS:
            return False, "max_attempts"
        return False, "invalid"

    otp.is_used = True
    otp.used_at = timezone.now()
    otp.save(update_fields=["is_used", "used_at"])

    user.is_active = True
    user.save(update_fields=["is_active"])

    from ..models import UserProfile
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.email_verified = True
    profile.save(update_fields=["email_verified"])

    from .notification_service import create_notification
    create_notification(
        recipient=user,
        notification_type="account.verified",
        title="Your email is verified",
        message="Your account is now fully set up.",
        send_email=False,  # they just proved they can read this inbox - no need to email them about it too
    )

    _convert_pending_share_invites(user)

    return True, ""


def _convert_pending_share_invites(user) -> None:
    """
    The one and only place a pending DocumentShare.invited_email
    becomes real access (see that field's own docstring on
    RAG.models.DocumentShare). Runs here - inside verify_otp(), right
    after activation - because this is the exact moment ownership of
    `user.email` is actually proven: the OTP was emailed to that
    address and typed back correctly, which is a stronger guarantee
    than the query-param-only prefill signup() does.
    """

    from ..models import DocumentShare
    from .notification_service import create_notification, document_open_url

    pending = DocumentShare.objects.filter(
        invited_email__iexact=user.email, shared_with_user__isnull=True,
    ).select_related("document", "shared_by")

    for share in pending:
        share.shared_with_user = user
        share.invited_email = ""
        share.save(update_fields=["shared_with_user", "invited_email"])

        create_notification(
            recipient=user,
            actor=share.shared_by,
            notification_type="document.shared",
            title=f"{share.shared_by.username if share.shared_by else 'Someone'} shared a document with you",
            message=f'"{share.document.title}" was shared with you.',
            data={"document_id": share.document_id, "share_id": share.id},
            action_url=document_open_url(share.document_id),
        )


def has_pending_verification(user) -> bool:
    """
    True if `user` has at least one unused, unexpired SIGNUP OTP - the
    signal auth_views.login_user uses to tell "this account is
    unverified" apart from "this account was suspended by an admin"
    (both are is_active=False, but only one has a pending OTP; see
    that view's own comment for why conflating them would be a real
    bug, not just a UX nit).
    """

    return EmailOTP.objects.filter(
        user=user, purpose=EmailOTP.Purpose.SIGNUP, is_used=False, expires_at__gte=timezone.now(),
    ).exists()

"""
Authentication views - signup, login, logout (and, from Phase 5/6
onward, OTP verification and password reset). Moved out of the
3400-line RAG/views.py into their own module since this is the
highest-risk, most-rewritten surface in the whole feature: real Django
forms with password-strength enforcement, rate limiting, and (later)
email OTP verification, replacing the previous raw request.POST[...]
handling that had none of that.

URL *names* (signup/login/logout) are unchanged from before this
module existed - every {% url %} reference elsewhere in the project
keeps working without modification; only urls.py's view target moved.
"""

import logging

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import views as django_auth_views
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from .models import Role, UserRole
from .services import otp_service
from .services.activity_log_service import log_activity
from .services.geolocation_service import get_client_ip
from .services.notification_service import create_notification
from .services.permission_service import USER, get_dashboard_url_for_user
from .services.rate_limit_service import is_rate_limited
from .utils.formatting import mask_email

PASSWORD_RESET_ATTEMPTS_PER_EMAIL = (3, 3600)   # 3 per hour
PASSWORD_RESET_ATTEMPTS_PER_IP = (10, 3600)     # 10 per hour

logger = logging.getLogger(__name__)

LOGIN_ATTEMPTS_PER_USERNAME = (5, 900)   # 5 per 15 minutes
LOGIN_ATTEMPTS_PER_IP = (20, 900)        # 20 per 15 minutes
SIGNUP_ATTEMPTS_PER_IP = (10, 3600)      # 10 per hour


class SignupForm(forms.Form):
    """
    Replaces signup()'s previous raw request.POST[...] handling (no
    validation beyond "password == confirm_password", no duplicate-
    email check, an uncaught IntegrityError on a duplicate username).
    Real per-field errors, case-insensitive uniqueness, and Django's
    own AUTH_PASSWORD_VALIDATORS enforced via validate_password() -
    the same validator set PasswordChangeForm already runs for
    in-session password changes (RAG.views.profile_view).
    """

    full_name = forms.CharField(max_length=150, label="Full name")
    email = forms.EmailField(label="Email")
    username = forms.CharField(max_length=150, label="Username")
    password = forms.CharField(widget=forms.PasswordInput, label="Password")
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("That username is already taken.")
        return username

    def clean_password(self):
        password = self.cleaned_data["password"]
        # validate_password() raises ValidationError with Django's own
        # AUTH_PASSWORD_VALIDATORS messages (length/common-password/
        # numeric-only/user-attribute-similarity) - real server-side
        # enforcement, not just a client-side hint.
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm_password = cleaned.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned


def signup(request):

    # Pre-fill only (not locked/read-only) - a document-share invite
    # link (RAG.tasks.send_share_invite_email_task) carries this so
    # the recipient doesn't have to retype the address the invite was
    # sent to. Nothing security-sensitive rides on it: the pending
    # DocumentShare only ever converts once this exact address is
    # later proven via OTP (RAG.services.otp_service.verify_otp), not
    # from this query param.
    invited_email = request.GET.get("invited_email", "")
    form = SignupForm(initial={"email": invited_email} if invited_email else None)

    if request.method == "POST":

        ip = get_client_ip(request)
        if ip and is_rate_limited(f"signup:ip:{ip}", *SIGNUP_ATTEMPTS_PER_IP):
            messages.error(request, "Too many signup attempts from this location. Please try again later.")
            return render(request, "signup.html", {"form": form})

        form = SignupForm(request.POST)

        if form.is_valid():

            name_parts = form.cleaned_data["full_name"].split()
            first_name = name_parts[0] if name_parts else ""
            last_name = " ".join(name_parts[1:])

            new_user = User.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                first_name=first_name,
                last_name=last_name,
                is_active=False,  # activated by otp_service.verify_otp() on successful email verification
            )

            default_role, _ = Role.objects.get_or_create(
                slug=USER,
                defaults={"name": "User", "is_system": True},
            )
            UserRole.objects.create(user=new_user, role=default_role)

            log_activity(
                actor=new_user,
                action="user.signed_up",
                description=f"{new_user.username} created an account",
                request=request,
            )

            otp_service.generate_and_send_otp(new_user)
            request.session["pending_verification_user_id"] = new_user.id

            return redirect("verify_otp")

    return render(request, "signup.html", {"form": form})


def verify_otp(request):
    """
    GET: shows the code-entry screen for whichever account is pending
    verification in this session (set by signup() or, for an existing
    unverified account, login_user()'s inert-until-verified branch
    below). POST: validates via otp_service.verify_otp() and, on
    success, logs the now-activated user in - the one place login()
    is called outside login_user() itself, since "just verified" is
    also "just proved you own this account".
    """

    user_id = request.session.get("pending_verification_user_id")
    user = User.objects.filter(id=user_id).first() if user_id else None

    if user is None or user.is_active:
        # Nothing pending (direct navigation, expired session, or an
        # already-verified account) - back to the start rather than a
        # confusing blank/error screen.
        return redirect("signup")

    if request.method == "POST":

        code = request.POST.get("code", "").strip()

        success, status = otp_service.verify_otp(user, code)

        if success:
            del request.session["pending_verification_user_id"]

            login(request, user)
            request.session.set_expiry(0)

            log_activity(
                actor=user,
                action="user.email_verified",
                description=f"{user.username} verified their email",
                request=request,
            )

            messages.success(request, "Email verified. Welcome!")
            return redirect(get_dashboard_url_for_user(user))

        error_messages = {
            "expired": "This code has expired. Request a new one below.",
            "invalid": "That code isn't right. Please try again.",
            "max_attempts": "Too many incorrect attempts. Request a new code below.",
            "none_pending": "No active code found. Request a new one below.",
            "rate_limited": "Too many attempts. Please wait a few minutes and try again.",
        }

        return render(
            request, "verify_otp.html",
            {"masked_email": mask_email(user.email), "error": error_messages.get(status, "Something went wrong. Please try again.")},
        )

    return render(request, "verify_otp.html", {"masked_email": mask_email(user.email)})


def resend_otp(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    user_id = request.session.get("pending_verification_user_id")
    user = User.objects.filter(id=user_id).first() if user_id else None

    if user is None or user.is_active:
        return JsonResponse({"error": "No pending verification."}, status=400)

    allowed, seconds_remaining = otp_service.can_resend(user)

    if not allowed:
        return JsonResponse({"error": "Please wait before requesting another code.", "cooldown_seconds": seconds_remaining}, status=429)

    otp_service.generate_and_send_otp(user)

    return JsonResponse({"cooldown_seconds": otp_service.RESEND_COOLDOWN_SECONDS})


def login_user(request):

    if request.method == "POST":

        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        remember_me = request.POST.get("remember_me") == "on"

        ip = get_client_ip(request)

        username_limited = username and is_rate_limited(f"login:user:{username.lower()}", *LOGIN_ATTEMPTS_PER_USERNAME)
        ip_limited = ip and is_rate_limited(f"login:ip:{ip}", *LOGIN_ATTEMPTS_PER_IP)

        if username_limited or ip_limited:
            return render(
                request, "login.html",
                {"error": "Too many login attempts. Please wait a few minutes and try again.", "username": username},
            )

        user = authenticate(request, username=username, password=password)

        if user is None and username and password:
            # authenticate() returns None for ANY inactive account
            # (Django's ModelBackend checks is_active itself) - a
            # suspended account and an unverified-signup account both
            # look identical at this point. Only redirect to OTP
            # verification if the password is actually correct AND
            # there's a real pending OTP for this account -
            # otherwise this must stay indistinguishable from "wrong
            # password" (a suspended account must never learn that its
            # credentials are still valid).
            candidate = User.objects.filter(username__iexact=username, is_active=False).first()
            if candidate and candidate.check_password(password) and otp_service.has_pending_verification(candidate):
                request.session["pending_verification_user_id"] = candidate.id
                return redirect("verify_otp")

        if user is not None:

            login(request, user)

            # Explicit every time (not left to SESSION_EXPIRE_AT_BROWSER_CLOSE's
            # implicit default alone) so behavior never depends on a
            # previous session's leftover expiry on the same browser -
            # login() already rotated the session key via cycle_key().
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

            return redirect(get_dashboard_url_for_user(user))

        return render(
            request, "login.html",
            {"error": "Invalid username or password.", "username": username},
        )

    return render(request, "login.html")


def logout_user(request):

    if request.user.is_authenticated:
        log_activity(
            actor=request.user,
            action="user.logout",
            description=f"{request.user.username} logged out",
            request=request,
        )

    logout(request)

    return redirect("login")


class RAGPasswordResetForm(PasswordResetForm):
    """
    Only send_mail() is overridden - PasswordResetForm.save() itself
    (uniqueness/active-user lookup, uid/token generation, the "silently
    do nothing for an unknown email" enumeration-resistance behavior)
    is untouched. Django's own template rendering path is bypassed
    entirely (no templates/registration/password_reset_email.* needed)
    in favor of RAG.services.email_service.send_templated_email() via
    the same backgrounded-task pattern every other email in this
    feature uses - a slow/failing SMTP send must never block this
    request. Passing the live `context["user"]` object across to the
    background task is safe here (unlike Celery, this is an in-process
    thread pool, not a serialized queue - see task_runner.py).
    """

    def send_mail(self, subject_template_name, email_template_name, context, from_email, to_email, html_email_template_name=None):
        from .services import task_runner
        from .tasks import send_password_reset_email_task

        task_runner.submit(
            send_password_reset_email_task,
            context["user"].id, context["uid"], context["token"], to_email,
        )


class RAGPasswordResetView(django_auth_views.PasswordResetView):
    template_name = "forgot_password.html"
    form_class = RAGPasswordResetForm
    success_url = reverse_lazy("password_reset_done")

    def form_valid(self, form):

        email = form.cleaned_data["email"].strip().lower()
        ip = get_client_ip(self.request)

        email_limited = is_rate_limited(f"pwreset:{email}", *PASSWORD_RESET_ATTEMPTS_PER_EMAIL)
        ip_limited = ip and is_rate_limited(f"pwreset:ip:{ip}", *PASSWORD_RESET_ATTEMPTS_PER_IP)

        if email_limited or ip_limited:
            # Never reveal rate limiting (or account existence) to a
            # potential enumerator - redirect to the exact same "check
            # your email" page a legitimate request lands on, the same
            # enumeration-resistance PasswordResetForm.save() already
            # gives an unknown email address.
            return redirect(self.get_success_url())

        return super().form_valid(form)


class RAGPasswordResetConfirmView(django_auth_views.PasswordResetConfirmView):
    template_name = "password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")

    def form_valid(self, form):
        # SetPasswordForm.save() runs Django's own validate_password()
        # (AUTH_PASSWORD_VALIDATORS) before ever calling this - no
        # extra wiring needed for password-strength enforcement here.
        response = super().form_valid(form)

        log_activity(
            actor=self.user,
            action="user.password_reset",
            description=f"{self.user.username} reset their password via email",
            request=self.request,
        )

        create_notification(
            recipient=self.user,
            notification_type="account.password_changed",
            title="Your password was changed",
            message="Your password was just reset. If this wasn't you, contact support immediately.",
        )

        return response

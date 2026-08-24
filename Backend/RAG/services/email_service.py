"""
Email Service

The one place in this project that ever calls django.core.mail directly.
No email infrastructure existed here before this module - every caller
(OTP, password reset, notifications, sharing invites) renders a template
pair and dispatches through send_templated_email() rather than building
its own EmailMultiAlternatives, so the never-raise contract and the
plain-text/HTML template convention only have to be right in one place.

Callers are responsible for backgrounding this via
RAG.services.task_runner.submit() when called from a request/response
cycle - this module itself is synchronous (it has to be, to return a
success/failure result the caller can persist), matching every other
RAG/services/*.py module's "do the work, let the caller decide how to
schedule it" split.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_templated_email(to_email: str, subject: str, template_base: str, context: dict) -> tuple[bool, str]:
    """
    Renders templates/emails/{template_base}.txt (required) and
    templates/emails/{template_base}.html (optional - sent as an
    alternative part if present) and sends via EmailMultiAlternatives.

    Never raises - any failure (missing template, SMTP error, DNS
    failure) is logged and returned as (False, sanitized_message)
    instead of propagating, the same never-raise contract every other
    RAG/services/*.py module follows, so a mail failure can never break
    the primary action (signup, sharing, password reset) that triggered
    it. `context` is never logged - only the template name and
    recipient are, so an OTP code or reset token passed via context
    never reaches the logs through this path.
    """

    if not to_email:
        logger.warning("send_templated_email: no recipient address for template=%s", template_base)
        return False, "No recipient email address."

    try:
        text_body = render_to_string(f"emails/{template_base}.txt", context)
    except TemplateDoesNotExist:
        logger.exception("send_templated_email: missing required text template emails/%s.txt", template_base)
        return False, "Email template not found."

    try:
        html_body = render_to_string(f"emails/{template_base}.html", context)
    except TemplateDoesNotExist:
        html_body = None

    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        if html_body:
            message.attach_alternative(html_body, "text/html")
        message.send(fail_silently=False)
    except Exception as exc:
        logger.exception("send_templated_email: delivery failed template=%s to=%s", template_base, to_email)
        return False, f"Email delivery failed: {exc.__class__.__name__}"

    return True, ""

"""
RBAC Decorators

Reusable view-level authorization - every admin-only view wraps
itself in one of these instead of re-checking request.user.is_staff
or duplicating permission logic inline. See RAG/middleware.py for the
matching defense-in-depth layer over the whole /admin/ namespace, and
RAG/services/permission_service.py for the underlying checks.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .services.permission_service import ADMIN_ROLES, SUPER_ADMIN, user_has_permission, user_has_role


def role_required(*role_slugs):
    """
    Restrict a view to users whose assigned role slug is one of
    `role_slugs`. Unauthenticated users go through Django's normal
    login flow (login_required); authenticated users with the wrong
    role get a 403 (via Django's standard PermissionDenied handling,
    templates/403.html) rather than a silent redirect that could look
    like the page just doesn't exist.
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped_view(request, *args, **kwargs):
            if not user_has_role(request.user, *role_slugs):
                raise PermissionDenied("You don't have access to this page.")
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def permission_required(*codenames):
    """
    Restrict a view to users whose role grants every permission in
    `codenames`.
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped_view(request, *args, **kwargs):
            if not all(user_has_permission(request.user, code) for code in codenames):
                raise PermissionDenied("You don't have access to this page.")
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def admin_required(view_func):
    """Shortcut for role_required(*ADMIN_ROLES) - the common admin-page case."""
    return role_required(*ADMIN_ROLES)(view_func)


def super_admin_required(view_func):
    """Shortcut for role_required(super_admin) - the most sensitive actions (e.g. granting the Super Admin role itself)."""
    return role_required(SUPER_ADMIN)(view_func)

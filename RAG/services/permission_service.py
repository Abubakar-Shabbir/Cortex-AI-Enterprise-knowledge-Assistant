"""
Permission Service

Single source of truth for role/permission checks. Decorators
(RAG/decorators.py), middleware (RAG/middleware.py), and views all go
through this module rather than querying Role/UserRole directly or
branching on is_staff/is_superuser - so adding or changing a role
later never means touching more than the seed data
(RAG/management/commands/seed_rbac.py).
"""

import logging

from django.urls import reverse

from ..models import Role, UserRole

logger = logging.getLogger(__name__)

SUPER_ADMIN = "super_admin"
ADMIN = "admin"
USER = "user"

# Roles allowed into the /admin/ namespace. Extending this (e.g. a
# future "auditor" role that can view but not manage admin pages)
# means updating this tuple and the relevant Roles' permissions - not
# any decorator or view.
ADMIN_ROLES = (SUPER_ADMIN, ADMIN)


def get_user_role(user):
    """
    The Role assigned to `user`, or the built-in "user" role if none
    is assigned yet (e.g. an account created before seed_rbac ran).
    Never raises - a missing assignment degrades to the
    least-privileged role rather than an error.
    """

    if not user or not getattr(user, "is_authenticated", False):
        return None

    assignment = UserRole.objects.select_related("role").filter(user=user).first()

    if assignment:
        return assignment.role

    logger.warning("User '%s' has no UserRole assignment - defaulting to '%s'.", user, USER)

    return Role.objects.filter(slug=USER).first()


def get_role_slug(user):
    role = get_user_role(user)
    return role.slug if role else None


def user_has_role(user, *slugs):
    return get_role_slug(user) in slugs


def is_admin(user):
    """True for admin and super_admin - the roles allowed into /admin/."""
    return user_has_role(user, *ADMIN_ROLES)


def is_super_admin(user):
    return user_has_role(user, SUPER_ADMIN)


def user_has_permission(user, codename):
    role = get_user_role(user)
    return bool(role and role.has_permission(codename))


def get_dashboard_url_for_user(user):
    """
    Where a user lands right after login, and where the "home" ('/')
    route redirects to - admin/super_admin go to the Admin Dashboard,
    everyone else to the User Dashboard.
    """

    return reverse("admin_dashboard") if is_admin(user) else reverse("user_dashboard")

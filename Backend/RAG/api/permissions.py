"""
DRF permission classes wrapping RAG.services.permission_service - the
same RBAC checks RAG/decorators.py enforces on the classic Django
views, so an API endpoint backing a React page is gated exactly the
same way its Django-template predecessor was. No new authorization
logic is introduced here, only a DRF-shaped adapter over the existing
one.
"""

from rest_framework.permissions import BasePermission

from ..services.permission_service import has_admin_area_access, user_has_permission


class HasAdminAreaAccess(BasePermission):
    """
    DRF mirror of RAG.decorators.admin_area_required - coarse,
    role-based "can this account reach the admin area at all" gate
    (permission_service.has_admin_area_access), not a specific
    permission codename. Used by the Admin Overview API endpoint, the
    same population admin_dashboard_view's Django-template predecessor
    is restricted to.
    """

    message = "You don't have access to this page."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and has_admin_area_access(request.user)
        )


def HasPagePermission(*codenames):
    """
    Factory mirroring RAG.decorators.permission_required(*codenames) -
    every codename must be granted by the requester's role. Usage:
    permission_classes = [HasPagePermission("pages.documents")]
    """

    class _HasPagePermission(BasePermission):
        message = "You don't have access to this resource."

        def has_permission(self, request, view):
            return bool(
                request.user
                and request.user.is_authenticated
                and all(user_has_permission(request.user, code) for code in codenames)
            )

    return _HasPagePermission

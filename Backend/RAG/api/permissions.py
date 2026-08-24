"""
DRF permission classes wrapping RAG.services.permission_service - the
same RBAC checks RAG/decorators.py enforces on the classic Django
views, so an API endpoint backing a React page is gated exactly the
same way its Django-template predecessor was. No new authorization
logic is introduced here, only a DRF-shaped adapter over the existing
one.
"""

from rest_framework.permissions import BasePermission

from ..services.permission_service import user_has_permission


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

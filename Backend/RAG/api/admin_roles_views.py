"""
Admin > Roles endpoints for the React SPA - thin JSON wrappers around
RAG.views.admin_roles_view's exact same service calls
(permission_service.get_permission_modules/compute_updated_role_permissions).
No new authorization logic.
"""

from django.utils.text import slugify
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import ADMIN_ROLE_SLUG, Permission, Role
from ..services.activity_log_service import log_activity
from ..services.permission_service import (
    SENSITIVE_PERMISSIONS,
    compute_updated_role_permissions,
    get_permission_modules,
    get_user_permission_set,
    is_admin,
)
from .permissions import HasPagePermission


def _serialize_permission(p):
    return {"codename": p.codename, "name": p.name, "description": p.description, "sensitive": p.codename in SENSITIVE_PERMISSIONS}


@api_view(["GET"])
@permission_classes([HasPagePermission("roles.manage")])
def admin_roles_view(request):
    actor_is_admin = is_admin(request.user)
    actor_perms = get_user_permission_set(request.user)

    permission_modules = []
    for module in get_permission_modules():
        visible_permissions = module["permissions"] if actor_is_admin else [p for p in module["permissions"] if p.codename in actor_perms]
        if not visible_permissions:
            continue
        permission_modules.append({
            "slug": module["slug"],
            "label": module["label"],
            "icon": module["icon"],
            "permissions": [_serialize_permission(p) for p in visible_permissions],
            "hidden_count": len(module["permissions"]) - len(visible_permissions),
        })

    total_permission_count = sum(len(m["permissions"]) for m in permission_modules)

    roles_data = []
    for role in Role.objects.prefetch_related("permissions").order_by("name"):
        role_granted = set(role.permissions.values_list("codename", flat=True))
        visible_granted = role_granted if actor_is_admin else (role_granted & actor_perms)
        roles_data.append({
            "id": role.id,
            "name": role.name,
            "slug": role.slug,
            "description": role.description,
            "is_system": role.is_system,
            "granted": sorted(visible_granted),
            "hidden_granted_count": len(role_granted - visible_granted),
        })

    return Response({
        "roles": roles_data,
        "permission_modules": permission_modules,
        "total_permission_count": total_permission_count,
    })


@api_view(["POST"])
@permission_classes([HasPagePermission("roles.manage")])
def admin_role_create_view(request):
    name = (request.data.get("name") or "").strip()
    slug = slugify(name)

    if not name or not slug:
        return Response({"error": "Role name is required."}, status=400)
    if Role.objects.filter(slug=slug).exists():
        return Response({"error": f'A role named "{name}" already exists.'}, status=400)

    Role.objects.create(name=name, slug=slug, description=(request.data.get("description") or "").strip())
    log_activity(actor=request.user, action="role.created", description=f'Role "{name}" created by {request.user.username}', request=request)
    return Response({"ok": True}, status=201)


@api_view(["POST"])
@permission_classes([HasPagePermission("roles.manage")])
def admin_role_permissions_view(request, role_id):
    role = Role.objects.filter(id=role_id).first()
    if role is None:
        return Response({"error": "Role not found."}, status=404)

    if role.slug == ADMIN_ROLE_SLUG:
        return Response({"error": "The Admin role always has full access and can't be edited."}, status=400)

    selected_codenames = set(request.data.get("permissions") or [])

    if not is_admin(request.user):
        current = set(role.permissions.values_list("codename", flat=True))
        attempted_escalation = (selected_codenames - get_user_permission_set(request.user)) - current
        if attempted_escalation:
            log_activity(
                actor=request.user, action="security.privilege_escalation_blocked",
                description=f'{request.user.username} tried to grant "{role.name}" permissions beyond their own ({", ".join(sorted(attempted_escalation))}) - blocked',
                request=request,
            )

    updated_codenames = compute_updated_role_permissions(request.user, role, selected_codenames)
    role.permissions.set(Permission.objects.filter(codename__in=updated_codenames))
    log_activity(actor=request.user, action="role.permissions_updated", description=f'Permissions updated for "{role.name}" by {request.user.username}', request=request)
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([HasPagePermission("roles.manage")])
def admin_role_delete_view(request, role_id):
    role = Role.objects.filter(id=role_id).first()
    if role is None:
        return Response({"error": "Role not found."}, status=404)

    role_permissions = set(role.permissions.values_list("codename", flat=True))

    if role.is_system:
        return Response({"error": f'"{role.name}" is a built-in role and can\'t be deleted.'}, status=400)
    if role.user_assignments.exists():
        return Response({"error": f'"{role.name}" is still assigned to {role.user_assignments.count()} user(s) - reassign them first.'}, status=400)
    if not is_admin(request.user) and not role_permissions.issubset(get_user_permission_set(request.user)):
        log_activity(
            actor=request.user, action="security.privilege_escalation_blocked",
            description=f'{request.user.username} tried to delete "{role.name}" (grants access beyond their own) - blocked',
            request=request,
        )
        return Response({"error": f'You don\'t have permission to delete "{role.name}" - it grants access beyond your own.'}, status=403)

    role_name = role.name
    role.delete()
    log_activity(actor=request.user, action="role.deleted", description=f'Role "{role_name}" deleted by {request.user.username}', request=request)
    return Response({"ok": True})

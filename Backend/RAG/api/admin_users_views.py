"""
Admin > Users endpoints for the React SPA - thin JSON wrappers around
RAG.views.admin_users_view/admin_user_profile_view's exact same
privilege-escalation guards (permission_service.py) and mutation
logic. No new authorization logic - every check below is the same
function the classic view already calls.
"""

from django.contrib.auth.models import User
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import ADMIN_ROLE_SLUG, Role, UserRole
from ..services import notification_service
from ..services.activity_log_service import log_activity
from ..services.permission_service import (
    can_actor_assign_role,
    can_actor_manage_target_user,
    get_assignable_roles,
    is_last_admin,
    user_has_permission,
)
from .permissions import HasPagePermission
from .profile_views import _serialize_profile


def _serialize_user(u):
    role = getattr(getattr(u, "role_assignment", None), "role", None)
    return {
        "id": u.id,
        "username": u.username,
        "full_name": u.get_full_name(),
        "email": u.email,
        "avatar_url": u.profile.avatar.url if getattr(u, "profile", None) and u.profile.avatar else None,
        "headline": getattr(getattr(u, "profile", None), "headline", ""),
        "role_name": role.name if role else None,
        "role_id": role.id if role else None,
        "role_assigned_at": u.role_assignment.assigned_at if getattr(u, "role_assignment", None) else None,
        "role_assigned_by": u.role_assignment.assigned_by.username if getattr(u, "role_assignment", None) and u.role_assignment.assigned_by_id else None,
        "is_active": u.is_active,
        "date_joined": u.date_joined,
    }


@api_view(["GET"])
@permission_classes([HasPagePermission("users.view_all")])
def admin_users_view(request):
    users_list = User.objects.select_related("role_assignment__role", "profile").order_by("-date_joined")

    admin_role = Role.objects.filter(slug=ADMIN_ROLE_SLUG).first()
    assignable_roles = get_assignable_roles(request.user)

    return Response({
        "users": [_serialize_user(u) for u in users_list],
        "assignable_roles": [{"id": r.id, "slug": r.slug, "name": r.name, "description": r.description} for r in assignable_roles],
        "assignable_role_ids": [r.id for r in assignable_roles],
        "admin_role_id": admin_role.id if admin_role else None,
        "current_user_id": request.user.id,
        "can_assign_role": user_has_permission(request.user, "users.assign_role"),
        "can_suspend": user_has_permission(request.user, "users.suspend"),
        "can_delete": user_has_permission(request.user, "users.delete"),
    })


@api_view(["POST"])
@permission_classes([HasPagePermission("users.view_all")])
def admin_user_action_view(request):
    action = request.data.get("action")
    target_user = User.objects.filter(id=request.data.get("user_id")).first()
    if target_user is None:
        return Response({"error": "User not found."}, status=404)

    if action in ("suspend", "activate") and not user_has_permission(request.user, "users.suspend"):
        return Response({"error": "You don't have permission to suspend/activate users."}, status=403)
    if action == "delete" and not user_has_permission(request.user, "users.delete"):
        return Response({"error": "You don't have permission to delete users."}, status=403)
    if action == "assign_role" and not user_has_permission(request.user, "users.assign_role"):
        return Response({"error": "You don't have permission to assign roles."}, status=403)

    if action in ("suspend", "activate", "delete", "assign_role") and not can_actor_manage_target_user(request.user, target_user):
        log_activity(
            actor=request.user,
            action="security.privilege_escalation_blocked",
            description=f'{request.user.username} tried to {action} "{target_user.username}" (more privileged account) - blocked',
            request=request,
        )
        return Response({"error": "You don't have permission to manage this account."}, status=403)

    if action == "suspend":
        if target_user == request.user:
            return Response({"error": "You can't suspend your own account."}, status=400)
        if is_last_admin(target_user):
            return Response({"error": "You can't suspend the last remaining Admin."}, status=400)
        target_user.is_active = False
        target_user.save(update_fields=["is_active"])
        log_activity(actor=request.user, action="user.suspended", description=f'"{target_user.username}" suspended by {request.user.username}', request=request)
        notification_service.create_notification(
            recipient=target_user, actor=request.user, notification_type="security.account_suspended",
            title="Your account has been suspended",
            message="Your account was suspended by an administrator. Contact support if you believe this is a mistake.",
        )

    elif action == "activate":
        target_user.is_active = True
        target_user.save(update_fields=["is_active"])
        log_activity(actor=request.user, action="user.reactivated", description=f'"{target_user.username}" reactivated by {request.user.username}', request=request)
        notification_service.create_notification(
            recipient=target_user, actor=request.user, notification_type="security.account_reactivated",
            title="Your account has been reactivated", message="Your account is active again - you can now log in normally.",
        )

    elif action == "delete":
        if target_user == request.user:
            return Response({"error": "You can't delete your own account."}, status=400)
        if is_last_admin(target_user):
            return Response({"error": "You can't delete the last remaining Admin."}, status=400)
        deleted_username = target_user.username
        deleted_email = target_user.email
        target_user.delete()
        log_activity(actor=request.user, action="user.deleted", description=f'"{deleted_username}" deleted by {request.user.username}', request=request)
        if deleted_email:
            from ..services import task_runner
            from ..tasks import send_account_deleted_email_task
            task_runner.submit(send_account_deleted_email_task, deleted_email, deleted_username)

    elif action == "assign_role":
        role = Role.objects.filter(slug=request.data.get("role")).first()
        if role is None:
            return Response({"error": "Role not found."}, status=404)

        if not can_actor_assign_role(request.user, role):
            log_activity(
                actor=request.user, action="security.privilege_escalation_blocked",
                description=f'{request.user.username} tried to assign "{role.name}" to "{target_user.username}" (exceeds their own permissions) - blocked',
                request=request,
            )
            return Response({"error": f'You don\'t have permission to assign the "{role.name}" role.'}, status=403)
        if role.slug != ADMIN_ROLE_SLUG and is_last_admin(target_user):
            return Response({"error": "You can't move the last remaining Admin out of the Admin role."}, status=400)

        UserRole.objects.update_or_create(user=target_user, defaults={"role": role, "assigned_by": request.user})
        log_activity(actor=request.user, action="user.role_changed", description=f'"{target_user.username}" set to {role.name} by {request.user.username}', request=request)
        notification_service.create_notification(
            recipient=target_user, actor=request.user, notification_type="account.role_changed",
            title="Your role has changed", message=f'Your role was changed to "{role.name}".',
        )
    else:
        return Response({"error": "Unknown action."}, status=400)

    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([HasPagePermission("users.view_all")])
def admin_user_profile_view(request, user_id):
    target_user = User.objects.filter(id=user_id).first()
    if target_user is None:
        return Response({"error": "User not found."}, status=404)

    data = _serialize_profile(target_user)
    data["user"]["is_active"] = target_user.is_active
    return Response(data)

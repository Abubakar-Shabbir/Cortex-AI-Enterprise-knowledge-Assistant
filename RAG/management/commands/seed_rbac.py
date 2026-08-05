"""
Seed default RBAC permissions/roles and backfill role assignments for
existing users. Idempotent - safe to re-run any time (e.g. after
adding a new permission to DEFAULT_PERMISSIONS).

Usage, after migrating the RBAC models:

    python manage.py migrate RAG
    python manage.py seed_rbac

Existing accounts are backfilled once, using is_superuser/is_staff
purely as a one-time bootstrap signal (superuser -> Super Admin,
staff -> Admin, everyone else -> User). Every check after this point
reads Role/Permission via RAG.services.permission_service, never
is_staff/is_superuser directly.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from RAG.models import Permission, Role, UserRole
from RAG.services.permission_service import ADMIN, SUPER_ADMIN, USER

# (codename, name, description) - namespaced "<area>.<action>" so new
# areas can be added without colliding with existing codenames.
DEFAULT_PERMISSIONS = [
    ("users.view_all", "View all users", "See the full user list and their assigned roles."),
    ("users.delete", "Delete users", "Permanently remove a user account."),
    ("users.suspend", "Suspend users", "Deactivate/reactivate a user account."),
    ("users.assign_role", "Assign roles", "Change a user's assigned role."),

    ("documents.view_all", "View all documents", "See document metadata (title/owner/size/status) across every user."),
    ("documents.delete_any", "Delete any document", "Delete a document owned by any user, not just your own."),

    ("analytics.view_all", "View all analytics", "View workspace-wide analytics, not just your own usage."),

    ("system.view_health", "View system health", "View database/pgvector/LLM/embedding health checks."),
    ("system.view_storage", "View storage", "View total storage used across the workspace."),
    ("system.view_embeddings", "View embeddings", "View embedding coverage/status."),
    ("system.view_api_status", "View API status", "View LLM/API provider configuration status."),

    ("queries.view_all_logs", "View all query logs", "View every user's Ask AI query log, not just your own."),
    ("activity.view_all_logs", "View all activity logs", "View a workspace-wide activity log."),

    ("settings.manage_llm", "Manage LLM configuration", "View/change the active LLM provider and model."),
    ("settings.manage_embedding", "Manage embedding model", "View/change the embedding model configuration."),
    ("settings.manage_chunking", "Manage chunk configuration", "View/change chunk size/overlap configuration."),
    ("settings.manage_api_keys", "Manage API keys", "View/rotate provider API keys."),
    ("settings.manage_database", "Manage database configuration", "View database connection configuration."),
]

# role slug -> (display name, permission codenames or "__all__")
DEFAULT_ROLES = {
    SUPER_ADMIN: {
        "name": "Super Admin",
        "permissions": "__all__",
    },
    ADMIN: {
        "name": "Admin",
        "permissions": "__all__",
    },
    USER: {
        "name": "User",
        "permissions": [],
    },
}


class Command(BaseCommand):
    help = "Seed default RBAC permissions/roles and backfill role assignments for existing users."

    @transaction.atomic
    def handle(self, *args, **options):

        permissions_by_codename = {}

        for codename, name, description in DEFAULT_PERMISSIONS:
            permission, created = Permission.objects.get_or_create(
                codename=codename,
                defaults={"name": name, "description": description},
            )
            permissions_by_codename[codename] = permission
            self.stdout.write(f"{'Created' if created else 'Exists'} permission: {codename}")

        roles_by_slug = {}

        for slug, config in DEFAULT_ROLES.items():
            role, created = Role.objects.get_or_create(
                slug=slug,
                defaults={"name": config["name"], "is_system": True},
            )
            roles_by_slug[slug] = role

            if config["permissions"] == "__all__":
                role.permissions.set(permissions_by_codename.values())
            else:
                role.permissions.set([permissions_by_codename[code] for code in config["permissions"]])

            self.stdout.write(f"{'Created' if created else 'Exists'} role: {slug}")

        default_role = roles_by_slug[USER]
        assigned = 0

        for user in User.objects.all():

            if hasattr(user, "role_assignment"):
                continue

            if user.is_superuser:
                role = roles_by_slug[SUPER_ADMIN]
            elif user.is_staff:
                role = roles_by_slug[ADMIN]
            else:
                role = default_role

            UserRole.objects.create(user=user, role=role)
            assigned += 1

        self.stdout.write(self.style.SUCCESS(
            f"RBAC seed complete. Backfilled role assignments for {assigned} user(s)."
        ))

"""
Removes the "Super Admin" role: Admin is now the sole built-in
top-tier role and always has full access (Role.has_permission's
bypass in RAG/models.py) - see CLAUDE.md's RBAC section. Any account
still holding the super_admin role is moved onto admin (created if it
doesn't exist yet, e.g. on a database that never ran seed_rbac), and
super_admin's permission set is folded into admin's before the row
itself is deleted.

UserRole.role uses on_delete=PROTECT, so every UserRole pointing at
super_admin must be reassigned before the role can be deleted - this
migration does that first.
"""

from django.db import migrations


def reassign_super_admin_to_admin(apps, schema_editor):
    Role = apps.get_model("RAG", "Role")
    UserRole = apps.get_model("RAG", "UserRole")

    super_admin = Role.objects.filter(slug="super_admin").first()

    if not super_admin:
        return

    admin_role, _ = Role.objects.get_or_create(
        slug="admin",
        defaults={"name": "Admin", "is_system": True},
    )

    UserRole.objects.filter(role=super_admin).update(role=admin_role)
    admin_role.permissions.add(*super_admin.permissions.all())
    super_admin.delete()


def noop_reverse(apps, schema_editor):
    # Super Admin was removed by design - nothing to restore on a
    # reverse migration.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("RAG", "0015_backfill_processing_status"),
    ]

    operations = [
        migrations.RunPython(reassign_super_admin_to_admin, noop_reverse),
    ]

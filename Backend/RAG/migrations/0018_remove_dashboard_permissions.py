"""
Removes the "pages.dashboard_user" and "pages.dashboard_admin"
Permission rows: Overview (Admin or User) is no longer gated by its
own dedicated permission - see
RAG.services.permission_service.get_dashboard_url_for_user for why.
Every authenticated account always gets an Overview page (scoped to
Admin or User shell by has_admin_area_access), the same way Profile is
never permission-gated either; the page's own content is what now
scales down per-widget based on the viewer's other permissions
(pages.documents, pages.ask_ai, etc.) instead of the whole page
vanishing behind one dashboard-specific permission.

Role.permissions is a plain M2M, so deleting these Permission rows
automatically drops the through-table rows for any role that held
them - no PROTECT'd FK to work around, unlike the Super Admin role
removal in 0016.
"""

from django.db import migrations


def remove_dashboard_permissions(apps, schema_editor):
    Permission = apps.get_model("RAG", "Permission")
    Permission.objects.filter(codename__in=["pages.dashboard_user", "pages.dashboard_admin"]).delete()


def noop_reverse(apps, schema_editor):
    # These permissions no longer gate anything - nothing to restore.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("RAG", "0017_alter_role_is_system"),
    ]

    operations = [
        migrations.RunPython(remove_dashboard_permissions, noop_reverse),
    ]

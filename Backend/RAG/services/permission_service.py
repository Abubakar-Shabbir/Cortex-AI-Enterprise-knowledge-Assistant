"""
Permission Service

Single source of truth for role/permission checks. Decorators
(RAG/decorators.py), middleware (RAG/middleware.py), context processors,
and views all go through this module rather than querying Role/UserRole
directly or branching on is_staff/is_superuser - so adding or changing
a role later never means touching more than the seed data
(RAG/management/commands/seed_rbac.py).

There is no "Super Admin" tier. Admin is the sole built-in top-tier
role and always has every permission (Role.has_permission's bypass in
RAG/models.py) - every other role, including the built-in "user", is
just data: created, edited, deleted, and granted permissions entirely
through Admin > Roles, with zero code changes required.
"""

import logging

from django.urls import reverse

from ..models import ADMIN_ROLE_SLUG, USER_ROLE_SLUG, Role, UserRole

logger = logging.getLogger(__name__)

ADMIN = ADMIN_ROLE_SLUG
USER = USER_ROLE_SLUG

# (slug, label, icon, codenames) - groups permissions into the feature
# module a person actually thinks in (e.g. "Documents" covers both
# "pages.documents" and the cross-user "documents.view_all"/
# "documents.delete_any", even though they don't share a codename
# namespace), not the raw "<namespace>.<action>" prefix. Powers the
# module-first Admin > Roles UI (RAG.views.admin_roles_view /
# templates/admin/roles.html): pick a module, then see (and
# "Select All") only its permissions, instead of one flat wall of
# checkboxes.
PERMISSION_MODULES = (
    ("documents", "Documents", "file-text", (
        "pages.documents", "documents.view_all", "documents.delete_any",
        "documents.share", "documents.manage_org_library",
    )),
    ("knowledge_base", "Knowledge Base", "share-2", (
        "pages.knowledge_base",
    )),
    ("ask_ai", "AI Search", "message-square", (
        "pages.ask_ai",
    )),
    ("queries", "Queries", "search", (
        "queries.view_all_logs", "queries.view_content",
    )),
    ("analytics", "Analytics", "bar-chart-3", (
        "pages.analytics", "analytics.view_all",
    )),
    ("reports", "Reports", "file-down", (
        "pages.reports",
    )),
    ("ai_tasks", "AI Tasks", "sparkles", (
        "pages.ai_tasks",
    )),
    ("users", "Users", "users", (
        "users.view_all", "users.suspend", "users.delete", "users.assign_role",
    )),
    ("roles", "Roles", "shield", (
        "roles.manage",
    )),
    ("settings", "Settings", "settings", (
        "settings.manage_llm", "settings.manage_chunking", "settings.manage_retrieval",
        "settings.manage_embedding", "settings.manage_api_keys", "settings.manage_database",
    )),
    ("system", "System Health", "heart-pulse", (
        "system.view_health", "system.view_ai_logs", "system.view_storage",
        "system.view_embeddings", "system.view_api_status",
    )),
    ("activity", "Activity Logs", "scroll-text", (
        "activity.view_all_logs", "activity.view_ip_location",
    )),
    ("notifications", "Notifications", "bell", (
        "notifications.send_announcement", "notifications.view_all",
    )),
)

# Permissions that expose personally-identifiable data (raw question/
# answer text, precise IP/geolocation) rather than metadata about an
# event - flagged with a "Sensitive" badge in Admin > Roles
# (templates/admin/roles.html) so a non-Admin "roles.manage" holder
# doesn't grant one of these to a custom role without realizing what
# it actually exposes.
SENSITIVE_PERMISSIONS = frozenset({
    "queries.view_content",
    "activity.view_ip_location",
})


def get_permission_modules():
    """
    Every Permission row grouped into its PERMISSION_MODULES entry, as
    a list of {"slug", "label", "icon", "permissions"} dicts in
    PERMISSION_MODULES order - the data the Admin > Roles template
    iterates to render one collapsible module per row. A permission
    that exists in the database but isn't yet listed in
    PERMISSION_MODULES (e.g. added to seed_rbac's DEFAULT_PERMISSIONS
    without a matching entry here) still gets a module of its own,
    grouped by codename namespace, rather than silently vanishing from
    the UI.
    """

    from ..models import Permission

    permissions_by_codename = {p.codename: p for p in Permission.objects.all()}
    mapped_codenames = set()
    modules = []

    for slug, label, icon, codenames in PERMISSION_MODULES:
        module_permissions = [permissions_by_codename[c] for c in codenames if c in permissions_by_codename]
        mapped_codenames.update(codenames)
        if module_permissions:
            modules.append({"slug": slug, "label": label, "icon": icon, "permissions": module_permissions})

    leftover_by_namespace = {}
    for codename, permission in permissions_by_codename.items():
        if codename not in mapped_codenames:
            leftover_by_namespace.setdefault(permission.namespace, []).append(permission)

    for namespace, perms in sorted(leftover_by_namespace.items()):
        modules.append({
            "slug": namespace,
            "label": namespace.replace("_", " ").title(),
            "icon": "puzzle",
            "permissions": perms,
        })

    return modules


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
    """True only for the built-in Admin role - the sole top-tier role now that Super Admin has been removed."""
    return user_has_role(user, ADMIN)


def user_has_permission(user, codename):
    role = get_user_role(user)
    return bool(role and role.has_permission(codename))


def _role_permission_set(role):
    """
    Every codename `role` grants, as a set - Admin expands to every
    Permission row that exists (Role.has_permission's bypass), not
    just whatever happens to be in its M2M table. Internal helper
    shared by get_user_permission_set() (below) and every
    privilege-escalation check further down this module, so "what does
    this role actually grant" is computed exactly one way.
    """

    from ..models import Permission

    if not role:
        return set()

    if role.slug == ADMIN:
        return set(Permission.objects.values_list("codename", flat=True))

    return set(role.permissions.values_list("codename", flat=True))


def get_user_permission_set(user):
    """The set-typed counterpart to get_user_permission_codenames(), for the privilege-escalation checks below that need set operations (subset/difference), not a sorted list."""
    return _role_permission_set(get_user_role(user))


def get_user_permission_codenames(user):
    """
    Every permission codename `user`'s role effectively grants, as a
    sorted list (JSON-serializable for templates - see
    partials/_command_palette.html's json_script use). Powers
    permission-based nav rendering, e.g.
    `{% if "pages.documents" in user_permissions %}`.
    """

    return sorted(get_user_permission_set(user))


# Codename prefixes that gate at least one /admin/* view (see
# RAG/urls.py's admin_* routes and their @permission_required /
# settings_access_required / system_logs_access_required decorators).
# "pages.*", "documents.*", and "analytics.view_all" are deliberately
# excluded - those gate cross-user scope *within* an ordinary
# workspace page (Documents, Analytics), not a separate /admin/ URL.
ADMIN_AREA_PERMISSION_PREFIXES = ("users.", "roles.", "settings.", "system.", "activity.", "queries.", "notifications.")


def has_admin_area_access(user):
    """
    True for the Admin role, or for any role holding at least one
    admin-area permission (ADMIN_AREA_PERMISSION_PREFIXES) - the single
    check that decides which sidebar shell renders
    (context_processors.sidebar_status), whether RoleBasedAccessMiddleware
    lets the request into /admin/ at all, and which dashboard shell a
    user lands on (get_dashboard_url_for_user). Permission-based, not
    role-based: a custom role built via Admin > Roles and granted a
    single admin-area permission (e.g. "system.view_health") gets the
    admin sidebar shell and passes the /admin/ coarse gate - this is
    what makes building a scoped Manager/HR/Auditor role (see
    RAG.views.admin_roles_view's docstring) actually work end to end,
    rather than only saving a permission grant that nothing ever
    reads. Real per-page access is still enforced by each view's own
    @permission_required/@settings_access_required/etc, which narrows
    down to the exact permission(s) that view needs - this function is
    only the coarse "does this role belong in the admin area at all"
    gate, same "coarse gate + fine-grained internal scoping" pattern
    has_any_settings_permission() uses for the Settings page alone.
    """

    if is_admin(user):
        return True

    return any(
        codename.startswith(ADMIN_AREA_PERMISSION_PREFIXES)
        for codename in get_user_permission_set(user)
    )


def get_user_access_snapshot(user):
    """
    role, has_admin_area_access(user), and get_user_permission_codenames(user)
    computed from a single get_user_role() call and a single
    role-permissions fetch, rather than each of those three calls
    independently re-querying UserRole (and, for a non-Admin role, the
    permission M2M) on its own. Same results as calling the three
    individually - this is purely a shared-computation shortcut for a
    caller (context_processors.sidebar_status, which needs all three
    on every authenticated page load) that would otherwise call all
    three back to back.
    """

    role = get_user_role(user)
    permission_set = _role_permission_set(role)
    is_admin_role = bool(role and role.slug == ADMIN)
    admin_area_access = is_admin_role or any(
        codename.startswith(ADMIN_AREA_PERMISSION_PREFIXES) for codename in permission_set
    )

    return role, admin_area_access, sorted(permission_set)


def has_any_settings_permission(user):
    """
    True if this role holds at least one settings.manage_* permission
    that gates something on the Settings page - the view-level gate for
    admin_settings_view. Real per-card visibility/edit rights inside
    that page are still scoped per field group
    (system_config_service.SETTINGS_PAGE_PERMISSIONS /
    MANAGED_SETTINGS_FIELDS), the same "coarse view gate + fine-grained
    internal scoping" pattern has_admin_area_access() already uses for
    the whole /admin/ namespace.
    """

    from .system_config_service import SETTINGS_PAGE_PERMISSIONS

    return any(user_has_permission(user, code) for code in SETTINGS_PAGE_PERMISSIONS)


# Every permission that gates a tab on the consolidated System Logs page
# (RAG.views.admin_system_logs_view) - Request Traces + Error Groups share
# "system.view_ai_logs", Activity uses its own "activity.view_all_logs".
# One nav entry, one view-level gate; which tabs actually render is scoped
# per permission inside the view/template, same "coarse gate + fine-grained
# internal scoping" pattern has_any_settings_permission() uses above.
SYSTEM_LOGS_PERMISSIONS = ["system.view_ai_logs", "activity.view_all_logs"]


def has_any_system_logs_permission(user):
    """True if this role can see at least one tab on the System Logs page."""

    return any(user_has_permission(user, code) for code in SYSTEM_LOGS_PERMISSIONS)


def get_dashboard_url_for_user(user):
    """
    Where a user lands right after login, and where the "home" ('/')
    route redirects to. Overview is the one page in this app that's
    never permission-gated as a whole, the same way Profile never is
    (see RAG.views.profile_view / user_dashboard / admin_dashboard_view) -
    every authenticated account gets *an* Overview, just scoped to a
    different shell: Admin Overview for the Admin role
    (has_admin_area_access - strictly role-based, see that function's
    docstring), User Overview for everyone else, regardless of which
    individual permissions their role holds. The page itself then shows
    only the modules/widgets the viewer's permissions actually cover
    (see dashboard.html / user_dashboard.html), rather than the page
    disappearing outright.
    """

    return reverse("admin_dashboard") if has_admin_area_access(user) else reverse("user_dashboard")


# ============================================================
# Privilege-escalation guards
# ============================================================
#
# The permission checks above answer "can this role do X at all".
# These answer a different question that a per-permission check alone
# can't: "does this specific action, against this specific target,
# hand out or exercise more power than the actor legitimately has".
# A role holding "users.assign_role" or "roles.manage" is a delegated
# capability, not a blank check - RAG.views.admin_users_view and
# admin_roles_view route every mutating action through these before
# touching the database, and RAG/admin.py applies the same functions
# for the Django Admin surface, so neither can be used to bypass the
# other.
#
# The invariants these enforce:
#   1. Only Admin can create, edit, delete, or assign the Admin role
#      itself - Admin is the one role no permission can ever unlock.
#   2. A non-Admin can never act on (suspend/delete/reassign) an Admin
#      account, or any account whose role is more privileged than
#      their own.
#   3. A non-Admin can never grant a role a permission they don't
#      personally hold, whether by assigning that role to someone or
#      by editing the role's own permission set.
#   4. Admin itself is exempt from 1-3 (it already has everything by
#      design) but not from the last-Admin check: no action, including
#      one Admin takes on themselves or another Admin, may leave the
#      workspace with zero Admins.


def is_last_admin(user):
    """
    True if `user` holds the Admin role and is the only account that
    does. The trigger for blocking suspend/delete/role-reassignment
    away from Admin - without this, it would be possible to leave a
    workspace with zero Admins, an unrecoverable lockout short of
    direct database access.
    """

    if not user_has_role(user, ADMIN):
        return False

    return UserRole.objects.filter(role__slug=ADMIN).count() <= 1


def can_actor_assign_role(actor, role):
    """
    True if `actor` may assign `role` to someone. Admin may assign any
    role, including Admin itself - that's the only way a second Admin
    is ever created. A non-Admin can never assign the Admin role (so
    "users.assign_role" alone can never be used to self-promote or
    promote someone else to Admin) and can only assign a role whose
    entire permission set is already contained in their own - never
    hand out more power than you hold yourself.
    """

    if is_admin(actor):
        return True

    if role.slug == ADMIN:
        return False

    return _role_permission_set(role).issubset(get_user_permission_set(actor))


def get_assignable_roles(actor):
    """
    The Roles `actor` is allowed to assign to someone else, in name
    order - the frontend counterpart to can_actor_assign_role(), so
    the role picker in RAG.views.admin_users_view /
    templates/admin/users.html (and the equivalent Django Admin
    widgets in RAG/admin.py) never even lists the Admin role, or a
    role more powerful than the viewer's own, as an option.
    """

    return [role for role in Role.objects.order_by("name") if can_actor_assign_role(actor, role)]


def can_actor_manage_target_user(actor, target_user):
    """
    True if `actor` may suspend, delete, or otherwise act on
    `target_user`'s account. Admin may act on anyone (subject to the
    last-Admin check, enforced separately by the caller). A non-Admin
    can never act on an Admin account - the concrete case the "never
    allowed to modify, suspend, delete... Admin accounts" requirement
    is about.

    Deliberately NOT a general "actor can only manage a target whose
    permissions are a subset of their own" rule: permission sets
    aren't a total order, they're specialized per role (a user-
    management role and a workspace-features role are just different,
    not higher/lower), so that comparison would incorrectly block
    completely ordinary actions - e.g. a role built for user
    management, holding "users.suspend" but none of the baseline
    "pages.*" permissions, suspending a plain "user"-role account that
    holds several "pages.*" permissions this role doesn't. The Admin
    check above is the actual, well-defined boundary this function
    exists to enforce.
    """

    if is_admin(actor):
        return True

    return not is_admin(target_user)


def compute_updated_role_permissions(actor, role, submitted_codenames):
    """
    The full permission codename set `role` should end up with after
    `actor` submits `submitted_codenames` from the Role Management
    form (or the equivalent Django Admin form). Admin can set a role
    to exactly whatever was submitted - Admin's own role is a separate,
    hardcoded exception the caller handles before ever reaching this
    function (see admin_roles_view / RAG.admin.RoleAdmin).

    A non-Admin "roles.manage" holder can only add or remove
    permissions within their OWN permission scope: anything the role
    currently holds outside that scope is preserved untouched. This
    does two things at once - it's impossible to grant a role a
    permission the actor doesn't personally hold (submitting it has no
    effect unless it's already in the actor's own set), and it's
    impossible to accidentally strip a role of a permission the actor
    doesn't hold either, just because the form never showed it to them
    as a checkbox to begin with.
    """

    current = _role_permission_set(role)

    if is_admin(actor):
        return set(submitted_codenames)

    actor_perms = get_user_permission_set(actor)
    outside_actor_scope = current - actor_perms
    within_actor_scope_submitted = set(submitted_codenames) & actor_perms

    return outside_actor_scope | within_actor_scope_submitted

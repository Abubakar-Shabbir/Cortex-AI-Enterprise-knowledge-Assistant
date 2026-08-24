from django.core.cache import cache

from .models import Document, QueryLog
from .services import notification_service
from .services.permission_service import get_user_access_snapshot
from .services.stats_service import get_system_status

# Maps a URL name to its breadcrumb trail: a list of (label, url_name)
# tuples. `url_name=None` marks the current page (rendered bold, not
# a link) - used as the last entry for pages with no dynamic leaf.
# Pages with a dynamic leaf (e.g. an entity's display_name) instead
# give every trail entry a url_name and pass their own
# `breadcrumb_leaf` in the view's context - see _breadcrumbs.html.
BREADCRUMB_MAP = {
    "home": [("Dashboard", None)],
    "admin_dashboard": [("Overview", None)],
    "user_dashboard": [("Dashboard", None)],
    "documents": [("Documents", None)],
    "favorites": [("Documents", "documents"), ("Favorites", None)],
    "collections": [("Documents", "documents"), ("Collections", None)],
    "collection_detail": [("Documents", "documents"), ("Collections", "collections")],
    "org_library": [("Documents", "documents"), ("Organization Library", None)],
    "shared_with_me": [("Documents", "documents"), ("Shared With Me", None)],
    "knowledge_base": [("Knowledge Base", None)],
    "entity_detail": [("Knowledge Base", "knowledge_base"), ("Entities", "knowledge_base")],
    "relationships": [("Knowledge Base", "knowledge_base"), ("Relationships", None)],
    "knowledge_graph": [("Knowledge Base", "knowledge_base"), ("Graph", None)],
    "citation_explorer": [("Knowledge Base", "knowledge_base"), ("Citations", None)],
    "knowledge_insights": [("Knowledge Base", "knowledge_base"), ("Insights", None)],
    "document_knowledge": [("Knowledge Base", "knowledge_base")],
    "ask_ai": [("AI Search", None)],
    "search_history": [("AI Search", "ask_ai"), ("Search History", None)],
    "ai_tasks": [("AI Tasks", None)],
    "ai_task_history": [("AI Tasks", "ai_tasks"), ("History", None)],
    "ai_task_results": [("AI Tasks", "ai_tasks"), ("Results", None)],
    "analytics": [("Analytics", None)],
    "reports": [("Reports", None)],
    "profile": [("Profile", None)],
    "monitoring": [("Monitoring", None)],
    "admin_users": [("Users", None)],
    "admin_user_profile": [("Users", "admin_users")],
    "admin_roles": [("Roles", None)],
    "admin_settings": [("Settings", None)],
    "admin_queries": [("Queries", None)],
    "admin_system_logs": [("System Logs", None)],
    "notifications": [("Notifications", None)],
    "admin_send_announcement": [("Send Announcement", None)],
}


# Sidebar nav items that represent more than one URL name (e.g. the
# "Knowledge Base" item should read as active from its browse page
# *and* every sub-page reachable under it) map here to the single nav
# item name _nav_item.html should highlight. Anything not listed maps
# to itself - a normal single-URL nav item.
NAV_GROUP_MAP = {
    "admin_dashboard": "home",
    "user_dashboard": "home",
    "admin_user_profile": "admin_users",
    "entity_detail": "knowledge_base",
    "relationships": "knowledge_base",
    "knowledge_graph": "knowledge_base",
    "citation_explorer": "knowledge_base",
    "knowledge_insights": "knowledge_base",
    "document_knowledge": "knowledge_base",
    "search_history": "ask_ai",
    "ai_task_history": "ai_tasks",
    "ai_task_results": "ai_tasks",
    "favorites": "documents",
    "collections": "documents",
    "collection_detail": "documents",
    "org_library": "documents",
    "shared_with_me": "documents",
}


def breadcrumbs(request):
    """
    Breadcrumb trail and active-nav-group for the current page, both
    keyed off the resolved URL name. Runs on every authenticated page
    render (registered alongside sidebar_status below) so no
    individual view needs to build its own trail for the common case;
    a view with a dynamic final breadcrumb segment (e.g. an entity's
    name) sets `breadcrumb_leaf` in its own context instead, which
    _breadcrumbs.html appends after this trail.
    """

    if not request.user.is_authenticated:
        return {}

    url_name = request.resolver_match.url_name if request.resolver_match else None

    return {
        "breadcrumb_trail": BREADCRUMB_MAP.get(url_name, []),
        "active_nav": NAV_GROUP_MAP.get(url_name, url_name),
    }


def sidebar_status(request):
    """
    Makes live system status and a short recent
    activity feed available on every authenticated
    page (sidebar footer, topbar notifications)
    without every view fetching it separately.
    Status is cached briefly since it costs a DB
    round trip.
    """

    if not request.user.is_authenticated:
        return {}

    events = []

    for doc in Document.objects.filter(user=request.user).order_by("-uploaded_at")[:3]:
        events.append({
            "icon": "file-up",
            "text": f'"{doc.title}" uploaded',
            "at": doc.uploaded_at,
        })

    for log in QueryLog.objects.filter(user=request.user).order_by("-created_at")[:3]:
        events.append({
            "icon": "message-square",
            "text": f'Asked: "{log.question[:60]}"',
            "at": log.created_at,
        })

    events.sort(key=lambda e: e["at"], reverse=True)

    # Computed once and shared below instead of calling
    # has_admin_area_access()/get_user_permission_codenames()/
    # get_user_role() independently - each of those re-queries
    # UserRole (and, for a non-Admin role, the permission M2M) on its
    # own, so calling all three back to back cost up to 4 duplicate
    # queries on every authenticated page load.
    role, can_view_admin_area, user_permissions = get_user_access_snapshot(request.user)

    return {
        "system_status": cache.get_or_set(
            "rag_system_status",
            get_system_status,
            30,
        ),
        "activity_feed": events[:5],
        # RBAC: whether the current viewer's role grants at least one
        # admin-area permission (drives which sidebar shell renders -
        # see base.html); real per-page access is still enforced by
        # each view's own @permission_required.
        "can_view_admin_area": can_view_admin_area,
        # Every permission codename the current viewer's role grants -
        # sorted list so nav templates can do
        # `{% if "pages.documents" in user_permissions %}` and
        # json_script it into partials/_command_palette.html.
        "user_permissions": user_permissions,
        # Deliberately uncached (see notification_service.get_unread_count's
        # own docstring) - must reflect mark_read/mark_all_read on the
        # very next page render, unlike the 30s-cached system_status
        # above.
        "unread_notification_count": notification_service.get_unread_count(request.user),
        # The viewer's actual Role (RAG.models.Role, e.g. "Admin",
        # "User", or a custom role like "Manager") - lets the sidebar
        # show the real, current role name instead of a hardcoded
        # Administrator/Member label that doesn't reflect custom roles
        # created via Admin > Roles.
        "sidebar_role": role,
    }

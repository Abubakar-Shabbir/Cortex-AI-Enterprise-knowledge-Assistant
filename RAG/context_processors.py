from django.core.cache import cache

from .models import Document, QueryLog
from .services.stats_service import get_system_status

# Maps a URL name to its breadcrumb trail: a list of (label, url_name)
# tuples. `url_name=None` marks the current page (rendered bold, not
# a link) - used as the last entry for pages with no dynamic leaf.
# Pages with a dynamic leaf (e.g. an entity's display_name) instead
# give every trail entry a url_name and pass their own
# `breadcrumb_leaf` in the view's context - see _breadcrumbs.html.
BREADCRUMB_MAP = {
    "home": [("Dashboard", None)],
    "documents": [("Documents", None)],
    "knowledge_base": [("Knowledge Base", None)],
    "entity_detail": [("Knowledge Base", "knowledge_base"), ("Entities", "knowledge_base")],
    "relationships": [("Knowledge Base", "knowledge_base"), ("Relationships", None)],
    "knowledge_graph": [("Knowledge Base", "knowledge_base"), ("Graph", None)],
    "citation_explorer": [("Knowledge Base", "knowledge_base"), ("Citations", None)],
    "ask_ai": [("AI Search", None)],
    "search_history": [("AI Search", "ask_ai"), ("Search History", None)],
    "analytics": [("Analytics", None)],
    "reports": [("Reports", None)],
    "profile": [("Profile", None)],
    "monitoring": [("Monitoring", None)],
}


# Sidebar nav items that represent more than one URL name (e.g. the
# "Knowledge Base" item should read as active from its browse page
# *and* every sub-page reachable under it) map here to the single nav
# item name _nav_item.html should highlight. Anything not listed maps
# to itself - a normal single-URL nav item.
NAV_GROUP_MAP = {
    "entity_detail": "knowledge_base",
    "relationships": "knowledge_base",
    "knowledge_graph": "knowledge_base",
    "citation_explorer": "knowledge_base",
    "search_history": "ask_ai",
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

    return {
        "system_status": cache.get_or_set(
            "rag_system_status",
            get_system_status,
            30,
        ),
        "activity_feed": events[:5],
    }

"""
URL configuration for myproject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from .import views

urlpatterns = [
    path("health/", views.health_check, name="health_check"),

    # "home" is a thin role-based dispatcher, not a page of its own -
    # every existing {% url 'home' %} link keeps working as a stable
    # "take me to my dashboard" entry point regardless of role. See
    # RAG.services.permission_service.get_dashboard_url_for_user.
    path("", views.home_redirect, name="home"),
    path("signup/", views.signup, name="signup"),
    path("login/", views.login_user, name="login"),
    path("logout/", views.logout_user, name="logout"),

    path("dashboard/", views.user_dashboard, name="user_dashboard"),

    path("ask/", views.ask_ai, name="ask_ai"),
    path("documents/", views.documents_view, name="documents"),
    path("documents/<int:doc_id>/delete/", views.document_delete, name="document_delete"),
    path("documents/<int:doc_id>/embed/", views.document_embed, name="document_embed"),
    path("documents/<int:doc_id>/status/", views.document_status, name="document_status"),
    path("history/", views.search_history, name="search_history"),
    path("analytics/", views.analytics_view, name="analytics"),
    path("profile/", views.profile_view, name="profile"),

    path("knowledge/", views.knowledge_base_view, name="knowledge_base"),
    path("knowledge/entities/<int:entity_id>/", views.entity_detail_view, name="entity_detail"),
    path("knowledge/relationships/", views.relationships_view, name="relationships"),
    path("knowledge/graph/", views.knowledge_graph_view, name="knowledge_graph"),
    path("knowledge/citations/", views.citation_explorer_view, name="citation_explorer"),

    path("reports/", views.reports_view, name="reports"),
    path("reports/documents.csv", views.export_documents_report, name="export_documents_report"),
    path("reports/usage.csv", views.export_usage_report, name="export_usage_report"),

    # ------------------------------------------------------------
    # Admin namespace. Every route below is gated at the view level by
    # @admin_required / @permission_required (RAG/decorators.py) AND,
    # as a defense-in-depth backstop covering the whole prefix even if
    # a future route forgets its decorator, by
    # RAG.middleware.RoleBasedAccessMiddleware.
    # ------------------------------------------------------------
    path("admin/", views.admin_dashboard_view, name="admin_dashboard"),
    path("admin/users/", views.admin_users_view, name="admin_users"),
    path("admin/roles/", views.admin_roles_view, name="admin_roles"),
    path("admin/settings/", views.admin_settings_view, name="admin_settings"),
    path("admin/queries/", views.admin_queries_view, name="admin_queries"),
    path("admin/activity-logs/", views.admin_activity_logs_view, name="admin_activity_logs"),
    path("admin/system-health/", views.monitoring_view, name="monitoring"),
]

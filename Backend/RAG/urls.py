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
from django.contrib.auth import views as django_auth_views
from django.urls import path, include
from .import views
from . import auth_views
from . import notification_views

urlpatterns = [
    path("health/", views.health_check, name="health_check"),

    # "home" is a thin role-based dispatcher, not a page of its own -
    # every existing {% url 'home' %} link keeps working as a stable
    # "take me to my dashboard" entry point regardless of role. See
    # RAG.services.permission_service.get_dashboard_url_for_user.
    path("", views.home_redirect, name="home"),
    path("signup/", auth_views.signup, name="signup"),
    path("login/", auth_views.login_user, name="login"),
    path("logout/", auth_views.logout_user, name="logout"),
    path("verify-otp/", auth_views.verify_otp, name="verify_otp"),
    path("verify-otp/resend/", auth_views.resend_otp, name="resend_otp"),

    path("password-reset/", auth_views.RAGPasswordResetView.as_view(), name="password_reset"),
    path("password-reset/sent/", django_auth_views.PasswordResetDoneView.as_view(template_name="password_reset_sent.html"), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.RAGPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset/done/", django_auth_views.PasswordResetCompleteView.as_view(template_name="password_reset_complete.html"), name="password_reset_complete"),

    path("dashboard/", views.user_dashboard, name="user_dashboard"),

    path("ask/", views.ask_ai, name="ask_ai"),
    path("ask/stream/", views.ask_ai_stream, name="ask_ai_stream"),
    path("documents/", views.documents_view, name="documents"),
    path("documents/<int:doc_id>/delete/", views.document_delete, name="document_delete"),
    path("documents/<int:doc_id>/download/", views.document_download, name="document_download"),
    path("documents/<int:doc_id>/embed/", views.document_embed, name="document_embed"),
    path("documents/<int:doc_id>/status/", views.document_status, name="document_status"),
    path("documents/<int:doc_id>/archive/", views.document_archive_toggle, name="document_archive_toggle"),
    path("documents/<int:doc_id>/preview/", views.document_preview, name="document_preview"),
    path("documents/<int:doc_id>/favorite/", views.document_favorite_toggle, name="document_favorite_toggle"),
    path("documents/favorites/", views.favorites_view, name="favorites"),
    path("documents/bulk/", views.documents_bulk_action, name="documents_bulk_action"),
    path("documents/tags/", views.tags_manage, name="tags_manage"),
    path("documents/tags/<int:tag_id>/delete/", views.tag_delete, name="tag_delete"),
    path("documents/categories/", views.categories_manage, name="categories_manage"),
    path("documents/categories/<int:category_id>/delete/", views.category_delete, name="category_delete"),
    path("documents/collections/", views.collections_view, name="collections"),
    path("documents/collections/<int:collection_id>/", views.collection_detail_view, name="collection_detail"),
    path("documents/shared-with-me/", views.shared_with_me_view, name="shared_with_me"),
    path("documents/org-library/", views.org_library_view, name="org_library"),
    path("documents/org-library/<int:doc_id>/toggle/", views.org_library_toggle, name="org_library_toggle"),
    path("documents/<int:doc_id>/share/", views.document_share, name="document_share"),
    path("documents/shares/<int:share_id>/revoke/", views.document_share_revoke, name="document_share_revoke"),
    path("documents/<int:doc_id>/versions/", views.document_versions, name="document_versions"),
    path("documents/<int:doc_id>/versions/upload/", views.document_version_upload, name="document_version_upload"),
    path("documents/versions/<int:version_id>/download/", views.document_version_download, name="document_version_download"),
    path("documents/select-dialog/search/", views.select_documents_search, name="select_documents_search"),

    path("ai-tasks/", views.ai_tasks_view, name="ai_tasks"),
    path("ai-tasks/create/", views.ai_task_create, name="ai_task_create"),
    path("ai-tasks/history/", views.ai_task_history, name="ai_task_history"),
    path("ai-tasks/<int:run_id>/status/", views.ai_task_status, name="ai_task_status"),
    path("ai-tasks/<int:run_id>/cancel/", views.ai_task_cancel, name="ai_task_cancel"),
    path("ai-tasks/<int:run_id>/delete/", views.ai_task_delete, name="ai_task_delete"),
    path("ai-tasks/<int:run_id>/results/", views.ai_task_results, name="ai_task_results"),
    path("ai-tasks/<int:run_id>/export.csv", views.ai_task_export, name="ai_task_export"),

    path("history/", views.search_history, name="search_history"),
    path("analytics/", views.analytics_view, name="analytics"),
    path("profile/", views.profile_view, name="profile"),

    path("notifications/", notification_views.notification_center_view, name="notifications"),
    path("notifications/unread-count/", notification_views.notification_unread_count, name="notification_unread_count"),
    path("notifications/list/", notification_views.notification_list_json, name="notification_list_json"),
    path("notifications/<int:notification_id>/read/", notification_views.notification_mark_read, name="notification_mark_read"),
    path("notifications/mark-all-read/", notification_views.notification_mark_all_read, name="notification_mark_all_read"),

    path("knowledge/", views.knowledge_base_view, name="knowledge_base"),
    path("knowledge/entities/<int:entity_id>/", views.entity_detail_view, name="entity_detail"),
    path("knowledge/relationships/", views.relationships_view, name="relationships"),
    path("knowledge/graph/", views.knowledge_graph_view, name="knowledge_graph"),
    path("knowledge/graph/nodes/<int:entity_id>.json", views.graph_node_detail_json, name="graph_node_detail"),
    path("knowledge/graph/edge.json", views.graph_edge_detail_json, name="graph_edge_detail"),
    path("knowledge/citations/", views.citation_explorer_view, name="citation_explorer"),
    path("knowledge/insights/", views.knowledge_insights_view, name="knowledge_insights"),
    path("knowledge/documents/<int:doc_id>/", views.document_knowledge_view, name="document_knowledge"),

    path("reports/", views.reports_view, name="reports"),
    path("reports/documents.csv", views.export_documents_report, name="export_documents_report"),
    path("reports/usage.csv", views.export_usage_report, name="export_usage_report"),
    path("reports/comparison.csv", views.export_comparison_report, name="export_comparison_report"),
    path("reports/ai-task-runs.csv", views.export_ai_task_runs_report, name="export_ai_task_runs_report"),
    path("reports/knowledge-topics.csv", views.export_knowledge_topics_report, name="export_knowledge_topics_report"),

    # ------------------------------------------------------------
    # Admin namespace. Every route below is gated at the view level by
    # @admin_required / @permission_required (RAG/decorators.py) AND,
    # as a defense-in-depth backstop covering the whole prefix even if
    # a future route forgets its decorator, by
    # RAG.middleware.RoleBasedAccessMiddleware.
    # ------------------------------------------------------------
    path("admin/", views.admin_dashboard_view, name="admin_dashboard"),
    path("admin/users/", views.admin_users_view, name="admin_users"),
    path("admin/users/<int:user_id>/profile/", views.admin_user_profile_view, name="admin_user_profile"),
    path("admin/roles/", views.admin_roles_view, name="admin_roles"),
    path("admin/settings/", views.admin_settings_view, name="admin_settings"),
    path("admin/settings/llm/health-check/", views.llm_provider_health_check, name="llm_provider_health_check"),
    path("admin/queries/", views.admin_queries_view, name="admin_queries"),
    path("admin/queries/export.csv", views.export_queries_report, name="export_queries_report"),
    path("admin/queries/<int:log_id>/detail/", views.admin_query_detail_view, name="admin_query_detail"),
    path("admin/queries/<int:log_id>/toggle-flag/", views.admin_query_toggle_flag_view, name="admin_query_toggle_flag"),
    path("admin/system-health/", views.monitoring_view, name="monitoring"),
    path("admin/system-logs/", views.admin_system_logs_view, name="admin_system_logs"),
    path("admin/system-logs/traces/<str:trace_id>/", views.admin_trace_detail_view, name="admin_trace_detail"),
    path("admin/system-logs/errors/<int:group_id>/", views.admin_error_group_detail_view, name="admin_error_group_detail"),
    path("admin/notifications/announce/", notification_views.admin_send_announcement_view, name="admin_send_announcement"),
]

"""
/api/ URL namespace for the React SPA (frontend/) - see myproject/urls.py.
Deliberately separate from RAG/urls.py (the classic template routes,
untouched by this migration) so the two can be developed/tested
independently and the classic pages keep working unmodified.
"""

from django.urls import path

from . import (
    admin_queries_views, admin_roles_views, admin_settings_views, admin_system_logs_views, admin_users_views,
    ai_tasks_views, analytics_views, ask_views, auth_views, collections_views, dashboard_views, documents_views,
    knowledge_views, monitoring_views, notification_views, profile_views, reports_views, search_history_views,
)

urlpatterns = [
    path("auth/session/", auth_views.session_view, name="api_session"),
    path("auth/login/", auth_views.login_view, name="api_login"),
    path("auth/logout/", auth_views.logout_view, name="api_logout"),
    path("auth/signup/", auth_views.signup_view, name="api_signup"),
    path("auth/verify-otp/", auth_views.verify_otp_view, name="api_verify_otp"),
    path("auth/verify-otp/status/", auth_views.verify_otp_status_view, name="api_verify_otp_status"),
    path("auth/verify-otp/resend/", auth_views.resend_otp_view, name="api_resend_otp"),
    path("auth/password-reset/", auth_views.password_reset_request_view, name="api_password_reset_request"),
    path("auth/password-reset/confirm/<uidb64>/<token>/", auth_views.password_reset_confirm_view, name="api_password_reset_confirm"),
    path("auth/password-reset/validate/<uidb64>/<token>/", auth_views.password_reset_validate_view, name="api_password_reset_validate"),

    path("dashboard/", dashboard_views.dashboard_view, name="api_dashboard"),
    path("dashboard/admin/", dashboard_views.admin_overview_view, name="api_admin_overview"),

    path("documents/", documents_views.documents_list_view, name="api_documents_list"),
    path("documents/meta/", documents_views.documents_meta_view, name="api_documents_meta"),
    path("documents/upload/", documents_views.document_upload_view, name="api_document_upload"),
    path("documents/<int:doc_id>/", documents_views.document_delete_view, name="api_document_delete"),
    path("documents/<int:doc_id>/embed/", documents_views.document_embed_view, name="api_document_embed"),
    path("documents/<int:doc_id>/status/", documents_views.document_status_view, name="api_document_status"),
    path("documents/<int:doc_id>/archive/", documents_views.document_archive_toggle_view, name="api_document_archive"),
    path("documents/<int:doc_id>/favorite/", documents_views.document_favorite_toggle_view, name="api_document_favorite"),
    path("documents/<int:doc_id>/preview/", documents_views.document_preview_view, name="api_document_preview"),
    path("documents/<int:doc_id>/download/", documents_views.document_download_view, name="api_document_download"),
    path("documents/select-dialog/search/", documents_views.select_documents_search_view, name="api_select_documents_search"),
    path("documents/favorites/", documents_views.favorites_view, name="api_favorites"),
    path("documents/shared-with-me/", documents_views.shared_with_me_view, name="api_shared_with_me"),
    path("documents/org-library/", documents_views.org_library_view, name="api_org_library"),
    path("documents/org-library/<int:doc_id>/toggle/", documents_views.org_library_toggle_view, name="api_org_library_toggle"),
    path("documents/bulk/", documents_views.documents_bulk_action_view, name="api_documents_bulk_action"),
    path("documents/<int:doc_id>/share/", documents_views.document_share_view, name="api_document_share"),
    path("documents/shares/<int:share_id>/revoke/", documents_views.document_share_revoke_view, name="api_document_share_revoke"),
    path("documents/<int:doc_id>/versions/", documents_views.document_versions_view, name="api_document_versions"),
    path("documents/<int:doc_id>/versions/upload/", documents_views.document_version_upload_view, name="api_document_version_upload"),
    path("documents/versions/<int:version_id>/download/", documents_views.document_version_download_view, name="api_document_version_download"),
    path("documents/collections/", collections_views.collections_view, name="api_collections"),
    path("documents/collections/<int:collection_id>/", collections_views.collection_detail_view, name="api_collection_detail"),

    path("history/", search_history_views.search_history_view, name="api_search_history"),

    path("monitoring/", monitoring_views.monitoring_view, name="api_monitoring"),

    path("admin/users/", admin_users_views.admin_users_view, name="api_admin_users"),
    path("admin/users/action/", admin_users_views.admin_user_action_view, name="api_admin_user_action"),
    path("admin/users/<int:user_id>/profile/", admin_users_views.admin_user_profile_view, name="api_admin_user_profile"),

    path("admin/roles/", admin_roles_views.admin_roles_view, name="api_admin_roles"),
    path("admin/roles/create/", admin_roles_views.admin_role_create_view, name="api_admin_role_create"),
    path("admin/roles/<int:role_id>/permissions/", admin_roles_views.admin_role_permissions_view, name="api_admin_role_permissions"),
    path("admin/roles/<int:role_id>/delete/", admin_roles_views.admin_role_delete_view, name="api_admin_role_delete"),

    path("admin/queries/", admin_queries_views.admin_queries_view, name="api_admin_queries"),
    path("admin/queries/export.csv", admin_queries_views.export_queries_report_view, name="api_export_queries_report"),
    path("admin/queries/<int:log_id>/detail/", admin_queries_views.admin_query_detail_view, name="api_admin_query_detail"),
    path("admin/queries/<int:log_id>/toggle-flag/", admin_queries_views.admin_query_toggle_flag_view, name="api_admin_query_toggle_flag"),

    path("admin/settings/", admin_settings_views.admin_settings_view, name="api_admin_settings"),
    path("admin/settings/health-check/", admin_settings_views.llm_provider_health_check_view, name="api_admin_settings_health_check"),

    path("admin/system-logs/", admin_system_logs_views.admin_system_logs_view, name="api_admin_system_logs"),
    path("admin/system-logs/traces/<str:trace_id>/", admin_system_logs_views.admin_trace_detail_view, name="api_admin_trace_detail"),
    path("admin/system-logs/errors/<int:group_id>/", admin_system_logs_views.admin_error_group_detail_view, name="api_admin_error_group_detail"),

    path("ask/context/", ask_views.ask_context_view, name="api_ask_context"),
    path("ask/log/<int:log_id>/", ask_views.ask_log_detail_view, name="api_ask_log_detail"),
    path("ask/", ask_views.ask_view, name="api_ask"),
    path("ask/stream/", ask_views.ask_stream_view, name="api_ask_stream"),

    path("profile/", profile_views.profile_view, name="api_profile"),
    path("profile/personal/", profile_views.profile_personal_view, name="api_profile_personal"),
    path("profile/extended/", profile_views.profile_extended_view, name="api_profile_extended"),
    path("profile/avatar/", profile_views.profile_avatar_view, name="api_profile_avatar"),
    path("profile/notifications/", profile_views.profile_notifications_view, name="api_profile_notifications"),
    path("profile/password/", profile_views.profile_password_view, name="api_profile_password"),

    path("notifications/", notification_views.notifications_view, name="api_notifications"),
    path("notifications/unread-count/", notification_views.notification_unread_count_view, name="api_notification_unread_count"),
    path("notifications/list/", notification_views.notification_list_json_view, name="api_notification_list"),
    path("notifications/<int:notification_id>/read/", notification_views.notification_mark_read_view, name="api_notification_mark_read"),
    path("notifications/mark-all-read/", notification_views.notification_mark_all_read_view, name="api_notification_mark_all_read"),

    path("knowledge/browse/", knowledge_views.knowledge_browse_view, name="api_knowledge_browse"),
    path("knowledge/entities/<int:entity_id>/", knowledge_views.entity_detail_view, name="api_entity_detail"),
    path("knowledge/relationships/", knowledge_views.relationships_view, name="api_relationships"),
    path("knowledge/graph/", knowledge_views.knowledge_graph_view, name="api_knowledge_graph"),
    path("knowledge/graph/nodes/<int:entity_id>/", knowledge_views.graph_node_detail_view, name="api_graph_node_detail"),
    path("knowledge/graph/edge/", knowledge_views.graph_edge_detail_view, name="api_graph_edge_detail"),
    path("knowledge/citations/", knowledge_views.citation_explorer_view, name="api_citation_explorer"),
    path("knowledge/insights/", knowledge_views.knowledge_insights_view, name="api_knowledge_insights"),
    path("knowledge/documents/<int:doc_id>/", knowledge_views.document_knowledge_view, name="api_document_knowledge"),

    path("ai-tasks/config/", ai_tasks_views.ai_tasks_config_view, name="api_ai_tasks_config"),
    path("ai-tasks/create/", ai_tasks_views.ai_task_create_view, name="api_ai_task_create"),
    path("ai-tasks/history/", ai_tasks_views.ai_task_history_view, name="api_ai_task_history"),
    path("ai-tasks/<int:run_id>/status/", ai_tasks_views.ai_task_status_view, name="api_ai_task_status"),
    path("ai-tasks/<int:run_id>/cancel/", ai_tasks_views.ai_task_cancel_view, name="api_ai_task_cancel"),
    path("ai-tasks/<int:run_id>/delete/", ai_tasks_views.ai_task_delete_view, name="api_ai_task_delete"),
    path("ai-tasks/<int:run_id>/results/", ai_tasks_views.ai_task_results_view, name="api_ai_task_results"),
    path("ai-tasks/<int:run_id>/export.csv", ai_tasks_views.ai_task_export_view, name="api_ai_task_export"),

    path("analytics/", analytics_views.analytics_view, name="api_analytics"),

    path("reports/", reports_views.reports_view, name="api_reports"),
    path("reports/documents.csv", reports_views.export_documents_report_view, name="api_export_documents_report"),
    path("reports/usage.csv", reports_views.export_usage_report_view, name="api_export_usage_report"),
    path("reports/comparison.csv", reports_views.export_comparison_report_view, name="api_export_comparison_report"),
    path("reports/ai-task-runs.csv", reports_views.export_ai_task_runs_report_view, name="api_export_ai_task_runs_report"),
    path("reports/knowledge-topics.csv", reports_views.export_knowledge_topics_report_view, name="api_export_knowledge_topics_report"),
]

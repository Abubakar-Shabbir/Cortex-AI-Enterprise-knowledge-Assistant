"""
/api/ URL namespace for the React SPA (frontend/) - see myproject/urls.py.
Deliberately separate from RAG/urls.py (the classic template routes,
untouched by this migration) so the two can be developed/tested
independently and the classic pages keep working unmodified.
"""

from django.urls import path

from . import ask_views, auth_views, dashboard_views, documents_views

urlpatterns = [
    path("auth/session/", auth_views.session_view, name="api_session"),
    path("auth/login/", auth_views.login_view, name="api_login"),
    path("auth/logout/", auth_views.logout_view, name="api_logout"),

    path("dashboard/", dashboard_views.dashboard_view, name="api_dashboard"),

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

    path("ask/context/", ask_views.ask_context_view, name="api_ask_context"),
    path("ask/log/<int:log_id>/", ask_views.ask_log_detail_view, name="api_ask_log_detail"),
    path("ask/", ask_views.ask_view, name="api_ask"),
    path("ask/stream/", ask_views.ask_stream_view, name="api_ask_stream"),
]

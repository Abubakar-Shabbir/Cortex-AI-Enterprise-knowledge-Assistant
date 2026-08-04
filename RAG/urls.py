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

    path("", views.dashboard, name="home"),
    path("signup/", views.signup, name="signup"),
    path("login/", views.login_user, name="login"),
    path("logout/", views.logout_user, name="logout"),

    path("ask/", views.ask_ai, name="ask_ai"),
    path("documents/", views.documents_view, name="documents"),
    path("documents/<int:doc_id>/delete/", views.document_delete, name="document_delete"),
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

    path("monitoring/", views.monitoring_view, name="monitoring"),
]

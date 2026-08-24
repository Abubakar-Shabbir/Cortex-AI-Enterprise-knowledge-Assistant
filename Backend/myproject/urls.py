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
from django.urls import path, re_path, include
from django.conf import settings
from django.conf.urls.static import static

from RAG.spa_views import spa_view

urlpatterns = [
    # Django's built-in admin site moved off /admin/ so that path is
    # free for this project's own role-based /admin/ dashboard
    # namespace (RAG/urls.py) - see CLAUDE.md's RBAC section.
    path('django-admin/', admin.site.urls),

    # React SPA (frontend/) API layer - see RAG/api/urls.py. Additive,
    # namespaced under /api/ so it can never collide with an existing
    # RAG.urls path; every classic template route below keeps working
    # completely unchanged.
    path('api/', include('RAG.api.urls')),

    # React SPA shell itself - served at /app/ and every sub-path
    # (client-side routing, see frontend/src/routes.jsx) so a hard
    # browser refresh on e.g. /app/documents still resolves to the SPA
    # instead of a Django 404. Registered before the classic
    # `include('RAG.urls')` below only for readability; there's no
    # actual overlap since RAG.urls has no /app/* pattern of its own.
    path('app/', spa_view, name='spa_root'),
    re_path(r'^app/.*$', spa_view, name='spa_catchall'),

    path('', include('RAG.urls')),
]
urlpatterns += static(
    settings.MEDIA_URL,
    document_root=settings.MEDIA_ROOT
)
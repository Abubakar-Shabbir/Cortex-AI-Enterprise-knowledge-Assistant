"""
Celery application (Sprint 10).

Standard Django/Celery wiring: settings prefixed `CELERY_` in
myproject/settings.py (CELERY_BROKER_URL, CELERY_RESULT_BACKEND, ...)
configure this app via the "CELERY" namespace, and `autodiscover_tasks()`
picks up `RAG/tasks.py` automatically since "RAG" is in INSTALLED_APPS.
Imported from myproject/__init__.py so `@shared_task` decorators
anywhere in the project bind to this app as soon as Django starts.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

app = Celery("myproject")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

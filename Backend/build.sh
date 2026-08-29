#!/usr/bin/env bash
# Render's build command (see render.yaml / DEPLOYMENT.md). Runs once
# per deploy, before the app's start command - not during every
# process boot, so this is the right place for anything one-off
# (installing deps, collecting static files, migrating) rather than
# code in settings.py/apps.py that would run on every worker start.
set -o errexit

pip install -r requirements.txt

# Requires STATIC_ROOT (settings.py) - collects every app's static/
# directory into one folder that WhiteNoise serves from at runtime.
python manage.py collectstatic --no-input

# Schema first, then RBAC seed (idempotent - safe on every deploy, see
# that command's own docstring) so a fresh database has working
# roles/permissions immediately, and an existing one just picks up any
# newly-added permission with zero manual steps.
python manage.py migrate --no-input
python manage.py seed_rbac

"""
Serves the built React SPA (frontend/) shell for /app/ and every
client-side route under it (see myproject/urls.py). The SPA itself
handles routing from that point on via React Router (frontend/src/routes.jsx)
- this view's only job is returning index.html so a hard browser
refresh on a deep route like /app/documents resolves to something
real instead of a Django 404.

In local dev, `npm run dev` (frontend/) serves the SPA directly from
Vite on its own port with its own dev server (see frontend/README.md) -
that's the normal way to work on it, since it gets instant HMR. This
view exists for the case where Django itself is asked for /app/* with
no Vite dev server running: with a production build present
(frontend/dist/index.html, via `npm run build`) it serves that; without
one, it redirects to the Vite dev server in DEBUG so following an
existing /app/ link never just dead-ends.
"""

from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect

FRONTEND_DIST = Path(settings.BASE_DIR) / "frontend" / "dist" / "index.html"
VITE_DEV_SERVER = "http://localhost:5173"


def spa_view(request):
    if FRONTEND_DIST.exists():
        return HttpResponse(FRONTEND_DIST.read_text(encoding="utf-8"), content_type="text/html")

    if settings.DEBUG:
        return HttpResponseRedirect(f"{VITE_DEV_SERVER}{request.path}")

    return HttpResponse(
        "The React SPA hasn't been built yet. Run `npm run build` inside frontend/ "
        "and redeploy, or run `npm run dev` there for local development.",
        status=501,
        content_type="text/plain",
    )

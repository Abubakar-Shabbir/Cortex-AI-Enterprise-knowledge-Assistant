"""
Geolocation Service

Resolves a request's client IP to a coarse city/region/country location
via ip-api.com's free JSON endpoint, for RAG.services.activity_log_service
to attach to every ActivityLog row. IP-based geolocation is inherently
approximate (city-level at best, ISP-dependent, often tens of km off) -
there is no vendor that can turn a bare IP into a street-address-exact
location, so this is the ceiling of what "location tracking" can mean
here.

Follows the same never-raise contract as graph_extraction_service and
the Sprint 6-8 retrieval services: a lookup failure (network error,
timeout, rate limit, malformed response) must never break the real
action being logged - it just means that ActivityLog row has no
location, not that the login/delete/role-change itself fails.
"""

import ipaddress
import logging

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ip-api.com's free tier: no key required, ~45 req/min. Fine for this
# use case since results are cached per-IP for a day and lookups only
# happen on already-infrequent audit events (logins, deletes, role
# changes, ...), never on every page view.
GEO_API_URL = "http://ip-api.com/json/{ip}"
GEO_API_TIMEOUT = 3
GEO_CACHE_TTL = 60 * 60 * 24
GEO_CACHE_PREFIX = "geoip:location:"

EMPTY_LOCATION = {
    "city": "",
    "region": "",
    "country": "",
    "country_code": "",
    "latitude": None,
    "longitude": None,
}


def get_client_ip(request):
    """
    Best-effort client IP from a Django request. Checks
    X-Forwarded-For first (the leftmost entry, i.e. the original
    client, since a reverse proxy appends its own hop to the end)
    before falling back to REMOTE_ADDR - the same precedence every
    reverse-proxy-aware Django app uses. Returns None rather than
    raising if neither header is present.
    """

    if request is None:
        return None

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        ip = forwarded_for.split(",")[0].strip()
        if ip:
            return ip

    return request.META.get("REMOTE_ADDR") or None


def _is_lookupable(ip):
    """Private/loopback/reserved IPs (localhost, LAN dev, Docker bridges) can never resolve to a real-world location - skip the API call entirely rather than send them to a third party."""

    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False

    return not (addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local)


def lookup_ip_location(ip):
    """
    Resolve an IP to {city, region, country, country_code, latitude,
    longitude}. Never raises - any failure (private IP, network error,
    timeout, API error response) returns EMPTY_LOCATION. Cached per-IP
    for GEO_CACHE_TTL so repeat activity from the same user/network
    doesn't re-hit the external API.
    """

    if not ip:
        return dict(EMPTY_LOCATION)

    cache_key = f"{GEO_CACHE_PREFIX}{ip}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    if not _is_lookupable(ip):
        cache.set(cache_key, dict(EMPTY_LOCATION), GEO_CACHE_TTL)
        return dict(EMPTY_LOCATION)

    location = dict(EMPTY_LOCATION)

    try:
        response = requests.get(
            GEO_API_URL.format(ip=ip),
            params={
                "fields": "status,message,country,countryCode,regionName,city,lat,lon",
            },
            timeout=GEO_API_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("status") == "success":
            location = {
                "city": payload.get("city") or "",
                "region": payload.get("regionName") or "",
                "country": payload.get("country") or "",
                "country_code": payload.get("countryCode") or "",
                "latitude": payload.get("lat"),
                "longitude": payload.get("lon"),
            }
        else:
            logger.info("Geolocation lookup for %s returned no result: %s", ip, payload.get("message"))
    except Exception:
        logger.exception("Geolocation lookup failed for IP %s.", ip)

    cache.set(cache_key, location, GEO_CACHE_TTL)
    return location

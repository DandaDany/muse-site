"""One-time control-plane export for removing the hosted Django/Postgres dependency.

The response is protected by the same Bearer token as the crawler APIs and contains
only operational control data: all tracked movies (including inactive/future rows),
all cinema chains, and all cinema locations. It never exports Django users,
sessions, passwords, tokens, or settings.
"""

from __future__ import annotations

from django.db.models import Max
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .api import _aliases_list, _check_token
from .models import CinemaChain, CinemaLocation, TrackedMovie


@require_http_methods(["GET"])
def control_export(request):
    denied = _check_token(request)
    if denied:
        return denied

    latest = TrackedMovie.objects.filter(is_active=True).aggregate(m=Max("updated_at"))["m"]
    version = int(latest.timestamp()) if latest else 0

    tracked_movies = [
        {
            "id": movie.id,
            "title": movie.title,
            "aliases": _aliases_list(movie.aliases),
            "target_date": movie.target_date.isoformat() if movie.target_date else None,
            "is_active": bool(movie.is_active),
            "sort_order": movie.sort_order,
            "notes": movie.notes,
            "created_at": movie.created_at.isoformat() if movie.created_at else None,
            "updated_at": movie.updated_at.isoformat() if movie.updated_at else None,
        }
        for movie in TrackedMovie.objects.all().order_by("sort_order", "title", "id")
    ]

    chains = [
        {
            "id": chain.id,
            "chain_name": chain.chain_name,
            "official_url": chain.official_url,
            "crawl_url": chain.crawl_url,
            "booking_url": chain.booking_url,
            "all_locations_assumed_showing": bool(chain.all_locations_assumed_showing),
            "notes": chain.notes,
            "active": bool(chain.active),
        }
        for chain in CinemaChain.objects.all().order_by("id")
    ]

    locations = [
        {
            "id": loc.id,
            "chain_id": loc.chain_id,
            "location_name": loc.location_name,
            "display_name": loc.display_name,
            "address": loc.address,
            "city": loc.city,
            "district": loc.district,
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "source_location_code": loc.source_location_code,
            "location_url": loc.location_url,
            "source_url": loc.source_url,
            "notes": loc.notes,
            "active": bool(loc.active),
        }
        for loc in CinemaLocation.objects.all().order_by("id")
    ]

    return JsonResponse(
        {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "tracked_movies_version": version,
            "counts": {
                "tracked_movies": len(tracked_movies),
                "chains": len(chains),
                "locations": len(locations),
            },
            "tracked_movies": tracked_movies,
            "chains": chains,
            "locations": locations,
        }
    )

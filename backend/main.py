"""Smart Route FastAPI backend.

Routing: FOSSGIS-hosted OSRM (shared demonstration service).
Place search: Photon / OpenStreetMap.

This service adds a bounded snapping radius and ranks returned OSRM alternatives
using ETA plus the amount of unnamed road distance. It cannot identify pavement
quality: an unnamed OSM road is not automatically unpaved or illegal to use.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

app = FastAPI(
    title="Smart Route API",
    description="Place search and road routing for the Smart Route learning project.",
    version="1.4.0",
)

origin_string = os.getenv(
    "FRONTEND_ORIGINS",
    "http://127.0.0.1:5500,http://localhost:5500",
)
allowed_origins = [item.strip() for item in origin_string.split(",") if item.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

USER_AGENT = "SmartRoute-StudentProject/1.4 (OpenStreetMap-based educational route planner)"
HTTP_TIMEOUT = httpx.Timeout(35.0, connect=10.0)

OSRM_SERVERS = {
    "driving-car": "https://routing.openstreetmap.de/routed-car",
    "foot-walking": "https://routing.openstreetmap.de/routed-foot",
    "cycling-regular": "https://routing.openstreetmap.de/routed-bike",
}

_route_lock = asyncio.Lock()
_last_route_request = 0.0


async def wait_for_route_slot() -> None:
    """Respect the public FOSSGIS server's approximately one-request/second policy."""
    global _last_route_request
    async with _route_lock:
        elapsed = time.monotonic() - _last_route_request
        if elapsed < 1.1:
            await asyncio.sleep(1.1 - elapsed)
        _last_route_request = time.monotonic()


_photon_cache: dict[tuple, tuple[float, dict]] = {}
_PHOTON_CACHE_TTL = 300.0
_photon_lock = asyncio.Lock()
_last_photon_request = 0.0


async def wait_for_photon_slot() -> None:
    global _last_photon_request
    async with _photon_lock:
        elapsed = time.monotonic() - _last_photon_request
        if elapsed < 1.1:
            await asyncio.sleep(1.1 - elapsed)
        _last_photon_request = time.monotonic()


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class RouteRequest(BaseModel):
    start: Location
    destination: Location
    profile: Literal["driving-car", "foot-walking", "cycling-regular"] = "driving-car"
    road_preference: Literal["named_roads", "balanced", "fastest"] = "named_roads"
    # Keep OSRM from silently snapping a misplaced pin a long way to an unrelated road.
    snap_radius_m: int = Field(default=150, ge=30, le=500)


def _normalise_photon_feature(feature: dict) -> dict | None:
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    if len(coordinates) < 2:
        return None

    try:
        lon, lat = float(coordinates[0]), float(coordinates[1])
    except (TypeError, ValueError):
        return None

    props = feature.get("properties") or {}
    name = (
        props.get("name")
        or props.get("street")
        or props.get("locality")
        or props.get("district")
        or props.get("city")
        or "Unnamed place"
    )

    address_parts: list[str] = []
    for value in (
        props.get("housenumber"),
        props.get("street"),
        props.get("district"),
        props.get("city"),
        props.get("state"),
        props.get("country"),
    ):
        if value and str(value).strip() and str(value).strip() not in address_parts:
            address_parts.append(str(value).strip())

    label = ", ".join(address_parts) if address_parts else str(name)
    category = props.get("osm_key") or props.get("type") or "place"
    place_type = props.get("type") or props.get("osm_value") or ""
    broad_types = {"country", "state", "city", "district", "county", "locality", "suburb"}
    zoom = 11 if str(place_type).lower() in broad_types else 17

    return {
        "name": str(name),
        "label": label,
        "lat": lat,
        "lon": lon,
        "category": str(category),
        "type": str(place_type),
        "country": props.get("country"),
        "osm_type": props.get("osm_type"),
        "osm_id": props.get("osm_id"),
        "zoom": zoom,
    }


@app.get("/api/health")
async def health_check() -> dict:
    return {
        "status": "online",
        "message": "Smart Route backend is working",
        "routing_provider": "FOSSGIS OSRM",
        "place_search_provider": "Photon / OpenStreetMap",
        "route_safety": "bounded snapping and road-name-aware alternatives",
    }


@app.get("/api/search")
async def search_places(
    q: str = Query(min_length=2, max_length=180),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
    limit: int = Query(default=8, ge=1, le=10),
) -> dict:
    """Search named places globally; lat/lon bias results but do not bound them."""
    query = " ".join(q.split())
    if not query:
        raise HTTPException(status_code=422, detail="Enter a place name to search.")

    bias_lat = round(lat, 2) if lat is not None else None
    bias_lon = round(lon, 2) if lon is not None else None
    cache_key = (query.casefold(), bias_lat, bias_lon, limit)
    cached = _photon_cache.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < _PHOTON_CACHE_TTL:
        return cached[1]

    params: dict[str, str | int | float] = {"q": query, "limit": limit, "lang": "en"}
    if lat is not None and lon is not None:
        params.update({"lat": lat, "lon": lon, "zoom": 10})

    try:
        await wait_for_photon_slot()
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(
                "https://photon.komoot.io/api/",
                params=params,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            response.raise_for_status()
            body = response.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Place search timed out. Please try again.") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Place search provider returned HTTP {exc.response.status_code}.",
        ) from exc
    except (httpx.RequestError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Could not reach the place search service.") from exc

    results = []
    for feature in body.get("features") or []:
        item = _normalise_photon_feature(feature)
        if item:
            results.append(item)

    result_body = {"provider": "Photon / OpenStreetMap", "query": query, "results": results}
    if len(_photon_cache) > 500:
        expired = [key for key, (created, _) in _photon_cache.items() if now - created >= _PHOTON_CACHE_TTL]
        for key in expired:
            _photon_cache.pop(key, None)
        if len(_photon_cache) > 500:
            _photon_cache.pop(next(iter(_photon_cache)))
    _photon_cache[cache_key] = (time.monotonic(), result_body)
    return result_body


def _build_instruction(step: dict) -> dict:
    maneuver = step.get("maneuver") or {}
    kind = maneuver.get("type", "")
    modifier = maneuver.get("modifier", "")
    name = str(step.get("name") or "").strip()
    ref = str(step.get("ref") or "").strip()
    road = name or ref or "an unnamed mapped road"
    is_unnamed = not (name or ref)

    if kind == "depart":
        instruction = f"Start on {road}"
    elif kind == "arrive":
        instruction = "You have arrived at your destination"
    elif kind in {"turn", "new name", "continue"} and modifier:
        instruction = f"Continue {modifier} onto {road}" if modifier == "straight" else f"Turn {modifier} onto {road}"
    elif kind == "roundabout":
        exit_number = maneuver.get("exit")
        instruction = "Enter the roundabout"
        if exit_number:
            instruction += f" and take exit {exit_number}"
        instruction += f" onto {road}"
    elif modifier == "straight":
        instruction = f"Continue straight on {road}"
    else:
        instruction = f"Continue on {road}"

    return {
        "instruction": instruction,
        "distance": float(step.get("distance") or 0),
        "duration": float(step.get("duration") or 0),
        "name": name,
        "ref": ref,
        "is_unnamed": is_unnamed,
        "maneuver": maneuver,
    }


def _normalise_osrm_route(route: dict) -> dict:
    segments = []
    unnamed_distance = 0.0
    named_distance = 0.0
    unnamed_count = 0

    for leg in route.get("legs") or []:
        steps = []
        for raw_step in leg.get("steps") or []:
            step = _build_instruction(raw_step)
            if step["is_unnamed"]:
                unnamed_distance += step["distance"]
                unnamed_count += 1
            else:
                named_distance += step["distance"]
            steps.append(step)
        segments.append({
            "distance": float(leg.get("distance") or 0),
            "duration": float(leg.get("duration") or 0),
            "steps": steps,
        })

    total_distance = float(route.get("distance") or 0)
    unnamed_ratio = unnamed_distance / total_distance if total_distance > 0 else 0.0
    if unnamed_ratio >= 0.30:
        label = "Many route metres are on unnamed mapped roads"
    elif unnamed_ratio >= 0.10:
        label = "Some route sections are unnamed in OpenStreetMap"
    else:
        label = "Most route metres have a road name or reference"

    return {
        "type": "Feature",
        "geometry": route.get("geometry"),
        "properties": {
            "summary": {
                "distance": total_distance,
                "duration": float(route.get("duration") or 0),
            },
            "segments": segments,
            "road_quality": {
                "unnamed_distance": round(unnamed_distance, 1),
                "named_distance": round(named_distance, 1),
                "unnamed_step_count": unnamed_count,
                "unnamed_distance_ratio": round(unnamed_ratio, 3),
                "label": label,
                "warning": (
                    "Unnamed means the OpenStreetMap road has no name/ref tag; it does not prove that it is unpaved. "
                    "Confirm access and road surface locally."
                    if unnamed_ratio >= 0.10 else ""
                ),
            },
        },
    }


def _rank_route(feature: dict, preference: str, fastest_duration: float) -> tuple[float, float, float]:
    props = feature.get("properties") or {}
    summary = props.get("summary") or {}
    quality = props.get("road_quality") or {}
    duration = float(summary.get("duration") or 0)
    ratio = float(quality.get("unnamed_distance_ratio") or 0)
    duration_ratio = duration / fastest_duration if fastest_duration > 0 else 1.0

    if preference == "fastest":
        score = duration_ratio
    elif preference == "balanced":
        score = (0.80 * duration_ratio) + (0.20 * ratio)
    else:  # named_roads
        score = (0.62 * duration_ratio) + (0.38 * ratio)

    return (score, duration, ratio)


@app.post("/api/route")
async def calculate_route(request: RouteRequest) -> dict:
    server = OSRM_SERVERS[request.profile]
    coordinates = (
        f"{request.start.lon},{request.start.lat};"
        f"{request.destination.lon},{request.destination.lat}"
    )
    url = f"{server}/route/v1/driving/{coordinates}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",
        "alternatives": "3",
        # A finite radius prevents far-away snapping to an unrelated road.
        "radiuses": f"{request.snap_radius_m};{request.snap_radius_m}",
    }

    try:
        await wait_for_route_slot()
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(
                url,
                params=params,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Route calculation timed out. Please try again.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Unable to connect to the routing server.") from exc

    # OSRM commonly reports routing errors (for example NoSegment) with HTTP 400
    # and a useful JSON body. Parse that body BEFORE interpreting the HTTP status;
    # otherwise the frontend only sees a generic 'HTTP 400' message.
    try:
        body = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Routing provider returned HTTP {response.status_code} with an unreadable response.",
        ) from exc

    code = body.get("code") if isinstance(body, dict) else None
    provider_message = body.get("message", "") if isinstance(body, dict) else ""

    if code == "NoSegment":
        raise HTTPException(
            status_code=422,
            detail=(
                f"No routable road was found within {request.snap_radius_m} metres of one of the selected points. "
                "For JAIN, choose 'JAIN Global Campus – Main Gate', not the campus-grounds marker. "
                "You can also move the pin closer to the public road."
            ),
        )

    if code == "NoRoute":
        raise HTTPException(
            status_code=404,
            detail=(provider_message or "No connected road route was found between these points.")
            + " Try another road-accessible start or destination.",
        )

    if not response.is_success:
        safe_message = provider_message or "The routing provider rejected the request."
        raise HTTPException(
            status_code=502,
            detail=f"Routing provider HTTP {response.status_code} ({code or 'unknown'}): {safe_message}",
        )

    if code != "Ok":
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected routing response ({code or 'no code'}): {provider_message or 'No route data returned.'}",
        )

    raw_routes = body.get("routes") or []
    if not raw_routes:
        raise HTTPException(status_code=404, detail="No route found.")

    features = [_normalise_osrm_route(route) for route in raw_routes]
    fastest_duration = min(
        float((feature.get("properties", {}).get("summary") or {}).get("duration") or 0)
        for feature in features
    )
    features.sort(key=lambda feature: _rank_route(feature, request.road_preference, fastest_duration))

    for index, feature in enumerate(features):
        quality = feature["properties"]["road_quality"]
        quality["rank"] = index + 1
        quality["selection_basis"] = request.road_preference

    waypoints = body.get("waypoints") or []
    snap_warnings = []
    for label, waypoint in zip(("Start", "Destination"), waypoints):
        snap_distance = float(waypoint.get("distance") or 0)
        snapped_name = str(waypoint.get("name") or "").strip()
        if snap_distance >= 40:
            snap_warnings.append(
                f"{label} point snapped {round(snap_distance)} m to the nearest routable road. Verify the entrance."
            )
        if not snapped_name:
            snap_warnings.append(f"{label} point snapped to an unnamed mapped road segment.")

    return {
        "code": "Ok",
        "provider": "FOSSGIS OSRM",
        "profile": request.profile,
        "road_preference": request.road_preference,
        "snap_radius_m": request.snap_radius_m,
        "features": features,
        "alternatives_count": len(features),
        "waypoints": waypoints,
        "warnings": snap_warnings,
        "routing_note": (
            "Routes are ranked using ETA and OpenStreetMap road-name coverage. "
            "Road names are not a reliable measurement of pavement quality or public access."
        ),
        "routing_algorithm": {
            "engine": "OSRM Route service",
            "search_mode": (
                "The hosted routing provider configures the search mode. OSRM supports "
                "Contraction Hierarchies and Multi-Level Dijkstra; the public endpoint "
                "does not expose its active mode."
            ),
            "alternative_ranking": {
                "named_roads": "0.62 * duration_ratio + 0.38 * unnamed_distance_ratio",
                "balanced": "0.80 * duration_ratio + 0.20 * unnamed_distance_ratio",
                "fastest": "duration_ratio"
            },
            "graph_lab_note": (
                "Graph Lab Dijkstra and A* are separate browser demonstrations; "
                "they do not calculate live map routes."
            )
        },
    }

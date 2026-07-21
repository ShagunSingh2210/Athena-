"""OpenStreetMap ingestion via the Overpass API — keyless, real data.

Engineering decision: the plan originally scoped Bhuvan (ISRO) for the
industrial-zone layer, but Bhuvan's WMS endpoints require an account login,
which conflicts with the no-keys constraint for this pass. OSM `landuse=industrial`
polygons are a defensible substitute — same semantic (industrial land parcels),
openly licensed, and queryable in one Overpass call alongside the road network.
Swap back to Bhuvan later only if you need finer industrial-type sub-classification.
"""
from __future__ import annotations

import pandas as pd
import requests

from config import DEFAULT_TIMEOUT_S, HTTP_USER_AGENT, CityConfig
from utils.caching import cached_fetch

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_HEADERS = {"User-Agent": HTTP_USER_AGENT}

# Road classes weighted roughly by typical traffic volume/emissions contribution.
_ROAD_WEIGHTS = {"motorway": 1.0, "trunk": 0.9, "primary": 0.7, "secondary": 0.5, "tertiary": 0.3}


def _bbox_str(city: CityConfig) -> str:
    return f"{city.lat_min},{city.lon_min},{city.lat_max},{city.lon_max}"


@cached_fetch("osm_roads")
def fetch_road_network(city: CityConfig) -> pd.DataFrame:
    """Pull road centerlines and a traffic-weight per segment for a city bbox.

    Args:
        city: Target city config.

    Returns:
        DataFrame: lat, lon (segment midpoint), road_class, traffic_weight.
        One row per way midpoint — deliberately point-like so it can reuse
        `utils.grid.assign_points_to_cells` for per-cell road density.
    """
    classes = "|".join(_ROAD_WEIGHTS)
    query = f"""
    [out:json][timeout:60];
    way["highway"~"^({classes})$"]({_bbox_str(city)});
    out geom;
    """
    resp = requests.post(_OVERPASS_URL, data={"data": query}, headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S * 4)
    resp.raise_for_status()
    elements = resp.json().get("elements", [])
    if not elements:
        raise ValueError(f"Overpass returned no roads for {city.name}")

    rows = []
    for way in elements:
        geom = way.get("geometry", [])
        if not geom:
            continue
        mid = geom[len(geom) // 2]
        road_class = way.get("tags", {}).get("highway", "unclassified")
        rows.append({
            "lat": mid["lat"], "lon": mid["lon"],
            "road_class": road_class,
            "traffic_weight": _ROAD_WEIGHTS.get(road_class, 0.2),
        })
    return pd.DataFrame(rows)


@cached_fetch("osm_industrial")
def fetch_industrial_zones(city: CityConfig) -> pd.DataFrame:
    """Pull industrial-landuse polygon centroids for a city bbox (Bhuvan substitute).

    Args:
        city: Target city config.

    Returns:
        DataFrame: lat, lon (polygon centroid), area_m2 (approx, shoelace formula).
    """
    query = f"""
    [out:json][timeout:60];
    way["landuse"="industrial"]({_bbox_str(city)});
    out geom;
    """
    resp = requests.post(_OVERPASS_URL, data={"data": query}, headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S * 4)
    resp.raise_for_status()
    elements = resp.json().get("elements", [])
    if not elements:
        raise ValueError(f"Overpass returned no industrial zones for {city.name}")

    rows = []
    for way in elements:
        geom = way.get("geometry", [])
        if len(geom) < 3:
            continue
        lats = [p["lat"] for p in geom]
        lons = [p["lon"] for p in geom]
        rows.append({
            "lat": sum(lats) / len(lats),
            "lon": sum(lons) / len(lons),
            "area_m2": _shoelace_area_m2(lats, lons),
        })
    return pd.DataFrame(rows)


def _shoelace_area_m2(lats: list[float], lons: list[float]) -> float:
    """Approximate polygon area in m^2 via the shoelace formula on a local
    equirectangular projection (fine at city scale, avoids a full CRS library)."""
    import numpy as np
    lat0 = np.mean(lats)
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * np.cos(np.radians(lat0))
    x = np.array(lons) * km_per_deg_lon * 1000
    y = np.array(lats) * km_per_deg_lat * 1000
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))

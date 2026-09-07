"""Length units used by distance relations and DuckDB ST_DWithin."""

from __future__ import annotations

METERS_PER: dict[str, float] = {
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "km": 1000.0,
    "kilometer": 1000.0,
    "kilometers": 1000.0,
    "ft": 0.3048,
    "foot": 0.3048,
    "feet": 0.3048,
    "mi": 1609.34,
    "mile": 1609.34,
    "miles": 1609.34,
    "yd": 0.9144,
    "yard": 0.9144,
    "yards": 0.9144,
}


def to_meters(distance: float, unit: str) -> float | None:
    """Convert *distance* in *unit* to metres. ``None`` if the unit is unknown."""
    factor = METERS_PER.get(unit.strip().lower())
    if factor is None:
        return None
    return distance * factor

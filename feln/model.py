"""FELN query model and spatial-relation grammar."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .identical import identical
from .units import to_meters

VALID_KINDS = {
    "intersects",
    "inside",
    "contains",
    "within",
    "withinDistance",
    "notWithinDistance",
}
DISTANCE_KINDS = {"withinDistance", "notWithinDistance"}
# DuckDB (and ArcGIS) treat these as the same predicate.
KIND_ALIASES = {"inside": "within"}
_KIND_INDEX = {k.lower(): k for k in VALID_KINDS}

_DISTANCE_ABS_M = 0.01


def canon_kind(kind: str) -> str:
    """Map a stored kind onto its comparison/SQL identity."""
    return KIND_ALIASES.get(kind, kind)


class Relation(BaseModel):
    """Parsed spatial relation from the primary layer to a secondary layer.

    ``kind == "none"`` is a no-op: no spatial join, the relationship is already
    in a WHERE clause (for example a ``dist_*`` column).
    """

    model_config = ConfigDict(frozen=True)

    kind: str = Field(
        description=(
            "none, intersects, inside, contains, within, withinDistance, or notWithinDistance"
        ),
    )
    distance: float = 0.0
    unit: str = ""

    def same(self, other: Relation) -> bool:
        if canon_kind(self.kind) != canon_kind(other.kind):
            return False
        if canon_kind(self.kind) not in DISTANCE_KINDS:
            return True
        metres_a = to_meters(self.distance, self.unit)
        metres_b = to_meters(other.distance, other.unit)
        if metres_a is None or metres_b is None:
            if abs(self.distance - other.distance) > 0.001:
                return False
            return self.unit.lower() == other.unit.lower()
        return abs(metres_a - metres_b) <= _DISTANCE_ABS_M


class FELN(BaseModel):
    """Find Existing Location with N layers.

    ``layers[0]`` is the primary layer whose features are returned.
    ``layers[1..]`` are spatial filters. ``relations[i]`` is the relationship
    from the primary to ``layers[i+1]``.
    """

    model_config = ConfigDict(frozen=True)

    layers: list[str] = Field(description="Layer names; primary first.")
    where: list[str] = Field(
        description="One SQL WHERE per layer. Empty string means no filter.",
    )
    relations: list[str] = Field(
        description=(
            "One relation per secondary layer: '' (no-op), intersects, inside, "
            "contains, within, 'withinDistance <n> <unit>', or "
            "'notWithinDistance <n> <unit>'."
        ),
    )

    @model_validator(mode="after")
    def _validate_lengths(self) -> FELN:
        n = len(self.layers)
        if n < 1:
            raise ValueError("layers must contain at least one layer")
        if len(self.where) != n:
            raise ValueError(f"where must have {n} entries (one per layer), got {len(self.where)}")
        if len(self.relations) != n - 1:
            raise ValueError(f"relations must have {n - 1} entries, got {len(self.relations)}")
        for rel in self.relations:
            parse_relation(rel)
        return self

    def same(self, other: object) -> bool:
        """True if *other* is the same query, ignoring secondary order."""
        if not isinstance(other, FELN):
            return False
        if len(self.layers) != len(other.layers):
            return False
        if self.layers[0].strip().lower() != other.layers[0].strip().lower():
            return False
        if not identical(self.where[0], other.where[0]):
            return False
        unused = set(range(1, len(other.layers)))
        for i, name in enumerate(self.layers[1:], start=1):
            key = name.strip().lower()
            match = next(
                (
                    j
                    for j in unused
                    if other.layers[j].strip().lower() == key
                    and identical(self.where[i], other.where[j])
                    and parse_relation(self.relations[i - 1]).same(
                        parse_relation(other.relations[j - 1])
                    )
                ),
                None,
            )
            if match is None:
                return False
            unused.remove(match)
        return not unused


def parse_relation(rel: str) -> Relation:
    """Parse a relation string. The kind token is matched case-insensitively."""
    parts = rel.strip().split()
    if not parts:
        return Relation(kind="none")
    kind_raw = parts[0]
    kind = _KIND_INDEX.get(kind_raw.lower())
    if kind is None:
        raise ValueError(
            f"Unknown relation kind: '{kind_raw}'. Must be one of {sorted(VALID_KINDS)}"
        )
    if kind in DISTANCE_KINDS:
        if len(parts) != 3:
            raise ValueError(f"{kind} relation must be '{kind} <value> <unit>', got: '{rel}'")
        try:
            distance = float(parts[1])
        except ValueError:
            raise ValueError(f"Invalid distance value: '{parts[1]}'") from None
        return Relation(kind=kind, distance=distance, unit=parts[2].lower())
    return Relation(kind=kind)

"""FELN / Relation grammar."""

from __future__ import annotations

import pytest

from feln import FELN, Relation, parse_relation


def test_two_layers_with_distance() -> None:
    query = FELN(
        layers=["wells", "pipeline"],
        where=["", "status = 'IN-SERVICE'"],
        relations=["withinDistance 5 miles"],
    )
    assert len(query.layers) == 2
    assert len(query.relations) == 1


def test_rejects_wrong_where_count() -> None:
    with pytest.raises(ValueError, match="where must have 2 entries"):
        FELN(layers=["wells", "pipeline"], where=[""], relations=["intersects"])


def test_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="Unknown relation kind"):
        FELN(layers=["a", "b"], where=["", ""], relations=["overlaps"])


def test_parse_empty_is_none() -> None:
    assert parse_relation("").kind == "none"
    assert parse_relation("   ").kind == "none"


def test_parse_distance_case_insensitive() -> None:
    parsed = parse_relation("WITHINDISTANCE 2.5 km")
    assert parsed.kind == "withinDistance"
    assert parsed.distance == 2.5
    assert parsed.unit == "km"


def test_same_ignores_secondary_order() -> None:
    left = FELN(
        layers=["wells", "pipeline", "counties"],
        where=["", "", ""],
        relations=["intersects", "within"],
    )
    right = FELN(
        layers=["wells", "counties", "pipeline"],
        where=["", "", ""],
        relations=["within", "intersects"],
    )
    assert left.same(right)


def test_same_within_equals_inside() -> None:
    left = FELN(layers=["wells", "counties"], where=["", ""], relations=["within"])
    right = FELN(layers=["wells", "counties"], where=["", ""], relations=["inside"])
    assert left.same(right)


def test_same_distance_unit_conversion() -> None:
    miles = Relation(kind="withinDistance", distance=5.0, unit="miles")
    km = Relation(kind="withinDistance", distance=8.0467, unit="kilometers")
    assert miles.same(km)

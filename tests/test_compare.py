"""The compare recommendations: name-align, within/inside, metres, canonical encode."""

from __future__ import annotations

import pytest

from feln import FELN, FELNCompare
from feln.compare import canonical_text, where_credit


def _wells_pipeline_counties(rels: list[str], layers: list[str] | None = None) -> FELN:
    return FELN(
        layers=layers or ["wells", "pipeline", "counties"],
        where=["", "", ""],
        relations=rels,
    )


def test_structural_aligns_secondary_order() -> None:
    left = _wells_pipeline_counties(["intersects", "within"])
    right = _wells_pipeline_counties(
        ["within", "intersects"],
        layers=["wells", "counties", "pipeline"],
    )
    assert FELNCompare.structural(left, right) == pytest.approx(1.0)


def test_structural_within_equals_inside() -> None:
    left = FELN(layers=["wells", "counties"], where=["", ""], relations=["within"])
    right = FELN(layers=["wells", "counties"], where=["", ""], relations=["inside"])
    assert FELNCompare.structural(left, right) == pytest.approx(1.0)


def test_structural_distance_unit_conversion() -> None:
    left = FELN(
        layers=["wells", "pipeline"],
        where=["", ""],
        relations=["withinDistance 5 miles"],
    )
    right = FELN(
        layers=["wells", "pipeline"],
        where=["", ""],
        relations=["withinDistance 8.0467 kilometers"],
    )
    assert FELNCompare.structural(left, right) == pytest.approx(1.0)


def test_structural_distance_partial_credit() -> None:
    left = FELN(
        layers=["wells", "pipeline"],
        where=["", ""],
        relations=["withinDistance 5 miles"],
    )
    right = FELN(
        layers=["wells", "pipeline"],
        where=["", ""],
        relations=["withinDistance 10 miles"],
    )
    # layers 1.0, where 1.0, relation 0.75 (half relative error after the 0.5 kind floor)
    assert FELNCompare.structural(left, right) == pytest.approx(0.925)


def test_semantic_canonicalizes_equivalent_where(encoder) -> None:
    left = FELN(
        layers=["wells"],
        where=["depth > 100 AND status = 'ACTIVE'"],
        relations=[],
    )
    right = FELN(
        layers=["wells"],
        where=["status = 'ACTIVE' AND depth > 100"],
        relations=[],
    )
    assert canonical_text(left) == canonical_text(right)
    assert FELNCompare.semantic(left, right, encoder) == pytest.approx(1.0, abs=1e-6)


def test_semantic_permutation_is_one(encoder) -> None:
    left = _wells_pipeline_counties(["intersects", "within"])
    right = _wells_pipeline_counties(
        ["within", "intersects"],
        layers=["wells", "counties", "pipeline"],
    )
    assert canonical_text(left) == canonical_text(right)
    assert FELNCompare.semantic(left, right, encoder) == pytest.approx(1.0, abs=1e-6)


def test_semantic_identical_is_one(encoder) -> None:
    query = FELN(
        layers=["wells", "pipeline"],
        where=["", "status = 'IN-SERVICE'"],
        relations=["withinDistance 5 miles"],
    )
    assert FELNCompare.semantic(query, query, encoder) == pytest.approx(1.0, abs=1e-6)


# --- partial credit / cost: values locked, an optimiser needs them ordered, not just > 0


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("a = 1 AND b = 2", "b = 2 AND a = 1", 1.0),
        ("", "", 1.0),
        ("buildingtypeid = 13 AND flooraboveground > 2", "flooraboveground > 2", 2 / 3),
        ("Female > 200 OR Male > 300", "Female > 200 AND Male > 300", 0.75),
        ("Bank_Distance < 250", '"Bank_Distance" < CAST(25 AS DOUBLE)', 0.775),
        ("Bank_Distance < 250", "School_Distance < 250", 0.5),
        ("a LIKE '%x%'", "a NOT LIKE '%x%'", 0.75),
        ("a = 1", "", 0.0),
        ("a = 1", "not sql (((", 0.0),
    ],
)
def test_where_credit(left: str, right: str, expected: float) -> None:
    assert where_credit(left, right) == pytest.approx(expected)
    assert where_credit(right, left) == pytest.approx(expected)


def test_partial_matches_structural_when_exact() -> None:
    query = FELN(
        layers=["wells", "pipeline"],
        where=["depth > 100", "status = 'IN-SERVICE'"],
        relations=["withinDistance 5 miles"],
    )
    assert FELNCompare.partial(query, query) == pytest.approx(1.0)
    assert FELNCompare.partial(query, query) == FELNCompare.structural(query, query)


def test_partial_swapped_primary_is_half_not_zero() -> None:
    gold = FELN(layers=["Neighborhoods", "Master"], where=["", "t = 13"], relations=["contains"])
    pred = FELN(layers=["Master", "Neighborhoods"], where=["t = 13", ""], relations=["within"])
    assert FELNCompare.structural(gold, pred) == pytest.approx(0.0)
    # layers 1.0 * swap 0.5 -> 0.2; WHEREs match by name -> 0.3; relation on the wrong side -> 0
    assert FELNCompare.partial(gold, pred) == pytest.approx(0.5)


def test_partial_grades_where() -> None:
    gold = FELN(layers=["Master"], where=["t = 13 AND floors > 2"], relations=[])
    dropped = FELN(layers=["Master"], where=["floors > 2"], relations=[])
    garbage = FELN(layers=["Master"], where=["name LIKE '%x%'"], relations=[])
    assert FELNCompare.structural(gold, dropped) == FELNCompare.structural(gold, garbage) == 0.7
    assert FELNCompare.partial(gold, dropped) == pytest.approx(0.4 + 0.3 * 2 / 3 + 0.3)
    assert FELNCompare.partial(gold, garbage) < FELNCompare.partial(gold, dropped) < 1.0


def test_cost_is_ordered_and_bounded() -> None:
    gold = FELN(layers=["Master"], where=["t = 13 AND floors > 2"], relations=[])
    dropped = FELN(layers=["Master"], where=["floors > 2"], relations=[])
    garbage = FELN(layers=["Master"], where=["name LIKE '%x%'"], relations=[])
    assert FELNCompare.cost(gold, None) == 1.0
    assert FELNCompare.cost(gold, gold) == pytest.approx(0.0)
    assert FELNCompare.cost(gold, gold, {1, 2}, {1, 2}) == pytest.approx(0.0)
    assert 0.0 < FELNCompare.cost(gold, dropped) < FELNCompare.cost(gold, garbage) <= 1.0
    # execution dominates: dropped predicate returned a superset (jaccard 0.5)
    with_ids = FELNCompare.cost(gold, dropped, {1, 2}, {1, 2, 3, 4})
    assert with_ids == pytest.approx(1 - (0.7 * 0.5 + 0.3 * FELNCompare.partial(gold, dropped)))
    # both empty: jaccard is blind, fall back to structure
    assert FELNCompare.cost(gold, garbage, set(), set()) == pytest.approx(
        1 - FELNCompare.partial(gold, garbage)
    )
    # empty gold but rows returned: jaccard 0 counts
    assert FELNCompare.cost(gold, gold, set(), {1}) == pytest.approx(0.7)

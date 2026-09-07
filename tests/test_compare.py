"""The compare recommendations: name-align, within/inside, metres, canonical encode."""

from __future__ import annotations

import pytest

from feln import FELN, FELNCompare
from feln.compare import canonical_text


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

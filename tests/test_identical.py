"""WHERE identity under the DuckDB dialect: case-insensitive identifiers, literal casts dropped."""

from __future__ import annotations

import pytest

from feln import identical, normalize_where


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Pipeline_Distance < 250", '"Pipeline_Distance" < CAST(250 AS DOUBLE)'),
        ("status = 13", "status = cast(13 as SMALLINT)"),
        ("d > timestamp '1995-01-01'", "d > CAST('1995-01-01' AS DATE)"),
        ("d > timestamp '1995-01-01'", "d > '1995-01-01'"),
        ("a = 1 AND (b = 2 OR c = 3)", "(a = 1 AND b = 2) OR (a = 1 AND c = 3)"),
        ("a = 1 AND b = 2", "b = 2 AND a = 1"),
    ],
)
def test_equivalent(left: str, right: str) -> None:
    assert identical(left, right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("content = 'GAS'", "content = 'gas'"),  # string literals stay case-sensitive
        ("Female > 200 OR Male > 300", "Female > 200 AND Male > 300"),
        ("status = 2 AND depth > 1000", "depth > 1000"),
        ("a = 1", ""),
    ],
)
def test_different(left: str, right: str) -> None:
    assert not identical(left, right)


def test_normalize_falls_back_on_bad_sql() -> None:
    assert normalize_where("garbage (((") == "garbage ((("
    assert normalize_where("   ") == ""


def test_negative_literal_cast_is_stripped():
    assert identical("discovery_type = cast(-1 as INTEGER)", "discovery_type = -1")
    assert not identical("discovery_type = cast(-1 as INTEGER)", "discovery_type = 1")


def test_normalized_ranges_compare_equal_to_their_source():
    where = "depth BETWEEN 0 AND 1 or distance BETWEEN 0 AND 10"
    normalized = normalize_where(where)
    assert normalize_where(normalized) == normalized
    assert identical(where, normalized)

"""Identifier and WHERE guards."""

from __future__ import annotations

import pytest

from feln.sanitize import sanitize_identifier, sanitize_where_clause


def test_identifier_ok() -> None:
    assert sanitize_identifier("Wells") == "Wells"


def test_identifier_rejects_spaces() -> None:
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        sanitize_identifier("Events by Magnitude")


def test_where_allows_semicolon_inside_literal() -> None:
    assert sanitize_where_clause("notes = 'a;b'") == "notes = 'a;b'"


def test_where_rejects_comment() -> None:
    with pytest.raises(ValueError, match="comment"):
        sanitize_where_clause("depth > 1 -- drop")


@pytest.mark.parametrize(
    "where",
    [
        "NAME IN (SELECT content FROM read_text('/etc/passwd'))",  # subquery + file read
        "depth > 1 UNION SELECT 1",
        "OBJECTID > 0 LIMIT 0",  # parses, but changes the result size
        "OBJECTID > 0 ORDER BY OBJECTID DESC LIMIT 3",
        "status = upper('x')",  # functions are not filters
        "Wells.status = 'X'",  # table-qualified column
        "depth >",  # unparseable
    ],
)
def test_where_rejects_non_filters(where: str) -> None:
    with pytest.raises(ValueError):
        sanitize_where_clause(where)


@pytest.mark.parametrize(
    "where",
    [
        "content_type = cast(17 as SMALLINT) and (field_name = 'KRISTIN' or field_name = 'ÅSGARD')",
        "discovery_type = cast(-1 as INTEGER) and name ILIKE '%35/11-4%'",
        "completion_date >= timestamp '1991-01-01' AND dimension BETWEEN 16.0 AND 42.0",
        "status IN ('P&A', 'SUSPENDED') AND NOT (field_name IS NULL)",
        "\"dimension\" > CAST(20.0 AS DOUBLE PRECISION) AND name NOT LIKE 'A%'",
        "",
    ],
)
def test_where_allows_plain_filters(where: str) -> None:
    assert sanitize_where_clause(where) == where


def test_where_pins_columns() -> None:
    assert sanitize_where_clause("DEPTH > 1", columns=["depth"]) == "DEPTH > 1"
    with pytest.raises(ValueError, match="unknown column"):
        sanitize_where_clause("medium = 'Gas'", columns=["depth"])

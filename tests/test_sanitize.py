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

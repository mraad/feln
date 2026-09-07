"""Logical identity of SQL WHERE fragments via sqlglot."""

from __future__ import annotations

import contextlib

import sqlglot
from sqlglot.optimizer import optimize
from sqlglot.optimizer.normalize import normalize


def normalize_where(where: str) -> str:
    """Return a canonical SQL form of *where*, or the stripped original on failure.

    Empty / whitespace-only clauses become ``""``. ``timestamp `` prefixes that
    ArcGIS-style catalogs emit are stripped before parsing so
    ``col > timestamp '1995-01-01'`` and ``col > '1995-01-01'`` agree.
    """
    where = where.strip()
    if not where:
        return ""
    with contextlib.suppress(Exception):
        parsed = sqlglot.parse_one(where.replace("timestamp ", ""))
        return normalize(optimize(parsed), dnf=False).sql()
    return where


def identical(where1: str, where2: str) -> bool:
    """True if two WHERE fragments are the same string or logically equivalent."""
    if where1 == where2:
        return True
    a, b = where1.strip(), where2.strip()
    if a == b:
        return True
    na, nb = normalize_where(a), normalize_where(b)
    return bool(na) and na == nb

"""Logical identity of SQL WHERE fragments via sqlglot."""

from __future__ import annotations

import contextlib
from functools import lru_cache

import sqlglot
from sqlglot import exp
from sqlglot.optimizer import optimize
from sqlglot.optimizer.normalize import normalize
from sqlglot.optimizer.simplify import simplify

DIALECT = "duckdb"


def _trim_number(lit: exp.Literal) -> exp.Literal:
    # ``1000.0`` and ``1000`` compare equal in DuckDB; only the digits carry meaning.
    # Exponent forms (``1.0e10``) are left alone: trimming would change the value.
    if lit.is_string or "." not in lit.this or "e" in lit.this.lower():
        return lit
    return exp.Literal.number(lit.this.rstrip("0").rstrip(".") or "0")


def _strip_literal_casts(node: exp.Expression) -> exp.Expression:
    # ``cast(2 as SMALLINT)``, ``timestamp '1995-01-01'`` and ``CAST(250 AS DOUBLE)`` all
    # compare like the bare literal in DuckDB; only the literal carries meaning.
    inner = node.this if isinstance(node, exp.Cast) else None
    if isinstance(inner, exp.Neg) and isinstance(inner.this, exp.Literal):
        # ``cast(-1.0 as DOUBLE)`` is Cast(Neg(Literal)); a replaced node's children are not
        # revisited, so trim here to match the bare ``-1.0``.
        return exp.Neg(this=_trim_number(inner.this))
    if isinstance(inner, exp.Literal):
        node = inner
    return _trim_number(node) if isinstance(node, exp.Literal) else node


def parse_where(where: str) -> exp.Expression:
    """DuckDB-dialect AST of *where* with literal casts stripped. Raises on bad SQL."""
    return sqlglot.parse_one(where, read=DIALECT).transform(_strip_literal_casts)


@lru_cache(maxsize=4096)
def normalize_where(where: str, dnf: bool = False) -> str:
    """Return a canonical SQL form of *where*, or the stripped original on failure.

    Empty / whitespace-only clauses become ``""``. Parsed as DuckDB, so identifiers
    are case-insensitive (``Pipeline_Distance`` ≡ ``"pipeline_distance"``) and literal casts
    are dropped (``cast(2 as SMALLINT)`` ≡ ``2``, ``timestamp '…'`` ≡ ``'…'``).
    """
    where = where.strip()
    if not where:
        return ""
    with contextlib.suppress(Exception):
        parsed = optimize(parse_where(where), dialect=DIALECT)
        # Normalization can expand BETWEEN/OR after optimize's final sort.
        return simplify(normalize(parsed, dnf=dnf)).sql(dialect=DIALECT)
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

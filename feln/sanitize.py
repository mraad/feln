"""Guards for identifiers and WHERE fragments interpolated into SQL."""

from __future__ import annotations

import re
from collections.abc import Iterable

import sqlglot
from sqlglot import exp

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# A plain attribute filter: comparisons, AND/OR/NOT, LIKE/ILIKE, IN, BETWEEN, IS [NOT] NULL,
# literals (``cast(2 as SMALLINT)``, ``timestamp '…'``) and columns. No functions, subqueries,
# or clauses after WHERE. Every WHERE in NorthSea's FELN.json and the generator fits this.
_ALLOWED_NODES = (
    exp.And, exp.Or, exp.Not, exp.Paren,
    exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
    exp.Like, exp.ILike, exp.In, exp.Between, exp.Is, exp.Null,
    exp.Literal, exp.Boolean, exp.Neg,
    exp.Column, exp.Identifier,
    exp.Cast, exp.DataType, exp.DataTypeParam,
)  # fmt: skip


def _strip_string_literals(clause: str) -> str:
    """Blank out quoted spans so tokens inside literals are not inspected."""
    result = list(clause)
    i = 0
    length = len(clause)
    while i < length:
        ch = clause[i]
        if ch in ("'", '"'):
            quote = ch
            result[i] = " "
            i += 1
            while i < length:
                if clause[i] == quote:
                    if i + 1 < length and clause[i + 1] == quote:
                        result[i] = " "
                        result[i + 1] = " "
                        i += 2
                    else:
                        result[i] = " "
                        i += 1
                        break
                else:
                    result[i] = " "
                    i += 1
        else:
            i += 1
    return "".join(result)


def sanitize_identifier(name: str) -> str:
    """Allow only ``[A-Za-z_][A-Za-z0-9_]*``."""
    if not name or not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


def sanitize_where_clause(where: str | None, columns: Iterable[str] | None = None) -> str | None:
    """Return *where* if it is a plain attribute filter, else raise ``ValueError``.

    An allowlist over the DuckDB AST (see ``_ALLOWED_NODES``), not a keyword blocklist.
    Columns must be unqualified; with *columns*, they must also be in that set
    (case-insensitive). Blank input passes through unchanged.
    """
    if where is None or not where.strip():
        return where
    unquoted = _strip_string_literals(where)
    if ";" in unquoted:
        raise ValueError(f"WHERE clause contains prohibited semicolon: {where!r}")
    if "--" in unquoted or "/*" in unquoted:
        raise ValueError(f"WHERE clause contains prohibited comment sequence: {where!r}")
    try:
        select = sqlglot.parse_one(f"SELECT 1 FROM t WHERE {where}", read="duckdb")
    except Exception as e:
        raise ValueError(f"unparseable WHERE clause {where!r}: {e}") from e
    # ``x > 0 LIMIT 0`` or ``x > 0 UNION SELECT 1`` parse fine but are not a filter.
    extra = [
        k
        for k, v in select.args.items()
        if v and k not in ("expressions", "from", "from_", "where")
    ]
    if not isinstance(select, exp.Select) or extra:
        raise ValueError(f"WHERE clause adds {extra or type(select).__name__}: {where!r}")
    allowed = {c.lower() for c in columns} if columns is not None else None
    for node in select.args["where"].this.walk():
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"disallowed SQL construct {type(node).__name__} in {where!r}")
        if isinstance(node, exp.Column):
            if node.table:
                raise ValueError(f"table-qualified column {node.sql()!r} in {where!r}")
            if allowed is not None and node.name.lower() not in allowed:
                raise ValueError(f"unknown column {node.name!r} in {where!r}")
    return where


def table_ident(layer_name: str, table_name: str | None = None) -> str:
    """Physical table name for SQL: catalog ``table_name`` or spaces→underscores."""
    raw = table_name or layer_name.replace(" ", "_")
    return sanitize_identifier(raw)

"""Guards for identifiers and WHERE fragments interpolated into SQL."""

from __future__ import annotations

import re

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DANGEROUS_KEYWORDS_RE = re.compile(
    r"\b("
    r"DROP|CREATE|ALTER|TRUNCATE|INSERT|UPDATE|DELETE|MERGE"
    r"|EXEC|EXECUTE|GRANT|REVOKE|ATTACH|DETACH|COPY|EXPORT|IMPORT"
    r"|UNION\s+ALL|UNION\s+SELECT"
    r")\b",
    re.IGNORECASE,
)


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


def sanitize_where_clause(where: str | None) -> str | None:
    """Reject multi-statement, comment, and DDL/DML smuggling outside literals."""
    if where is None:
        return None
    unquoted = _strip_string_literals(where)
    if ";" in unquoted:
        raise ValueError(f"WHERE clause contains prohibited semicolon: {where!r}")
    if "--" in unquoted or "/*" in unquoted:
        raise ValueError(f"WHERE clause contains prohibited comment sequence: {where!r}")
    if _DANGEROUS_KEYWORDS_RE.search(unquoted):
        raise ValueError(f"WHERE clause contains prohibited keyword: {where!r}")
    return where


def table_ident(layer_name: str, table_name: str | None = None) -> str:
    """Physical table name for SQL: catalog ``table_name`` or spaces→underscores."""
    raw = table_name or layer_name.replace(" ", "_")
    return sanitize_identifier(raw)

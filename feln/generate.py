"""Grammar sampler: Layers.json catalog → templated NL + FELN meta."""

from __future__ import annotations

import json
import random
import re
from collections.abc import Iterable

from layers_json.layers import Column, Layer, Layers

from .identical import normalize_where
from .model import FELN

INT_TYPES = {"SmallInteger": "SMALLINT", "Integer": "INTEGER", "BigInteger": "BIGINT"}
DATE_TYPES = {"Date", "DateOnly", "DateTime"}
DISTANCES = [1, 2, 3, 5, 10, 15, 20, 25, 30, 50]
UNITS = [("kilometers", 6), ("meters", 2), ("miles", 2), ("feet", 1)]
SHOW = ["Show", "Show me", "Show me all", "Find", "Find all", "List", "List all", "Locate"]
RELATIONS = {
    ("Point", "Polygon"): ["within"],
    ("Polygon", "Point"): ["contains"],
    ("Polyline", "Polygon"): ["intersects"],
    ("Polygon", "Polyline"): ["intersects"],
    ("Polygon", "Polygon"): ["within", "contains", "intersects"],
    ("Point", "Polyline"): [],
    ("Polyline", "Point"): [],
    ("Point", "Point"): [],
    ("Polyline", "Polyline"): ["intersects"],
}
SPATIAL = {"Point", "Polyline", "Polygon", "Multipoint"}


def _q(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _coded_value(col: Column, code: str) -> str:
    return f"cast({code} as {INT_TYPES[col.dtype]})" if col.dtype in INT_TYPES else _q(code)


def _sampleable(col: Column) -> bool:
    return bool(col.keyval or col.values) or col.dtype in DATE_TYPES or col.dtype == "Double"


def _like_operator(col: Column) -> str | None:
    hints = " ".join(col.hints).lower()
    if "never" in hints:
        return None
    if re.search(r"\bilike\b", hints):
        return "ILIKE"
    return "LIKE" if re.search(r"\blike\b", hints) else None


def _string_value(col: Column, value: str) -> str:
    hints = " ".join(col.hints).lower()
    if "uppercase the compared values" in hints:
        return value.upper()
    if "lowercase the compared values" in hints:
        return value.lower()
    return value


def _boolean_text(col: Column, value: str, fallback: str) -> str:
    """Read an optional, catalog-owned natural-language description of a flag."""
    prefix = f"Text for value {value}: "
    return next((h[len(prefix) :].rstrip(".") for h in col.hints if h.startswith(prefix)), fallback)


def _predicate_text(text: str) -> str:
    if text.startswith("without "):
        return f"the feature has no {text[8:]}"
    if text.startswith("with "):
        return f"the feature has {text[5:]}"
    if text.startswith("that are "):
        return f"the feature is {text[9:]}"
    return text


def _qualified(label: str, condition_text: str) -> str:
    if not condition_text:
        return label
    link = " " if condition_text.startswith(("with", "that ")) else " where "
    return label + link + condition_text


def condition(rng: random.Random, col: Column) -> tuple[str, str]:
    """One (NL fragment, SQL fragment) for *col*."""
    alias = col.alias or col.name.replace("_", " ")
    if col.keyval:
        code, label = rng.choice(list(col.keyval.items()))
        sql_val = _coded_value(col, code)
        if rng.random() < 0.15:
            return f"{alias} is not {label}", f"{col.name} <> {sql_val}"
        return f"{alias} is {label}", f"{col.name} = {sql_val}"
    if col.dtype in INT_TYPES and col.values and set(col.values) <= {"0", "1"}:
        flag = rng.choice([1, 1, 0])
        nl = _boolean_text(col, str(flag), f"with {alias}" if flag else f"without {alias}")
        return nl, f"{col.name} = cast({flag} as {INT_TYPES[col.dtype]})"
    if col.dtype == "Double" or col.dtype in INT_TYPES:
        numeric = float if col.dtype == "Double" else int
        sql_type = "DOUBLE PRECISION" if col.dtype == "Double" else INT_TYPES[col.dtype]
        pool = [numeric(v) for v in col.values] or [10, 20, 50, 100]
        unit = f" {col.utype}" if col.utype else ""
        op = rng.choices(["gt", "lt", "ge", "le", "eq", "between"], [4, 3, 2, 2, 1, 2])[0]
        if op == "between" and len(set(pool)) < 2:
            op = "gt"
        if op == "between":
            left, right = sorted(rng.sample(sorted(set(pool)), 2))
            return (
                f"{alias} is between {left} and {right}{unit}, inclusive",
                f"{col.name} BETWEEN cast({left} as {sql_type}) AND cast({right} as {sql_type})",
            )
        value = rng.choice(pool)
        word, sym = {
            "gt": ("more than", ">"),
            "lt": (rng.choice(["less than", "under"]), "<"),
            "ge": ("at least", ">="),
            "le": (rng.choice(["at most", "no more than"]), "<="),
            "eq": ("equal to", "="),
        }[op]
        return (
            f"{alias} is {word} {value}{unit}",
            f"{col.name} {sym} cast({value} as {sql_type})",
        )
    if col.dtype in DATE_TYPES:
        years = sorted({int(v[:4]) for v in col.values if v[:4].isdigit()})
        year = rng.choice(years) if years else rng.randint(1970, 2020)
        op = rng.choices(
            ["after", "before", "in", "since", "through", "between"], [4, 3, 2, 2, 1, 2]
        )[0]
        ts = "timestamp '{}-01-01'".format
        if op == "between":
            other = rng.choice(years) if years else rng.randint(1970, 2020)
            lo, hi = sorted((year, other if other != year else year + 1))
            return (
                f"{alias} between {lo} and {hi}",
                f"{col.name} >= {ts(lo)} AND {col.name} < {ts(hi + 1)}",
            )
        text, sql = {
            "after": (f"after {year}", f">= {ts(year + 1)}"),
            "since": (f"since {year}", f">= {ts(year)}"),
            "before": (f"before {year}", f"< {ts(year)}"),
            "through": (f"through {year}", f"< {ts(year + 1)}"),
            "in": (f"in {year}", f">= {ts(year)} AND {col.name} < {ts(year + 1)}"),
        }[op]
        return f"{alias} {text}", f"{col.name} {sql}"
    if (operator := _like_operator(col)) and col.values:
        value = _string_value(col, rng.choice(col.values))
        tokens = [t.strip(",()") for t in value.split() if len(t.strip(",()")) >= 2] or [value]
        frag = rng.choice(tokens)
        kind = rng.choices(["contains", "starts", "ends"], [6, 2, 2])[0]
        frag = tokens[0] if kind == "starts" else tokens[-1] if kind == "ends" else frag
        escaped = frag.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        pattern = (
            escaped + "%"
            if kind == "starts"
            else "%" + escaped
            if kind == "ends"
            else "%" + escaped + "%"
        )
        suffix = " ESCAPE '!'" if escaped != frag else ""
        word = {"starts": "starts with", "ends": "ends with", "contains": "contains"}[kind]
        return f"{alias} {word} {_q(frag)}", f"{col.name} {operator} {_q(pattern)}{suffix}"
    if col.values and set(col.values) <= {"YES", "NO"}:
        yes = rng.random() < 0.7
        value = "YES" if yes else "NO"
        return (
            _boolean_text(col, value, f"{alias} is {value.lower()}"),
            f"{col.name} = {_q(value)}",
        )
    roll = rng.random()
    if roll < 0.08:
        return f"{alias} is blank", f"{col.name} = ''"
    if roll < 0.14:
        return f"{alias} is not blank", f"{col.name} <> ''"
    if roll < 0.26 and len(col.values) >= 2:
        left, right = rng.sample(col.values, 2)
        return (
            f"{alias} is either {_q(left)} or {_q(right)}",
            f"{col.name} = {_q(_string_value(col, left))} or {col.name} = {_q(_string_value(col, right))}",
        )
    value = rng.choice(col.values or ["x"])
    if roll < 0.36:
        return f"{alias} is not {_q(value)}", f"{col.name} <> {_q(_string_value(col, value))}"
    return f"{alias} is {_q(value)}", f"{col.name} = {_q(_string_value(col, value))}"


def where_clause(
    rng: random.Random, layer: Layer, n_conditions: int, *, exclude: str = ""
) -> tuple[str, str]:
    cols = [c for c in layer.columns if c.name.casefold() != exclude.casefold() and _sampleable(c)]
    if not cols or n_conditions <= 0:
        return "", ""
    n_conditions = min(n_conditions, len(cols), 2)
    parts = [condition(rng, c) for c in rng.sample(cols, n_conditions)]
    if len(parts) == 1:
        return parts[0]
    (nl1, sql1), (nl2, sql2) = parts
    nl1, nl2 = _predicate_text(nl1), _predicate_text(nl2)
    if rng.random() < 0.2:
        return (
            f"either ({nl1}) or ({nl2})",
            f"({sql1}) or ({sql2})",
        )
    return f"({nl1}) and ({nl2})", f"({sql1}) and ({sql2})"


def layer_phrase(
    rng: random.Random,
    layer: Layer,
    n_conditions: int,
    *,
    alias_suffix: bool = False,
    layer_only: float = 0.0,
    ignore_subtype: bool = False,
) -> tuple[str, str, str]:
    """A layer/subtype noun phrase, extra condition text, and its complete filter.

    Subtype labels are lowercased; *alias_suffix* appends the layer alias
    (``oil discoveries``, ``dry wells``) so labels shared across layers stay
    unambiguous. Leave it off when the alias is not a noun (for example ``all``).
    *layer_only* is the share of subtyped layers phrased by alias alone
    (``Show wells``) with no subtype filter; the subtype column is then an
    ordinary condition candidate (``wells where content type is DRY``).
    *ignore_subtype* uses the alias and excludes the subtype column entirely.
    """
    if not 0 <= layer_only <= 1:
        raise ValueError(f"layer_only must be within [0, 1], got {layer_only}")
    subtype = next(
        (
            c
            for c in layer.columns
            if c.name.casefold() == (layer.subtype or "").casefold() and c.keyval
        ),
        None,
    )
    alias = (layer.alias or layer.name).lower()
    if ignore_subtype:
        nl, sql = where_clause(rng, layer, n_conditions, exclude=layer.subtype or "")
        return alias, nl, sql
    if subtype is None or (layer_only and rng.random() < layer_only):
        nl, sql = where_clause(rng, layer, n_conditions)
        return alias, nl, sql
    code, label = rng.choice(list(subtype.keyval.items()))
    noun = label.lower()
    if alias_suffix and not noun.endswith(alias):
        noun = (
            f"{alias} classified as {_q(noun)}"
            if " " in noun or "/" in noun or noun == "shows"
            else f"{noun} {alias}"
        )
    nl, sql = where_clause(rng, layer, max(0, n_conditions - 1), exclude=subtype.name)
    predicate = f"{subtype.name} = {_coded_value(subtype, code)}"
    # OR in an attribute filter must never allow another subtype through.
    return noun, nl, f"{predicate} and ({sql})" if sql else predicate


def relation(rng: random.Random, primary: Layer, secondary: Layer) -> tuple[str, str]:
    kinds = list(RELATIONS.get((primary.stype, secondary.stype), [])) + [
        "withinDistance",
        "notWithinDistance",
    ]
    weights = {"withinDistance": 4, "notWithinDistance": 1.5}
    kind = rng.choices(kinds, [weights.get(k, 4) for k in kinds])[0]
    if kind == "within":
        return rng.choice(["located inside", "within", "that are in"]), "within"
    if kind == "contains":
        return rng.choice(["that contain", "containing", "that have"]), "contains"
    if kind == "intersects":
        return rng.choice(
            ["that cross", "that intersect", "crossed by", "that overlap"]
        ), "intersects"
    unit = rng.choices([u for u, _ in UNITS], [w for _, w in UNITS])[0]
    distance = rng.choice(DISTANCES if unit != "meters" else [500, 1000, 2000, 5000])
    if rng.random() < 0.1:
        distance = distance + 0.5
    text_unit = ("foot" if unit == "feet" else unit.removesuffix("s")) if distance == 1 else unit
    if kind == "withinDistance":
        phrase = rng.choice(["within", "no more than"])
        tail = "of" if phrase == "within" else "from"
        return f"{phrase} {distance:g} {text_unit} {tail}", f"withinDistance {distance:g} {unit}"
    return (
        f"more than {distance:g} {text_unit} away from any",
        f"notWithinDistance {distance:g} {unit}",
    )


def sample(
    rng: random.Random,
    layers: list[Layer],
    *,
    alias_suffix: bool = False,
    layer_only: float = 0.0,
    ignore_subtype: bool = False,
    normalize: bool = False,
) -> tuple[str, FELN]:
    """One templated request and a valid FELN drawn from *layers*.

    *normalize* writes each WHERE in the canonical ``normalize_where`` form that
    ``identical()`` compares by: quoted lower-case identifiers, sorted conjuncts,
    bare literals (``"content_type" = 2``, not ``content_type = cast(2 as SMALLINT)``).
    """
    spatial = [layer for layer in layers if layer.stype in SPATIAL]
    if not layers:
        raise ValueError("catalog has no layers")
    max_n = min(3, len(spatial)) if spatial else 1
    n = 1 if max_n == 1 else rng.choices(list(range(1, max_n + 1)), [4, 4, 2][:max_n])[0]
    chosen = rng.sample(list(layers) if n == 1 else spatial, n)
    n_conds = [rng.choices([0, 1, 2], [1, 5, 3])[0]] + [
        rng.choices([0, 1, 2], [4, 5, 1])[0] for _ in chosen[1:]
    ]
    if n == 1 and n_conds[0] == 0:
        n_conds[0] = 1
    labels, nls, sqls = zip(
        *(
            layer_phrase(
                rng,
                layer,
                k,
                alias_suffix=alias_suffix,
                layer_only=layer_only,
                ignore_subtype=ignore_subtype,
            )
            for layer, k in zip(chosen, n_conds, strict=True)
        )
    )
    text = [f"{rng.choice(SHOW)} {_qualified(labels[0], nls[0])}."]
    rels: list[str] = []
    for i, sec in enumerate(chosen[1:], start=1):
        rel_nl, rel = relation(rng, chosen[0], sec)
        rels.append(rel)
        secondary = _qualified(labels[i], nls[i])
        if rel.startswith("notWithinDistance"):
            _, distance, unit = rel.split()
            text_unit = (
                ("foot" if unit == "feet" else unit.removesuffix("s"))
                if float(distance) == 1
                else unit
            )
            phrase = f"be more than {distance} {text_unit} from all matching {secondary}"
        elif rel.startswith("withinDistance"):
            phrase = f"be {rel_nl} {secondary}"
        else:
            verb = {"within": "lie within", "contains": "contain", "intersects": "intersect"}[rel]
            phrase = f"{verb} one or more {secondary}"
        primary = chosen[0].alias or chosen[0].name
        text.append(f"The returned {primary} must {phrase}.")
    meta = FELN(
        layers=[layer.name for layer in chosen],
        where=[normalize_where(s) for s in sqls] if normalize else list(sqls),
        relations=rels,
    )
    return " ".join(t for t in text if t), meta


def generate(
    catalog: Layers,
    n: int,
    *,
    seed: int = 0,
    max_attempts: int | None = None,
    alias_suffix: bool = False,
    layer_only: float = 0.0,
    ignore_subtype: bool = False,
    normalize: bool = False,
) -> list[dict]:
    """Draw *n* unique FELN metas. Each record is ``{"text", "meta"}``."""
    rng = random.Random(seed)
    layers = list(catalog.layers)
    if not layers:
        raise ValueError("catalog has no layers")
    budget = max_attempts if max_attempts is not None else max(n * 40, 40)
    seen: set[str] = set()
    records: list[dict] = []
    attempts = 0
    while len(records) < n and attempts < budget:
        attempts += 1
        text, meta = sample(
            rng,
            layers,
            alias_suffix=alias_suffix,
            layer_only=layer_only,
            ignore_subtype=ignore_subtype,
            normalize=normalize,
        )
        key = json.dumps(meta.model_dump(), sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        records.append({"text": text, "meta": meta.model_dump()})
    return records


def records_to_jsonl(records: Iterable[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)

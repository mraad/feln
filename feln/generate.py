"""Grammar sampler: Layers.json catalog → templated NL + FELN meta."""

from __future__ import annotations

import json
import random
from collections.abc import Iterable

from layers_json.layers import Column, Layer, Layers

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


def _sampleable(col: Column) -> bool:
    return bool(col.keyval or col.values) or col.dtype in DATE_TYPES or col.dtype == "Double"


def _like_column(col: Column) -> bool:
    hints = " ".join(col.hints).lower()
    return "like" in hints and "never" not in hints


def condition(rng: random.Random, col: Column) -> tuple[str, str]:
    """One (NL fragment, SQL fragment) for *col*."""
    alias = col.alias or col.name.replace("_", " ")
    if col.keyval:
        code, label = rng.choice(list(col.keyval.items()))
        sql_val = f"cast({code} as {INT_TYPES[col.dtype]})" if col.dtype in INT_TYPES else _q(code)
        if rng.random() < 0.15:
            return f"{alias} is not {label}", f"{col.name} <> {sql_val}"
        return f"{alias} is {label}", f"{col.name} = {sql_val}"
    if col.dtype == "Double":
        pool = [float(v) for v in col.values] or [10.0, 20.0, 50.0, 100.0]
        unit = f" {col.utype}" if col.utype else ""
        op = rng.choices(["gt", "lt", "ge", "le", "eq", "between"], [4, 3, 2, 2, 1, 2])[0]
        if op == "between" and len(set(pool)) < 2:
            op = "gt"
        if op == "between":
            left, right = sorted(rng.sample(list(set(pool)), 2))
            return (
                f"{alias} between {left:g} and {right:g}{unit}",
                f"{col.name} BETWEEN {float(left)} AND {float(right)}",
            )
        value = rng.choice(pool)
        word, sym = {
            "gt": ("more than", ">"),
            "lt": ("less than", "<"),
            "ge": ("at least", ">="),
            "le": ("at most", "<="),
            "eq": ("equal to", "="),
        }[op]
        return (
            f"{alias} {word} {value:g}{unit}",
            f"{col.name} {sym} cast({float(value)} as DOUBLE PRECISION)",
        )
    if col.dtype in INT_TYPES:
        if set(col.values) <= {"0", "1"}:
            flag = rng.choice([1, 1, 0])
            nl = f"with {alias}" if flag else f"without {alias}"
            return nl, f"{col.name} = cast({flag} as {INT_TYPES[col.dtype]})"
        value = rng.choice(col.values or ["1"])
        return f"{alias} is {value}", f"{col.name} = cast({value} as {INT_TYPES[col.dtype]})"
    if col.dtype in DATE_TYPES:
        year = rng.randint(1970, 2020)
        op = rng.choices(["after", "before", "in"], [5, 3, 2])[0]
        if op == "after":
            return f"{alias} after {year}", f"{col.name} > timestamp '{year}-01-01'"
        if op == "before":
            return f"{alias} before {year}", f"{col.name} < timestamp '{year}-01-01'"
        return (
            f"{alias} in {year}",
            f"{col.name} BETWEEN timestamp '{year}-01-01' AND timestamp '{year}-12-31'",
        )
    if _like_column(col) and col.values:
        value = rng.choice(col.values)
        tokens = [t.strip(",()") for t in value.split() if len(t.strip(",()")) >= 2] or [value]
        frag = rng.choice(tokens)
        kind = rng.choices(["contains", "starts", "ends"], [6, 2, 2])[0]
        if kind == "starts":
            frag = tokens[0]
            return f"{alias} starts with {frag}", f"{col.name} LIKE {_q(frag + '%')}"
        if kind == "ends":
            frag = tokens[-1]
            return f"{alias} ends with {frag}", f"{col.name} LIKE {_q('%' + frag)}"
        return f"{alias} contains {frag}", f"{col.name} LIKE {_q('%' + frag + '%')}"
    if set(col.values) <= {"YES", "NO"}:
        yes = rng.random() < 0.7
        return (
            (f"with {alias}" if yes else f"without {alias}"),
            f"{col.name} = {_q('YES' if yes else 'NO')}",
        )
    roll = rng.random()
    if roll < 0.08:
        return f"{alias} is blank", f"{col.name} = ''"
    if roll < 0.14:
        return f"with a {alias}", f"{col.name} <> ''"
    if roll < 0.26 and len(col.values) >= 2:
        left, right = rng.sample(col.values, 2)
        return (
            f"{alias} is {left.lower()} or {right.lower()}",
            f"{col.name} = {_q(left)} or {col.name} = {_q(right)}",
        )
    value = rng.choice(col.values or ["x"])
    if roll < 0.36:
        return f"{alias} is not {value.lower()}", f"{col.name} <> {_q(value)}"
    return f"{alias} is {value.lower()}", f"{col.name} = {_q(value)}"


def where_clause(rng: random.Random, layer: Layer, n_conditions: int) -> tuple[str, str]:
    cols = [c for c in layer.columns if _sampleable(c)]
    if not cols or n_conditions <= 0:
        return "", ""
    n_conditions = min(n_conditions, len(cols))
    parts = [condition(rng, c) for c in rng.sample(cols, n_conditions)]
    if len(parts) == 1:
        return parts[0]
    (nl1, sql1), (nl2, sql2) = parts
    if rng.random() < 0.2:
        return (
            f"{nl1} or {nl2}",
            f"({sql1}) or ({sql2})" if " or " in sql1 + sql2 else f"{sql1} or {sql2}",
        )
    sql1, sql2 = (f"({s})" if " or " in s else s for s in (sql1, sql2))
    return f"{nl1} and {nl2}", f"{sql1} and {sql2}"


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
    if kind == "withinDistance":
        return f"within {distance:g} {unit} of", f"withinDistance {distance:g} {unit}"
    return (
        f"more than {distance:g} {unit} away from any",
        f"notWithinDistance {distance:g} {unit}",
    )


def sample(rng: random.Random, layers: list[Layer]) -> tuple[str, FELN]:
    """One templated sentence and a valid FELN drawn from *layers*."""
    spatial = [layer for layer in layers if layer.stype in SPATIAL]
    pool = spatial or list(layers)
    max_n = min(3, len(pool))
    n = 1 if max_n == 1 else rng.choices(list(range(1, max_n + 1)), [4, 4, 2][:max_n])[0]
    chosen = rng.sample(pool, n)
    n_conds = [rng.choices([0, 1, 2], [1, 5, 3])[0]] + [
        rng.choices([0, 1, 2], [4, 5, 1])[0] for _ in chosen[1:]
    ]
    if n == 1 and n_conds[0] == 0:
        n_conds[0] = 1
    nls, sqls = zip(
        *(where_clause(rng, layer, k) for layer, k in zip(chosen, n_conds, strict=True))
    )
    text = [rng.choice(SHOW), chosen[0].alias or chosen[0].name]
    if nls[0]:
        text += [
            "" if nls[0].startswith("with") else rng.choice(["where", "with", "whose"]),
            nls[0],
        ]
    rels: list[str] = []
    for i, sec in enumerate(chosen[1:], start=1):
        rel_nl, rel = relation(rng, chosen[0], sec)
        rels.append(rel)
        text += [
            "and" if i > 1 else "that are" if "Distance" in rel else "",
            rel_nl,
            sec.alias or sec.name,
        ]
        if nls[i]:
            text += ["" if nls[i].startswith("with") else rng.choice(["where", "with"]), nls[i]]
    meta = FELN(
        layers=[layer.name for layer in chosen],
        where=list(sqls),
        relations=rels,
    )
    return " ".join(t for t in text if t), meta


def generate(
    catalog: Layers,
    n: int,
    *,
    seed: int = 0,
    max_attempts: int | None = None,
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
        text, meta = sample(rng, layers)
        key = json.dumps(meta.model_dump(), sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        records.append({"text": text, "meta": meta.model_dump()})
    return records


def records_to_jsonl(records: Iterable[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)

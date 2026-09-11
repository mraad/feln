# feln

Standalone library and CLI for **FELN** — Find Existing Location with N layers.
It sits on a [`layers-json`](https://github.com/mraad/layers-json) catalog
(`Layers.json`) and does not import `gait`.

A FELN is three parallel lists:

```json
{
  "layers": ["Wells", "Pipelines"],
  "where": ["status = 'SUSPENDED'", "medium = 'Oil'"],
  "relations": ["withinDistance 5 kilometers"]
}
```

`layers[0]` is the primary layer (the features returned). Each
`relations[i]` is the spatial relationship from that primary to
`layers[i+1]`. An empty relation means the join is already captured by a
pre-computed column (for example `dist_*`) in a WHERE clause.

## Install

```bash
uv sync --extra dev
```

`layers-json[model]` is pinned to a commit of the private
[layers-json](https://github.com/mraad/layers-json) repo, so installing needs
GitHub credentials (`gh auth login`, or a token in CI). Its `model` extra is the
`Column` / `Layer` / `Layers` catalog model this package imports and re-exports.
Runtime needs pydantic, sqlglot, and numpy; GDAL is not required.

Working on both repos at once? Shadow the pin with the local checkout:

```bash
uv pip install -e ../layers-json      # edits in ../layers-json take effect immediately
uv run --no-sync pytest -q            # --no-sync, or plain uv run puts the pin back
```

`uv run` re-syncs the environment first, which silently reinstalls the pinned
commit — so use `uv run --no-sync` (or `.venv/bin/python`) while the override is
in place, and a plain `uv sync` to drop it. When a layers-json change is needed
for real, push it and bump the `rev` in `pyproject.toml`.

## CLI

```bash
# Sample synthetic FELN metas from a catalog (jsonl: text + meta).
uv run feln generate path/to/Layers.json -n 20 -o metas.jsonl

# DuckDB spatial SQL for one FELN against that catalog.
uv run feln sql path/to/Layers.json query.json

# Structural similarity (0..1) between two FELN JSON files.
uv run feln compare a.json b.json
```

`generate` writes one JSON object per line:

```json
{"text": "Show wells that are within 5 kilometers of pipelines", "meta": {"layers": ["Wells", "Pipelines"], "where": ["", ""], "relations": ["withinDistance 5 kilometers"]}}
```

Pass `--sql` to add a DuckDB SQL string on each record.

When a layer has subtype labels, they always supply the feature name in text,
for both primary and spatial filter layers. For example, a subtype label `Hospitals` produces
`Show hospitals` with `kind = cast(1 as INTEGER)` while `meta.layers` keeps the catalog layer name.
Labels are lowercased in text; `--alias-suffix` (`generate(..., alias_suffix=True)`) appends the
layer alias — `Show oil discoveries`, `List all dry wells` — which disambiguates labels shared
across layers. Leave it off when the alias is not a noun (`master`). `--layer-only 0.25`
(`layer_only=0.25`) phrases that share of subtyped layers by alias alone — `Show wells`,
`List pipelines` — with no subtype filter, and the subtype column then competes as an
ordinary condition (`wells where content type is DRY`). Additional conditions are ANDed
with the subtype filter; no pluralization or dataset-specific filters are added. Missing
subtype metadata falls back to the layer alias and ordinary field conditions.

## Library

```python
from feln import FELN, FELNCompare, FELNToDuckDB, Layers, parse_relation

catalog = Layers.load("Layers.json")
query = FELN(
    layers=["Wells", "Pipelines"],
    where=["status = 'SUSPENDED'", ""],
    relations=["withinDistance 5 miles"],
)

score = FELNCompare.structural(query, other)
sql = FELNToDuckDB()(
    [catalog.find_layer(n) for n in query.layers],
    query.where,
    [parse_relation(r) for r in query.relations],
)
```

Structural compare pins the primary layer, matches secondaries by name
(order-independent), treats `within`/`inside` as the same kind, and scores
distance relations in meters so `5 miles` and `8.05 kilometers` can agree.
`FELNCompare.partial` is the graded version — layers matched at any position
(a swapped primary keeps half credit), WHERE scored per predicate (a dropped
conjunct ≈ 0.67, `OR` written as `AND` 0.75) — and `FELNCompare.cost(gold, pred,
gold_ids, pred_ids)` turns it into a minimisable `[0, 1]` cost, blended 70/30 with
OBJECTID jaccard when execution results are supplied. `identical()` parses as
DuckDB, so identifiers are case-insensitive and `cast(2 as SMALLINT)` equals `2`.
Semantic compare encodes one canonical string per FELN (sqlglot-normalized
WHERE, parsed relations, secondaries sorted) and returns cosine similarity.

## Tests

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

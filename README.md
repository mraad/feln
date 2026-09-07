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

From a checkout, next to `layers-json`:

```bash
uv sync --extra dev
```

`layers-json[model]` is a path dependency (`../layers-json`); its `model`
extra is the `Column` / `Layer` / `Layers` catalog model this package imports
and re-exports. Runtime needs pydantic, sqlglot, and numpy; GDAL is not
required.

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
Semantic compare encodes one canonical string per FELN (sqlglot-normalized
WHERE, parsed relations, secondaries sorted) and returns cosine similarity.

## Tests

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

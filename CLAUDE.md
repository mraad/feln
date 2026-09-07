# CLAUDE.md

`README.md` covers what this produces and how to run it. This file is the
other half: what breaks when you edit things.

## Commands

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run feln generate tests/fixtures/layers.json -n 5
uv run feln sql tests/fixtures/layers.json /tmp/q.json
uv run feln compare a.json b.json
```

Runtime dependencies are pydantic, sqlglot, numpy, and a path dependency on
the sibling `../layers-json` checkout. GDAL is **not** required: this project
reads `Layers.json`, it does not author one.

## Architecture

```
Layers.json ──feln.layers.Layers──> catalog
                 │
                 ├── generate.py ──> synthetic {text, meta} jsonl
                 ├── sql.py      ──> DuckDB spatial SQL
                 └── compare.py  ──> structural / semantic score
```

`layers-json` is the catalog **producer**. This package is a **consumer**: it
parses the JSON `Column` / `Layer` / `Layers` byte shape that `NanoMap.pyt`
emits (field names and empties included). Do not import toolbox classes at
runtime — `load_toolbox()` is a test-only round-trip so the parser cannot
drift from the producer. A new field on the toolbox `Layer.to_dict()` is
ignored here until `feln.layers.Layer` grows it; `table_name` is already
modelled because SQL uses it.

FELN list lengths are the invariant: `len(where) == len(layers)` and
`len(relations) == len(layers) - 1`. `layers[0]` is primary;
`relations[i]` applies to `layers[i+1]`. Changing that breaks SQL, compare,
and generate together.

## Compare (do not regress)

`FELNCompare.structural` is **not** positional `zip`. It pins the primary
layer and greedily matches secondaries by case-insensitive stripped name, so
a permutation of the same filters scores ~1. `within` and `inside` are the
same kind (DuckDB already emits `ST_Within` for both). Distance relations
convert to meters before scoring; unknown units fall back to kind-only
partial credit.

`FELNCompare.semantic` encodes **one canonical string per FELN**, not a
mean-pool of raw parts. Canonical form sorts secondaries, runs WHERE through
the same sqlglot normalize path as `identical()`, and prints relations as
`kind [meters]`. Two `encode_document` calls are collapsed to one batch
(unique strings). Do not reintroduce the `"empty"` sentinel or a
`max_n == 0` branch — `FELN` cannot have zero layers.

Weights stay 0.4 layers / 0.3 WHERE / 0.3 relations.

## SQL

`FELNToDuckDB` is the only dialect. No-op relations (`kind == "none"`) skip
the spatial join; a no-op plus a non-empty secondary WHERE is an error
(the filter would be silently dropped). `notWithinDistance` is `NOT EXISTS`,
never `NOT ST_DWithin` inside an inner join. Distances go through
`feln.units.to_meters`. Table names come from `Layer.table_name` when set,
else `name` with spaces turned into underscores, then
`sanitize_identifier`.

## Generate

`generate.sample` is a grammar over the catalog: it does **not** execute SQL
and does not need DuckDB. NorthSea-specific skip lists do not belong here.
If you add a new relation kind, teach `model.parse_relation`, `compare`,
`sql._on_clause`, and `generate.relation` in the same change.

## Testing notes

- `tests/fixtures/layers.json` is a hand-written catalog in the NanoMap
  byte shape. Prefer it over a live ArcGIS project.
- `test_layers.py` round-trips a toolbox `Layers.dump` through `Layers.load`
  so a producer field change shows up here. That test imports
  `layers_json.layers_from_aprx.load_toolbox` (no GDAL).
- Compare tests lock exact scores for permutation, `within`/`inside`, and
  mile/kilometre equivalence. Do not widen them to `0 < score < 1`.

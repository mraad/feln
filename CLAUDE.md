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

Runtime dependencies are pydantic, sqlglot, numpy, and `layers-json[model]`
pinned to a commit of the public [layers-json](https://github.com/mraad/layers-json)
repo — the `model` extra is the catalog model this package imports. No credentials
are needed; the pin means a local edit in `../layers-json` is invisible here until it is pushed
and the `rev` bumped. To work across both, `uv pip install -e ../layers-json`
and then run with `uv run --no-sync` — a plain `uv run` re-syncs and silently
restores the pin. GDAL is **not** required: this project reads `Layers.json`, it
does not author one.

## Architecture

```text
Layers.json ──layers_json.layers.Layers──> catalog
                 │
                 ├── generate.py ──> synthetic {text, meta} jsonl
                 ├── sql.py      ──> DuckDB spatial SQL
                 └── compare.py  ──> structural / semantic score
```

`layers-json` is the catalog **producer** *and* owns the consumer-side model.
`Column` / `Layer` / `Layers` live in `layers_json.layers` (the `model` extra)
and are re-exported from `feln` for convenience — there is no `feln/layers.py`,
and re-adding one puts the `Layers.pyt` byte shape back in two places. A new
field on the toolbox `Layer.to_dict()` is ignored until `layers_json.layers`
grows it, and `layers-json`'s own `tests/test_layers_model.py` is the round-trip
that catches the drift. Do not import toolbox classes at runtime: they are
producer-side plain dicts reachable only via `load_toolbox()` with arcpy stubbed.
`table_name` is already modelled because SQL uses it.

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

`FELNCompare.partial` / `cost` are the optimisation-side scores and keep the
same weights. `partial` differs from `structural` in two ways only: layers
align by name at *any* position (a swapped primary scores `_SWAP_PENALTY`, not
0) and WHERE credit is `where_credit` — DNF atoms `(columns, op, literals)`
matched best-pair-first, F1 of atom credit (column 0.5 / op 0.25 / literal
0.25, numeric literals by relative closeness), times `_SHAPE_PENALTY` when the
OR-group count differs. `cost` is `1 - partial`, or `1 - (0.7 jaccard + 0.3
partial)` when both OBJECTID sets are given, except when both sets are empty
(jaccard is blind there). `pred=None` costs 1. Tests lock these values
(dropped conjunct 2/3, AND↔OR 0.75, swap 0.5); do not loosen them.

`identical()` / `normalize_where()` parse with `read="duckdb"` and strip
`Cast(Literal)` before normalising: DuckDB identifiers are case-insensitive
and `cast(2 as SMALLINT)`, `timestamp '…'`, `CAST(250 AS DOUBLE)` all compare
as the bare literal. Without this every quoted or cast column from a compiler
(`"Bank_Distance" < CAST(250 AS DOUBLE)`) scored 0 against `Bank_Distance <
250`. String literals stay case-sensitive, as in DuckDB.

Normalization caches at most 4,096 immutable strings; do not cache mutable ASTs.
Keep the final simplification after normalization: expanding ORs of BETWEEN
ranges can otherwise leave conjuncts in a different order on the second pass.
Graded literal comparison must retain unary minus (`x > -5` is not `x > 5`).

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

`withinDistance` includes equality, so its text uses only "within" or "no more
than", never strict "less than". Table-only catalogs sample one layer per query
to avoid generating spatial relations without geometry.

## Testing notes

- NorthSea is the only named project referenced in this repository. Keep other
  projects' reports and derived artifacts in their respective project folders;
  shared code and regression cases remain catalog-independent.
- Use `$HOME` in shell examples and `~` in descriptive paths; never commit
  personal home-directory names, credentials, or real personal records in fixtures.
- `tests/fixtures/layers.json` is a hand-written catalog in the Layers.pyt
  byte shape. Prefer it over a live ArcGIS project.
- `test_layers.py` covers the fixture contract only. The producer→consumer
  round-trip moved to `layers-json`'s `tests/test_layers_model.py`, which is
  where the model now lives; do not re-add a copy here.
- Compare tests lock exact scores for permutation, `within`/`inside`, and
  mile/kilometre equivalence. Do not widen them to `0 < score < 1`.

# feln

Standalone library and CLI for **FELN** — Find Existing Location with N layers.
It sits on a [`layers-json`](https://github.com/mraad/layers-json) catalog
(`Layers.json`) and does not import `gait`.

Start with the examples below; [Goal](#goal) explains how structured queries
make generation measurable and support different execution engines.

## Examples

These text/target pairs use the small catalog in
[`tests/fixtures/layers.json`](tests/fixtures/layers.json). Field names and coded
values must come from the catalog used for your data. The generator produces
synthetic text/target pairs; it does not parse arbitrary natural language.

Read each example as three parallel lists:

- `layers[0]` is the layer whose features are returned.
- `where[i]` filters `layers[i]`; `""` means no attribute filter.
- `relations[i]` relates the primary layer to `layers[i+1]`.
  With one layer, `relations` is empty. With three layers, it has two entries.

### 1. Filter one layer

**“Find wells deeper than 1,000 meters.”**

```json
{
  "layers": ["Wells"],
  "where": ["DEPTH > 1000"],
  "relations": []
}
```

Only wells are returned. `DEPTH > 1000` excludes wells exactly 1,000 meters
deep. No other layer is involved, so there is no spatial relationship to supply.

### 2. Filter both sides of a distance relationship

**“Find suspended wells within 5 kilometers of oil pipelines.”**

```json
{
  "layers": ["Wells", "Pipelines"],
  "where": ["STATUS = 2", "MEDIUM = 'OIL'"],
  "relations": ["withinDistance 5 kilometers"]
}
```

The fixture maps `STATUS = 2` to suspended wells and stores oil as `OIL`.
The first filter applies to wells; the second applies to pipelines. A well is
returned if at least one matching pipeline is within 5 kilometers, including
exactly 5 kilometers. Pipelines constrain the answer but are not returned.

### 3. Exclude nearby features

**“Find wells more than 500 meters from every pipeline.”**

```json
{
  "layers": ["Wells", "Pipelines"],
  "where": ["", ""],
  "relations": ["notWithinDistance 500 meters"]
}
```

Both attribute filters are empty, so every pipeline is considered.
`notWithinDistance` keeps a well only when no pipeline is within 500 meters.
A well exactly 500 meters from a pipeline is excluded. This checks the absence
of any nearby pipeline; finding one distant pipeline is not sufficient.

### 4. Combine attribute conditions

**“Find active wells named Alpha… with depths from 250 to 1,000 meters.”**

```json
{
  "layers": ["Wells"],
  "where": ["STATUS = 1 AND NAME LIKE 'Alpha%' AND DEPTH BETWEEN 250 AND 1000"],
  "relations": []
}
```

All three conditions must hold for the same well. `STATUS = 1` means active,
`LIKE 'Alpha%'` matches names beginning with `Alpha`, and `BETWEEN` includes
both depth endpoints. Multiple attribute conditions still occupy one `where`
entry because they apply to one layer.

### 5. Select points inside an area

**“Find wells inside County A.”**

```json
{
  "layers": ["Wells", "Counties"],
  "where": ["", "NAME = 'County A'"],
  "relations": ["within"]
}
```

The county-name filter selects the area used to constrain the wells. `within`
is evaluated from each well to that county. With the DuckDB compiler, a point
on the county boundary is not strictly within it. `County A` is a synthetic label
in the synthetic fixture, not a NorthSea catalog assumption.

### 6. Change which features are returned

**“Find counties containing at least one suspended well.”**

```json
{
  "layers": ["Counties", "Wells"],
  "where": ["", "STATUS = 2"],
  "relations": ["contains"]
}
```

Putting `Counties` first makes counties the output. The relationship is now
`contains`, from county to well. Each matching county is returned once even
if it contains several suspended wells; this query does not count wells.

### 7. Apply two spatial constraints to the same primary layer

**“Find active wells inside County A and within 2 kilometers of a gas pipeline.”**

```json
{
  "layers": ["Wells", "Counties", "Pipelines"],
  "where": ["STATUS = 1", "NAME = 'County A'", "MEDIUM = 'GAS'"],
  "relations": ["within", "withinDistance 2 kilometers"]
}
```

Each returned well must satisfy both spatial constraints. `relations[0]`
connects wells to counties; `relations[1]` connects wells to pipelines.
The relationships do not form a county-to-pipeline chain. The gas pipeline
does not itself have to be inside the selected county.

An empty relation string (`""`) is a separate case from an empty `relations`
list: it skips that secondary layer's spatial join when a precomputed column
(such as `dist_*`) already captures the constraint in a WHERE clause. That
secondary layer must also have an empty WHERE, or compilation rejects the query
instead of silently ignoring its filter.

### Generate examples from NorthSea

After [installation](#install), generate 20 text/FELN pairs with normalized
filters and compiled DuckDB SQL:

```bash
uv run feln generate "$HOME/Documents/ArcGIS/Projects/NorthSea/Layers.json" \
  -n 20 --seed 0 --normalize --sql --alias-suffix -o northsea-examples.jsonl
```

`Layers.json` itself is produced by
[`layers-json`](https://github.com/mraad/layers-json); this package consumes
that catalog to generate examples. See [CLI](#cli) for generation options,
SQL compilation, and comparison commands.

## Goal

Use [`layers-json`](https://github.com/mraad/layers-json) to generate the
`Layers.json` catalog from an ArcGIS project and its data sources. The catalog
captures layer names, field aliases, subtypes, coded values, and sample values
that connect the words in a request to the data. FELN consumes that context to
generate text/query examples and compare structured queries. For catalog setup
and generation, see the
[layers-json documentation](https://github.com/mraad/layers-json#create-a-metadata-catalog).

The idea is **text → structured output → measurement and execution**. A natural
language request becomes an explicit selection of layers, SQL predicates, and
spatial relationships. That structure makes the generated answer measurable
against a reference answer, so generation can be evaluated and optimized.

Measure different aspects separately:

- **Exact-match accuracy:** the fraction of predictions matching their reference
  FELN under `FELN.same()` normalization and secondary-order rules.
- **Precision and recall:** compare returned feature IDs with reference IDs
  from the same primary dataset.
  True positives (TP) are shared IDs, false positives (FP) are unexpected IDs,
  and false negatives (FN) are missed IDs. Precision is `TP / (TP + FP)`;
  recall is `TP / (TP + FN)`. For example,
  reference `{1, 2}` and prediction `{2, 3, 4}` give precision `1/3` and recall
  `1/2`. Define empty-set conventions before aggregating these metrics.
- **Graded similarity and cost:** compare layers, normalized SQL WHERE
  predicates, and spatial relations with `FELNCompare.partial`; minimize
  `FELNCompare.cost`, optionally incorporating execution results.

This also supports evaluating a regression model that predicts a numeric
parameter such as a distance: measure numeric error, then compare the resulting
structured query and its selected features. Accuracy, precision, and recall
apply to that query or feature selection; they are not automatic metrics for
an unconstrained continuous prediction. SQL comparison provides a repeatable
structural signal, while execution tests whether queries select the same
features. Normalization is not a proof of SQL equivalence on every database.
The package supplies comparison scores and cost; aggregate accuracy,
precision, and recall are computed by the evaluation pipeline.

The same structure can also be implemented through different execution
mechanisms: DuckDB SQL, ArcPy operations, or Spark with suitable spatial
functions. Each implementation translates the layer filters and relationships
into its engine's operations, preserving types, units, coordinate systems,
and boundary semantics. **This package currently implements DuckDB SQL only**;
ArcPy and Spark are possible backends, not existing integrations. Separating
the structured query from execution lets generation improve against measurable
targets while the execution engine is chosen for the data and workload.

## Install

```bash
uv sync --extra dev
```

`layers-json[model]` is pinned to a commit of the public
[layers-json](https://github.com/mraad/layers-json) repo (no credentials needed).
Its `model` extra is the `Column` / `Layer` / `Layers` catalog model this package
imports and re-exports.
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

Pass `--sql` to add a DuckDB SQL string on each record. `--normalize` writes each
WHERE in the canonical `normalize_where` form `identical()` compares by — quoted
lower-case identifiers, sorted conjuncts, bare literals: `"content_type" = 2 AND
"countryname" LIKE '%Denmark%'`, not `content_type = cast(2 as SMALLINT) and (...)`.

When a layer has subtype labels, they always supply the feature name in text,
for both primary and spatial filter layers. For example, a subtype label `Oil wells` produces
`Show oil wells` with `kind = cast(1 as INTEGER)` while `meta.layers` keeps the catalog layer name.
Labels are lowercased in text; `--alias-suffix` (`generate(..., alias_suffix=True)`) appends the
layer alias — `Show oil discoveries`, `List all dry wells` — which disambiguates labels shared
across layers. Leave it off when the alias is not a noun (`all`). `--layer-only 0.25`
(`layer_only=0.25`) phrases that share of subtyped layers by alias alone — `Show wells`,
`List pipelines` — with no subtype filter, and the subtype column then competes as an
ordinary condition (`wells where content type is DRY`). Additional conditions are ANDed
with the subtype filter; no pluralization or dataset-specific filters are added. Missing
subtype metadata falls back to the layer alias and ordinary field conditions.

`--ignore-subtype` (`ignore_subtype=True`) uses layer aliases and excludes the
subtype column from all conditions, on primary and secondary layers.

Numeric comparisons cover decimals and non-boolean integers. “No more than”
and “at most” generate `<=`, including equality at the boundary. “Under” and
“less than” generate strict `<`. Previously generated datasets using the old
“no more than” → `<` mapping must be regenerated or audited; this fix does not
rewrite existing files. Distance text uses “within” and “no more than”,
represented by `withinDistance` (`ST_DWithin`, including the distance boundary).
It no longer uses strict “less than” wording for that inclusive relation;
regenerate or audit older distance examples as well. Seeded output may change.

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
gold_ids, pred_ids)` turns it into a minimisable `[0, 1]` cost. When execution
results are supplied, similarity is 70% OBJECTID Jaccard and 30% partial score;
when both result sets are empty, it falls back to partial score alone.
`identical()` parses as
DuckDB, so identifiers are case-insensitive and `cast(2 as SMALLINT)` equals `2`.
Semantic compare encodes one canonical string per FELN (sqlglot-normalized
WHERE, parsed relations, secondaries sorted) and returns cosine similarity.

## Security

FELN generates SQL; it does not execute it or provide a SQL sandbox. Treat
catalog metadata, WHERE expressions, and compiler options as trusted inputs.
The WHERE guard rejects some unsafe syntax, but it does not prevent subqueries
or database functions that read files or access external resources. Geometry,
output-alias, and CRS options must not come directly from untrusted users.

Before executing model-generated or user-supplied queries, enforce the
application's allowed tables, columns, and operations, and isolate the database
process with restricted filesystem/network access and resource limits. See
[DuckDB's security guidance](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview).
Structural similarity and successful SQL parsing are not security checks.

## Tests

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

Read-only smoke checks against NorthSea (1,000 records in each of five
generation modes):

```bash
uv run python -m tasks.smoke_catalogs \
  "$HOME/Documents/ArcGIS/Projects/NorthSea/Layers.json"
```

This checks generation, reproducibility, catalog field references, SQL parsing,
and comparison with normalized output. It does not execute SQL against project
data. See [review and smoke results](tasks/review-smoke-20260915.md).

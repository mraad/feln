# Implementation review and NorthSea smoke test — 2026-09-15

## Findings fixed

- **Incorrect full credit for opposite signed thresholds:** predicate extraction
  dropped unary minus, so `where_credit("x > -5", "x > 5")` returned 1.0.
  Preserve the sign; this now returns 0.75 (matching column and operator only).
- **Normalized queries could fail comparison with their source:** predicates
  such as `depth BETWEEN 0 AND 1 or distance BETWEEN 0 AND 10` expanded into
  conjunctive normal form with a different predicate order on the second pass.
  A final simplification makes this comparison stable.
- **Distance text disagreed with SQL at equality:** removed strict "less than"
  from the inclusive `withinDistance` relation's wording.
- **Non-spatial catalogs could generate spatial joins:** table-only sampling
  now selects one layer; empty direct `sample()` calls raise a clear ValueError.

Regression tests cover these cases. Seeded generated output may differ from
older versions; existing project catalogs and generated files were not modified.

## Optimization

Profiling 1,000 normalized NorthSea records attributed 2.53 of 2.63 profiled
seconds to SQL normalization. Added the standard-library `lru_cache`, bounded
to 4,096 immutable string results, with no new dependency.

Final implementation, 1,000 normalized records, seed 20260915, median of three
runs per mode on this machine. The uncached column bypasses the decorator;
cold runs clear the cache first; warm runs reuse the same workload.

| Catalog | Cache bypassed | Cold cache | Warm cache |
| --- | ---: | ---: | ---: |
| NorthSea | 0.840 s | 0.289 s | 0.023 s |

The cold-cache speedup is 2.9×. Warm results describe repeated
inputs; they do not predict throughput for entirely new predicates.

## Validation

The source catalog was loaded from
`~/Documents/ArcGIS/Projects/NorthSea/Layers.json`.

| Project | Catalog layers | Records checked | Result |
| --- | ---: | ---: | --- |
| NorthSea | 5 (including 2 tables) | 5,000 | Passed |

NorthSea ran 1,000 samples in each mode: default, normalized,
alias-suffix, layer-only (0.25), and ignore-subtype. Each batch was generated
again to verify reproducibility. Checks cover unique metas, model validation,
layer and column references, single-statement DuckDB SQL parsing, equality
against normalized metas, structural/partial score 1, and cost 0.

The CLI also passed `generate --normalize --sql` (20 records), `sql`, and
`compare --partial` for NorthSea. Temporary CLI outputs were removed.

- 83 unit tests passed.
- Ruff lint and formatting checks passed.
- `git diff --check` passed.
- Reusable smoke command: `python -m tasks.smoke_catalogs <catalog> ...`.

## Scope and limits

These are catalog generation/compilation/comparison smoke tests, not execution
against source features. DuckDB is not installed in the checked Python
environments; query result IDs, spatial CRS correctness, and runtime SQL types
were not validated. No accuracy, precision, or recall benchmark is claimed
without reference queries and execution results.

Review was performed locally. The installed CodeRabbit CLI reported version
0.7.6, but `codesign --verify` failed with "invalid signature (code or signature
have been modified)". No CodeRabbit review was run after that verification
failure; this report is not a CodeRabbit clean-review result.

README now explains text → structured output → measurement and execution,
including metric definitions, regression-derived query evaluation, and potential
DuckDB/ArcPy/Spark execution. DuckDB is the only implemented compiler.

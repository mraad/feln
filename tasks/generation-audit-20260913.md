# FELN generation audit — 2026-09-13

## Follow-up: source repair completed

The user subsequently authorized correcting NorthSea.aprx and regenerating its
catalog and samples. The `npd_papers` source alias is now `NPD papers`; all other
APRX member contents were verified unchanged. Regenerated Layers.json differs
only in that alias and its related hint. Regenerated 1,000 FELN samples with seed
20260913, alias_suffix=True, layer_only=0.25, normalize=True; all pass the training
schema compiler. Published JSON and JSONL under the NorthSea project directory.
Originals are backed up in `backups/20260913-npd-alias/` there. The obsolete
NorthSea.updated.aprx was moved to Trash and is additionally backed up.
The investigation and unchanged-source statements below describe the earlier
diagnostic checkpoint, not the current state.

Official meaning: the availability of wellbore PDF documents published by NPD
(Norwegian Petroleum Directorate; now Norwegian Offshore Directorate), distinct
from physical core samples. See https://factpages.sodir.no/en/wellbore/Attributes.

## Numeric boundary fix

`condition()` sampled "no more than" from the strict `lt` branch and emitted
`<`. Moved that wording into `le`, alongside "at most", emitting `<=`.
"Less than" and "under" remain strict `<`. Integer types and floating-point
casts are preserved; normalized output also retains the inclusive operator.

The old test explicitly required the wrong mapping. It now rejects inclusive
wording from the strict branch, and a new test covers both inclusive phrases for
Double, SmallInteger, Integer, and BigInteger, including a value beyond float's
exact integer range. All 78 tests pass. README semantics updated.
Existing generated files are not rewritten by this code change. Regeneration
can differ for the same seed because the phrase sampling choices changed.
Spatial "no more than" already maps to `withinDistance` / inclusive
`ST_DWithin`; that relation representation was not changed.

## Why core-sample questions target npd_papers

Read-only inspection of both source archives:

- `~/Documents/ArcGIS/Projects/NorthSea/NorthSea.aprx`
- `~/Documents/ArcGIS/Projects/NorthSea/NorthSea.updated.aprx`

In each ZIP, `Map/Wells.json` → `featureTable.fieldDescriptions` contains:

```json
{"fieldName": "npd_papers", "alias": "core_sample"}
{"fieldName": "core_sample", "alias": "core_sample"}
```

`layers-json/layers_json/layers_from_aprx.py::describe_columns` prefers the CIM
alias, replaces underscores with spaces, and lowercases it. The ArcPy toolbox
path likewise uses `field.aliasName`. Both therefore describe these distinct
fields as "core sample". The numeric hint builder also embeds that alias in
its SQL examples. The sibling `HideUpdateTool.json` only rewrites `*_hc_*`
aliases, so it does not repair this duplicate.

The resulting live `Layers.json` contains:

| Field | Alias | Type | Values |
| --- | --- | --- | --- |
| `npd_papers` | core sample | SmallInteger | 0, 1 |
| `core_sample` | core sample | String | YES, NO |

`feln.generate.condition()` uses `col.alias` for text and `col.name` for SQL.
Reproduced with the live catalog: `condition(Random(0), npd_column)` returns
`("with core sample", "npd_papers = cast(1 as SMALLINT)")`.
The updated 1,000-example FELN file contains 34 question/target pairs mentioning
core sample while referencing `npd_papers`. This is inherited metadata ambiguity,
not a random field substitution by the model.

Recommended upstream correction: set the Wells `npd_papers` alias to "NPD papers"
in the ArcGIS layer metadata (or an explicit hide/update rule), leaving the real
`core_sample` alias as "core sample". Regenerate the catalog and FELN afterward;
do not merely rename JSON aliases while leaving stale hints and examples.
Confirm the field's intended business label if it should be more specific.

The user requested investigation of this target, not a metadata rewrite.
Neither ArcGIS project, original Layers/FELN file, nor the layers-json producer
was modified. No dataset-specific field remapping was added to the generic
generator. Retraining remains paused pending source-metadata/data resolution.
No commit or push. CodeRabbit unavailable (signed out); local checks used.

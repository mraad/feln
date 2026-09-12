"""Grammar sampler over a Layers.json catalog."""

from __future__ import annotations

from feln import FELN, Layers, sample
from feln.generate import generate


def test_sample_is_valid_feln(catalog: Layers) -> None:
    import random

    text, meta = sample(random.Random(0), list(catalog.layers))
    assert text
    assert meta.layers[0] in {layer.name for layer in catalog.layers}
    FELN.model_validate(meta.model_dump())


def test_generate_unique_count(catalog: Layers) -> None:
    records = generate(catalog, 8, seed=1)
    assert len(records) == 8
    metas = {str(r["meta"]) for r in records}
    assert len(metas) == 8
    for record in records:
        FELN.model_validate(record["meta"])
        for name in record["meta"]["layers"]:
            assert catalog.find_layer(name) is not None


def test_calendar_year_conditions_have_complete_boundaries():
    import random
    from unittest.mock import patch

    from feln import Column
    from feln.generate import condition

    for dtype in ("Date", "DateOnly", "DateTime"):
        column = Column(name="entry_date", alias="entry date", dtype=dtype)
        for op, expected in {
            "in": "entry_date >= timestamp '2005-01-01' AND entry_date < timestamp '2006-01-01'",
            "after": "entry_date >= timestamp '2006-01-01'",
            "before": "entry_date < timestamp '2005-01-01'",
        }.items():
            rng = random.Random(0)
            with (
                patch.object(rng, "randint", return_value=2005),
                patch.object(rng, "choices", return_value=[op]),
            ):
                text, sql = condition(rng, column)
            assert text == f"entry date {op} 2005"
            assert sql == expected


def test_normalize_writes_canonical_where(catalog: Layers) -> None:
    from feln.identical import identical, normalize_where

    raw = generate(catalog, 30, seed=3)
    canon = generate(catalog, 30, seed=3, normalize=True)
    assert [r["text"] for r in raw] == [r["text"] for r in canon]
    for a, b in zip(raw, canon, strict=True):
        for wa, wb in zip(a["meta"]["where"], b["meta"]["where"], strict=True):
            assert wb == normalize_where(wa)
            assert identical(wa, wb)
            assert "cast(" not in wb.lower() and "timestamp" not in wb.lower()
    assert any("cast(" in w for r in raw for w in r["meta"]["where"])
    assert any('"' in w for r in canon for w in r["meta"]["where"])

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


def test_table_only_catalog_has_no_spatial_relations():
    import random

    import pytest

    from feln import Column, Layer

    tables = [
        Layer(name=name, stype="Table", columns=[Column(name="amount", dtype="Double")])
        for name in ("Sales", "Orders")
    ]
    for seed in range(20):
        _, query = sample(random.Random(seed), tables)
        assert len(query.layers) == 1
        assert query.relations == []
    with pytest.raises(ValueError, match="catalog has no layers"):
        sample(random.Random(0), [])


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


def test_numeric_less_than_variants_preserve_types_and_boundaries():
    import random
    from unittest.mock import patch

    from feln import Column
    from feln.generate import condition

    for dtype, value, sql_type in [
        ("Double", "5.0", "DOUBLE PRECISION"),
        ("SmallInteger", "5", "SMALLINT"),
        ("Integer", "5", "INTEGER"),
        ("BigInteger", "9007199254740993", "BIGINT"),
    ]:
        col = Column(name="amount", dtype=dtype, values=[value])
        seen = set()
        for seed in range(40):
            rng = random.Random(seed)
            with patch.object(rng, "choices", return_value=["lt"]):
                text, sql = condition(rng, col)
            assert sql == f"amount < cast({value} as {sql_type})"
            seen.add(text)
        assert all("no more than" not in text for text in seen)
        assert any("less than" in text for text in seen)
        assert any("under" in text for text in seen)


def test_distance_variants_keep_relation(catalog):
    import random
    from unittest.mock import patch

    from feln.generate import relation

    seen = set()
    for seed in range(40):
        rng = random.Random(seed)
        with patch.object(rng, "choices", side_effect=[["withinDistance"], ["miles"]]):
            text, meta = relation(rng, *list(catalog.layers)[:2])
        distance = meta.split()[1]
        assert text in {
            f"within {distance} miles of",
            f"no more than {distance} miles from",
        }
        seen.add(text.split()[0])
    assert seen == {"within", "no"}


def test_numeric_inclusive_and_boolean_conditions():
    import random
    from unittest.mock import patch

    from feln import Column
    from feln.generate import condition

    rng = random.Random(0)
    with patch.object(rng, "choices", return_value=["le"]):
        text, sql = condition(rng, Column(name="count", dtype="Integer", values=["5"]))
    assert text in {"count is at most 5", "count is no more than 5"}
    assert sql == "count <= cast(5 as INTEGER)"
    text, sql = condition(rng, Column(name="logs", dtype="Integer", values=["0", "1"]))
    assert text in {"with logs", "without logs"}
    assert sql in {"logs = cast(0 as INTEGER)", "logs = cast(1 as INTEGER)"}


def test_no_more_than_is_inclusive_for_every_numeric_type():
    import random
    from unittest.mock import patch

    from feln import Column
    from feln.generate import condition
    from feln.identical import normalize_where

    for dtype, value, sql_type in [
        ("Double", "71.0", "DOUBLE PRECISION"),
        ("SmallInteger", "71", "SMALLINT"),
        ("Integer", "71", "INTEGER"),
        ("BigInteger", "9007199254740993", "BIGINT"),
    ]:
        col = Column(name="amount", dtype=dtype, values=[value])
        seen = set()
        for seed in range(40):
            rng = random.Random(seed)
            with patch.object(rng, "choices", return_value=["le"]):
                text, sql = condition(rng, col)
            assert sql == f"amount <= cast({value} as {sql_type})"
            assert " <= " in normalize_where(sql)
            seen.add(text)
        assert seen == {f"amount is at most {value}", f"amount is no more than {value}"}

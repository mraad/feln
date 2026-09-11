"""Text noun phrases and subtype SQL must select the same features."""

import random
from unittest.mock import patch

from feln import FELN, Column, Layer, Layers
from feln.generate import generate, layer_phrase, sample
from feln.sql import feln_to_sql


def subtype_layer(**kwargs):
    return Layer(
        name="Places",
        alias="places",
        subtype="kind",
        columns=[
            Column(name="KIND", dtype="Integer", keyval={"1": "Hospitals", "2": "Schools"}),
            Column(name="NAME", values=["A", "B"]),
        ],
        **kwargs,
    )


def test_subtype_noun_keeps_code_and_parenthesizes_extra_filter():
    layer = subtype_layer()
    with patch(
        "feln.generate.where_clause", return_value=("name is A or B", "NAME = 'A' or NAME = 'B'")
    ) as where:
        label, nl, sql = layer_phrase(random.Random(1), layer, 2)
    assert label == "Hospitals"
    assert nl == "name is A or B"
    assert sql == "KIND = cast(1 as INTEGER) and (NAME = 'A' or NAME = 'B')"
    assert where.call_args.kwargs == {"exclude": "KIND"}


def test_string_subtype_codes_are_escaped():
    layer = Layer(
        name="Places", subtype="KIND", columns=[Column(name="kind", keyval={"O'Brien": "Clinics"})]
    )
    label, nl, sql = layer_phrase(random.Random(1), layer, 1)
    assert (label, nl, sql) == ("Clinics", "", "kind = 'O''Brien'")


def test_missing_subtype_mapping_falls_back():
    for subtype in (None, "absent", "kind"):
        layer = Layer(name="Places", alias="places", subtype=subtype, columns=[Column(name="kind")])
        assert layer_phrase(random.Random(1), layer, 1) == ("places", "", "")


def test_primary_and_secondary_subtypes_match_generated_sql():
    layers = [
        subtype_layer(),
        Layer(
            name="Areas",
            alias="areas",
            stype="Polygon",
            subtype="TYPE",
            columns=[Column(name="TYPE", dtype="Integer", keyval={"3": "Districts"})],
        ),
    ]
    seen = set()
    for seed in range(100):
        phrases = []

        def capture(*args):
            result = layer_phrase(*args)
            phrases.append(result)
            return result

        with patch("feln.generate.layer_phrase", side_effect=capture):
            text, meta = sample(random.Random(seed), layers)
        FELN.model_validate(meta.model_dump())
        feln_to_sql(meta, Layers(layers=layers))
        for i, (label, _, sql) in enumerate(phrases):
            expected = {
                "Hospitals": "KIND = cast(1 as INTEGER)",
                "Schools": "KIND = cast(2 as INTEGER)",
                "Districts": "TYPE = cast(3 as INTEGER)",
            }.get(label)
            if expected:
                assert label in text
                assert sql == meta.where[i]
                assert sql.startswith(expected)
                assert "featuretype" not in sql
                seen.add(i)
    assert seen >= {0, 1}
    catalog = Layers(layers=layers)
    assert generate(catalog, 20, seed=5) == generate(catalog, 20, seed=5)


def test_subtyped_master_never_uses_catalog_name_in_text():
    master = Layer(
        name="Master",
        alias="master",
        subtype="KIND",
        columns=[
            Column(
                name="KIND", dtype="Integer", keyval={"1": "villa", "2": "hospital", "3": "park"}
            )
        ],
    )
    seen = set()
    for seed in range(100):
        text, meta = sample(random.Random(seed), [master])
        assert "master" not in text.casefold()
        assert meta.layers == ["Master"]
        for code, label in master.columns[0].keyval.items():
            if label in text:
                seen.add(label)
                assert meta.where == [f"KIND = cast({code} as INTEGER)"]
    assert seen == {"villa", "hospital", "park"}

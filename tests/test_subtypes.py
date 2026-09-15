"""Text noun phrases and subtype SQL must select the same features."""

import random
from unittest.mock import patch

import pytest

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
    assert label == "hospitals"
    assert nl == "name is A or B"
    assert sql == "KIND = cast(1 as INTEGER) and (NAME = 'A' or NAME = 'B')"
    assert where.call_args.kwargs == {"exclude": "KIND"}


def test_string_subtype_codes_are_escaped():
    layer = Layer(
        name="Places", subtype="KIND", columns=[Column(name="kind", keyval={"O'Brien": "Clinics"})]
    )
    label, nl, sql = layer_phrase(random.Random(1), layer, 1)
    assert (label, nl, sql) == ("clinics", "", "kind = 'O''Brien'")


def test_alias_suffix_follows_lowercased_label():
    layer = subtype_layer()
    label, _, sql = layer_phrase(random.Random(1), layer, 1, alias_suffix=True)
    assert label in {"hospitals places", "schools places"}
    assert sql.startswith("KIND = cast(")
    # A label that already ends with the alias is not doubled.
    layer = Layer(
        name="Wells",
        alias="wells",
        subtype="KIND",
        columns=[Column(name="KIND", dtype="Integer", keyval={"1": "Dry Wells"})],
    )
    assert layer_phrase(random.Random(1), layer, 1, alias_suffix=True)[0] == "dry wells"
    texts = [r["text"] for r in generate(Layers(layers=[subtype_layer()]), 6, alias_suffix=True)]
    assert all(("hospitals places" in t) ^ ("schools places" in t) for t in texts)


def test_layer_only_names_the_whole_layer_without_a_subtype_filter():
    layer = subtype_layer()
    for bad in (-0.1, 1.5):
        with pytest.raises(ValueError, match="layer_only"):
            layer_phrase(random.Random(1), layer, 1, layer_only=bad)
    assert layer_phrase(random.Random(1), layer, 0, layer_only=1.0) == ("places", "", "")
    phrases = set()
    for seed in range(40):
        label, nl, sql = layer_phrase(random.Random(seed), layer, 1, layer_only=1.0)
        assert label == "places"
        assert bool(nl) == bool(sql)  # a filter is always spoken, never implied
        phrases.add(nl)
    # The subtype column is back in the pool as an ordinary condition.
    assert any(nl.lower().startswith("kind is") for nl in phrases)
    assert any(nl.lower().startswith("name") for nl in phrases)
    catalog = Layers(layers=[layer])
    assert generate(catalog, 10, seed=2) == generate(catalog, 10, seed=2, layer_only=0.0)
    mixed = {r["text"].split()[1] for r in generate(catalog, 30, seed=2, layer_only=0.5)}
    assert mixed >= {"places", "hospitals", "schools"}


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

        def capture(*args, **kwargs):
            result = layer_phrase(*args, **kwargs)
            phrases.append(result)
            return result

        with patch("feln.generate.layer_phrase", side_effect=capture):
            text, meta = sample(random.Random(seed), layers)
        FELN.model_validate(meta.model_dump())
        feln_to_sql(meta, Layers(layers=layers))
        for i, (label, _, sql) in enumerate(phrases):
            expected = {
                "hospitals": "KIND = cast(1 as INTEGER)",
                "schools": "KIND = cast(2 as INTEGER)",
                "districts": "TYPE = cast(3 as INTEGER)",
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


def test_subtyped_layer_never_uses_catalog_name_in_text():
    layer = Layer(
        name="Features",
        alias="features",
        subtype="KIND",
        columns=[
            Column(
                name="KIND",
                dtype="Integer",
                keyval={"1": "oil wells", "2": "gas wells", "3": "dry wells"},
            )
        ],
    )
    seen = set()
    for seed in range(100):
        text, meta = sample(random.Random(seed), [layer])
        assert "features" not in text.casefold()
        assert meta.layers == ["Features"]
        for code, label in layer.columns[0].keyval.items():
            if label in text:
                seen.add(label)
                assert meta.where == [f"KIND = cast({code} as INTEGER)"]
    assert seen == {"oil wells", "gas wells", "dry wells"}

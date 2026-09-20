"""Metadata instructions must survive generation, including text scope."""

import random
from unittest.mock import patch

from sqlglot import exp, parse_one

from feln import Column, Layer, Layers
from feln.generate import condition, generate, layer_phrase, where_clause
from feln.identical import parse_where


def test_case_insensitive_patterns_escape_literal_wildcards():
    column = Column(name="name", values=["Ab_c%O'Brien"], hints=["Use SQL ILIKE."])
    seen = set()
    for seed in range(30):
        text, sql = condition(random.Random(seed), column)
        tree = parse_where(sql)
        assert isinstance(tree, exp.Escape)
        assert isinstance(tree.this, exp.ILike)
        assert "Ab!_c!%O''Brien" in sql
        assert "Ab_c%O''Brien" in text
        seen.add(text.split()[1])
    assert seen == {"starts", "ends", "contains"}
    # A LIKE-only catalog retains its original case-sensitive contract.
    _, sql = condition(random.Random(0), column.model_copy(update={"hints": ["Use SQL LIKE."]}))
    assert " ILIKE " not in sql and " LIKE " in sql


def test_coded_values_and_never_like_keep_equality():
    column = Column(name="country", keyval={"GB": "United Kingdom"}, hints=["NEVER use SQL LIKE."])
    for seed in range(20):
        text, sql = condition(random.Random(seed), column)
        assert "United Kingdom" in text and "'GB'" in sql
        assert "LIKE" not in sql


def test_casing_and_numeric_range_casts_follow_metadata():
    column = Column(name="operator", values=["Mixed Case"], hints=["uppercase the compared values"])
    for seed in range(20):
        _, sql = condition(random.Random(seed), column)
        assert "Mixed Case" not in sql
    rng = random.Random(0)
    with patch.object(rng, "choices", return_value=["between"]):
        text, sql = condition(rng, Column(name="depth", dtype="Double", values=["10", "20"]))
    tree = parse_one(sql, read="duckdb")
    assert isinstance(tree, exp.Between)
    assert isinstance(tree.args["low"], exp.Cast)
    assert isinstance(tree.args["high"], exp.Cast)
    assert "inclusive" in text


def test_metadata_boolean_phrases_and_boolean_grouping():
    flag = Column(
        name="included",
        values=["YES", "NO"],
        hints=[
            "Text for value YES: that are included in a field.",
            "Text for value NO: that are not included in a field.",
        ],
    )
    for seed in range(20):
        text, sql = condition(random.Random(seed), flag)
        assert ("not included" in text) == ("'NO'" in sql)
    layer = Layer(name="Sites", columns=[flag, Column(name="name", values=["A", "B"])])
    rng = random.Random(0)
    with (
        patch(
            "feln.generate.condition",
            side_effect=[("with logs", "logs = 1"), ("name is A or B", "name = 'A' or name = 'B'")],
        ),
        patch.object(rng, "random", return_value=0.9),
    ):
        text, sql = where_clause(rng, layer, 2)
    assert text == "(the feature has logs) and (name is A or B)"
    assert sql == "(logs = 1) and (name = 'A' or name = 'B')"


def test_mixed_catalog_samples_tables_without_spatial_joins_and_anchors_relations():
    catalog = Layers(
        layers=[
            Layer(
                name="Sites",
                alias="sites",
                stype="Point",
                columns=[Column(name="name", values=["A", "B"])],
            ),
            Layer(
                name="Roads",
                alias="roads",
                stype="Polyline",
                columns=[Column(name="name", values=["C", "D"])],
            ),
            Layer(
                name="Areas",
                alias="areas",
                stype="Polygon",
                columns=[Column(name="name", values=["E", "F"])],
            ),
            Layer(
                name="Stats",
                alias="statistics",
                stype="Table",
                columns=[Column(name="value", dtype="Double", values=["2", "3"])],
            ),
        ]
    )
    records = generate(catalog, 100, seed=42)
    assert any(r["meta"]["layers"] == ["Stats"] for r in records)
    assert any(len(r["meta"]["layers"]) == 3 for r in records)
    for row in records:
        plan = row["meta"]
        if "Stats" in plan["layers"]:
            assert plan["layers"] == ["Stats"] and not plan["relations"]
        primary = catalog.find_layer(plan["layers"][0]).alias
        assert row["text"].count(f"The returned {primary} must") == len(plan["relations"])


def test_composite_subtype_label_is_not_a_logical_or():
    layer = Layer(
        name="Wells",
        alias="wells",
        subtype="kind",
        columns=[
            Column(name="kind", dtype="Integer", keyval={"1": "Gas/Condensate Shows"}),
        ],
    )
    text, _, sql = layer_phrase(random.Random(0), layer, 1, alias_suffix=True)
    assert text == "wells classified as 'gas/condensate shows'"
    assert sql == "kind = cast(1 as INTEGER)"

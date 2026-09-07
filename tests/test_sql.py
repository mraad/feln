"""DuckDB SQL from FELN."""

from __future__ import annotations

import pytest

from feln import FELN, Column, FELNToDuckDB, Layer, Layers, Relation, feln_to_sql, to_meters


def _layer(name: str, stype: str = "Point") -> Layer:
    return Layer(
        name=name,
        alias=name.lower(),
        stype=stype,  # type: ignore[arg-type]
        uri=f"uri/{name}",
        table_name=name.replace(" ", "_"),
        columns=[
            Column(name="status", alias="Status", dtype="String"),
            Column(name="depth", alias="Depth", dtype="Double"),
        ],
    )


def test_single_layer() -> None:
    sql = FELNToDuckDB()([_layer("wells")], ["depth > 1000"], [])
    assert "FROM Wells" in sql or "FROM wells" in sql
    assert "WHERE depth > 1000" in sql


def test_two_layers_distance() -> None:
    sql = FELNToDuckDB()(
        [_layer("wells"), _layer("pipeline", "Polyline")],
        ["", "status = 'IN-SERVICE'"],
        [Relation(kind="withinDistance", distance=5.0, unit="miles")],
    )
    assert "ST_DWithin" in sql
    assert "L0" in sql and "L1" in sql and "J0" in sql
    assert "status = 'IN-SERVICE'" in sql
    assert "8046.7" in sql  # 5 miles in metres


def test_not_within_distance_is_not_exists() -> None:
    sql = FELNToDuckDB()(
        [_layer("sites"), _layer("depots")],
        ["country='DE'", ""],
        [Relation(kind="notWithinDistance", distance=40.0, unit="kilometers")],
    )
    assert "NOT EXISTS" in sql
    assert "ST_DWithin" in sql
    assert "NOT ST_DWithin" not in sql
    assert "40000" in sql


def test_within_and_inside_both_st_within() -> None:
    layers = [_layer("wells"), _layer("counties", "Polygon")]
    for kind in ("within", "inside"):
        sql = FELNToDuckDB()(layers, ["", ""], [Relation(kind=kind)])
        assert "ST_Within" in sql


def test_noop_skips_join() -> None:
    sql = FELNToDuckDB()(
        [_layer("wells"), _layer("pipeline", "Polyline")],
        ["dist_pipeline_mi <= 5.0", ""],
        [Relation(kind="none")],
    )
    assert "dist_pipeline_mi <= 5.0" in sql
    assert "JOIN" not in sql
    assert "ST_" not in sql


def test_noop_with_secondary_where_raises() -> None:
    with pytest.raises(ValueError, match="no-op.*non-empty WHERE"):
        FELNToDuckDB()(
            [_layer("wells"), _layer("pipeline", "Polyline")],
            ["dist_pipeline_mi <= 5.0", "status = 'ACTIVE'"],
            [Relation(kind="none")],
        )


def test_feln_to_sql_resolves_catalog(catalog: Layers) -> None:
    query = FELN(
        layers=["Wells", "Pipelines"],
        where=["", ""],
        relations=["intersects"],
    )
    sql = feln_to_sql(query, catalog)
    assert "ST_Intersects" in sql
    assert "FROM Wells" in sql
    assert "FROM Pipelines" in sql


def test_to_meters() -> None:
    assert to_meters(1, "kilometers") == 1000
    assert to_meters(1, "miles") == pytest.approx(1609.34)
    assert to_meters(1, "parsecs") is None

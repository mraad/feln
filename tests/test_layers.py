"""Layers.json consumer, including a round-trip through layers-json's toolbox dump."""

from __future__ import annotations

from pathlib import Path

from feln import Layers


def test_load_fixture(catalog: Layers) -> None:
    assert len(catalog) == 3
    wells = catalog.find_layer("Wells")
    assert wells is not None
    assert wells.stype == "Point"
    assert catalog.find_layer("pipelines") is not None  # alias
    counties = catalog.find_layer("Counties")
    assert counties is not None
    assert counties.table_name == "Counties"


def test_load_from_directory(tmp_path: Path, catalog: Layers) -> None:
    target = tmp_path / "Layers.json"
    target.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
    loaded = Layers.load(str(tmp_path))
    assert loaded.find_layer("Wells") is not None


def test_parses_layers_json_toolbox_dump(tmp_path: Path) -> None:
    from layers_json.layers_from_aprx import load_toolbox

    toolbox = load_toolbox()
    wells = toolbox.Layer(
        name="Wells",
        table_name="Wells",
        alias="wells",
        stype="Point",
        uri="/data/NorthSea.gdb/Wells",
        display="NAME",
        columns=[
            toolbox.Column(
                name="STATUS",
                alias="status",
                dtype="Integer",
                keyval={"1": "Active"},
                values=["1"],
            ),
            toolbox.Column(name="NAME", alias="name", dtype="String", values=["A"]),
        ],
    )
    pipes = toolbox.Layer(
        name="Pipelines",
        table_name="Pipelines",
        alias="pipelines",
        stype="Polyline",
        uri="/data/NorthSea.gdb/Pipelines",
        columns=[toolbox.Column(name="MEDIUM", alias="medium", dtype="String", values=["Oil"])],
    )
    path = toolbox.Layers(layers=[wells, pipes]).dump(str(tmp_path))
    catalog = Layers.load(path)
    loaded_wells = catalog.find_layer("Wells")
    loaded_pipes = catalog.find_layer("pipelines")
    assert loaded_wells is not None
    assert loaded_pipes is not None
    assert loaded_wells.stype == "Point"
    assert loaded_pipes.name == "Pipelines"
    assert loaded_wells.columns[0].keyval == {"1": "Active"}

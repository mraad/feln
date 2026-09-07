"""The fixture catalog contract. The model itself is layers_json.layers, and its
round-trip against the Layers.pyt producer is layers-json's own test.
"""

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

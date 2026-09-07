"""Consumer of the Layers.json catalog authored by layers-json / NanoMap.pyt."""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Column(BaseModel):
    """One field in a Layers.json layer. Field names match the producer dump."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    alias: str = ""
    dtype: str = "String"
    utype: str | None = None
    minmax: list[int | float] = Field(default_factory=list)
    keyval: dict[str, str] = Field(default_factory=dict)
    hints: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)


class Layer(BaseModel):
    """One layer/table in a Layers.json catalog."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    alias: str = ""
    stype: Literal["Point", "Polyline", "Polygon", "Multipoint", "Table"] = "Point"
    display: str | None = None
    subtype: str | None = None
    columns: list[Column] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    uri: str = ""
    table_name: str | None = None

    @property
    def sql_table(self) -> str:
        """Physical table name: catalog ``table_name`` or spaces→underscores."""
        return self.table_name or self.name.replace(" ", "_")


class Layers(BaseModel):
    """Top-level Layers.json container."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    layers: list[Layer] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.layers)

    def find_layer(self, name: str | None) -> Layer | None:
        """Resolve by name, alias, table_name, or uri (case-insensitive except uri)."""
        if not name:
            return None
        key = name.lower()
        return next(
            (
                layer
                for layer in self.layers
                if layer.uri == name
                or layer.name.lower() == key
                or layer.alias.lower() == key
                or (layer.table_name is not None and layer.table_name.lower() == key)
            ),
            None,
        )

    @classmethod
    def load(cls, filename: str) -> Layers:
        """Load a Layers.json file or a directory containing one."""
        filename = os.path.expanduser(filename)
        if os.path.isdir(filename):
            filename = os.path.join(filename, "Layers.json")
        with open(filename, encoding="utf-8") as fp:
            return cls.model_validate_json(fp.read())

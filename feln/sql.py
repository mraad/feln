"""DuckDB spatial SQL for a FELN query against a layers-json catalog."""

from __future__ import annotations

from textwrap import dedent

from .layers import Layer, Layers
from .model import FELN, Relation, parse_relation
from .sanitize import sanitize_identifier, sanitize_where_clause, table_ident
from .units import to_meters


class FELNToDuckDB:
    """CTE chain: filtered L0..Ln, one join CTE per spatial relation, L0 rows in every J_i."""

    def __init__(
        self,
        objectid: str | None = None,
        geometry: str | None = None,
        alias: str | None = None,
        crs_inp: str | None = None,
        crs_out: str | None = None,
    ) -> None:
        self.objectid = objectid or "OBJECTID"
        self.geometry = geometry or "geometry"
        self.alias = alias or "geometry"
        self.crs_inp = crs_inp
        self.crs_out = crs_out

    def __call__(
        self,
        layers: list[Layer],
        wheres: list[str],
        relations: list[Relation],
        st_as: str | None = None,
    ) -> str:
        n = len(layers)
        if n == 0:
            raise ValueError("layers must contain at least one layer.")
        if len(wheres) != n:
            raise ValueError(f"wheres must have {n} entries, got {len(wheres)}.")
        if len(relations) != n - 1:
            raise ValueError(
                f"relations must have {n - 1} entries for {n} layers, got {len(relations)}."
            )
        if n == 1:
            return self._single_layer(layers[0], wheres[0], st_as)

        objectid = sanitize_identifier(self.objectid)
        geometry = sanitize_identifier(self.geometry)
        cte_parts: list[str] = []
        for i, (layer, where) in enumerate(zip(layers, wheres, strict=True)):
            table = table_ident(layer.name, layer.table_name)
            where_clause = f" WHERE {sanitize_where_clause(where)}" if where else ""
            cte_parts.append(
                f"L{i} AS (\n    SELECT {objectid}, {geometry}\n    FROM {table}{where_clause}\n)"
            )

        join_indices: list[int] = []
        for i, relation in enumerate(relations):
            if relation.kind == "none":
                if wheres[i + 1]:
                    raise ValueError(
                        f"Relation {i} is a no-op but layer '{layers[i + 1].name}' "
                        f"has a non-empty WHERE clause ('{wheres[i + 1]}'). "
                        f"A no-op relation skips the spatial join, so the secondary "
                        f"layer's filter would be silently ignored."
                    )
                continue
            if relation.kind == "notWithinDistance":
                distance_m = self._distance_m(relation)
                cte_parts.append(
                    f"J{i} AS (\n"
                    f"    SELECT A.{objectid}\n"
                    f"    FROM L0 A\n"
                    f"    WHERE NOT EXISTS (\n"
                    f"        SELECT 1 FROM L{i + 1} B\n"
                    f"        WHERE ST_DWithin(A.{geometry}, B.{geometry}, {distance_m})\n"
                    f"    )\n"
                    f")"
                )
            else:
                on_clause = self._on_clause(relation, f"A.{geometry}", f"B.{geometry}")
                cte_parts.append(
                    f"J{i} AS (\n"
                    f"    SELECT DISTINCT A.{objectid}\n"
                    f"    FROM L0 A\n"
                    f"    JOIN L{i + 1} B\n"
                    f"    ON {on_clause}\n"
                    f")"
                )
            join_indices.append(i)

        if not join_indices:
            return self._single_layer(layers[0], wheres[0], st_as)

        table0 = table_ident(layers[0].name, layers[0].table_name)
        has_distance = any(r.kind in ("withinDistance", "notWithinDistance") for r in relations)
        select_clause = ",\n    ".join(self._select_columns(layers[0], st_as, has_distance))
        join_clauses = "\n".join(
            f"JOIN J{i} M{i} ON L.{objectid} = M{i}.{objectid}" for i in join_indices
        )
        cte_str = ",\n".join(cte_parts)
        return dedent(
            f"""WITH {cte_str}
SELECT
    {select_clause}
FROM {table0} L
{join_clauses}"""
        ).strip()

    def _single_layer(self, layer: Layer, where: str, st_as: str | None) -> str:
        table = table_ident(layer.name, layer.table_name)
        where_clause = f"\nWHERE {sanitize_where_clause(where)}" if where else ""
        select_clause = ",\n".join(self._select_columns(layer, st_as, is_dwithin=False))
        return f"SELECT\n{select_clause}\nFROM {table} L{where_clause}"

    def _select_columns(self, layer: Layer, st_as: str | None, is_dwithin: bool) -> list[str]:
        if st_as == "WKB":
            return [f"ST_AsWKB({self._transform(is_dwithin)}) AS '{self.alias}'"]
        if st_as in ("WKT", "Text"):
            return [f"ST_AsText({self._transform(is_dwithin)}) AS '{self.alias}'"]
        if st_as == "GeoJSON":
            expr = self.geometry
            if is_dwithin and self.crs_inp and self.crs_out and self.crs_inp != self.crs_out:
                expr = f"ST_Transform({self.geometry},'{self.crs_inp}','EPSG:4326',always_xy:=TRUE)"
            return [f"ST_AsGeoJSON({expr}) AS '{self.alias}'"]
        return [f"L.{sanitize_identifier(self.objectid)}"]

    def _transform(self, is_dwithin: bool) -> str:
        if is_dwithin and self.crs_inp and self.crs_out and self.crs_inp != self.crs_out:
            return (
                f"ST_Transform({self.geometry},'{self.crs_inp}','{self.crs_out}',always_xy:=TRUE)"
            )
        return self.geometry

    def _on_clause(self, relation: Relation, lhs_geom: str, rhs_geom: str) -> str:
        match relation.kind:
            case "contains":
                return f"ST_Contains({lhs_geom}, {rhs_geom})"
            case "intersects":
                return f"ST_Intersects({lhs_geom}, {rhs_geom})"
            case "within" | "inside":
                return f"ST_Within({lhs_geom}, {rhs_geom})"
            case "withinDistance":
                return f"ST_DWithin({lhs_geom}, {rhs_geom}, {self._distance_m(relation)})"
            case _:
                raise ValueError(f"Unknown relation kind: {relation.kind}")

    @staticmethod
    def _distance_m(relation: Relation) -> float:
        metres = to_meters(relation.distance, relation.unit)
        return relation.distance if metres is None else metres


def feln_to_sql(
    feln: FELN,
    catalog: Layers,
    *,
    st_as: str | None = None,
    geometry: str | None = None,
    objectid: str | None = None,
) -> str:
    """Resolve *feln* against *catalog* and return DuckDB SQL."""
    resolved: list[Layer] = []
    for name in feln.layers:
        layer = catalog.find_layer(name)
        if layer is None:
            raise ValueError(f"unknown layer {name!r}")
        resolved.append(layer)
    return FELNToDuckDB(objectid=objectid, geometry=geometry)(
        resolved,
        list(feln.where),
        [parse_relation(r) for r in feln.relations],
        st_as=st_as,
    )

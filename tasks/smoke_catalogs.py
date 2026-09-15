"""Read-only catalog smoke test: python -m tasks.smoke_catalogs path/to/Layers.json ..."""

import argparse
import json
from time import perf_counter

import sqlglot
from sqlglot import exp

from feln import FELN, FELNCompare, Layers, feln_to_sql
from feln.generate import generate
from feln.identical import normalize_where


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalogs", nargs="+")
    parser.add_argument("-n", type=int, default=1000)
    args = parser.parse_args()
    if args.n < 1:
        parser.error("-n must be positive")
    modes = {
        "default": {},
        "normalized": {"normalize": True},
        "alias_suffix": {"alias_suffix": True},
        "layer_only": {"layer_only": 0.25},
        "ignore_subtype": {"ignore_subtype": True},
    }
    for path in args.catalogs:
        catalog = Layers.load(path)
        for mode, options in modes.items():
            start = perf_counter()
            records = generate(catalog, args.n, seed=20260915, **options)
            assert len(records) == args.n, (path, mode, "sampling budget exhausted")
            assert records == generate(catalog, args.n, seed=20260915, **options)
            assert len({json.dumps(r["meta"], sort_keys=True) for r in records}) == args.n
            for record in records:
                query = FELN.model_validate(record["meta"])
                assert record["text"]
                for name, where in zip(query.layers, query.where, strict=True):
                    layer = catalog.find_layer(name)
                    assert layer is not None, name
                    if where:
                        tree = sqlglot.parse_one(where, read="duckdb")
                        columns = {c.name.casefold() for c in layer.columns}
                        assert all(c.name.casefold() in columns for c in tree.find_all(exp.Column))
                sql = feln_to_sql(query, catalog)
                statements = sqlglot.parse(sql, read="duckdb")
                assert len(statements) == 1 and isinstance(statements[0], exp.Select)
                normalized = FELN(
                    layers=query.layers,
                    where=[normalize_where(w) for w in query.where],
                    relations=query.relations,
                )
                assert query.same(normalized)
                assert abs(FELNCompare.structural(query, normalized) - 1) < 1e-9
                assert abs(FELNCompare.partial(query, normalized) - 1) < 1e-9
                assert abs(FELNCompare.cost(query, normalized)) < 1e-9
            print(
                json.dumps(
                    dict(
                        catalog=path,
                        mode=mode,
                        records=len(records),
                        seconds=round(perf_counter() - start, 3),
                    )
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()

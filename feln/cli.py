"""CLI: generate FELN from Layers.json, emit DuckDB SQL, compare two queries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from layers_json.layers import Layers

from .compare import FELNCompare
from .generate import generate, records_to_jsonl
from .model import FELN
from .sql import feln_to_sql


def _load_feln(path: Path) -> FELN:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "meta" in payload:
        payload = payload["meta"]
    return FELN.model_validate(payload)


def _load_catalog(path: Path) -> Layers:
    if not path.exists():
        raise FileNotFoundError(path)
    return Layers.load(str(path))


def cmd_generate(args: argparse.Namespace) -> int:
    catalog = _load_catalog(args.layers_json)
    records = generate(
        catalog,
        args.n,
        seed=args.seed,
        alias_suffix=args.alias_suffix,
        layer_only=args.layer_only,
        normalize=args.normalize,
    )
    if args.sql:
        for record in records:
            record["sql"] = feln_to_sql(FELN.model_validate(record["meta"]), catalog)
    text = records_to_jsonl(records)
    if args.out is None or str(args.out) == "-":
        sys.stdout.write(text)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {len(records)} -> {args.out}", file=sys.stderr)
    if len(records) < args.n:
        print(
            f"warning: only {len(records)} unique metas after sampling (asked {args.n})",
            file=sys.stderr,
        )
    return 0


def cmd_sql(args: argparse.Namespace) -> int:
    catalog = _load_catalog(args.layers_json)
    query = _load_feln(args.query)
    print(feln_to_sql(query, catalog, st_as=args.st_as, geometry=args.geometry))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    left = _load_feln(args.a)
    right = _load_feln(args.b)
    score = FELNCompare.structural(left, right)
    print(f"{score:.6f}")
    if args.partial:
        print(f"partial {FELNCompare.partial(left, right):.6f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feln",
        description="Generate, SQL-compile, and compare FELN queries over a Layers.json catalog.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    gen = sub.add_parser("generate", help="sample synthetic FELN metas from a catalog")
    gen.add_argument("layers_json", type=Path, help="Layers.json file or its parent directory")
    gen.add_argument("-n", type=int, default=20, help="number of unique metas (default 20)")
    gen.add_argument("-o", "--out", type=Path, default=None, help="jsonl path (default: stdout)")
    gen.add_argument("--seed", type=int, default=0)
    gen.add_argument("--sql", action="store_true", help="add DuckDB SQL on each record")
    gen.add_argument(
        "--alias-suffix",
        action="store_true",
        help="append the layer alias to subtype labels in text (oil discoveries, dry wells)",
    )
    gen.add_argument(
        "--layer-only",
        type=float,
        default=0.0,
        metavar="SHARE",
        help="share [0,1] of subtyped layers phrased by alias alone, no subtype filter "
        "(Show wells); default 0",
    )
    gen.add_argument(
        "--normalize",
        action="store_true",
        help="canonical WHERE (normalize_where): quoted lower-case identifiers, sorted "
        "conjuncts, bare literals",
    )
    gen.set_defaults(func=cmd_generate)

    sql = sub.add_parser("sql", help="compile one FELN JSON file to DuckDB spatial SQL")
    sql.add_argument("layers_json", type=Path)
    sql.add_argument("query", type=Path, help="FELN JSON (or {meta: FELN})")
    sql.add_argument(
        "--st-as", dest="st_as", default=None, choices=["WKB", "WKT", "Text", "GeoJSON"]
    )
    sql.add_argument("--geometry", default=None, help="geometry column (default: geometry)")
    sql.set_defaults(func=cmd_sql)

    cmp_ = sub.add_parser("compare", help="structural similarity of two FELN JSON files")
    cmp_.add_argument("a", type=Path)
    cmp_.add_argument("b", type=Path)
    cmp_.add_argument("--partial", action="store_true", help="also print the graded score")
    cmp_.set_defaults(func=cmd_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "generate" and args.n < 1:
        parser.error("-n must be at least 1")
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"error: not found: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

"""CLI entry points: generate, sql, compare."""

from __future__ import annotations

import json
from pathlib import Path

from feln.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "layers.json"


def test_generate_stdout(capsys) -> None:
    code = main(["generate", str(FIXTURE), "-n", "3", "--seed", "0"])
    assert code == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln]
    assert len(lines) == 3
    row = json.loads(lines[0])
    assert "text" in row and "meta" in row
    assert "layers" in row["meta"]


def test_generate_sql_flag(capsys) -> None:
    code = main(["generate", str(FIXTURE), "-n", "1", "--seed", "0", "--sql"])
    assert code == 0
    row = json.loads(capsys.readouterr().out.splitlines()[0])
    assert "SELECT" in row["sql"]
    assert "FROM" in row["sql"]


def test_generate_alias_suffix_flag(capsys) -> None:
    code = main(["generate", str(FIXTURE), "-n", "20", "--seed", "0", "--alias-suffix"])
    assert code == 0
    texts = [json.loads(ln)["text"] for ln in capsys.readouterr().out.splitlines() if ln]
    assert any("active wells" in t or "suspended wells" in t for t in texts)
    assert not any("Active" in t or "Suspended" in t for t in texts)


def test_generate_layer_only_share(capsys) -> None:
    code = main(["generate", str(FIXTURE), "-n", "30", "--seed", "0", "--layer-only", "1"])
    assert code == 0
    texts = [json.loads(ln)["text"] for ln in capsys.readouterr().out.splitlines() if ln]
    assert not any("active" in t or "suspended" in t for t in texts if "status" not in t)
    assert any(t.split()[1] == "wells" for t in texts)


def test_generate_normalize_flag(capsys) -> None:
    code = main(["generate", str(FIXTURE), "-n", "20", "--seed", "0", "--normalize", "--sql"])
    assert code == 0
    rows = [json.loads(ln) for ln in capsys.readouterr().out.splitlines() if ln]
    assert not any("cast(" in w.lower() for r in rows for w in r["meta"]["where"])
    assert all("SELECT" in r["sql"] for r in rows)


def test_sql_and_compare(tmp_path: Path, capsys) -> None:
    query = {
        "layers": ["Wells", "Pipelines"],
        "where": ["", ""],
        "relations": ["withinDistance 5 miles"],
    }
    permuted = {
        "layers": ["Wells", "Pipelines"],
        "where": ["", ""],
        "relations": ["withinDistance 8.0467 kilometers"],
    }
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(query), encoding="utf-8")
    b.write_text(json.dumps(permuted), encoding="utf-8")

    assert main(["sql", str(FIXTURE), str(a)]) == 0
    sql = capsys.readouterr().out
    assert "ST_DWithin" in sql

    assert main(["compare", str(a), str(b)]) == 0
    score = float(capsys.readouterr().out.strip())
    assert score == 1.0

    assert main(["compare", "--partial", str(a), str(b)]) == 0
    assert capsys.readouterr().out.splitlines() == ["1.000000", "partial 1.000000"]


def test_generate_layer_only_out_of_range(capsys) -> None:
    assert main(["generate", str(FIXTURE), "-n", "1", "--layer-only", "2"]) == 1
    assert "layer_only must be within [0, 1]" in capsys.readouterr().err


def test_generate_missing_catalog() -> None:
    assert main(["generate", "/no/such/Layers.json", "-n", "1"]) == 1

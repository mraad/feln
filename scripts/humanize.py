"""Humanize generated FELN text locally with Ollama (default model: qwen3.8:27b-mlx).

Input: FELN.json (JSON array) or .jsonl of {text, meta}. Output: same records with
``text`` paraphrased and the generator sentence kept as ``source_text``. Resumable:
each batch lands in ``<out>.batches/NNNNN.json``; rerun to continue after a stop.

    uv run python scripts/humanize.py FELN.json -o FELN.humanized.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.request

PROMPT = """You rewrite machine-generated GIS query sentences into natural requests a human analyst would type.
Each input has "layers": the first layer is what the query returns; later layers are the related layers
(a subtype word such as "injection" or "oil" refers to that layer's features, never to something else).
Rules:
- Keep every condition, value, number, unit, quoted string, layer/subtype name and column meaning EXACTLY. Never add, drop or soften a condition.
- Keep spatial semantics exact: within distance / more than distance from / inside (within) / contains / intersects (cross, overlap). Do not swap direction.
- Keep date semantics exact: after Y = later than Y; before Y = earlier than Y; since Y = Y onward; through Y = up to and including Y; in Y = during Y; between A and B = A through B inclusive.
- Keep AND/OR structure and "not"/"blank"/"is specified" exactly.
- Vary style across items: questions, imperatives, terse and verbose forms, casual wording. No preamble.
Return ONLY JSON: {"items": [{"id": <int>, "text": "<paraphrase>"}, ...]}, one per input, same ids.
Inputs:
"""
SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["id", "text"],
            },
        }
    },
    "required": ["items"],
}


def load(path: pathlib.Path) -> list[dict]:
    raw = path.read_text()
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    return json.loads(raw)


def literals(text: str) -> set[str | float]:
    """Quoted strings and numbers that must survive a paraphrase ("4.0" == "4")."""
    quoted = set(re.findall(r"(?<!\w)'[^']*'(?!\w)", text))  # skip apostrophes: isn't
    numbers = {float(n) for n in re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?!\w)", text)}
    return quoted | numbers


def call(model: str, host: str, batch: list[dict], timeout: int) -> dict[int, str]:
    body = {
        "model": model,
        "prompt": PROMPT + json.dumps(batch, ensure_ascii=False),
        "stream": False,
        "format": SCHEMA,
        "think": False,
        "options": {"temperature": 0.7, "num_ctx": 16384},
    }
    req = urllib.request.Request(
        f"{host}/api/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        items = json.loads(json.load(resp)["response"])["items"]
    return {int(it["id"]): it["text"].strip() for it in items}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("src", type=pathlib.Path)
    ap.add_argument("-o", "--out", type=pathlib.Path, required=True)
    ap.add_argument("--model", default="qwen3.8:27b-mlx")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()

    rows = load(a.src)
    bdir = a.out.with_suffix(a.out.suffix + ".batches")
    bdir.mkdir(exist_ok=True)
    t0 = time.time()
    for start in range(0, len(rows), a.batch):
        bfile = bdir / f"{start:05d}.json"
        if bfile.exists():
            continue
        chunk = rows[start : start + a.batch]
        pending = {
            start + i: {"id": start + i, "layers": r["meta"]["layers"], "text": r["text"]}
            for i, r in enumerate(chunk)
        }
        done: dict[int, str] = {}
        for attempt in range(a.retries + 1):
            if not pending:
                break
            try:
                got = call(a.model, a.host, list(pending.values()), a.timeout)
            except Exception as e:  # noqa: BLE001 — network/JSON failure: retry the batch
                print(f"batch {start}: attempt {attempt} failed: {e}", file=sys.stderr, flush=True)
                continue
            for i, src in list(pending.items()):
                new = got.get(i, "")
                if new and new != src["text"] and literals(src["text"]) <= literals(new):
                    done[i] = new
                    del pending[i]
        for i in pending:  # give up: keep the generator sentence, flag it
            done[i] = rows[i]["text"]
        bfile.write_text(json.dumps({"text": done, "kept": sorted(pending)}, ensure_ascii=False))
        print(
            f"batch {start}: ok, kept {len(pending)} verbatim, {time.time() - t0:.0f}s elapsed",
            flush=True,
        )

    kept = 0
    for start in range(0, len(rows), a.batch):
        b = json.loads((bdir / f"{start:05d}.json").read_text())
        kept += len(b["kept"])
        for i, new in b["text"].items():
            r = rows[int(i)]
            r["source_text"] = r.get("source_text", r["text"])
            r["text"] = new
    a.out.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} -> {a.out} ({kept} kept verbatim after retries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

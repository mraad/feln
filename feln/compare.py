"""Similarity between two FELN queries.

Structural: primary pinned, secondaries matched by name, sqlglot WHERE,
distance in metres, ``within`` ≡ ``inside``. Weighted 40 / 30 / 30.

Partial / cost: the same skeleton with graded credit — layers matched at any
position (swapped primary costs half), WHERE scored per predicate instead of
all-or-nothing — blended with OBJECTID jaccard when execution results exist.
``cost`` is what an optimiser minimises; ``structural`` stays the report score.

Semantic: one canonical string per FELN, one batched ``encode_document``,
cosine of L2-normalised vectors.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
from sqlglot import exp
from sqlglot.optimizer import optimize
from sqlglot.optimizer.normalize import normalize

from .identical import DIALECT, identical, normalize_where, parse_where
from .model import DISTANCE_KINDS, FELN, Relation, canon_kind, parse_relation
from .units import to_meters

_LAYER_W = 0.4
_WHERE_W = 0.3
_REL_W = 0.3
_SWAP_PENALTY = 0.5  # layer credit when the primary differs but the names overlap
_SHAPE_PENALTY = 0.75  # WHERE credit when the OR-group count differs (AND ↔ OR)
_EXEC_W = 0.7  # jaccard share of ``cost`` when both OBJECTID sets are known


class Encoder(Protocol):
    """Anything with ``encode_document`` (gait Encoder, SentenceTransformer wrapper, …)."""

    def encode_document(self, sentences: str | list[str], **kwargs: object) -> np.ndarray: ...


def _align(a: FELN, b: FELN) -> list[tuple[int | None, int | None]]:
    """Greedy name match of secondaries. Returns ``(index_a, index_b)`` pairs.

    Index 0 (primary) is always paired with 0. Unmatched secondaries pad with
    ``None`` so the denominator can penalise extra layers.
    """
    pairs: list[tuple[int | None, int | None]] = [(0, 0)]
    unused = set(range(1, len(b.layers)))
    for i, name in enumerate(a.layers[1:], start=1):
        key = name.strip().lower()
        match = next(
            (j for j in unused if b.layers[j].strip().lower() == key),
            None,
        )
        if match is not None:
            unused.remove(match)
        pairs.append((i, match))
    for j in sorted(unused):
        pairs.append((None, j))
    return pairs


def _relation_credit(ra: Relation | None, rb: Relation | None) -> float:
    """0..1 credit for one aligned relation pair."""
    if ra is None or rb is None:
        return 0.0
    if ra.same(rb):
        return 1.0
    if canon_kind(ra.kind) != canon_kind(rb.kind):
        return 0.0
    if canon_kind(ra.kind) not in DISTANCE_KINDS:
        return 0.5
    metres_a = to_meters(ra.distance, ra.unit)
    metres_b = to_meters(rb.distance, rb.unit)
    if metres_a is None or metres_b is None:
        if ra.unit.lower() != rb.unit.lower():
            return 0.5
        da, db = ra.distance, rb.distance
    else:
        da, db = metres_a, metres_b
    denom = max(abs(da), abs(db), 1e-9)
    return 0.5 + 0.5 * (1.0 - min(1.0, abs(da - db) / denom))


Atom = tuple[tuple[str, ...], str, tuple[str, ...]]  # (columns, operator, literals)


def _atom(node: exp.Expression) -> Atom:
    op = type(node).__name__
    if isinstance(node, exp.Not):
        op = "NOT " + type(node.this).__name__
    elif node.args.get("negate"):  # sqlglot spells ``NOT LIKE`` as Like(negate=True)
        op = "NOT " + op
    cols = tuple(sorted(c.name.lower() for c in node.find_all(exp.Column)))
    lits = tuple(lit.this for lit in node.find_all(exp.Literal))
    return cols, op, lits


def _groups(where: str) -> list[list[Atom]]:
    """DNF of *where*: a list of AND-groups, each a list of atoms. Raises on bad SQL."""
    tree = normalize(optimize(parse_where(where), dialect=DIALECT), dnf=True)
    groups = tree.flatten() if isinstance(tree, exp.Or) else [tree]
    return [
        [_atom(a) for a in (g.flatten() if isinstance(g, exp.And) else [g])]
        for g in (g.unnest() for g in groups)
    ]


def _lit_close(a: tuple[str, ...], b: tuple[str, ...]) -> float:
    if a == b:
        return 1.0
    if len(a) == len(b) == 1:
        try:
            x, y = float(a[0]), float(b[0])
        except ValueError:
            return 0.0
        return 1.0 - min(1.0, abs(x - y) / max(abs(x), abs(y), 1e-9))
    return 0.0


def _atom_credit(a: Atom, b: Atom) -> float:
    return 0.5 * (a[0] == b[0]) + 0.25 * (a[1] == b[1]) + 0.25 * _lit_close(a[2], b[2])


def where_credit(a: str, b: str) -> float:
    """0..1 credit for two WHERE fragments, graded per predicate.

    Both are put in DNF; atoms (column, operator, literal) are matched greedily by
    best pair first, credit = F1 of matched atom credit. A different number of OR
    groups (AND ↔ OR) multiplies by ``_SHAPE_PENALTY``. Unparseable input falls
    back to ``identical``.
    """
    if identical(a, b):
        return 1.0
    try:
        ga, gb = _groups(a) if a.strip() else [], _groups(b) if b.strip() else []
    except Exception:
        return 0.0
    atoms_a = [x for g in ga for x in g]
    atoms_b = [x for g in gb for x in g]
    if not atoms_a or not atoms_b:
        return 0.0
    # ponytail: greedy best-pair-first over ≤8×8 atoms; Hungarian if a WHERE ever has more.
    pairs = sorted(
        ((_atom_credit(x, y), i, j) for i, x in enumerate(atoms_a) for j, y in enumerate(atoms_b)),
        reverse=True,
    )
    used_a: set[int] = set()
    used_b: set[int] = set()
    hits = 0.0
    for credit, i, j in pairs:
        if credit == 0.0:
            break
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        hits += credit
    f1 = 2.0 * hits / (len(atoms_a) + len(atoms_b))
    return f1 * (_SHAPE_PENALTY if len(ga) != len(gb) else 1.0)


def _align_any(a: FELN, b: FELN) -> list[tuple[int | None, int | None]]:
    """Greedy name match over every position (primary included), padded with ``None``."""
    pairs: list[tuple[int | None, int | None]] = []
    unused = set(range(len(b.layers)))
    for i, name in enumerate(a.layers):
        key = name.strip().lower()
        match = next((j for j in sorted(unused) if b.layers[j].strip().lower() == key), None)
        if match is not None:
            unused.remove(match)
        pairs.append((i, match))
    pairs.extend((None, j) for j in sorted(unused))
    return pairs


def _relation_at(feln: FELN, index: int | None) -> Relation | None:
    if index is None or index == 0:
        return None
    return parse_relation(feln.relations[index - 1])


def canonical_relation(rel: str) -> str:
    """Stable relation text: aliased kind, distance in metres when convertible."""
    parsed = parse_relation(rel)
    kind = canon_kind(parsed.kind)
    if kind == "none":
        return "none"
    if kind not in DISTANCE_KINDS:
        return kind
    metres = to_meters(parsed.distance, parsed.unit)
    if metres is None:
        return f"{kind} {parsed.distance:g} {parsed.unit.lower()}"
    return f"{kind} {metres:g} meters"


def canonical_text(feln: FELN) -> str:
    """One string a semantic encoder sees: primary, then secondaries sorted by name."""
    chunks = [f"layer: {feln.layers[0].strip()}"]
    where0 = normalize_where(feln.where[0])
    if where0:
        chunks.append(f"where: {where0}")
    rest: list[tuple[str, str, str, str]] = []
    for name, where, rel in zip(feln.layers[1:], feln.where[1:], feln.relations, strict=True):
        rest.append(
            (name.strip().lower(), name.strip(), normalize_where(where), canonical_relation(rel))
        )
    rest.sort(key=lambda row: (row[0], row[3], row[2]))
    for _, name, where, rel in rest:
        chunks.append(f"rel: {rel} {name}")
        if where:
            chunks.append(f"where: {where}")
    return " | ".join(chunks)


def _l2(vec: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(vec))
    if n == 0.0:
        return vec
    return vec / n


def _as_matrix(embeddings: np.ndarray, n: int) -> np.ndarray:
    arr = np.asarray(embeddings, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.shape[0] != n:
        raise ValueError(f"encoder returned {arr.shape[0]} rows, expected {n}")
    return arr


def _cosine_unit(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))


class FELNCompare:
    """Similarity between two FELN instances."""

    @staticmethod
    def structural(a: FELN, b: FELN) -> float:
        """Weighted score in ``[0, 1]``. Secondaries are matched by name, not index."""
        pairs = _align(a, b)
        max_n = max(len(a.layers), len(b.layers))
        layer_hits = 0.0
        where_hits = 0.0
        for ia, ib in pairs:
            la = a.layers[ia].strip().lower() if ia is not None else None
            lb = b.layers[ib].strip().lower() if ib is not None else None
            if la is not None and la == lb:
                layer_hits += 1.0
            wa = a.where[ia] if ia is not None else None
            wb = b.where[ib] if ib is not None else None
            if wa is not None and wb is not None and identical(wa, wb):
                where_hits += 1.0
        layer_score = layer_hits / max_n
        where_score = where_hits / max_n

        max_r = max(len(a.relations), len(b.relations))
        if max_r == 0:
            relation_score = 1.0
        else:
            rel_hits = 0.0
            for ia, ib in pairs:
                if ia == 0 and ib == 0:
                    continue
                ra = parse_relation(a.relations[ia - 1]) if ia is not None else None
                rb = parse_relation(b.relations[ib - 1]) if ib is not None else None
                rel_hits += _relation_credit(ra, rb)
            relation_score = rel_hits / max_r

        return _LAYER_W * layer_score + _WHERE_W * where_score + _REL_W * relation_score

    @staticmethod
    def partial(a: FELN, b: FELN) -> float:
        """``structural`` with graded credit: any-position layer match (swapped primary
        keeps ``_SWAP_PENALTY``), per-predicate WHERE credit, relation credit. ``[0, 1]``."""
        pairs = _align_any(a, b)
        max_n = max(len(a.layers), len(b.layers))
        matched = [(ia, ib) for ia, ib in pairs if ia is not None and ib is not None]
        same_primary = a.layers[0].strip().lower() == b.layers[0].strip().lower()
        layer_score = len(matched) / max_n * (1.0 if same_primary else _SWAP_PENALTY)
        where_score = sum(where_credit(a.where[ia], b.where[ib]) for ia, ib in matched) / max_n
        max_r = max(len(a.relations), len(b.relations))
        if max_r == 0:
            relation_score = 1.0
        else:
            rel_hits = sum(
                _relation_credit(_relation_at(a, ia), _relation_at(b, ib))
                for ia, ib in pairs
                if not (ia == 0 and ib == 0)
            )
            relation_score = rel_hits / max_r
        return _LAYER_W * layer_score + _WHERE_W * where_score + _REL_W * relation_score

    @staticmethod
    def cost(
        gold: FELN,
        pred: FELN | None,
        gold_ids: set[int] | None = None,
        pred_ids: set[int] | None = None,
    ) -> float:
        """Minimisable cost in ``[0, 1]``; 0 is a perfect answer.

        ``pred is None`` (malformed or guard-rejected) costs 1. With both OBJECTID sets
        the cost blends jaccard (``_EXEC_W``) with ``partial``; without them, or when
        both sets are empty (jaccard is blind there), it is ``1 - partial``.
        """
        if pred is None:
            return 1.0
        struct = FELNCompare.partial(gold, pred)
        if gold_ids is None or pred_ids is None or not (gold_ids or pred_ids):
            return 1.0 - struct
        jaccard = len(gold_ids & pred_ids) / len(gold_ids | pred_ids)
        return 1.0 - (_EXEC_W * jaccard + (1.0 - _EXEC_W) * struct)

    @staticmethod
    def semantic(a: FELN, b: FELN, encoder: Encoder) -> float:
        """Cosine of two canonical embeddings. Batches unique strings into one call."""
        texts = [canonical_text(a), canonical_text(b)]
        unique = list(dict.fromkeys(texts))
        matrix = _as_matrix(encoder.encode_document(unique), len(unique))
        index = {text: _l2(matrix[i]) for i, text in enumerate(unique)}
        return _cosine_unit(index[texts[0]], index[texts[1]])

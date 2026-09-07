"""Similarity between two FELN queries.

Structural: primary pinned, secondaries matched by name, sqlglot WHERE,
distance in metres, ``within`` ≡ ``inside``. Weighted 40 / 30 / 30.

Semantic: one canonical string per FELN, one batched ``encode_document``,
cosine of L2-normalised vectors.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from .identical import identical, normalize_where
from .model import DISTANCE_KINDS, FELN, Relation, canon_kind, parse_relation
from .units import to_meters

_LAYER_W = 0.4
_WHERE_W = 0.3
_REL_W = 0.3


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
    def semantic(a: FELN, b: FELN, encoder: Encoder) -> float:
        """Cosine of two canonical embeddings. Batches unique strings into one call."""
        texts = [canonical_text(a), canonical_text(b)]
        unique = list(dict.fromkeys(texts))
        matrix = _as_matrix(encoder.encode_document(unique), len(unique))
        index = {text: _l2(matrix[i]) for i, text in enumerate(unique)}
        return _cosine_unit(index[texts[0]], index[texts[1]])

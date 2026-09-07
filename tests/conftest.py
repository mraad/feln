from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from feln import Layers

FIXTURE = Path(__file__).parent / "fixtures" / "layers.json"


class HashEncoder:
    """Deterministic encoder: MD5 seed → unit vector. Stable across PYTHONHASHSEED."""

    dim = 32

    def encode_document(self, sentences, **kwargs):
        if isinstance(sentences, str):
            sentences = [sentences]
        vecs = []
        for text in sentences:
            seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % 2**31
            rng = np.random.RandomState(seed)
            vec = rng.randn(self.dim)
            vec = vec / np.linalg.norm(vec)
            vecs.append(vec)
        return np.array(vecs)


@pytest.fixture
def catalog() -> Layers:
    return Layers.load(str(FIXTURE))


@pytest.fixture
def encoder() -> HashEncoder:
    return HashEncoder()

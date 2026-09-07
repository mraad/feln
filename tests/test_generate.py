"""Grammar sampler over a Layers.json catalog."""

from __future__ import annotations

from feln import FELN, Layers, sample
from feln.generate import generate


def test_sample_is_valid_feln(catalog: Layers) -> None:
    import random

    text, meta = sample(random.Random(0), list(catalog.layers))
    assert text
    assert meta.layers[0] in {layer.name for layer in catalog.layers}
    FELN.model_validate(meta.model_dump())


def test_generate_unique_count(catalog: Layers) -> None:
    records = generate(catalog, 8, seed=1)
    assert len(records) == 8
    metas = {str(r["meta"]) for r in records}
    assert len(metas) == 8
    for record in records:
        FELN.model_validate(record["meta"])
        for name in record["meta"]["layers"]:
            assert catalog.find_layer(name) is not None

from __future__ import annotations

from pathlib import Path

import pytest

from feln import Layers

FIXTURE = Path(__file__).parent / "fixtures" / "layers.json"


@pytest.fixture
def catalog() -> Layers:
    return Layers.load(str(FIXTURE))

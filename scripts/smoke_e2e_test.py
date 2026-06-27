"""Gated wrapper that runs the E2E smoke test under pytest.

Skipped by default so ``uv run pytest`` stays hermetic. Bring up the
stack and opt in explicitly::

    docker compose up -d
    PULSEGRAPH_E2E=1 uv run pytest -m e2e
"""

import os
import pathlib
import sys

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.skipif(
    os.getenv("PULSEGRAPH_E2E") != "1",
    reason="real-stack E2E test; set PULSEGRAPH_E2E=1 to run",
)
def test_e2e_smoke() -> None:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from smoke_e2e import run_smoke

    run_smoke()

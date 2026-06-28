"""Gated wrapper that runs the GDPR cascade E2E under pytest.

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
def test_gdpr_cascade_e2e() -> None:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from gdpr_cascade_e2e import run_checks

    run_checks()

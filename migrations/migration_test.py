"""Guards on the migration history (no database required)."""

from alembic.config import Config
from alembic.script import ScriptDirectory


def _script() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config("alembic.ini"))


def test_single_head() -> None:
    # More than one head means branching migrations were merged badly.
    assert len(_script().get_heads()) == 1


def test_single_base_revision() -> None:
    assert len(_script().get_bases()) == 1

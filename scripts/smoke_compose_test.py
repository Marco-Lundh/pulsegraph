"""Hermetic tests for the smoke script's compose-command detection."""

import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from smoke_e2e import _compose_cmd  # noqa: E402


def test_prefers_docker_compose_plugin(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert _compose_cmd() == ["docker", "compose"]
    assert calls == [["docker", "compose", "version"]]


def test_falls_back_to_standalone_binary(monkeypatch) -> None:
    def fake_run(cmd, **_kwargs):
        if cmd[:2] == ["docker", "compose"]:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert _compose_cmd() == ["docker-compose"]


def test_raises_when_no_compose_available(monkeypatch) -> None:
    def fake_run(cmd, **_kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError):
        _compose_cmd()

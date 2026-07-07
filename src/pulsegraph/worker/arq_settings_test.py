"""Tests for the arq WorkerSettings class the `arq` CLI loads."""

from arq.connections import RedisSettings

from pulsegraph.worker.arq_settings import WorkerSettings
from pulsegraph.worker.tasks import run_watch


def test_redis_settings_is_an_instance_not_a_method():
    # arq reads ``WorkerSettings.redis_settings`` off the class and passes it
    # straight to ``create_pool``; if it is a classmethod/callable instead of
    # a RedisSettings instance the worker crashes on startup with
    # ``'classmethod' object has no attribute 'host'``. Guard against that
    # regression (ADR 0015/0017).
    assert isinstance(WorkerSettings.redis_settings, RedisSettings)
    assert not callable(WorkerSettings.redis_settings)


def test_redis_settings_reflects_configured_url():
    # Parsed from settings.redis_url via RedisSettings.from_dsn, so the host
    # and port are populated (the local-first default is localhost:6379).
    settings = WorkerSettings.redis_settings
    assert settings.host
    assert isinstance(settings.port, int)


def test_worker_registers_the_run_watch_task():
    assert run_watch in WorkerSettings.functions


def test_worker_wires_startup_and_shutdown_hooks():
    assert callable(WorkerSettings.on_startup)
    assert callable(WorkerSettings.on_shutdown)

"""Smoke tests for the FastAPI app."""

from pulsegraph.api._fake import make_client


def test_health() -> None:
    client, _, _ = make_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_unknown_route_returns_404() -> None:
    client, _, _ = make_client()
    assert client.get("/nonexistent").status_code == 404

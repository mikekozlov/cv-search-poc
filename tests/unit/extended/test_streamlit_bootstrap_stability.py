from cv_search.app.bootstrap import load_stateless_services
from cv_search.clients.openai_client import StubOpenAIBackend


def test_bootstrap_uses_stub_backend_when_use_openai_stub_set(monkeypatch):
    monkeypatch.setenv("USE_OPENAI_STUB", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    services = load_stateless_services()
    client = services["client"]

    assert isinstance(client.backend, StubOpenAIBackend)


def test_bootstrap_uses_stub_backend_when_openai_key_missing(monkeypatch):
    monkeypatch.delenv("USE_OPENAI_STUB", raising=False)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "")

    services = load_stateless_services()
    client = services["client"]

    assert isinstance(client.backend, StubOpenAIBackend)


def test_bootstrap_no_longer_exposes_embedder(monkeypatch):
    monkeypatch.setenv("USE_OPENAI_STUB", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    services = load_stateless_services()

    assert "embedder" not in services

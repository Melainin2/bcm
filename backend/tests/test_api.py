"""Tests de l'API FastAPI (health, source, file, validations chat)."""

from fastapi.testclient import TestClient


def _client(store):
    import main as api
    api._state["store"] = store
    api._state["pipeline"] = None
    return TestClient(api.app), api


def test_health_ok(populated_store):
    store, chunks = populated_store
    client, _ = _client(store)
    h = client.get("/api/health").json()
    assert h["status"] == "ok"
    assert h["rag_ready"] is True
    assert h["chroma_ready"] is True
    assert h["documents_indexed"] == len(chunks)
    assert h["claude_model"]
    assert isinstance(h["available_claude_models"], list) and h["available_claude_models"]
    assert h["embedding_model"]
    assert "similarity_threshold" in h
    # Sécurité : api_key_configured est un booléen, jamais la clé elle-même.
    assert isinstance(h["api_key_configured"], bool)
    assert "ANTHROPIC_API_KEY" not in h
    assert not any(isinstance(v, str) and v.startswith("sk-ant") for v in h.values())


def test_source_lookup(populated_store):
    store, chunks = populated_store
    client, _ = _client(store)
    sid = chunks[0].id
    s = client.get(f"/api/source/{sid}").json()
    assert s["source_id"] == sid
    assert s["text"]
    assert "title" in s


def test_source_not_found(populated_store):
    store, _ = populated_store
    client, _ = _client(store)
    r = client.get("/api/source/does::p1::c9")
    assert r.status_code == 404


def test_chat_empty_rejected(populated_store):
    store, _ = populated_store
    client, _ = _client(store)
    r = client.post("/api/chat", json={"question": ""})
    assert r.status_code == 422


def test_chat_topk_bounds(populated_store):
    store, _ = populated_store
    client, _ = _client(store)
    r = client.post("/api/chat", json={"question": "x", "top_k": 99})
    assert r.status_code == 422


def test_chat_invalid_model_rejected(populated_store):
    """Un modèle Claude hors AVAILABLE_CLAUDE_MODELS doit renvoyer 400."""
    store, _ = populated_store
    client, _ = _client(store)
    r = client.post(
        "/api/chat",
        json={"question": "x", "model": "gpt-4-turbo"},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "model_not_allowed"
    assert "non autorisé" in detail["message"]


def test_file_endpoint_serves_pdf(populated_store):
    store, _ = populated_store
    client, _ = _client(store)
    # Un fichier réel du corpus.
    r = client.get("/api/file/oracle/oracle_tablespaces.md")
    assert r.status_code == 200


def test_file_endpoint_blocks_traversal(populated_store):
    store, _ = populated_store
    client, _ = _client(store)
    # Traversée encodée (%2e%2e = "..", %2f = "/") pour atteindre réellement
    # l'endpoint /api/file sans que le client HTTP ne normalise le chemin.
    # Le garde-fou (résolution + vérif « sous data/ ») doit renvoyer 404.
    r = client.get("/api/file/..%2f..%2fetc%2fpasswd")
    assert r.status_code == 404


def test_spa_fallback_serves_index(populated_store):
    """Déploiement service unique : une route SPA inconnue renvoie index.html."""
    store, _ = populated_store
    client, _ = _client(store)
    r = client.get("/une/route/react")
    # Si le build frontend existe, on obtient index.html (200) ; sinon 404 (pas de build).
    if r.status_code == 200:
        assert "<!doctype html" in r.text.lower() or "<html" in r.text.lower()


def test_unknown_api_route_not_masked_by_spa(populated_store):
    """Une route /api/* inconnue reste un 404 (jamais l'index HTML)."""
    store, _ = populated_store
    client, _ = _client(store)
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert "<html" not in r.text.lower()

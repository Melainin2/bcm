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
    r = client.get("/api/file/../../etc/passwd")
    assert r.status_code == 404

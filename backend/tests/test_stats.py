"""Tests des statistiques système (fichiers disque vs index) et db_type/file_type."""

from rag.loader import detect_db_type, detect_file_type
from rag.stats import compute_file_stats, compute_index_stats, build_stats


def test_detect_db_type():
    assert detect_db_type("oracle/guide.pdf") == "oracle"
    assert detect_db_type("postgresql/vacuum.md") == "postgresql"
    assert detect_db_type("logs/alert.log") == "logs"
    assert detect_db_type("misc/readme.txt") == "unknown"


def test_detect_file_type():
    assert detect_file_type("guide.PDF") == "pdf"
    assert detect_file_type("a.md") == "md"
    assert detect_file_type("a.log") == "log"
    assert detect_file_type("a.txt") == "txt"
    assert detect_file_type("a.rtf") == "other"


def test_file_stats_postgresql_zero_when_absent(tmp_path):
    (tmp_path / "oracle").mkdir()
    (tmp_path / "oracle" / "a.md").write_text("hello", encoding="utf-8")
    stats = compute_file_stats(str(tmp_path))
    assert stats["postgresql_files"] == 0
    assert stats["oracle_files"] == 1
    assert stats["total_files"] == 1


def test_file_stats_postgresql_counted_when_present(tmp_path):
    pg = tmp_path / "postgresql"
    pg.mkdir()
    (pg / "perf.md").write_text("VACUUM tuning", encoding="utf-8")
    (pg / "manual.pdf").write_text("%PDF-1.4 fake", encoding="utf-8")
    stats = compute_file_stats(str(tmp_path))
    assert stats["postgresql_files"] == 2
    assert stats["pdf_count"] == 1
    assert stats["md_count"] == 1


def test_index_stats_counts_chunks_by_db_type(populated_store):
    """Les chunks indexés sont comptés par db_type (métadonnée ou source_path)."""
    store, chunks = populated_store
    idx = compute_index_stats(store)
    assert idx["total_indexed_chunks"] == len(chunks)
    # Le corpus texte contient des .md oracle et postgresql.
    assert idx["indexed_postgresql_chunks"] >= 1
    assert idx["indexed_oracle_chunks"] >= 1
    assert idx["indexed_postgresql_files"] >= 1
    assert idx["indexed_files_count"] >= 2


def test_index_stats_empty_store():
    """Sans store, tous les compteurs d'index sont à zéro (pas de crash)."""
    idx = compute_index_stats(None)
    assert idx["total_indexed_chunks"] == 0
    assert idx["indexed_postgresql_chunks"] == 0


def test_build_stats_warning_when_detected_not_indexed(populated_store, monkeypatch):
    """Fichiers PostgreSQL sur disque mais non indexés -> avertissement."""
    store, _ = populated_store
    import rag.stats as stats_mod

    # Simule 3 PDF PostgreSQL présents sur disque, dont 0 indexé.
    monkeypatch.setattr(
        stats_mod, "compute_file_stats",
        lambda _p: {"postgresql_files": 3, "oracle_files": 0, "logs_files": 0,
                    "unknown_files": 0, "total_files": 3, "pdf_count": 3,
                    "md_count": 0, "txt_count": 0, "log_count": 0},
    )
    monkeypatch.setattr(
        stats_mod, "compute_index_stats",
        lambda _s: {"total_indexed_chunks": 0, "indexed_files_count": 0,
                    "indexed_postgresql_chunks": 0, "indexed_postgresql_files": 0,
                    "indexed_oracle_chunks": 0, "indexed_oracle_files": 0,
                    "indexed_logs_chunks": 0, "indexed_logs_files": 0,
                    "indexed_unknown_chunks": 0, "indexed_unknown_files": 0},
    )
    data = stats_mod.build_stats(store)
    assert any("PostgreSQL" in w for w in data["warnings"])


def test_stats_endpoint(populated_store):
    """L'endpoint /api/stats renvoie fichiers, index, config et modèles."""
    from fastapi.testclient import TestClient
    import main as api

    api._state["store"], _ = populated_store
    api._state["pipeline"] = None
    client = TestClient(api.app)

    s = client.get("/api/stats").json()
    assert s["rag_ready"] is True
    assert s["files"]["postgresql_files"] >= 1  # data/postgresql/ réel
    assert s["files"]["oracle_files"] >= 1
    assert s["indexed"]["total_indexed_chunks"] > 0
    assert s["indexed"]["indexed_postgresql_chunks"] >= 1
    assert s["claude_model"]
    assert isinstance(s["available_claude_models"], list) and s["available_claude_models"]
    assert "similarity_threshold" in s
    assert "warnings" in s

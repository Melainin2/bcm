"""Tests de la détection de langue (ar / fr / en)."""

from rag import lang


def test_detect_english():
    assert lang.detect_language("How does VACUUM work in PostgreSQL?") == "en"


def test_detect_french():
    assert lang.detect_language("Comment fonctionne le VACUUM dans PostgreSQL ?") == "fr"


def test_detect_arabic():
    assert lang.detect_language("ما هو الـ tablespace في Oracle؟") == "ar"


def test_arabic_wins_even_with_latin_tokens():
    # Présence de tokens latins (Oracle, RMAN) mais question arabe.
    assert lang.detect_language("كيف تعمل RMAN في Oracle؟") == "ar"


def test_empty_defaults_english():
    assert lang.detect_language("") == "en"
    assert lang.detect_language("   ") == "en"


def test_supported_and_names():
    for code in lang.SUPPORTED:
        assert code in lang.LANG_NAMES
    assert lang.LANG_NAMES["ar"]["dir"] == "rtl"

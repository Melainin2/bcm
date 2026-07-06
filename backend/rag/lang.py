"""Détection de la langue de la question : arabe / français / anglais.

On combine une détection rapide par script (présence de caractères arabes) et
langdetect pour distinguer fr/en. Le résultat pilote la consigne de langue
envoyée à Claude ET est renvoyé à l'UI.
"""

from __future__ import annotations

import re

from langdetect import DetectorFactory, detect

# Rend langdetect déterministe (sinon résultats variables sur textes courts).
DetectorFactory.seed = 0

_ARABIC_RE = re.compile(r"[؀-ۿ]")

LANG_NAMES = {
    "ar": {"name": "arabe", "english": "Arabic", "native": "العربية", "dir": "rtl"},
    "fr": {"name": "français", "english": "French", "native": "Français", "dir": "ltr"},
    "en": {"name": "anglais", "english": "English", "native": "English", "dir": "ltr"},
}

SUPPORTED = ("ar", "fr", "en")


def detect_language(text: str) -> str:
    """Retourne 'ar', 'fr' ou 'en' (défaut 'en')."""
    if not text or not text.strip():
        return "en"
    # 1) Script arabe = décision immédiate et fiable.
    if _ARABIC_RE.search(text):
        return "ar"
    # 2) langdetect pour le reste, restreint aux langues supportées.
    try:
        code = detect(text)
    except Exception:
        return "en"
    if code.startswith("ar"):
        return "ar"
    if code.startswith("fr"):
        return "fr"
    return "en"

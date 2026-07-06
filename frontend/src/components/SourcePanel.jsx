import React, { useState } from "react";
import SourceCard from "./SourceCard.jsx";

function ConfidencePill({ confidence, t }) {
  if (!confidence || !confidence.level) return null;
  const level = confidence.level;
  const label =
    level === "HIGH" ? t.confHigh : level === "MEDIUM" ? t.confMedium : t.confLow;
  return (
    <span className={`badge conf-${level.toLowerCase()}`}>
      {t.confidence}: {label}
    </span>
  );
}

/**
 * Panneau de sources professionnel.
 * - Fermé par défaut : barre compacte « Sources utilisées (n) · Confidence · Voir détails ».
 * - Au clic, déploiement animé des cards.
 * - Si aucune source pertinente : rien n'est affiché (le message de réponse
 *   indique déjà l'absence de source) — jamais de fausse source.
 */
export default function SourcePanel({ sources, confidence, t }) {
  const [open, setOpen] = useState(false);
  if (!sources || sources.length === 0) return null;

  return (
    <div className={`source-panel ${open ? "is-open" : ""}`}>
      <button className="source-panel-bar" onClick={() => setOpen((o) => !o)}>
        <span className="spb-left">
          <span className="spb-icon">🗂</span>
          <span className="spb-title">
            {t.sources} <span className="spb-count">({sources.length})</span>
          </span>
          <ConfidencePill confidence={confidence} t={t} />
        </span>
        <span className="spb-toggle">
          {open ? t.hideDetails : t.showDetails}
          <span className={`chevron ${open ? "down" : ""}`}>▸</span>
        </span>
      </button>

      <div className={`source-panel-body ${open ? "open" : ""}`}>
        {open &&
          sources.map((s, i) => (
            <SourceCard key={s.id || i} source={s} index={i} t={t} />
          ))}
      </div>
    </div>
  );
}

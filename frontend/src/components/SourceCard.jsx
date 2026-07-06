import React, { useState } from "react";
import { fileUrl, getSource } from "../api.js";
import { detectDir } from "../i18n.js";

function pct(x) {
  return typeof x === "number" ? `${Math.round(x * 100)}%` : null;
}

export default function SourceCard({ source, index, t }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [full, setFull] = useState(null);
  const [loadingFull, setLoadingFull] = useState(false);

  const isPdf = (source.filename || "").toLowerCase().endsWith(".pdf");
  const canOpenPdf = isPdf && source.page && source.source_path;
  const excerpt = source.excerpt || "";

  async function copyExcerpt() {
    try {
      await navigator.clipboard.writeText(excerpt);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (e) {
      /* clipboard indisponible */
    }
  }

  async function toggleExpand() {
    const next = !expanded;
    setExpanded(next);
    // Au premier déploiement, on charge le chunk complet (viewer interne).
    if (next && full === null && source.id) {
      setLoadingFull(true);
      try {
        const data = await getSource(source.id);
        setFull(data?.text || excerpt);
      } catch (e) {
        setFull(excerpt);
      } finally {
        setLoadingFull(false);
      }
    }
  }

  const shownText = expanded ? (loadingFull ? "…" : full ?? excerpt) : null;

  return (
    <div className={`src-card ${expanded ? "is-open" : ""}`}>
      <button className="src-card-head" onClick={toggleExpand} aria-expanded={expanded}>
        <span className="src-card-idx">{index + 1}</span>
        <span className="src-card-meta">
          <span className="src-card-file" title={source.filename}>
            📄 {source.filename}
          </span>
          <span className="src-card-sub">
            {source.page != null && (
              <span>
                {t.page} {source.page}
              </span>
            )}
            {source.section && <span className="src-card-section"> · {source.section}</span>}
          </span>
        </span>
        <span className="src-card-badges">
          {pct(source.similarity) && (
            <span className="badge badge-sim" title={t.score}>
              {pct(source.similarity)}
            </span>
          )}
          {pct(source.rerank_score) && (
            <span className="badge badge-rerank" title="rerank">
              ↻ {pct(source.rerank_score)}
            </span>
          )}
          <span className={`chevron ${expanded ? "down" : ""}`}>▸</span>
        </span>
      </button>

      <div className={`src-card-body ${expanded ? "open" : ""}`}>
        {expanded && (
          <>
            <blockquote className="src-excerpt" dir={detectDir(shownText)}>
              {shownText}
            </blockquote>
            <div className="src-card-actions">
              {canOpenPdf ? (
                <a
                  className="src-btn"
                  href={fileUrl(source.source_path, source.page)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  📄 {t.openPdf} {source.page})
                </a>
              ) : (
                <span className="src-btn disabled" title={t.pathUnavailable}>
                  {t.pathUnavailable}
                </span>
              )}
              <button className="src-btn" onClick={copyExcerpt}>
                {copied ? `✓ ${t.copied}` : `⧉ ${t.copyExcerpt}`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

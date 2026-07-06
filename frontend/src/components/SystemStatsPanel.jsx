import React from "react";

// Formate un nombre avec séparateurs de milliers (13057 -> 13 057).
function fmt(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString();
}

// Raccourcit un nom de modèle long (garde la partie utile pour l'affichage).
function shortModel(name) {
  if (!name) return "—";
  return name.replace(/^intfloat\//, "").replace(/^BAAI\//, "");
}

function Row({ label, value, mono, accent, title }) {
  return (
    <div className="stat-row">
      <span className="stat-label">{label}</span>
      <span
        className={`stat-value${mono ? " mono" : ""}${accent ? " accent" : ""}`}
        title={title != null ? title : (typeof value === "string" ? value : undefined)}
      >
        {value}
      </span>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="stat-section">
      <div className="stat-section-title">{title}</div>
      {children}
    </div>
  );
}

// Ligne « fichiers détectés vs chunks indexés » avec alerte si écart.
function DocRow({ label, detected, indexedChunks, indexedFiles, t }) {
  const notIndexed = detected > 0 && indexedFiles < detected;
  return (
    <div className={`stat-row${notIndexed ? " stat-row-warn" : ""}`}>
      <span className="stat-label">
        {label}
        {notIndexed && <span className="stat-warn-dot" title={t.notIndexed}>!</span>}
      </span>
      <span className="stat-value mono" title={`${t.filesDetected}: ${detected} · ${t.chunksIndexed}: ${indexedChunks}`}>
        {fmt(indexedChunks)}
        <span className="stat-sub"> / {fmt(detected)}</span>
      </span>
    </div>
  );
}

// Sidebar technique : fichiers sur disque vs chunks réellement indexés (/api/stats).
export default function SystemStatsPanel({ stats, t, activeModel }) {
  if (!stats) {
    return (
      <aside className="stats-sidebar" aria-label={t.systemStatus}>
        <div className="stats-header">
          <span className="stats-title">{t.systemStatus}</span>
          <span className="stats-dot off" />
        </div>
        <div className="stats-empty">{t.statsUnavailable}</div>
      </aside>
    );
  }

  const ready = stats.rag_ready;
  const files = stats.files || {};
  const idx = stats.indexed || {};
  const warnings = stats.warnings || [];

  return (
    <aside className="stats-sidebar" aria-label={t.systemStatus}>
      <div className="stats-header">
        <span className="stats-title">{t.systemStatus}</span>
        <span className={`stats-badge ${ready ? "ok" : "off"}`}>
          {ready ? t.ready : t.notReady}
        </span>
      </div>

      {warnings.length > 0 && (
        <div className="stats-warning" role="alert">
          {warnings.map((w, i) => (
            <div key={i} className="stats-warning-line">⚠ {w}</div>
          ))}
        </div>
      )}

      <Section title={t.secIndex}>
        <Row label={t.documentsIndexed} value={fmt(idx.indexed_files_count)} mono />
        <Row label={t.chunks} value={fmt(idx.total_indexed_chunks)} mono accent={ready} />
        <Row label={t.pdfs} value={fmt(files.pdf_count)} mono />
      </Section>

      <Section title={t.secDocuments}>
        <div className="stat-legend">{t.legendChunksFiles}</div>
        <DocRow
          label="Oracle"
          detected={files.oracle_files}
          indexedChunks={idx.indexed_oracle_chunks}
          indexedFiles={idx.indexed_oracle_files}
          t={t}
        />
        <DocRow
          label="PostgreSQL"
          detected={files.postgresql_files}
          indexedChunks={idx.indexed_postgresql_chunks}
          indexedFiles={idx.indexed_postgresql_files}
          t={t}
        />
        <DocRow
          label={t.logsDocs}
          detected={files.logs_files}
          indexedChunks={idx.indexed_logs_chunks}
          indexedFiles={idx.indexed_logs_files}
          t={t}
        />
      </Section>

      <Section title={t.secModels}>
        <Row
          label={t.embedding}
          value={shortModel(stats.embedding_model)}
          title={stats.embedding_model}
          mono
        />
        <Row
          label="Claude"
          value={activeModel || stats.claude_model}
          title={activeModel || stats.claude_model}
          mono
        />
      </Section>

      <Section title={t.secRetrieval}>
        <Row label={t.topK} value={fmt(stats.top_k)} mono />
        <Row
          label={t.threshold}
          value={stats.similarity_threshold != null ? stats.similarity_threshold.toFixed(2) : "—"}
          mono
        />
        <Row label={t.reranker} value={stats.reranker_enabled ? t.enabled : t.disabled} />
      </Section>

      {stats.last_indexed_at && (
        <div className="stats-footer" title={stats.last_indexed_at}>
          {t.lastIndexed}: {new Date(stats.last_indexed_at).toLocaleString()}
        </div>
      )}
    </aside>
  );
}

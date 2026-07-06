import React from "react";
import SourcePanel from "./SourcePanel.jsx";
import { detectDir } from "../i18n.js";

function ConfidenceBadge({ confidence, t }) {
  if (!confidence || !confidence.level) return null;
  const { level, score } = confidence;
  const label =
    level === "HIGH" ? t.confHigh : level === "MEDIUM" ? t.confMedium : t.confLow;
  const pct = typeof score === "number" ? ` ${(score * 100).toFixed(0)}%` : "";
  return (
    <span className={`badge conf-${level.toLowerCase()}`} title={`${t.confidence}: ${label}`}>
      {t.confidence}: {label}
      {pct}
    </span>
  );
}

function QueryHints({ correctedQuery, analysis, t }) {
  const suggestions = (analysis && analysis.suggestions) || [];
  if (!correctedQuery && suggestions.length === 0) return null;
  return (
    <div className="query-hints">
      {correctedQuery && (
        <span className="hint hint-corrected">
          {t.corrected}: <b>{correctedQuery}</b>
        </span>
      )}
      {suggestions.map((s, i) => (
        <span key={i} className="hint hint-suggest">
          {t.didYouMean} <b>{s.to}</b> ?
        </span>
      ))}
    </div>
  );
}

function Timings({ timing, t }) {
  if (!timing || !timing.total_ms) return null;
  const parts = [];
  if (timing.retrieval_ms != null) parts.push(`retrieval ${timing.retrieval_ms}ms`);
  if (timing.rerank_ms != null) parts.push(`rerank ${timing.rerank_ms}ms`);
  if (timing.claude_ms != null) parts.push(`claude ${timing.claude_ms}ms`);
  return (
    <div className="timings">
      ⏱ {t.timings}: {(timing.total_ms / 1000).toFixed(1)}s ({parts.join(" · ")})
    </div>
  );
}

export default function Message({ message, t }) {
  const isUser = message.role === "user";
  const dir = detectDir(message.content);
  const assistant = !isUser && !message.error;

  return (
    <div className={`message ${isUser ? "message-user" : "message-assistant"}`}>
      <div className="message-role">
        {isUser ? t.you : t.assistant}
        {assistant && <ConfidenceBadge confidence={message.confidence} t={t} />}
      </div>

      {assistant && (
        <QueryHints
          correctedQuery={message.correctedQuery}
          analysis={message.queryAnalysis}
          t={t}
        />
      )}

      <div className="message-body" dir={dir}>
        {message.error ? (
          <span className="message-error">
            {t.error}: {message.content}
          </span>
        ) : (
          message.content
        )}
      </div>

      {assistant && (
        <>
          <SourcePanel sources={message.sources} confidence={message.confidence} t={t} />
          <Timings timing={message.timing} t={t} />
        </>
      )}
    </div>
  );
}

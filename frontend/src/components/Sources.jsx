import React, { useState } from "react";
import { getSource, fileUrl } from "../api.js";
import { detectDir } from "../i18n.js";

// Surligne, dans le texte complet du chunk, le passage exact (l'extrait).
function Highlighted({ full, excerpt, dir }) {
  const text = full || "";
  const needle = (excerpt || "").trim();
  const idx = needle ? text.indexOf(needle) : -1;
  if (idx === -1) {
    return (
      <span dir={dir} style={{ whiteSpace: "pre-wrap" }}>
        {text}
      </span>
    );
  }
  return (
    <span dir={dir} style={{ whiteSpace: "pre-wrap" }}>
      {text.slice(0, idx)}
      <mark className="hl">{text.slice(idx, idx + needle.length)}</mark>
      {text.slice(idx + needle.length)}
    </span>
  );
}

export default function Sources({ sources, t }) {
  const [openId, setOpenId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);

  if (!sources || sources.length === 0) return null;

  async function openSource(source) {
    if (openId === source.source_id) {
      setOpenId(null);
      setDetail(null);
      return;
    }
    setOpenId(source.source_id);
    setLoading(true);
    try {
      const data = await getSource(source.source_id);
      setDetail(data);
    } catch (e) {
      setDetail({ text: `${t.error}: ${e.message}` });
    } finally {
      setLoading(false);
    }
  }

  const isPdf = (s) => (s.filename || "").toLowerCase().endsWith(".pdf");

  return (
    <div className="sources">
      <div className="sources-title">{t.sources}</div>
      {sources.map((s, i) => (
        <div className="source-card" key={s.source_id || i}>
          <div className="source-head">
            <span className="source-file">
              📄 {s.filename} · {t.page} {s.page}
              {s.title && <span className="source-section"> · {s.title}</span>}
              {typeof s.rerank_score === "number" ? (
                <span className="source-score">
                  {" "}
                  · {t.score} {(s.rerank_score * 100).toFixed(0)}%
                </span>
              ) : (
                typeof s.score === "number" && (
                  <span className="source-score">
                    {" "}
                    · {t.score} {(s.score * 100).toFixed(0)}%
                  </span>
                )
              )}
            </span>
            <span className="source-actions">
              {isPdf(s) && (
                <a
                  className="link-btn"
                  href={fileUrl(s.source_path, s.page)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t.openPdf} {s.page})
                </a>
              )}
              <button className="link-btn" onClick={() => openSource(s)}>
                {openId === s.source_id ? t.close : t.openSource}
              </button>
            </span>
          </div>
          <blockquote className="source-excerpt" dir={detectDir(s.excerpt)}>
            {s.excerpt}
          </blockquote>
          {openId === s.source_id && (
            <div className="source-detail" dir={detectDir(detail?.text)}>
              {loading ? (
                "..."
              ) : (
                <Highlighted
                  full={detail?.text}
                  excerpt={s.excerpt}
                  dir={detectDir(detail?.text)}
                />
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

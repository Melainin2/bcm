import React, { useEffect, useState } from "react";
import ChatBox from "./components/ChatBox.jsx";
import SystemStatsPanel from "./components/SystemStatsPanel.jsx";
import { getHealth, getStats, sendChat } from "./api.js";
import { LANGUAGES, STRINGS } from "./i18n.js";

const MODEL_KEY = "dbagpt.model";

export default function App() {
  const [lang, setLang] = useState("fr");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [model, setModel] = useState(() => localStorage.getItem(MODEL_KEY) || "");

  const t = STRINGS[lang];
  const dir = LANGUAGES[lang].dir;

  const availableModels = (stats && stats.available_claude_models) || [];

  useEffect(() => {
    document.documentElement.dir = dir;
    document.documentElement.lang = lang;
  }, [lang, dir]);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null));
    getStats().then(setStats).catch(() => setStats(null));
  }, []);

  // Cale le modèle sélectionné sur une valeur autorisée dès que les stats arrivent.
  // Si le modèle stocké (localStorage) n'est plus autorisé (ex. modèle retiré de
  // AVAILABLE_CLAUDE_MODELS), on le remplace ET on met à jour localStorage.
  useEffect(() => {
    if (!availableModels.length) return;
    setModel((current) => {
      if (current && availableModels.includes(current)) return current;
      const next = stats.claude_model && availableModels.includes(stats.claude_model)
        ? stats.claude_model
        : availableModels[0];
      localStorage.setItem(MODEL_KEY, next);
      return next;
    });
  }, [stats]); // eslint-disable-line react-hooks/exhaustive-deps

  // Changement de langue -> on démarre un chat propre (sans relancer de requête).
  useEffect(() => {
    resetChat();
  }, [lang]); // eslint-disable-line react-hooks/exhaustive-deps

  function resetChat() {
    setMessages([]);
    setInput("");
    setLoading(false);
  }

  function handleModelChange(next) {
    setModel(next);
    localStorage.setItem(MODEL_KEY, next);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const question = input.trim();
    if (!question || loading) return;

    setMessages((m) => [...m, { role: "user", content: question }]);
    setInput("");
    setLoading(true);

    try {
      const data = await sendChat(question, { model: model || null });
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: data.answer,
          sources: data.sources,
          confidence: data.confidence,
          language: data.language,
          timing: data.timing,
          correctedQuery: data.corrected_query,
          queryAnalysis: data.query_analysis,
        },
      ]);
    } catch (err) {
      // Message localisé si le backend a fourni un code connu, sinon message propre.
      const localized = (err.code && t.errors && t.errors[err.code]) || err.message;
      setMessages((m) => [
        ...m,
        { role: "assistant", content: localized, error: true },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app" dir={dir}>
      <header className="header">
        <div>
          <h1>{t.title}</h1>
          <p className="subtitle">{t.subtitle}</p>
        </div>
        <div className="header-right">
          <select
            className="lang-select"
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            aria-label="language"
          >
            {Object.entries(LANGUAGES).map(([code, { label }]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>

          {availableModels.length > 0 && (
            <select
              className="model-select"
              value={model}
              onChange={(e) => handleModelChange(e.target.value)}
              aria-label={t.model}
              title={t.model}
            >
              {availableModels.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          )}

          <button
            type="button"
            className="clear-btn"
            onClick={resetChat}
            disabled={messages.length === 0 && !loading}
            title={t.clearChat}
          >
            {t.clearChat}
          </button>
        </div>
      </header>

      {health && (
        <div className="status-bar">
          <span>
            {health.documents_indexed} {t.indexed}
          </span>
          <span>· {model || health.model}</span>
          {!health.api_key_configured && (
            <span className="status-warn"> · {t.noKey}</span>
          )}
        </div>
      )}

      <div className="app-layout">
        <main className="chat-area">
          <ChatBox messages={messages} loading={loading} t={t} />

          <form className="composer" onSubmit={handleSubmit}>
            <input
              className="composer-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t.placeholder}
              disabled={loading}
            />
            <button className="composer-btn" type="submit" disabled={loading}>
              {loading ? t.sending : t.send}
            </button>
          </form>
        </main>

        <SystemStatsPanel stats={stats} t={t} activeModel={model} />
      </div>
    </div>
  );
}

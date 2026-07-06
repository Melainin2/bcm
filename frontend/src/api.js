// URL du backend, configurable au build.
// - Déploiement Render en service unique : laisser VITE_API_BASE_URL vide ("")
//   -> les requêtes /api/* pointent vers le MÊME domaine que le frontend.
// - Dev local (frontend :5173, backend séparé) : définir VITE_API_BASE_URL
//   (ex. http://localhost:8001) dans frontend/.env.
// On utilise `??` (et non `||`) pour respecter une valeur vide explicite.
const API_URL =
  import.meta.env.VITE_API_BASE_URL ??
  import.meta.env.VITE_API_URL ??
  "";

export async function getHealth() {
  const res = await fetch(`${API_URL}/api/health`);
  if (!res.ok) throw new Error(`Health ${res.status}`);
  return res.json();
}

export async function getStats() {
  const res = await fetch(`${API_URL}/api/stats`);
  if (!res.ok) throw new Error(`Stats ${res.status}`);
  return res.json();
}

// Envoie une question. `opts` : { model, topK }. Le modèle sélectionné dans
// l'interface est transmis au backend, qui le valide et l'utilise pour Claude.
export async function sendChat(question, opts = {}) {
  const { model = null, topK = null } = opts;
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, top_k: topK, model }),
  });
  if (!res.ok) {
    // Le backend renvoie soit une string, soit {code, message}. On n'expose
    // JAMAIS de JSON Anthropic brut : on extrait uniquement code + message.
    let message = `Erreur ${res.status}`;
    let code = null;
    try {
      const data = await res.json();
      const detail = data.detail;
      if (detail && typeof detail === "object") {
        code = detail.code || null;
        message = detail.message || message;
      } else if (typeof detail === "string") {
        message = detail;
      }
    } catch (e) {
      /* réponse non-JSON : on garde le message générique */
    }
    const err = new Error(message);
    err.code = code;
    throw err;
  }
  return res.json();
}

export async function getSource(sourceId) {
  const res = await fetch(`${API_URL}/api/source/${encodeURIComponent(sourceId)}`);
  if (!res.ok) throw new Error(`Source ${res.status}`);
  return res.json();
}

// URL du fichier source original (PDF), ouvrable à une page précise via #page=N.
export function fileUrl(sourcePath, page) {
  const path = String(sourcePath || "")
    .split("/")
    .map(encodeURIComponent)
    .join("/");
  const anchor = page ? `#page=${page}` : "";
  return `${API_URL}/api/file/${path}${anchor}`;
}

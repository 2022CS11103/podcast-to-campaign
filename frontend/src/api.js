const configuredBase = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
export const API_BASE = configuredBase || (import.meta.env.DEV ? "/api" : "");

let accessTokenProvider = async () => null;

export function setAccessTokenProvider(provider) {
  accessTokenProvider = provider;
}

export function apiUrl(path) {
  if (/^https?:\/\//i.test(path || "")) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function apiFetch(path, options = {}) {
  const token = await accessTokenProvider();
  const headers = new Headers(options.headers || {});
  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(apiUrl(path), { ...options, headers });
  const type = response.headers.get("content-type") || "";
  const data = type.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      (typeof data === "object" && (data.detail || data.error)) ||
      (typeof data === "string" && data) ||
      `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data;
}

export const creatorApi = {
  accounts: () => apiFetch("/accounts"),
  disconnectYouTube: () =>
    apiFetch("/disconnect/youtube", { method: "POST" }),
  startCampaign: (payload) =>
    apiFetch("/process", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  status: (jobId) => apiFetch(`/status/${jobId}`),
  board: () => apiFetch("/campaign-board"),
  recommendPlan: (brandContext) =>
    apiFetch("/recommend-plan", {
      method: "POST",
      body: JSON.stringify({ brand_context: brandContext }),
    }),
  uploadSource: (file) => {
    const body = new FormData();
    body.append("file", file);
    return apiFetch("/uploads/video", { method: "POST", body });
  },
  uploadYouTube: (itemId) =>
    apiFetch("/youtube/upload", {
      method: "POST",
      body: JSON.stringify({
        item_id: itemId || null,
        privacy_status: "private",
        made_for_kids: false,
      }),
    }),
};

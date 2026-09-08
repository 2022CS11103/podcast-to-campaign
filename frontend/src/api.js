const configuredBase = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
export const API_BASE = configuredBase || (import.meta.env.DEV ? "/api" : "");

let accessTokenProvider = async () => null;
let userEmailProvider = async () => null;

export function setAccessTokenProvider(provider) {
  accessTokenProvider = provider;
}

export function setUserEmailProvider(provider) {
  userEmailProvider = provider;
}

export function apiUrl(path) {
  if (/^https?:\/\//i.test(path || "")) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function apiFetch(path, options = {}) {
  const token = await accessTokenProvider();
  const email = await userEmailProvider();
  const headers = new Headers(options.headers || {});
  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (email) headers.set("X-User-Email", email);

  const response = await fetch(apiUrl(path), { ...options, headers });
  const type = response.headers.get("content-type") || "";
  const data = type.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail = typeof data === "object" ? data.detail : null;
    const message =
      (typeof detail === "object" && detail?.message) ||
      (typeof detail === "string" && detail) ||
      (typeof data === "object" && data.error) ||
      (typeof data === "string" && data) ||
      `Request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    error.detail = detail;
    error.payload = data;
    throw error;
  }
  return data;
}

export const creatorApi = {
  accounts: () => apiFetch("/accounts"),
  disconnectAccount: (platform) =>
    apiFetch(`/disconnect/${platform}`, { method: "POST" }),
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
  getBrand: () => apiFetch("/brand"),
  saveBrand: (payload) =>
    apiFetch("/brand", { method: "PUT", body: JSON.stringify(payload) }),
  uploadLogo: (file) => {
    const body = new FormData();
    body.append("file", file);
    return apiFetch("/uploads/logo", { method: "POST", body });
  },
  clearLogo: () => apiFetch("/brand/logo", { method: "DELETE" }),
  uploadYouTube: (itemId) =>
    apiFetch("/youtube/upload", {
      method: "POST",
      body: JSON.stringify({
        item_id: itemId || null,
        privacy_status: "private",
        made_for_kids: false,
      }),
    }),
  stopJob: (jobId, payload = {}) =>
    apiFetch(`/jobs/${jobId}/stop`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  reduceScope: (jobId, plan) =>
    apiFetch(`/jobs/${jobId}/scope`, {
      method: "POST",
      body: JSON.stringify({ plan }),
    }),
  calendar: (year, month) => {
    const query = year && month ? `?year=${year}&month=${month}` : "";
    return apiFetch(`/campaign-calendar${query}`);
  },
  holdPlatform: (platform, year, month) =>
    apiFetch("/schedule/hold", { method: "POST", body: JSON.stringify({ platform, year, month }) }),
  resumePlatform: (platform, year, month) =>
    apiFetch("/schedule/resume", { method: "POST", body: JSON.stringify({ platform, year, month }) }),
  skipPost: (itemId, year, month) =>
    apiFetch(`/schedule/skip/${itemId}`, { method: "POST", body: JSON.stringify({ year, month }) }),
  pausePost: (itemId, year, month) =>
    apiFetch(`/schedule/pause/${itemId}`, { method: "POST", body: JSON.stringify({ year, month }) }),
  resumePost: (itemId, year, month) =>
    apiFetch(`/schedule/resume-item/${itemId}`, { method: "POST", body: JSON.stringify({ year, month }) }),
  setPostStatus: (itemId, status, year, month) =>
    apiFetch(`/schedule/status/${itemId}`, { method: "POST", body: JSON.stringify({ status, year, month }) }),
  reviewBulk: (payload = {}) =>
    apiFetch("/review/bulk", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  authConfig: () => apiFetch("/auth/config"),
  transcript: (source) =>
    apiFetch(source ? `/transcript?source=${encodeURIComponent(source)}` : "/transcript"),
  fetchClip: (payload = {}) =>
    apiFetch("/tools/fetch-clip", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  transcribeClip: (payload = {}) =>
    apiFetch("/tools/transcribe-clip", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  billingStatus: () => apiFetch("/billing/status"),
  createCheckout: (payload = {}) =>
    apiFetch("/billing/checkout", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  createPortal: (payload = {}) =>
    apiFetch("/billing/portal", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

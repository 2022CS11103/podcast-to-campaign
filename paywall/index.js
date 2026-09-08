/**
 * creatorOS paywall — zero-dependency Node server (same shape as proxy.js).
 *
 *   pm2 delete creatoros-paywall
 *   pm2 start paywall/index.js --name creatoros-paywall
 *
 * Listens on 127.0.0.1:8000 so nginx / p2m can proxy to it.
 */
const fs = require("fs");
const http = require("http");
const https = require("https");
const path = require("path");

const PORT = Number(process.env.PORT || 8000);
const HOST = process.env.HOST || "127.0.0.1";
const PUBLIC_DIR = path.join(__dirname, "public");

loadEnv(path.join(__dirname, ".env"));
loadEnv(path.join(__dirname, "..", ".env"));

/** Where the FastAPI studio lives (landing CTAs open signup here). */
function resolveStudioUrl() {
  const fromEnv = String(process.env.STUDIO_URL || "").trim();
  if (fromEnv) {
    // Prefer signup entry for marketing CTAs unless already query-shaped.
    if (/[?&]mode=/.test(fromEnv) || /signup=/.test(fromEnv)) return fromEnv;
    const base = fromEnv.replace(/\/?$/, "/");
    return `${base}?mode=signup`;
  }
  const publicUrl = String(process.env.PUBLIC_URL || "").trim().replace(/\/$/, "");
  if (publicUrl) return `${publicUrl}/app/?mode=signup`;
  return "http://127.0.0.1:8002/app/?mode=signup";
}
const STUDIO_URL = resolveStudioUrl();

const TRIAL_DAYS = Math.max(0, Number(process.env.STRIPE_TRIAL_DAYS || 7));

const PLANS = {
  starter: {
    id: "starter",
    name: "Starter",
    tagline: "A light cadence from a couple of source videos.",
    monthly: 2900,
    yearly: 29000,
  },
  creator: {
    id: "creator",
    name: "Creator",
    popular: true,
    tagline: "One video in. A month of content across every channel.",
    monthly: 8900,
    yearly: 89000,
  },
  studio: {
    id: "studio",
    name: "Studio",
    tagline: "Unlimited runs for teams that ship every week.",
    monthly: 19900,
    yearly: 199000,
  },
};

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".webp": "image/webp",
  ".json": "application/json; charset=utf-8",
};

function loadEnv(file) {
  if (!fs.existsSync(file)) return;
  for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq < 1) continue;
    const key = trimmed.slice(0, eq).trim();
    if (process.env[key] != null) continue;
    let value = trimmed.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    process.env[key] = value;
  }
}

function stripeMode() {
  const key = process.env.STRIPE_SECRET_KEY || "";
  if (key.startsWith("sk_live_") || key.startsWith("rk_live_")) return "live";
  if (key.startsWith("sk_test_") || key.startsWith("rk_test_")) return "test";
  return key ? "unknown" : "off";
}

function envKey(planId, interval, kind) {
  return `STRIPE_${kind}_${planId.toUpperCase()}_${interval === "year" ? "YEARLY" : "MONTHLY"}`;
}

function send(res, status, body, headers) {
  const payload = Buffer.from(body);
  res.writeHead(status, {
    "Content-Length": payload.length,
    ...headers,
  });
  res.end(payload);
}

function sendJson(res, status, data) {
  send(res, status, JSON.stringify(data), {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
}

function sendFile(res, filePath) {
  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(path.resolve(PUBLIC_DIR))) {
    send(res, 403, "Forbidden", { "Content-Type": "text/plain; charset=utf-8" });
    return;
  }
  fs.readFile(resolved, (err, data) => {
    if (err) {
      send(res, 404, "Not found", { "Content-Type": "text/plain; charset=utf-8" });
      return;
    }
    let body = data;
    const ext = path.extname(resolved);
    // Inject studio URL so CTA buttons always deep-link into the app.
    if (ext === ".html") {
      const html = data.toString("utf8").replace(
        /<\/head>/i,
        `<script>window.__CREATOROS_STUDIO__=${JSON.stringify(STUDIO_URL)};</script>\n</head>`,
      );
      body = Buffer.from(html);
    }
    send(res, 200, body, {
      "Content-Type": MIME[ext] || "application/octet-stream",
      "Cache-Control": [".html", ".css", ".js"].includes(ext)
        ? "no-store"
        : "public, max-age=3600",
    });
  });
}

function publicOrigin(req) {
  const configured = String(process.env.PUBLIC_URL || "").replace(/\/$/, "");
  if (configured) return configured;
  const host = req.headers["x-forwarded-host"] || req.headers.host || `${HOST}:${PORT}`;
  const proto = req.headers["x-forwarded-proto"] || "https";
  return `${proto}://${host}`;
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > 32 * 1024) {
        reject(new Error("body too large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function encodeForm(data, prefix) {
  const parts = [];
  for (const [key, value] of Object.entries(data)) {
    if (value == null || value === false) continue;
    const name = prefix ? `${prefix}[${key}]` : key;
    if (Array.isArray(value)) {
      value.forEach((item, index) => {
        if (item && typeof item === "object") parts.push(encodeForm(item, `${name}[${index}]`));
        else parts.push(`${encodeURIComponent(`${name}[${index}]`)}=${encodeURIComponent(String(item))}`);
      });
    } else if (typeof value === "object") {
      parts.push(encodeForm(value, name));
    } else if (value === true) {
      parts.push(`${encodeURIComponent(name)}=true`);
    } else {
      parts.push(`${encodeURIComponent(name)}=${encodeURIComponent(String(value))}`);
    }
  }
  return parts.filter(Boolean).join("&");
}

function stripeRequest(method, apiPath, form) {
  const key = process.env.STRIPE_SECRET_KEY;
  if (!key) return Promise.reject(new Error("missing Stripe key"));
  const body = form ? encodeForm(form) : "";
  return new Promise((resolve, reject) => {
    const req = https.request(
      {
        hostname: "api.stripe.com",
        path: apiPath,
        method,
        headers: {
          Authorization: `Bearer ${key}`,
          "Content-Type": "application/x-www-form-urlencoded",
          "Content-Length": Buffer.byteLength(body),
        },
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          let json = {};
          try {
            json = JSON.parse(text);
          } catch {
            json = { error: { message: text || "Stripe returned an empty response" } };
          }
          if (res.statusCode >= 400) {
            reject(new Error(json.error?.message || `Stripe HTTP ${res.statusCode}`));
            return;
          }
          resolve(json);
        });
      },
    );
    req.on("error", reject);
    req.end(body);
  });
}

async function checkout(req, res) {
  let payload = {};
  try {
    payload = JSON.parse((await readBody(req)) || "{}");
  } catch {
    sendJson(res, 400, { error: "Invalid checkout request." });
    return;
  }
  const planId = String(payload.plan || "").toLowerCase();
  const interval = payload.interval === "year" ? "year" : "month";
  const plan = PLANS[planId];
  if (!plan) {
    sendJson(res, 400, { error: "Choose a Starter, Creator, or Studio plan." });
    return;
  }

  const paymentLink = process.env[envKey(planId, interval, "LINK")];
  if (paymentLink) {
    sendJson(res, 200, { url: paymentLink });
    return;
  }
  if (!process.env.STRIPE_SECRET_KEY) {
    sendJson(res, 503, {
      error: "Checkout is not configured yet. Add STRIPE_SECRET_KEY or a Stripe Payment Link.",
    });
    return;
  }

  const origin = publicOrigin(req);
  const priceId = process.env[envKey(planId, interval, "PRICE")];
  const amount = interval === "year" ? plan.yearly : plan.monthly;
  const label = interval === "year" ? `${plan.name} · yearly` : `${plan.name} · monthly`;
  const form = {
    mode: "subscription",
    allow_promotion_codes: "true",
    billing_address_collection: "auto",
    success_url: `${origin}/success.html?session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${origin}/#pricing`,
    metadata: { plan: plan.id, interval, product: "creatorOS" },
    subscription_data: {
      metadata: { plan: plan.id, interval },
      ...(TRIAL_DAYS > 0 ? { trial_period_days: TRIAL_DAYS } : {}),
    },
    line_items: [
      priceId
        ? { quantity: 1, price: priceId }
        : {
            quantity: 1,
            price_data: {
              currency: "usd",
              unit_amount: amount,
              recurring: { interval },
              product_data: {
                name: `creatorOS ${label}`,
                description: plan.tagline,
              },
            },
          },
    ],
  };

  try {
    const session = await stripeRequest("POST", "/v1/checkout/sessions", form);
    sendJson(res, 200, { url: session.url });
  } catch (error) {
    console.error("Stripe checkout failed:", error.message);
    sendJson(res, 502, { error: "Stripe could not start checkout. Check the API key and try again." });
  }
}

async function sessionLookup(req, res, url) {
  const id = String(url.searchParams.get("session_id") || "");
  if (!process.env.STRIPE_SECRET_KEY || !id.startsWith("cs_")) {
    sendJson(res, 200, { ok: false });
    return;
  }
  try {
    const session = await stripeRequest("GET", `/v1/checkout/sessions/${encodeURIComponent(id)}`);
    const plan = PLANS[session.metadata?.plan] || null;
    sendJson(res, 200, {
      ok: session.status === "complete" || session.payment_status === "paid" || session.status === "open",
      email: session.customer_details?.email || session.customer_email || "",
      plan: plan ? plan.name : session.metadata?.plan || "",
      interval: session.metadata?.interval || "",
    });
  } catch (error) {
    console.error("Stripe session lookup failed:", error.message);
    sendJson(res, 200, { ok: false });
  }
}

function handler(req, res) {
  const url = new URL(req.url || "/", `http://${req.headers.host || `${HOST}:${PORT}`}`);
  const route = url.pathname.replace(/\/+$/, "") || "/";

  if (req.method === "GET" && route === "/health") {
    sendJson(res, 200, { status: "ok", service: "creatoros-paywall", stripe: stripeMode(), port: PORT, studio: STUDIO_URL });
    return;
  }
  if (req.method === "GET" && route === "/api/config") {
    sendJson(res, 200, { studioUrl: STUDIO_URL, paywall: false });
    return;
  }
  if (req.method === "GET" && route === "/api/plans") {
    sendJson(res, 200, { trialDays: TRIAL_DAYS, stripe: stripeMode(), plans: Object.values(PLANS) });
    return;
  }
  if (req.method === "POST" && route === "/api/checkout") {
    sendJson(res, 503, { error: "Checkout is paused — open the studio to explore for free." });
    return;
  }
  if (req.method === "GET" && route === "/api/session") {
    sessionLookup(req, res, url).catch((error) => {
      console.error(error);
      sendJson(res, 200, { ok: false });
    });
    return;
  }
  if (req.method === "GET" || req.method === "HEAD") {
    if (
      route === "/app"
      || route === "/login"
      || route === "/signup"
      || route === "/open-studio"
      || route === "/try"
      || route === "/demo"
      || route === "/trial"
      || route === "/free-demo"
    ) {
      res.writeHead(302, { Location: STUDIO_URL });
      res.end();
      return;
    }
    if (route === "/") {
      sendFile(res, path.join(PUBLIC_DIR, "index.html"));
      return;
    }
    const relative = decodeURIComponent(url.pathname);
    const filePath = path.join(PUBLIC_DIR, relative);
    fs.stat(filePath, (err, stat) => {
      if (!err && stat.isFile()) {
        sendFile(res, filePath);
        return;
      }
      sendFile(res, path.join(PUBLIC_DIR, "index.html"));
    });
    return;
  }
  send(res, 405, "Method not allowed", { "Content-Type": "text/plain; charset=utf-8" });
}

const server = http.createServer(handler);
server.on("error", (error) => {
  console.error(`Paywall failed to bind http://${HOST}:${PORT}:`, error.message);
  process.exit(1);
});
server.listen(PORT, HOST, () => {
  console.log(`creatorOS landing on http://${HOST}:${PORT}  studio=${STUDIO_URL}  (checkout paused)`);
});

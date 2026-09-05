/**
 * creatorOS paywall — independent one-pager with Stripe subscriptions.
 *
 *   cd paywall
 *   npm install
 *   cp .env.example .env    # add STRIPE_SECRET_KEY
 *   npm start               # or: pm2 start ecosystem.config.cjs
 *
 * Listens on port 8000. Does not start the Python studio.
 */
const path = require("path");
const express = require("express");
const Stripe = require("stripe");

require("dotenv").config({ path: path.join(__dirname, ".env") });
require("dotenv").config({ path: path.join(__dirname, "..", ".env") });

const PORT = Number(process.env.PORT || 8000);
const PUBLIC_DIR = path.join(__dirname, "public");
const TRIAL_DAYS = Math.max(0, Number(process.env.STRIPE_TRIAL_DAYS || 7));

const PLANS = {
  starter: {
    id: "starter",
    name: "Starter",
    tagline: "A light cadence from a couple of source videos.",
    monthly: 2900,
    yearly: 29000,
    features: [
      "2 source videos each month",
      "YouTube Shorts and Instagram Reels",
      "14-day content calendar",
      "Captions burned into every cut",
      "Email support",
    ],
  },
  creator: {
    id: "creator",
    name: "Creator",
    popular: true,
    tagline: "One video in. A month of content across every channel.",
    monthly: 8900,
    yearly: 89000,
    features: [
      "12 source videos each month",
      "Shorts, Reels, LinkedIn, and X",
      "30-day calendar with pause and skip",
      "Platform-specific copy, not copy-paste",
      "Brand end screens and logo",
      "Priority email support",
    ],
  },
  studio: {
    id: "studio",
    name: "Studio",
    tagline: "Unlimited runs for teams that ship every week.",
    monthly: 19900,
    yearly: 199000,
    features: [
      "Unlimited source videos",
      "Everything in Creator",
      "Multiple workspaces and brands",
      "Priority processing queue",
      "Shared calendar control",
      "Onboarding call",
    ],
  },
};

function envKey(planId, interval, kind) {
  return `STRIPE_${kind}_${planId.toUpperCase()}_${interval.toUpperCase() === "year" ? "YEARLY" : "MONTHLY"}`;
}

function publicOrigin(req) {
  const configured = String(process.env.PUBLIC_URL || "").replace(/\/$/, "");
  if (configured) return configured;
  const host = req.get("host") || `127.0.0.1:${PORT}`;
  return `${req.protocol}://${host}`;
}

function stripeClient() {
  const key = process.env.STRIPE_SECRET_KEY;
  if (!key) return null;
  return new Stripe(key);
}

function stripeMode() {
  const key = process.env.STRIPE_SECRET_KEY || "";
  if (key.startsWith("sk_live_")) return "live";
  if (key.startsWith("sk_test_")) return "test";
  return key ? "unknown" : "off";
}

const app = express();
app.set("trust proxy", 1);
app.use(express.json({ limit: "32kb" }));
app.use(express.static(PUBLIC_DIR, { index: false, maxAge: "1h" }));

app.get("/health", (_req, res) => {
  res.json({ status: "ok", service: "creatoros-paywall", stripe: stripeMode() });
});

app.get("/api/plans", (_req, res) => {
  res.json({
    trialDays: TRIAL_DAYS,
    stripe: stripeMode(),
    plans: Object.values(PLANS),
  });
});

app.post("/api/checkout", async (req, res) => {
  const planId = String(req.body?.plan || "").toLowerCase();
  const interval = req.body?.interval === "year" ? "year" : "month";
  const plan = PLANS[planId];
  if (!plan) {
    res.status(400).json({ error: "Choose a Starter, Creator, or Studio plan." });
    return;
  }

  const paymentLink = process.env[envKey(planId, interval, "LINK")];
  if (paymentLink) {
    res.json({ url: paymentLink });
    return;
  }

  const stripe = stripeClient();
  if (!stripe) {
    res.status(503).json({
      error: "Checkout is not configured yet. Add STRIPE_SECRET_KEY or a Stripe Payment Link.",
    });
    return;
  }

  const origin = publicOrigin(req);
  const priceId = process.env[envKey(planId, interval, "PRICE")];
  const amount = interval === "year" ? plan.yearly : plan.monthly;
  const label = interval === "year" ? `${plan.name} · yearly` : `${plan.name} · monthly`;

  try {
    const session = await stripe.checkout.sessions.create({
      mode: "subscription",
      allow_promotion_codes: true,
      billing_address_collection: "auto",
      success_url: `${origin}/success.html?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${origin}/#pricing`,
      metadata: { plan: plan.id, interval, product: "creatorOS" },
      subscription_data: {
        metadata: { plan: plan.id, interval },
        ...(TRIAL_DAYS > 0 ? { trial_period_days: TRIAL_DAYS } : {}),
      },
      line_items: [
        {
          quantity: 1,
          ...(priceId
            ? { price: priceId }
            : {
                price_data: {
                  currency: "usd",
                  unit_amount: amount,
                  recurring: { interval },
                  product_data: {
                    name: `creatorOS ${label}`,
                    description: plan.tagline,
                  },
                },
              }),
        },
      ],
    });
    res.json({ url: session.url });
  } catch (error) {
    console.error("Stripe checkout failed:", error.message);
    res.status(502).json({ error: "Stripe could not start checkout. Check the API key and try again." });
  }
});

app.get("/api/session", async (req, res) => {
  const id = String(req.query.session_id || "");
  const stripe = stripeClient();
  if (!stripe || !id.startsWith("cs_")) {
    res.json({ ok: false });
    return;
  }
  try {
    const session = await stripe.checkout.sessions.retrieve(id);
    const plan = PLANS[session.metadata?.plan] || null;
    res.json({
      ok: session.status === "complete" || session.payment_status === "paid" || session.status === "open",
      email: session.customer_details?.email || session.customer_email || "",
      plan: plan ? plan.name : session.metadata?.plan || "",
      interval: session.metadata?.interval || "",
    });
  } catch (error) {
    console.error("Stripe session lookup failed:", error.message);
    res.json({ ok: false });
  }
});

app.get(["/", "/app", "/app/", "/login", "/signup"], (_req, res) => {
  res.sendFile(path.join(PUBLIC_DIR, "index.html"));
});

app.use((req, res, next) => {
  if (req.method !== "GET" && req.method !== "HEAD") {
    next();
    return;
  }
  if (req.path.includes(".")) {
    next();
    return;
  }
  res.sendFile(path.join(PUBLIC_DIR, "index.html"));
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`creatorOS paywall  http://0.0.0.0:${PORT}  stripe=${stripeMode()}`);
});

import { useEffect, useMemo, useState } from "react";
import { Check, CreditCard, LoaderCircle, Sparkles } from "lucide-react";
import { creatorApi } from "./api";
import { useAuth } from "./auth";

export const FALLBACK_PLANS = [
  {
    id: "campaign_14",
    name: "Sprint · 14 days",
    days: 14,
    interval: "month",
    price_label: "$19/mo",
    price_id: "",
    blurb: "Two-week content burst — ideal for a product launch or client pilot.",
    features: [
      "Up to 14-day content calendar",
      "Shorts + Reels + LinkedIn + X posts",
      "Platform-specific captions (not copy-paste)",
      "Human review board before publish",
    ],
  },
  {
    id: "campaign_30",
    name: "Standard · 30 days",
    days: 30,
    interval: "month",
    price_label: "$29/mo",
    price_id: "",
    blurb: "Full month strategy — the default CreatorOS campaign length.",
    features: [
      "Up to 30-day content calendar",
      "Everything in Sprint",
      "Brand end screens / client rebrand",
      "Partial URL download by timespan",
    ],
  },
  {
    id: "campaign_45",
    name: "Growth · 45 days",
    days: 45,
    interval: "month",
    price_label: "$39/mo",
    price_id: "",
    blurb: "Six weeks of runway for agencies juggling a longer client cycle.",
    features: [
      "Up to 45-day content calendar",
      "Everything in Standard",
      "More slots for LinkedIn + X cadence",
      "Transcript desk for editors",
    ],
  },
  {
    id: "campaign_60",
    name: "Scale · 60 days",
    days: 60,
    interval: "month",
    price_label: "$49/mo",
    price_id: "",
    blurb: "Two-month plan — longest calendar option in the campaign picker.",
    features: [
      "Up to 60-day content calendar",
      "Everything in Growth",
      "Best for multi-client agency desks",
      "Unlocks every duration below",
    ],
  },
];

/** Always surface 14/30/45/60 packs, even if the API still returns legacy Creator Pro rows. */
export function normalizePlans(apiPlans) {
  const incoming = Array.isArray(apiPlans) ? apiPlans : [];
  const byDays = new Map();
  for (const plan of incoming) {
    const days = Number(plan?.days);
    if (days === 14 || days === 30 || days === 45 || days === 60) {
      byDays.set(days, plan);
    }
  }
  const durationPlans = FALLBACK_PLANS.map((fallback) => {
    const match = byDays.get(fallback.days) || {};
    return {
      ...fallback,
      ...match,
      id: match.id || fallback.id,
      name: match.name || fallback.name,
      days: fallback.days,
      blurb: match.blurb || fallback.blurb,
      features: (match.features && match.features.length ? match.features : fallback.features),
      price_label: match.price_label || fallback.price_label,
      price_id: match.price_id || "",
      interval: match.interval || "month",
    };
  });

  const extras = incoming.filter((plan) => {
    const id = String(plan?.id || "");
    const days = Number(plan?.days);
    if (id.startsWith("campaign_")) return false;
    if ([14, 30, 45, 60].includes(days)) return false;
    // Keep optional yearly unlock if present
    return id === "pro_yearly" || plan?.interval === "year";
  }).map((plan) => ({
    ...plan,
    days: Number(plan.days) || 60,
    blurb: plan.blurb || "Annual unlock — all campaign durations.",
    features: plan.features || ["All 14 / 30 / 45 / 60-day calendars"],
  }));

  return [...durationPlans, ...extras];
}

export function recommendPlan(plans, durationDays) {
  const list = normalizePlans(plans);
  const want = Number(durationDays) || 30;
  const exact = list.find((p) => Number(p.days) === want && String(p.id).startsWith("campaign_"));
  if (exact) return exact;
  const covering = [...list]
    .filter((p) => Number(p.days) >= want)
    .sort((a, b) => Number(a.days) - Number(b.days));
  return covering[0] || list[list.length - 1] || null;
}

function isSubscribed(billing) {
  if (!billing?.billing_enabled || !billing?.checkout_ready) return false;
  const maxDays = Number(billing?.max_campaign_days || 0);
  const status = String(billing?.status || "").toLowerCase();
  if (maxDays <= 0) return false;
  if (["none", "canceled", "cancelled", "incomplete"].includes(status)) return false;
  return Boolean(billing?.entitled) && maxDays > 0;
}

/** Paywall only when Stripe checkout is explicitly ready to charge. */
export function paywallActive(billing) {
  return Boolean(
    billing?.billing_enabled
    && billing?.checkout_ready === true
    && billing?.entitled === false
  );
}

export function checkoutIsReady(billing) {
  return Boolean(billing?.billing_enabled && billing?.checkout_ready === true);
}

export function useBilling() {
  const auth = useAuth();
  const [billing, setBilling] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await creatorApi.billingStatus();
      setBilling(data);
      return data;
    } catch (err) {
      setError(err.message || "Could not load billing.");
      setBilling({
        billing_enabled: false,
        checkout_ready: false,
        billing_preview: true,
        entitled: true,
        status: "dev",
        plan: "dev",
        max_campaign_days: 60,
        plans: FALLBACK_PLANS,
        message: null,
      });
      return null;
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    return undefined;
  }, [auth?.user?.email]);

  const startCheckout = async (priceId, campaignDays) => {
    setBusy(true);
    setError("");
    try {
      if (!checkoutIsReady(billing)) {
        throw new Error(
          "Billing is optional while testing — generate campaigns freely. "
          + "Add BILLING_ENABLED=true, BILLING_ENFORCE=true, and a valid Stripe key only when you want to charge."
        );
      }
      if (!auth.user?.email) {
        throw new Error("Sign in first, then subscribe.");
      }
      const data = await creatorApi.createCheckout({
        email: auth.user?.email,
        user_id: auth.user?.id || "",
        price_id: priceId || "",
        campaign_days: campaignDays || undefined,
      });
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
        return;
      }
      throw new Error("Stripe did not return a checkout URL.");
    } catch (err) {
      const raw = err.message || "Checkout failed.";
      if (/invalid api key|authentication/i.test(raw)) {
        setError(
          "Stripe key is invalid. For testing, leave BILLING_ENFORCE unset (or set BILLING_ENABLED=false) and restart — packs stay as preview only."
        );
      } else {
        setError(raw);
      }
    } finally {
      setBusy(false);
    }
  };

  const openPortal = async () => {
    setBusy(true);
    setError("");
    try {
      if (!auth.user?.email) {
        throw new Error("Sign in first to manage billing.");
      }
      const data = await creatorApi.createPortal({ email: auth.user?.email });
      if (data.portal_url) {
        window.location.href = data.portal_url;
        return;
      }
      throw new Error("Stripe did not return a portal URL.");
    } catch (err) {
      setError(err.message || "Billing portal failed.");
    } finally {
      setBusy(false);
    }
  };

  return { billing, loading, error, busy, refresh, startCheckout, openPortal, setError };
}

export function PaywallCard({
  title = "Unlock a campaign pack",
  description = "Plans match your campaign duration: 14, 30, 45, or 60 days.",
  onUpgrade,
  busy = false,
  plans = FALLBACK_PLANS,
  durationDays = 30,
  billingEnabled = false,
}) {
  const recommended = useMemo(() => recommendPlan(plans, durationDays), [plans, durationDays]);
  return (
    <section className="panel campaign-panel paywall-card">
      <div className="section-heading">
        <div>
          <span className="overline">Campaign packs</span>
          <h2>{title}</h2>
        </div>
        <Sparkles size={20} />
      </div>
      <p className="account-copy">{description}</p>
      <p className="account-copy">
        Your campaign is set to <strong>{durationDays} days</strong>
        {recommended ? <> — recommended pack: <strong>{recommended.name}</strong></> : null}.
      </p>
      <div className="page-actions">
        <button
          className="primary-button"
          onClick={() => onUpgrade?.(recommended?.price_id, durationDays)}
          disabled={busy || (billingEnabled && !recommended?.price_id)}
        >
          {busy ? <LoaderCircle className="spin" size={16} /> : <CreditCard size={16} />}
          {recommended ? `Get ${recommended.name}` : "Upgrade with Stripe"}
        </button>
      </div>
    </section>
  );
}

function PlanCards({ plans, subscribed, billingEnabled, busy, onSubscribe, durationDays, maxDays }) {
  return (
    <div className="billing-plans billing-plans-duration">
      {plans.map((plan) => {
        const days = Number(plan.days) || 0;
        const recommended = Number(durationDays) === days && String(plan.id).startsWith("campaign_");
        const covered = Boolean(subscribed && days > 0 && Number(maxDays) >= days);
        const canBuy = billingEnabled && !covered && Boolean(plan.price_id);
        return (
          <div className={`billing-plan ${recommended ? "is-recommended" : ""}`} key={plan.id}>
            <div className="billing-plan-head">
              <strong>{plan.name}</strong>
              {recommended ? <span className="billing-badge">Matches your campaign</span> : null}
              {covered ? <span className="billing-badge ok">Included</span> : null}
            </div>
            <span className="billing-price">{plan.price_label}</span>
            <p className="billing-blurb">{plan.blurb}</p>
            <ul>
              {(plan.features || []).map((feature) => (
                <li key={feature}><Check size={14} /> {feature}</li>
              ))}
            </ul>
            {covered ? (
              <p className="billing-note">Your plan covers this duration</p>
            ) : (
              <button
                className="primary-button"
                disabled={busy || (billingEnabled && !canBuy)}
                onClick={() => onSubscribe(plan.price_id, days)}
              >
                {busy ? <LoaderCircle className="spin" size={16} /> : null}
                {!billingEnabled
                  ? "Preview only"
                  : plan.price_id
                    ? `Subscribe · ${days} days`
                    : "Add Stripe price ID"}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function BillingPanel({ durationDays = 30 }) {
  const { billing, loading, error, busy, refresh, startCheckout, openPortal } = useBilling();
  const params = new URLSearchParams(window.location.search);
  const billingFlag = params.get("billing");

  useEffect(() => {
    if (billingFlag === "success") {
      refresh();
    }
  }, [billingFlag]);

  if (loading) {
    return (
      <section className="panel campaign-panel billing-panel" id="billing">
        <p className="account-copy"><LoaderCircle className="spin" size={16} /> Loading billing…</p>
      </section>
    );
  }

  const enabled = Boolean(billing?.billing_enabled);
  const subscribed = isSubscribed(billing);
  const plans = normalizePlans(billing?.plans);
  const maxDays = Number(billing?.max_campaign_days || 0);
  const recommended = recommendPlan(plans, durationDays);
  const status = String(billing?.status || "none");

  return (
    <section className="panel campaign-panel billing-panel paywall-card" id="billing">
      <div className="section-heading">
        <div>
          <span className="overline">Billing & campaign packs</span>
          <h2>
            {!enabled
              ? (billing?.billing_preview ? "Preview packs (optional)" : "Plans by campaign length")
              : subscribed
                ? `Active · up to ${maxDays} days`
                : "Choose a duration pack"}
          </h2>
        </div>
        <CreditCard size={18} />
      </div>

      <p className="account-copy">
        {!enabled
          ? (billing?.billing_preview
            ? "Billing is optional while you test. Packs are preview-only — generation stays open. Turn on a real Stripe key later to charge."
            : "Choose a campaign length that matches your calendar.")
          : subscribed
            ? `Status: ${status}. You can generate calendars up to ${maxDays} days — upgrade if you need a longer run.`
            : `No active pack yet (status: ${status}). Pick the pack that matches your ${durationDays}-day campaign — recommended: ${recommended?.name || "Standard · 30 days"}.`}
      </p>
      {billing?.message && !enabled ? (
        <p className="account-copy">{billing.message}</p>
      ) : null}
      {billingFlag === "success" ? (
        <p className="account-copy billing-success">Payment received — refreshing your access.</p>
      ) : null}
      {billingFlag === "cancel" ? (
        <p className="account-copy">Checkout canceled. You can upgrade whenever you’re ready.</p>
      ) : null}
      {error ? <p className="account-copy billing-error">{error}</p> : null}

      <PlanCards
        plans={plans}
        subscribed={!enabled || subscribed}
        billingEnabled={enabled}
        busy={busy}
        onSubscribe={startCheckout}
        durationDays={durationDays}
        maxDays={!enabled ? 60 : maxDays}
      />

      {enabled && subscribed ? (
        <div className="page-actions" style={{ marginTop: 14 }}>
          <button className="secondary-button" onClick={openPortal} disabled={busy}>
            {busy ? <LoaderCircle className="spin" size={16} /> : <CreditCard size={16} />}
            Manage subscription
          </button>
          <button className="secondary-button" onClick={refresh} disabled={busy}>
            Refresh status
          </button>
        </div>
      ) : enabled ? (
        <div className="page-actions" style={{ marginTop: 14 }}>
          <button className="secondary-button" onClick={refresh} disabled={busy}>
            Refresh status
          </button>
        </div>
      ) : null}
    </section>
  );
}

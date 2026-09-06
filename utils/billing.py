"""Stripe subscription billing for CreatorOS.

Plans match the campaign duration picker in the app: 14 / 30 / 45 / 60 days.

Env:
  BILLING_ENABLED=true|false   (default false — preview UI only)
  BILLING_ENFORCE=true|false   (default false — paywall off until you opt in)
  STRIPE_SECRET_KEY=sk_...
  STRIPE_WEBHOOK_SECRET=whsec_...
  STRIPE_PRICE_CAMPAIGN_14=price_...
  STRIPE_PRICE_CAMPAIGN_30=price_...
  STRIPE_PRICE_CAMPAIGN_45=price_...
  STRIPE_PRICE_CAMPAIGN_60=price_...
  # Optional labels / legacy aliases:
  STRIPE_PRICE_PRO_MONTHLY=price_...   # treated as 30-day pack if CAMPAIGN_30 unset
  STRIPE_PRICE_PRO_YEARLY=price_...    # unlocks all durations
  FRONTEND_URL=http://localhost:8000
  BILLING_BYPASS_EMAILS=you@example.com

While testing, leave BILLING_ENFORCE unset (and optionally BILLING_ENABLED too).
Packs can still show as preview; generation stays open until you enforce with a real Stripe key.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORE_FILE = PROJECT_ROOT / "memory" / "subscriptions.json"
_lock = threading.Lock()

ACTIVE_STATUSES = {"active", "trialing"}

CAMPAIGN_DURATIONS = (14, 30, 45, 60)

PLAN_CATALOG = [
    {
        "id": "campaign_14",
        "days": 14,
        "name": "Sprint · 14 days",
        "env_price": "STRIPE_PRICE_CAMPAIGN_14",
        "env_label": "STRIPE_PRICE_CAMPAIGN_14_LABEL",
        "default_label": "$19/mo",
        "blurb": "Two-week content burst — ideal for a product launch or client pilot.",
        "features": [
            "Up to 14-day content calendar",
            "Shorts + Reels + LinkedIn + X posts",
            "Platform-specific captions (not copy-paste)",
            "Human review board before publish",
        ],
    },
    {
        "id": "campaign_30",
        "days": 30,
        "name": "Standard · 30 days",
        "env_price": "STRIPE_PRICE_CAMPAIGN_30",
        "env_label": "STRIPE_PRICE_CAMPAIGN_30_LABEL",
        "default_label": "$29/mo",
        "blurb": "Full month strategy — the default CreatorOS campaign length.",
        "features": [
            "Up to 30-day content calendar",
            "Everything in Sprint",
            "Brand end screens / client rebrand",
            "Partial URL download by timespan",
        ],
        "legacy_price_envs": ("STRIPE_PRICE_PRO_MONTHLY",),
        "legacy_label_envs": ("STRIPE_PRICE_PRO_MONTHLY_LABEL",),
    },
    {
        "id": "campaign_45",
        "days": 45,
        "name": "Growth · 45 days",
        "env_price": "STRIPE_PRICE_CAMPAIGN_45",
        "env_label": "STRIPE_PRICE_CAMPAIGN_45_LABEL",
        "default_label": "$39/mo",
        "blurb": "Six weeks of runway for agencies juggling a longer client cycle.",
        "features": [
            "Up to 45-day content calendar",
            "Everything in Standard",
            "More slots for LinkedIn + X cadence",
            "Transcript desk for editors",
        ],
    },
    {
        "id": "campaign_60",
        "days": 60,
        "name": "Scale · 60 days",
        "env_price": "STRIPE_PRICE_CAMPAIGN_60",
        "env_label": "STRIPE_PRICE_CAMPAIGN_60_LABEL",
        "default_label": "$49/mo",
        "blurb": "Two-month plan — longest calendar option in the campaign picker.",
        "features": [
            "Up to 60-day content calendar",
            "Everything in Growth",
            "Best for multi-client agency desks",
            "Unlocks every duration below",
        ],
    },
]


def billing_enabled() -> bool:
    """User flipped the feature on in .env (may still be preview-only)."""
    raw = (os.getenv("BILLING_ENABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def stripe_secret_key() -> str:
    return (os.getenv("STRIPE_SECRET_KEY") or "").strip()


def stripe_configured() -> bool:
    """True only when a real-looking Stripe secret is present."""
    key = stripe_secret_key()
    if not key.startswith(("sk_test_", "sk_live_")):
        return False
    if "..." in key or "your" in key.lower() or "xxx" in key.lower():
        return False
    return len(key) >= 20


def billing_enforced() -> bool:
    """Paywall only when explicitly enforced — safe default for testing.

    Set BILLING_ENFORCE=true (plus BILLING_ENABLED and a valid Stripe secret)
    when you are ready to charge. Until then packs stay preview-only.
    """
    enforce = (os.getenv("BILLING_ENFORCE") or "").strip().lower() in {"1", "true", "yes", "on"}
    return enforce and billing_enabled() and stripe_configured()


def bypass_emails() -> set[str]:
    raw = os.getenv("BILLING_BYPASS_EMAILS") or ""
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def _env_first(*keys: str) -> str:
    for key in keys:
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return ""


def plans() -> list[dict[str, Any]]:
    rows = []
    for spec in PLAN_CATALOG:
        legacy_prices = spec.get("legacy_price_envs") or ()
        legacy_labels = spec.get("legacy_label_envs") or ()
        price_id = _env_first(spec["env_price"], *legacy_prices)
        label = _env_first(spec["env_label"], *legacy_labels) or spec["default_label"]
        rows.append({
            "id": spec["id"],
            "name": spec["name"],
            "days": spec["days"],
            "interval": "month",
            "price_label": label,
            "price_id": price_id,
            "blurb": spec["blurb"],
            "features": list(spec["features"]),
            "recommended_for": spec["days"],
        })

    yearly = _env_first("STRIPE_PRICE_PRO_YEARLY")
    if yearly:
        rows.append({
            "id": "pro_yearly",
            "name": "Agency · Yearly",
            "days": 60,
            "interval": "year",
            "price_label": _env_first("STRIPE_PRICE_PRO_YEARLY_LABEL") or "$290/yr",
            "price_id": yearly,
            "blurb": "Annual unlock — run 14 / 30 / 45 / 60-day campaigns all year.",
            "features": [
                "All campaign durations unlocked",
                "Best value vs monthly packs",
                "Priority for agency multi-client workflows",
            ],
            "recommended_for": 60,
        })
    return rows


def plan_by_price_id(price_id: str | None) -> dict[str, Any] | None:
    price_id = (price_id or "").strip()
    if not price_id:
        return None
    for plan in plans():
        if plan.get("price_id") and plan["price_id"] == price_id:
            return plan
    return None


def plan_for_days(days: int | None) -> dict[str, Any] | None:
    try:
        want = int(days or 30)
    except (TypeError, ValueError):
        want = 30
    catalog = plans()
    exact = next(
        (p for p in catalog if int(p.get("days") or 0) == want and str(p["id"]).startswith("campaign_")),
        None,
    )
    if exact:
        return exact
    covering = sorted(
        [p for p in catalog if int(p.get("days") or 0) >= want],
        key=lambda p: int(p.get("days") or 0),
    )
    return covering[0] if covering else (catalog[-1] if catalog else None)


def max_days_for_plan_id(plan_id: str | None) -> int:
    plan_id = (plan_id or "").strip()
    if plan_id == "pro_yearly":
        return 60
    for spec in PLAN_CATALOG:
        if spec["id"] == plan_id:
            return int(spec["days"])
    if plan_id in {"pro", "pro_monthly"}:
        return 30
    return 0


def _empty_store() -> dict:
    return {"customers": {}}


def _load_store() -> dict:
    if not STORE_FILE.exists():
        return _empty_store()
    try:
        data = json.loads(STORE_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, TypeError):
        return _empty_store()
    if not isinstance(data.get("customers"), dict):
        data["customers"] = {}
    return data


def _save_store(data: dict) -> None:
    STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(STORE_FILE)


def get_record(email: str | None) -> dict:
    key = normalize_email(email)
    if not key:
        return {}
    with _lock:
        return dict((_load_store().get("customers") or {}).get(key) or {})


def upsert_record(email: str | None, patch: dict) -> dict:
    key = normalize_email(email)
    if not key:
        return {}
    with _lock:
        data = _load_store()
        customers = data.setdefault("customers", {})
        row = dict(customers.get(key) or {})
        row.update({k: v for k, v in patch.items() if v is not None})
        customers[key] = row
        _save_store(data)
        return dict(row)


def find_email_by_customer(customer_id: str | None) -> str:
    customer_id = (customer_id or "").strip()
    if not customer_id:
        return ""
    with _lock:
        for email, row in (_load_store().get("customers") or {}).items():
            if (row or {}).get("stripe_customer_id") == customer_id:
                return email
    return ""


def entitled_max_days(email: str | None) -> int:
    """Highest campaign duration (days) this subscriber may generate."""
    if not billing_enforced():
        return 60
    key = normalize_email(email)
    if not key:
        return 0
    if key in bypass_emails():
        return 60
    row = get_record(key)
    if (row.get("status") or "").lower() not in ACTIVE_STATUSES:
        return 0
    stored = row.get("max_campaign_days")
    try:
        if stored is not None:
            return max(0, int(stored))
    except (TypeError, ValueError):
        pass
    return max_days_for_plan_id(row.get("plan")) or 30


def has_access(email: str | None) -> bool:
    return entitled_max_days(email) > 0


def can_run_campaign(email: str | None, campaign_days: int | None) -> bool:
    try:
        days = int(campaign_days or 30)
    except (TypeError, ValueError):
        days = 30
    return entitled_max_days(email) >= days


def status_payload(email: str | None) -> dict:
    key = normalize_email(email)
    flag_on = billing_enabled()
    enforced = billing_enforced()
    row = get_record(key) if key else {}
    status = (row.get("status") or "none").lower()
    max_days = entitled_max_days(key) if key else 0

    # Testing / preview: show packs optionally, never block generation.
    if not enforced:
        return {
            "billing_enabled": False,
            "billing_preview": flag_on,
            "checkout_ready": False,
            "email": key,
            "entitled": True,
            "status": "active",
            "plan": "dev",
            "max_campaign_days": 60,
            "campaign_durations": list(CAMPAIGN_DURATIONS),
            "price_id": "",
            "current_period_end": None,
            "stripe_customer_id": (row.get("stripe_customer_id") or ""),
            "plans": plans(),
            "message": (
                "Billing is optional right now (preview only). "
                "When ready to charge: BILLING_ENABLED=true, BILLING_ENFORCE=true, "
                "and a valid STRIPE_SECRET_KEY."
                if flag_on
                else None
            ),
        }

    entitled = max_days > 0 and status in ACTIVE_STATUSES
    if not entitled:
        max_days = 0
        if status in ACTIVE_STATUSES:
            status = "none"

    return {
        "billing_enabled": True,
        "billing_preview": False,
        "checkout_ready": True,
        "email": key,
        "entitled": entitled,
        "status": status,
        "plan": row.get("plan") or "free",
        "max_campaign_days": max_days,
        "campaign_durations": list(CAMPAIGN_DURATIONS),
        "price_id": row.get("price_id") or "",
        "current_period_end": row.get("current_period_end"),
        "stripe_customer_id": row.get("stripe_customer_id") or "",
        "plans": plans(),
        "message": (
            None
            if entitled
            else "Pick a campaign pack (14 / 30 / 45 / 60 days) to generate."
        ),
    }


def _stripe():
    secret = stripe_secret_key()
    if not secret:
        raise RuntimeError(
            "Stripe is not configured yet. Leave billing optional while testing, "
            "or set a valid STRIPE_SECRET_KEY (sk_test_...) in .env."
        )
    if not stripe_configured():
        raise RuntimeError(
            "STRIPE_SECRET_KEY looks invalid. Use a real sk_test_… key from the Stripe Dashboard, "
            "or set BILLING_ENABLED=false while testing."
        )
    try:
        import stripe
    except ImportError as exc:
        raise RuntimeError("Install stripe: pip install stripe") from exc
    stripe.api_key = secret
    return stripe


def frontend_base() -> str:
    """Origin for redirects. Accepts http://host:8000 or .../app."""
    base = (os.getenv("FRONTEND_URL") or "http://localhost:8000").rstrip("/")
    if base.lower().endswith("/app"):
        base = base[: -len("/app")]
    return base.rstrip("/")


def create_checkout_session(
    email: str,
    price_id: str | None = None,
    user_id: str | None = None,
    campaign_days: int | None = None,
) -> dict:
    key = normalize_email(email)
    if not key:
        raise ValueError("Sign in with an email before checkout.")
    if not billing_enforced():
        raise RuntimeError(
            "Billing checkout is optional right now. "
            "When ready: BILLING_ENABLED=true, BILLING_ENFORCE=true, and a valid STRIPE_SECRET_KEY."
        )

    stripe = _stripe()
    price = (price_id or "").strip()
    if not price:
        recommended = plan_for_days(campaign_days)
        price = (recommended or {}).get("price_id") or ""
    if not price:
        price = _env_first("STRIPE_PRICE_CAMPAIGN_30", "STRIPE_PRICE_PRO_MONTHLY")
    if not price:
        raise RuntimeError(
            "No Stripe price configured. Set STRIPE_PRICE_CAMPAIGN_14/30/45/60 in .env."
        )

    matched = plan_by_price_id(price)
    row = get_record(key)
    customer_id = row.get("stripe_customer_id") or None
    try:
        if not customer_id:
            customer = stripe.Customer.create(
                email=key,
                metadata={"creatoros_user_id": user_id or "", "creatoros_email": key},
            )
            customer_id = customer["id"]
            upsert_record(key, {"stripe_customer_id": customer_id})

        base = frontend_base()
        success = f"{base}/app/workspace?billing=success"
        cancel = f"{base}/app/workspace?billing=cancel"
        meta = {
            "creatoros_email": key,
            "creatoros_user_id": user_id or "",
            "creatoros_plan": (matched or {}).get("id") or "",
            "creatoros_max_days": str((matched or {}).get("days") or ""),
        }

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            client_reference_id=key,
            line_items=[{"price": price, "quantity": 1}],
            success_url=success + "&session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel,
            allow_promotion_codes=True,
            metadata=meta,
            subscription_data={"metadata": meta},
        )
    except Exception as exc:
        name = type(exc).__name__
        msg = str(exc)
        if "AuthenticationError" in name or "Invalid API Key" in msg:
            raise RuntimeError(
                "Stripe rejected the API key. Fix STRIPE_SECRET_KEY, or leave "
                "BILLING_ENFORCE unset while testing."
            ) from exc
        raise
    return {
        "checkout_url": session.url,
        "session_id": session.id,
        "plan": matched,
    }


def create_portal_session(email: str) -> dict:
    key = normalize_email(email)
    if not key:
        raise ValueError("Sign in with an email before opening the billing portal.")
    row = get_record(key)
    customer_id = row.get("stripe_customer_id")
    if not customer_id:
        raise RuntimeError("No Stripe customer yet — subscribe first.")
    stripe = _stripe()
    portal = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{frontend_base()}/app/workspace",
    )
    return {"portal_url": portal.url}


def _plan_from_price(price_id: str | None) -> str:
    matched = plan_by_price_id(price_id)
    if matched:
        return matched["id"]
    price_id = (price_id or "").strip()
    yearly = _env_first("STRIPE_PRICE_PRO_YEARLY")
    if yearly and price_id == yearly:
        return "pro_yearly"
    if price_id:
        return "campaign_30"
    return "campaign_30"


def sync_subscription(email: str | None, subscription: Any) -> dict:
    key = normalize_email(email)
    if not key:
        key = find_email_by_customer(
            getattr(subscription, "customer", None) or (subscription or {}).get("customer")
        )
    if not key:
        return {}

    if hasattr(subscription, "to_dict"):
        sub = subscription.to_dict()
    elif isinstance(subscription, dict):
        sub = subscription
    else:
        sub = dict(subscription)

    items = ((sub.get("items") or {}).get("data") or [])
    price_id = ""
    if items:
        price_id = ((items[0].get("price") or {}).get("id")) or ""

    plan_id = _plan_from_price(price_id)
    return upsert_record(key, {
        "stripe_customer_id": sub.get("customer"),
        "subscription_id": sub.get("id"),
        "status": sub.get("status") or "none",
        "price_id": price_id,
        "plan": plan_id,
        "max_campaign_days": max_days_for_plan_id(plan_id),
        "current_period_end": sub.get("current_period_end"),
    })


def construct_webhook_event(payload: bytes, signature: str | None):
    secret = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not set.")
    stripe = _stripe()
    return stripe.Webhook.construct_event(payload, signature or "", secret)


def handle_webhook_event(event: dict | Any) -> dict:
    if hasattr(event, "to_dict"):
        event = event.to_dict()
    elif not isinstance(event, dict):
        event = dict(event)

    etype = event.get("type") or ""
    obj = (event.get("data") or {}).get("object") or {}

    if etype == "checkout.session.completed":
        email = normalize_email(
            obj.get("client_reference_id")
            or (obj.get("metadata") or {}).get("creatoros_email")
            or (obj.get("customer_details") or {}).get("email")
            or obj.get("customer_email")
        )
        customer_id = obj.get("customer")
        subscription_id = obj.get("subscription")
        meta = obj.get("metadata") or {}
        plan_id = meta.get("creatoros_plan") or "campaign_30"
        try:
            max_days = int(meta.get("creatoros_max_days") or max_days_for_plan_id(plan_id) or 30)
        except (TypeError, ValueError):
            max_days = max_days_for_plan_id(plan_id) or 30
        if email and customer_id:
            upsert_record(email, {
                "stripe_customer_id": customer_id,
                "subscription_id": subscription_id,
                "status": "active",
                "plan": plan_id,
                "max_campaign_days": max_days,
            })
        if subscription_id:
            stripe = _stripe()
            sub = stripe.Subscription.retrieve(subscription_id)
            sync_subscription(email, sub)
        return {"ok": True, "handled": etype}

    if etype in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        email = normalize_email((obj.get("metadata") or {}).get("creatoros_email"))
        sync_subscription(email, obj)
        return {"ok": True, "handled": etype}

    if etype in {"invoice.paid", "invoice.payment_failed"}:
        customer_id = obj.get("customer")
        email = find_email_by_customer(customer_id)
        subscription_id = obj.get("subscription")
        if subscription_id:
            stripe = _stripe()
            sub = stripe.Subscription.retrieve(subscription_id)
            sync_subscription(email, sub)
        elif email and etype == "invoice.payment_failed":
            upsert_record(email, {"status": "past_due"})
        return {"ok": True, "handled": etype}

    return {"ok": True, "handled": None}

"""OAuth for Instagram, LinkedIn, and X. Tokens sit next to the YouTube file."""

from __future__ import annotations

import json
import os
import secrets
import threading
from pathlib import Path
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
KEY_FILE = DATA_DIR / ".oauth_key"

_state_lock = threading.Lock()
_oauth_states: dict[str, dict] = {}

PLATFORMS = {
    "instagram": {
        "label": "Instagram",
        "id_keys": ("INSTAGRAM_APP_ID", "INSTAGRAM_CLIENT_ID", "META_APP_ID"),
        "secret_keys": ("INSTAGRAM_APP_SECRET", "META_APP_SECRET"),
        "redirect_keys": ("INSTAGRAM_REDIRECT_URI",),
        "auth_url": "https://www.instagram.com/oauth/authorize",
        "token_url": "https://api.instagram.com/oauth/access_token",
        "scope": "instagram_business_basic,instagram_business_content_publish",
        "pkce": False,
    },
    "linkedin": {
        "label": "LinkedIn",
        "id_keys": ("LINKEDIN_CLIENT_ID",),
        "secret_keys": ("LINKEDIN_CLIENT_SECRET",),
        "redirect_keys": ("LINKEDIN_REDIRECT_URI",),
        "auth_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "scope": "openid profile email w_member_social",
        "pkce": False,
    },
    "twitter": {
        "label": "Twitter / X",
        "id_keys": ("TWITTER_CLIENT_ID", "X_CLIENT_ID"),
        "secret_keys": ("TWITTER_CLIENT_SECRET", "X_CLIENT_SECRET"),
        "redirect_keys": ("TWITTER_REDIRECT_URI", "X_REDIRECT_URI"),
        "auth_url": "https://twitter.com/i/oauth2/authorize",
        "token_url": "https://api.twitter.com/2/oauth2/token",
        "scope": "tweet.read tweet.write users.read offline.access",
        "pkce": True,
    },
}


def _load_env():
    load_dotenv(PROJECT_ROOT / ".env", override=True)


def _first_env(keys) -> str:
    _load_env()
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def _settings(platform: str) -> dict:
    spec = PLATFORMS[platform]
    return {
        "client_id": _first_env(spec["id_keys"]),
        "client_secret": _first_env(spec["secret_keys"]),
        "redirect_uri": _first_env(spec["redirect_keys"]),
    }


def configured(platform: str) -> bool:
    if platform not in PLATFORMS:
        return False
    cfg = _settings(platform)
    return bool(cfg["client_id"] and cfg["client_secret"] and cfg["redirect_uri"])


def _token_path(platform: str) -> Path:
    return DATA_DIR / f"{platform}_token.enc"


def _fernet() -> Fernet:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    env_key = os.getenv("OAUTH_TOKEN_ENCRYPTION_KEY", "").strip()
    if env_key:
        return Fernet(env_key.encode("ascii"))
    if not KEY_FILE.exists():
        KEY_FILE.write_bytes(Fernet.generate_key())
    return Fernet(KEY_FILE.read_bytes().strip())


def _save(platform: str, payload: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(payload).encode("utf-8")
    _token_path(platform).write_bytes(_fernet().encrypt(blob))


def _load(platform: str) -> dict | None:
    path = _token_path(platform)
    if not path.exists():
        return None
    try:
        return json.loads(_fernet().decrypt(path.read_bytes()).decode("utf-8"))
    except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Stored {platform} token cannot be decrypted. Connect again.") from exc


def authorization_url(platform: str) -> str:
    spec = PLATFORMS.get(platform)
    if not spec:
        raise RuntimeError(f"Unknown platform: {platform}")
    cfg = _settings(platform)
    missing = [name for name, value in cfg.items() if not value]
    if missing:
        raise RuntimeError(
            f"{spec['label']} OAuth is not configured. "
            "Add the app id, secret, and redirect URI to .env, then try Connect again."
        )
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "scope": spec["scope"],
        "state": state,
    }
    record = {"platform": platform, "verifier": None}
    if spec["pkce"]:
        verifier = secrets.token_urlsafe(64)
        record["verifier"] = verifier
        params["code_challenge"] = _pkce_challenge(verifier)
        params["code_challenge_method"] = "S256"
    if platform == "linkedin":
        params["scope"] = spec["scope"]
    if cfg["redirect_uri"].startswith("http://localhost"):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    with _state_lock:
        _oauth_states[state] = record
    return f"{spec['auth_url']}?{urlencode(params)}"


def _pkce_challenge(verifier: str) -> str:
    import base64
    import hashlib

    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def exchange_callback(platform: str, code: str, state: str) -> dict:
    spec = PLATFORMS[platform]
    cfg = _settings(platform)
    with _state_lock:
        record = _oauth_states.pop(state, None)
    if not record or record.get("platform") != platform:
        raise RuntimeError(f"Invalid or expired OAuth state. Start Connect {spec['label']} again.")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg["redirect_uri"],
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
    }
    headers = {"Accept": "application/json"}
    auth = None
    if record.get("verifier"):
        data["code_verifier"] = record["verifier"]
    if platform == "twitter":
        auth = (cfg["client_id"], cfg["client_secret"])
        data.pop("client_secret", None)
    response = requests.post(spec["token_url"], data=data, headers=headers, auth=auth, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(f"{spec['label']} token exchange failed: {response.text[:400]}")
    try:
        token = response.json()
    except ValueError:
        from urllib.parse import parse_qs
        token = {key: values[0] for key, values in parse_qs(response.text).items()}
    if isinstance(token.get("data"), list) and token["data"]:
        token = token["data"][0]
    access = token.get("access_token")
    if not access:
        raise RuntimeError(f"{spec['label']} did not return an access token.")
    profile = _profile(platform, access)
    payload = {
        "access_token": access,
        "refresh_token": token.get("refresh_token"),
        "token_type": token.get("token_type") or "Bearer",
        "expires_in": token.get("expires_in"),
        "user_id": token.get("user_id") or profile.get("id"),
        "display_name": profile.get("name") or profile.get("username") or spec["label"],
        "username": profile.get("username") or "",
    }
    _save(platform, payload)
    return payload


def _profile(platform: str, access_token: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        if platform == "instagram":
            res = requests.get(
                "https://graph.instagram.com/v21.0/me",
                params={"fields": "user_id,username,name"},
                headers=headers,
                timeout=20,
            )
        elif platform == "linkedin":
            res = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers, timeout=20)
        else:
            res = requests.get(
                "https://api.twitter.com/2/users/me",
                params={"user.fields": "name,username"},
                headers=headers,
                timeout=20,
            )
        if res.status_code >= 400:
            return {}
        data = res.json()
        if platform == "twitter":
            data = data.get("data") or {}
        return {
            "id": data.get("sub") or data.get("id") or data.get("user_id"),
            "name": data.get("name"),
            "username": data.get("username") or data.get("preferred_username"),
        }
    except requests.RequestException:
        return {}


def disconnect(platform: str) -> None:
    _token_path(platform).unlink(missing_ok=True)


def connection_status(platform: str) -> dict:
    spec = PLATFORMS[platform]
    row = {
        "platform": platform,
        "label": spec["label"],
        "status": "not_connected",
        "connected": False,
        "configured": configured(platform),
    }
    if not row["configured"]:
        row["status"] = "not_configured"
        return row
    try:
        payload = _load(platform)
    except Exception as exc:
        row["status"] = "reconnect_required"
        row["error"] = str(exc)
        return row
    if not payload:
        return row
    row.update({
        "status": "connected",
        "connected": True,
        "display_name": payload.get("display_name") or spec["label"],
        "username": payload.get("username") or "",
    })
    return row


def all_statuses() -> list:
    return [connection_status(key) for key in PLATFORMS]

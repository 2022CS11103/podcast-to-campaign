"""Single-user YouTube OAuth and upload support for the local CreatorOS studio.

Tokens are encrypted at rest under data/. Production should replace this file
store with a per-user database and a managed encryption key.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TOKEN_FILE = DATA_DIR / "youtube_token.enc"
KEY_FILE = DATA_DIR / ".oauth_key"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

_state_lock = threading.Lock()
_oauth_states: dict[str, str | None] = {}


def _settings() -> dict:
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    return {
        "client_id": os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI", "").strip(),
    }


def configured() -> bool:
    return all(_settings().values())


def _client_config() -> dict:
    cfg = _settings()
    missing = [key for key, value in cfg.items() if not value]
    if missing:
        raise RuntimeError(f"Missing Google OAuth setting(s): {', '.join(missing)}")
    return {
        "web": {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [cfg["redirect_uri"]],
        }
    }


def _flow(state: str | None = None, code_verifier: str | None = None) -> Flow:
    cfg = _settings()
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        state=state,
        code_verifier=code_verifier,
        autogenerate_code_verifier=code_verifier is None,
    )
    flow.redirect_uri = cfg["redirect_uri"]
    if cfg["redirect_uri"].startswith("http://localhost"):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    return flow


def authorization_url() -> str:
    state = secrets.token_urlsafe(32)
    flow = _flow(state=state)
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent select_account",
    )
    with _state_lock:
        _oauth_states[state] = flow.code_verifier
    return url


def _consume_state(state: str) -> str | None:
    with _state_lock:
        if not state or state not in _oauth_states:
            raise RuntimeError("Invalid or expired OAuth state. Start Connect YouTube again.")
        return _oauth_states.pop(state)


def _fernet() -> Fernet:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    env_key = os.getenv("OAUTH_TOKEN_ENCRYPTION_KEY", "").strip()
    if env_key:
        return Fernet(env_key.encode("ascii"))
    if not KEY_FILE.exists():
        KEY_FILE.write_bytes(Fernet.generate_key())
    return Fernet(KEY_FILE.read_bytes().strip())


def _credential_payload(credentials: Credentials) -> dict:
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes or SCOPES),
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
    }


def _save_credentials(credentials: Credentials) -> None:
    payload = json.dumps(_credential_payload(credentials)).encode("utf-8")
    TOKEN_FILE.write_bytes(_fernet().encrypt(payload))


def exchange_callback(code: str, state: str) -> None:
    code_verifier = _consume_state(state)
    if not code_verifier:
        raise RuntimeError("OAuth PKCE verifier was lost. Start Connect YouTube again.")
    flow = _flow(state=state, code_verifier=code_verifier)
    try:
        flow.fetch_token(code=code, code_verifier=code_verifier)
    except Exception as exc:
        raise RuntimeError(
            f"OAuth token exchange failed (PKCE verifier length={len(code_verifier)}): {exc}"
        ) from exc
    credentials = flow.credentials
    if not credentials.refresh_token:
        raise RuntimeError("Google did not return a refresh token. Revoke access and connect again.")
    _save_credentials(credentials)


def load_credentials(refresh: bool = True) -> Credentials | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        payload = json.loads(_fernet().decrypt(TOKEN_FILE.read_bytes()).decode("utf-8"))
    except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Stored YouTube token cannot be decrypted. Reconnect YouTube.") from exc
    credentials = Credentials.from_authorized_user_info(payload, scopes=SCOPES)
    if refresh and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        _save_credentials(credentials)
    return credentials


def disconnect() -> None:
    TOKEN_FILE.unlink(missing_ok=True)


def connection_status() -> dict:
    if not configured():
        return {
            "platform": "youtube",
            "label": "YouTube",
            "status": "not_configured",
            "connected": False,
        }
    try:
        credentials = load_credentials()
    except Exception as exc:
        return {
            "platform": "youtube",
            "label": "YouTube",
            "status": "reconnect_required",
            "connected": False,
            "error": str(exc),
        }
    return {
        "platform": "youtube",
        "label": "YouTube",
        "status": "connected" if credentials else "not_connected",
        "connected": bool(credentials),
    }


def upload_video(
    media_path: Path,
    title: str,
    description: str,
    privacy_status: str = "private",
    made_for_kids: bool = False,
) -> dict:
    credentials = load_credentials()
    if not credentials:
        raise RuntimeError("YouTube is not connected.")
    if privacy_status not in {"private", "unlisted", "public"}:
        raise ValueError("privacy_status must be private, unlisted, or public")
    media_path = media_path.resolve()
    if not media_path.exists() or media_path.suffix.lower() != ".mp4":
        raise FileNotFoundError(f"MP4 not found: {media_path}")

    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    body = {
        "snippet": {
            "title": (title or media_path.stem)[:100],
            "description": (description or "")[:5000],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": bool(made_for_kids),
        },
    }
    media = MediaFileUpload(
        str(media_path),
        mimetype="video/mp4",
        chunksize=8 * 1024 * 1024,
        resumable=True,
    )
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
        notifySubscribers=False,
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return {
        "video_id": response["id"],
        "url": f"https://youtu.be/{response['id']}",
        "privacy_status": privacy_status,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }

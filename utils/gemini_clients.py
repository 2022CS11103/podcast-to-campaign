import os
import time
import itertools
from threading import Lock
from dotenv import load_dotenv
from google import genai

load_dotenv()

MODEL = "gemini-3.1-flash-lite"
MAX_ATTEMPTS = 6

# Collect all available keys (GEMINI_API_KEY_1, _2, _3, ...)
_keys = []
i = 1
while True:
    key = os.getenv(f"GEMINI_API_KEY_{i}")
    if not key:
        break
    _keys.append(key)
    i += 1

# Fallback: if only the old single-key variable exists
if not _keys:
    single = os.getenv("GEMINI_API_KEY")
    if single:
        _keys = [single]

if not _keys:
    raise RuntimeError("No Gemini API keys found in .env")

_key_cycle = itertools.cycle(_keys)
_key_lock = Lock()


def get_client():
    """Returns a fresh client using the next key in rotation."""
    with _key_lock:
        key = next(_key_cycle)
    return genai.Client(api_key=key)


def _retryable(exc):
    msg = str(exc).lower()
    code = getattr(exc, "status_code", None)
    if code in (429, 500, 503, 504):
        return True
    return any(
        token in msg
        for token in (
            "503", "429", "500", "504",
            "unavailable", "overloaded", "resource exhausted",
            "deadline", "temporarily",
        )
    )


def generate_content(prompt: str):
    """Call Gemini, rotating keys and backing off on 503/429."""
    last = None
    for attempt in range(MAX_ATTEMPTS):
        client = get_client()
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )
            text = getattr(response, "text", None)
            if text:
                return response
            last = RuntimeError("Empty Gemini response")
        except Exception as exc:
            last = exc
            if not _retryable(exc) or attempt == MAX_ATTEMPTS - 1:
                raise
            wait = min(2 ** attempt, 16)
            print(
                f"  Gemini busy ({type(exc).__name__}), "
                f"retry {attempt + 1}/{MAX_ATTEMPTS} in {wait}s..."
            )
            time.sleep(wait)
    raise last


def generate_multimodal(contents):
    """Gemini call that can include audio bytes, with the same retry policy."""
    last = None
    for attempt in range(MAX_ATTEMPTS):
        client = get_client()
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=contents,
            )
            text = getattr(response, "text", None)
            if text:
                return response
            last = RuntimeError("Empty Gemini response")
        except Exception as exc:
            last = exc
            if not _retryable(exc) or attempt == MAX_ATTEMPTS - 1:
                raise
            wait = min(2 ** attempt, 16)
            print(
                f"  Gemini busy ({type(exc).__name__}), "
                f"retry {attempt + 1}/{MAX_ATTEMPTS} in {wait}s..."
            )
            time.sleep(wait)
    raise last
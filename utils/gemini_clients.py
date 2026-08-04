import os
import itertools
from dotenv import load_dotenv
from google import genai

load_dotenv()

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


def get_client():
    """Returns a fresh client using the next key in rotation."""
    key = next(_key_cycle)
    return genai.Client(api_key=key)
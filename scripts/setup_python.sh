#!/bin/sh
set -e
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi

# cPanel / shared hosts often create a venv with no pip.
if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  .venv/bin/python -m ensurepip --upgrade 2>/dev/null || true
fi
if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  echo "Bootstrapping pip into .venv ..."
  curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
fi

.venv/bin/python -m pip install -U pip
# Install the server first so a later ML-package failure still leaves uvicorn.
.venv/bin/python -m pip install "uvicorn[standard]" fastapi python-dotenv python-multipart
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -c "import uvicorn; print('uvicorn ok:', uvicorn.__file__)"

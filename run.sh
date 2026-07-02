#!/usr/bin/env bash
# Launch the Havn Club hang-tag generator.
# First run: creates a virtualenv and installs dependencies.
set -e
cd "$(dirname "$0")"

PY=python3.12
command -v $PY >/dev/null 2>&1 || PY=python3

if [ ! -d ".venv" ]; then
  echo "Setting up virtual environment…"
  $PY -m venv .venv
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -r requirements.txt
fi

exec ./.venv/bin/streamlit run app.py

#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH=.
uvicorn apps.api.main:app --reload --port 8000

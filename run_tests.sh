#!/usr/bin/env bash
cd "$(dirname "$0")/backend" && . .venv/bin/activate && python -m pytest "$@"

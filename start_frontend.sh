#!/usr/bin/env bash
cd "$(dirname "$0")/frontend" || exit 1
[ -d node_modules ] || npm install || exit 1
echo "Open http://localhost:5173  (backend must be running: ./start.sh)"
exec npm run dev

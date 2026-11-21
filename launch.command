#!/bin/sh
# pdf2md 웹 앱 실행 (Finder에서 더블클릭해도 됨): http://127.0.0.1:8000
cd "$(dirname "$0")"
PORT="${PORT:-8000}"
(sleep 2 && open "http://127.0.0.1:$PORT") &
exec .venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port "$PORT"

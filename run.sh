#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-8501}"
export API_MODE="${API_MODE:-live}"
export API_URL="${API_URL:-http://127.0.0.1:${API_PORT}}"

echo "Démarrage de l'API FastAPI sur ${API_URL} ..."
uvicorn app.api.main:app --host 127.0.0.1 --port "${API_PORT}" &
API_PID=$!

cleanup() {
    kill "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT

sleep 2
echo "Démarrage de l'interface Streamlit sur http://127.0.0.1:${UI_PORT} (API_MODE=${API_MODE}) ..."
streamlit run ui/app.py --server.port "${UI_PORT}" --server.headless true

#!/usr/bin/env bash
# Open a Cloudflare quick tunnel to the local app so Otari can reach our MCP
# server and guardrail service. Writes the public URL to .tunnel-url.
#   scripts/tunnel.sh [port]     (default 8765)
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${1:-${SADE_PORT:-8765}}"
rm -f .tunnel-url
cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:${PORT}" > .tunnel.log 2>&1 &
PID=$!
for _ in $(seq 1 60); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' .tunnel.log | head -1 || true)
  if [ -n "${URL}" ]; then
    echo "${URL}" > .tunnel-url
    echo "Tunnel: ${URL} (pid ${PID})"
    exit 0
  fi
  sleep 1
done
echo "Tunnel did not start; see .tunnel.log" >&2
kill "${PID}" 2>/dev/null || true
exit 1

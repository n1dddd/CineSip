#!/usr/bin/env bash
# Deploy CineSip on the VPS. Idempotent — safe to re-run.
set -euo pipefail

cd ~/cinesip

echo "== freeing port 80 from host nginx =="
if systemctl is-active --quiet nginx; then
  sudo systemctl stop nginx
  sudo systemctl disable nginx
  echo "host nginx stopped and disabled"
else
  echo "host nginx not running"
fi

echo "== rebuilding containers =="
docker compose down --remove-orphans || true
docker compose build
docker compose up -d

echo "== waiting for health =="
for i in $(seq 1 30); do
  if curl -sf http://localhost/api/health >/dev/null 2>&1; then
    echo "healthy after ${i}s"
    break
  fi
  sleep 1
done

echo "== status =="
docker compose ps
echo "-- api health --"
curl -s http://localhost/api/health || echo "API UNREACHABLE"
echo
echo "-- frontend title --"
curl -s http://localhost/ | grep -o '<title>.*</title>' || echo "NO TITLE"

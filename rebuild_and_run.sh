#!/bin/bash
# Rebuild the backend Docker image and restart all services.
# Run this from the project root:  bash rebuild_and_run.sh

set -e
cd "$(dirname "$0")"

echo "=== Rebuilding backend image (this takes ~2 min) ==="
sudo docker compose build backend

echo "=== Restarting all services ==="
sudo docker compose up -d

echo "=== Waiting for backend to be ready ==="
for i in $(seq 1 30); do
  if curl -s http://localhost:8000/api/v1/auth/login/ -o /dev/null; then
    echo "Backend is up!"
    break
  fi
  sleep 2
done

echo ""
echo "=== All done. Services running at ==="
sudo docker compose ps

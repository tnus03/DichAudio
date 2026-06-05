#!/usr/bin/env bash
# Render start script
set -e

echo "Starting DichAudio Server..."

# Tao media directory
mkdir -p media logs

# Chay FastAPI server
exec uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-10000}

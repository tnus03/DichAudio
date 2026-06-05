#!/usr/bin/env bash
# Render build script - cai dat FFmpeg va dependencies
set -e

echo "Install system dependencies..."
apt-get update && apt-get install -y ffmpeg chromium-browser 2>/dev/null || true

echo "Install Python dependencies..."
pip install -r requirements.txt

echo "Install Playwright browsers..."
python -m playwright install chromium 2>/dev/null || true

echo "Build complete!"

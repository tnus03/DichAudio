FROM python:3.11-slim

WORKDIR /app

# Cai FFmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Cai Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Tao thu muc can thiet
RUN mkdir -p media logs

# Port
EXPOSE 10000

# Start
CMD uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-10000}

# ══════════════════════════════════════════════════════════
# Project AETHER — Autonomous Constellation Manager
# HARD REQUIREMENT: Must use ubuntu:22.04 base image
# ══════════════════════════════════════════════════════════

# --- Stage 1: Build the Frontend (React/Vite) ---
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

# Install wget and ca-certificates to download Earth textures securely
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./

# Download Earth textures BEFORE npm build so Vite copies them to dist/
RUN mkdir -p public/textures \
    && wget -q -O public/textures/earth_daymap.jpg \
         "https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg" \
    && wget -q -O public/textures/earth_nightmap.jpg \
         "https://unpkg.com/three-globe/example/img/earth-night.jpg"

RUN npm run build

# --- Stage 2: Production Image (MUST be ubuntu:22.04 per PS) ---
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy pre-built frontend (includes textures now)
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Copy backend and scripts
COPY backend/ /app/backend/
COPY scripts/ /app/scripts/

# Regenerate initial data with correct orbital mechanics
RUN python3 /app/scripts/generate_initial_data.py

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
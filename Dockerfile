# ══════════════════════════════════════════════════════════
# Project AETHER — Autonomous Constellation Manager
# HARD REQUIREMENT: ubuntu:22.04 base image (per PS)
# ══════════════════════════════════════════════════════════

# --- Stage 1: Build the Frontend (React/Vite) ---
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./

# Textures are committed in frontend/public/textures/ — no download needed
# This makes the build fully reproducible for grading

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

# Copy pre-built frontend (includes textures)
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Copy backend and scripts
COPY backend/ /app/backend/
COPY scripts/ /app/scripts/

# Regenerate initial data with correct orbital mechanics
RUN python3 /app/scripts/generate_initial_data.py

EXPOSE 8000

# Bind to 0.0.0.0 (required by PS, not just localhost)
CMD ["python3", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

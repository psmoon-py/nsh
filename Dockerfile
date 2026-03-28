# ══════════════════════════════════════════════════════════
# Project AETHER — Autonomous Constellation Manager
# HARD REQUIREMENT: Must use ubuntu:22.04 base image
# ══════════════════════════════════════════════════════════

# --- Stage 1: Build the Frontend (React/Vite) ---
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Production Image (MUST be ubuntu:22.04 per PS) ---
FROM ubuntu:22.04

# Prevent interactive prompts during apt
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install Python 3.11+ and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the PRE-BUILT frontend files from Stage 1
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Copy Backend code and scripts
COPY backend/ /app/backend/
COPY scripts/ /app/scripts/

# Generate initial data
RUN python3 /app/scripts/generate_initial_data.py || true

# Open the port
EXPOSE 8000

# Start the FastAPI server — MUST bind 0.0.0.0 per PS
CMD ["python3", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- Stage 1: Build the Frontend (React/Vite) ---
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

# Copy only package files first to cache the install step
COPY frontend/package*.json ./
RUN npm install

# Copy the rest of the frontend and build it
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Final Production Image (Python Backend) ---
FROM python:3.12-slim
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install minimal system dependencies
RUN apt-get update && apt-get install -y \
    curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the PRE-BUILT frontend files from Stage 1
# This puts your built React site into /app/frontend/dist
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Copy Backend code and scripts
COPY backend/ /app/backend/
COPY scripts/ /app/scripts/

# Generate initial data (tle/eci files) if the script exists
RUN python /app/scripts/generate_initial_data.py || true

# Open the port
EXPOSE 8000

# Start the FastAPI server
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

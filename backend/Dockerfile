# ============================================================
# AgAI_31: Backend Dockerfile
# ============================================================

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Railway overrides with $PORT)
EXPOSE 8080

# Start server — Railway injects $PORT dynamically
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
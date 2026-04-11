FROM python:3.12-slim

# Create non-root user
RUN groupadd -r agent && useradd -r -g agent agent

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY agent/ ./agent/
COPY api/ ./api/
COPY db/ ./db/
COPY worker/ ./worker/
COPY runbooks/ ./runbooks/

# Create data directory
RUN mkdir -p /data && chown agent:agent /data

# Switch to non-root user
USER agent

# ANTHROPIC_API_KEY must be injected at runtime — never baked into image
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

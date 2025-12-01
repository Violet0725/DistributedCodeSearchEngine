# CodeSearch Docker Image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install the package
RUN pip install -e .

# Create data directory
RUN mkdir -p /app/data/repos /app/data/index

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV REPOS_PATH=/app/data/repos
ENV INDEX_PATH=/app/data/index

# Default command
CMD ["python", "-m", "codesearch.cli", "serve", "--host", "0.0.0.0"]


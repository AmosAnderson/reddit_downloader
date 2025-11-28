# Use Python 3.13 as base image (3.14 might not be available yet in Docker)
FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY README.md ./
COPY src/ ./src/

# Install Python dependencies
RUN uv venv && uv sync

# Create downloads directory
RUN mkdir -p /downloads

# Expose port for web interface
EXPOSE 5000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command - run web interface
CMD ["/app/.venv/bin/python", "-m", "reddit_downloader", "web", "--host", "0.0.0.0", "--port", "5000", "--output", "/downloads"]

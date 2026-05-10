# Use Python 3.13 as base image (3.14 might not be available yet in Docker)
FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy project metadata first for reproducible dependency installation
COPY pyproject.toml uv.lock ./
COPY README.md ./

# Install Python dependencies from the lockfile without dev extras
RUN uv venv && uv sync --frozen --no-dev --no-install-project

# Copy source after dependency installation for better Docker layer caching
COPY src/ ./src/

# Install the project itself from the already-copied source without changing dependencies
RUN uv sync --frozen --no-dev

# Create non-root user and downloads directory
RUN useradd --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /downloads \
    && chown -R app:app /app /downloads

# Expose port for web interface
EXPOSE 5000

# Set environment variables
ENV PYTHONUNBUFFERED=1

USER app

# Default command - run web interface
CMD ["/app/.venv/bin/python", "-m", "reddit_downloader", "web", "--host", "0.0.0.0", "--port", "5000", "--output", "/downloads", "--no-open-browser"]

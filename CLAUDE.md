# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Technical Requirements
- **Language**: Python
- **Library**: PRAW (Python Reddit API Wrapper)
- **Python Version**: 3.14
- **Package Manager**: uv (for dependency and environment management)
- **Type Annotations**: Required throughout the codebase

## Project Goals
- Download media for a given post based on the URL of that post
- If the URL given is a link to a user, download all media for each post from that user
- Respect Reddit API rate limits for personal API usage
- Provide a local web interface for easy drag-and-drop and paste URL operations

## Architecture Overview

### Triple Interface Design
The package must support:
1. **Library API**: Importable modules for programmatic use
2. **CLI Tool**: Command-line interface for direct usage
3. **Web Interface**: Local web server with drag-and-drop and paste functionality for Reddit URLs

### Core Components
- **Reddit API Integration**: PRAW-based client handling authentication and API calls
- **Media Downloader**: Download handler for various media types (images, videos, galleries)
- **Rate Limiter**: Ensures compliance with Reddit's API limits
- **URL Parser**: Distinguishes between post URLs and user profile URLs
- **Web Server**: Local Flask/FastAPI server for web interface with drag-and-drop support

## Common Commands

### Environment Setup
```bash
uv venv                    # Create virtual environment
uv sync                    # Install dependencies from pyproject.toml
uv add <package>           # Add new dependency
uv add --dev <package>     # Add development dependency
```

### Running the Application
```bash
uv run python -m reddit_downloader post <url>     # Download from post
uv run python -m reddit_downloader user <user>    # Download from user
uv run python -m reddit_downloader web            # Start local web interface
```

### Development Tools
```bash
uv run pytest                           # Run tests
uv run pytest --cov=reddit_downloader   # Run tests with coverage
uv run mypy src/                        # Type checking
uv run ruff check src/                  # Linting
uv run ruff format src/                 # Format code
```

## Development Guidelines

### Code Quality
- Source must be tidy and clean
- Type annotations required for all functions and methods
- Follow Python best practices and PEP 8 style guide

### API Rate Limiting
- Implement proper rate limiting to stay within Reddit's personal use API limits
- Use PRAW's built-in rate limiting features
- Add delays between batch operations when processing multiple posts

### Error Handling
- Handle network failures gracefully
- Validate URLs before processing
- Provide clear error messages for invalid credentials or API issues

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Setup:**
```bash
uv venv && uv sync --dev
cp .env.example .env  # Add REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET
```

**Run the app:**
```bash
uv run python -m reddit_downloader web          # Web interface at http://127.0.0.1:5000
uv run python -m reddit_downloader post <url>   # CLI: download a single post
uv run python -m reddit_downloader user <name>  # CLI: download a user's posts
```

**Tests:**
```bash
uv run pytest                          # Run all tests (coverage enabled by default)
uv run pytest tests/test_downloader.py # Run a single test file
uv run pytest -k "TestDownloadVideo"   # Run a specific test class
```

**Lint / type-check:**
```bash
uv run ruff check src/
uv run ruff format src/
uv run mypy src/
```

## Architecture

The package lives under `src/reddit_downloader/` (PEP 517 src layout). Entry point is `__main__.py`, which routes to three subcommands: `post`, `user`, and `web`.

**Core modules:**
- `client.py` — `RedditClient` wraps PRAW. Loads credentials from `.env` via `python-dotenv`. Provides `get_post(id)` and `get_user_posts(username, limit)`.
- `parser.py` — URL parsing and validation. Returns a typed dict with `url_type`, `post_id`, and `username`.
- `downloader.py` — `MediaDownloader` handles the actual HTTP downloads. Reddit videos (`v.redd.it`) have separate video and audio DASH streams; this class downloads both and merges them with `ffmpeg` via `subprocess`. Falls back to video-only if ffmpeg is absent.
- `types.py` — All shared dataclasses and enums: `URLType`, `MediaType`, `JobStatus`, `MediaInfo`, `DownloadResult`, `DownloadJob`.

**Web layer (`web/`):**
- `app.py` — Flask app factory (`create_app`). The `RedditDownloaderApp` subclass holds typed attributes (`job_manager`, `reddit_client`, `output_directory`) on the app object rather than in config. Routes are defined inline inside `create_app`. File cleanup (delete-on-download) is wired via Flask's `response.call_on_close`.
- `jobs.py` — `JobManager` runs each download in a daemon `threading.Thread`. Cancellation is signalled via `threading.Event`. Jobs are stored in-memory (no persistence across restarts).

**Data flow for a web download:**
1. POST `/api/download` → `JobManager.create_job` + `start_job` (spawns thread)
2. Thread calls `MediaDownloader.download_post_media` which dispatches to `download_image`, `download_video`, or `download_gallery`
3. GET `/api/status/<job_id>` for polling; GET `/api/files/<job_id>` to list results
4. GET `/api/download-file/<job_id>/<index>` or `/api/download-archive/<job_id>?format=zip|tar.zst` to retrieve files — both delete files from disk after transfer

**Toolchain:** `uv` for package management, `ruff` for lint/format (line length 100), `mypy` in strict mode, `pytest` with `pytest-cov` (coverage runs by default via `addopts`).

**External dependency:** `ffmpeg` must be installed separately for video+audio merging. Docker image includes it; local installs need `brew install ffmpeg` / `apt install ffmpeg`.

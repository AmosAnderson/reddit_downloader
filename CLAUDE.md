# CLAUDE.md

This file provides project guidance for coding agents working in this repository.

## Commands

**Setup:**

```bash
uv venv
uv sync --extra dev
cp .env.example .env  # Add REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET
```

**Run the app:**

```bash
uv run python -m reddit_downloader              # Launch terminal user interface (TUI, default)
uv run python -m reddit_downloader tui          # Launch TUI app explicitly
uv run python -m reddit_downloader web          # Web TUI interface at http://127.0.0.1:8000
uv run python -m reddit_downloader post <url>   # Download a single post
uv run python -m reddit_downloader user <name>  # Download a user's posts
```

**Tests and validation:**

```bash
uv run pytest
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
```

## Architecture

The package uses a PEP 517 `src/` layout. The entry point is `src/reddit_downloader/__main__.py`, which routes to the `tui`, `web`, `post`, and `user` subcommands.

Core modules:

- `client.py` — `RedditClient` wraps PRAW. Credentials are read from explicit arguments or environment variables loaded from `.env`.
- `parser.py` — URL parsing and validation. It classifies Reddit post and user URLs and rejects unsupported schemes or direct `v.redd.it` media IDs.
- `security.py` — Public-network validation for media download URLs.
- `downloader.py` — `MediaDownloader` handles HTTP downloads, retry behavior, file-size limits, cancellation checks, Reddit gallery ordering, and `ffmpeg` video/audio merging.
- `jobs.py` — In-memory background job manager. Each job runs in a daemon thread, receives its own output directory, uses a per-job cancellation event, returns job snapshots, and performs TTL/count-based cleanup.
- `types.py` — Shared dataclasses and enums: `URLType`, `MediaType`, `JobStatus`, `MediaInfo`, `DownloadResult`, and `DownloadJob`.

TUI modules:

- `tui/app.py` — Textual terminal user interface application code with cyber theme, active progress bars, folder opening, credentials configuration modal, and background job polling.

## TUI / Web workflow

1. The TUI application (or browser-hosted TUI via `textual-serve`) provides an input form for Reddit URLs and limit.
2. The user initiates a download, validating the URL and client connection before queuing a job via `JobManager.create_job()`.
3. The job manager runs the download inside a background daemon thread, updating the progress and status dynamically.
4. The TUI app's interval timer polls `JobManager` states every 1.0 second, updating the active list of `JobWidget` components.
5. Pressing `w` in the TUI spawns a background `textual-serve` server on port 8000, allowing browser access.

## Operational notes

- `ffmpeg` must be installed separately for local video/audio merging.
- Jobs are in-memory only; they do not persist across process restarts.
- Completed, failed, and cancelled web jobs are eligible for cleanup after 24 hours, and the job list is capped at 100 jobs.

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
uv run python -m reddit_downloader web          # Web interface at http://127.0.0.1:5000
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

**Docker:**

```bash
docker compose up -d
docker compose run --rm reddit-downloader-cli post <url>
docker compose build
```

## Architecture

The package uses a PEP 517 `src/` layout. The entry point is `src/reddit_downloader/__main__.py`, which routes to the `post`, `user`, and `web` subcommands.

Core modules:

- `client.py` — `RedditClient` wraps PRAW. Credentials are read from explicit arguments or environment variables loaded from `.env`.
- `parser.py` — URL parsing and validation. It classifies Reddit post and user URLs and rejects unsupported schemes or direct `v.redd.it` media IDs.
- `security.py` — Public-network validation for media download URLs.
- `downloader.py` — `MediaDownloader` handles HTTP downloads, retry behavior, file-size limits, cancellation checks, Reddit gallery ordering, and `ffmpeg` video/audio merging.
- `types.py` — Shared dataclasses and enums: `URLType`, `MediaType`, `JobStatus`, `MediaInfo`, `DownloadResult`, and `DownloadJob`.

Web modules:

- `web/app.py` — Flask application factory, routes, optional API bearer-token enforcement, archive creation, health check, and web server startup.
- `web/jobs.py` — In-memory background job manager. Each job runs in a daemon thread, receives its own output directory, uses a per-job cancellation event, returns job snapshots, and performs TTL/count-based cleanup.

## Web download flow

1. `POST /api/download` validates the URL and optional limit, creates a job, runs cleanup, and starts a background thread.
2. The job thread creates or receives a `RedditClient`, creates `MediaDownloader(<output_dir>/<job_id>)`, and downloads the requested post or user media.
3. `GET /api/status/<job_id>` returns job progress.
4. `POST /api/cancel/<job_id>` signals cancellation for queued or running jobs.
5. `GET /api/files/<job_id>` lists successful result files.
6. `GET /api/download-file/<job_id>/<index>` serves one file; `GET /api/download-archive/<job_id>?format=zip|tar.zst` serves an archive.
7. Source files remain until normal old-job cleanup. Temporary archive files are deleted after the response closes.

## Operational notes

- `ffmpeg` must be installed separately for local video/audio merging. The Docker image includes it.
- The Docker Compose web service binds to `127.0.0.1:5000` by default.
- Set `REDDIT_DOWNLOADER_AUTH_TOKEN` to require `Authorization: Bearer <token>` on `/api/*` routes.
- Jobs are in-memory only; they do not persist across process restarts.
- Completed, failed, and cancelled web jobs are eligible for cleanup after 24 hours, and the job list is capped at 100 jobs.

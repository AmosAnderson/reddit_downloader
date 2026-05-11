# Reddit Downloader

Reddit Downloader is a Python application for downloading media from Reddit posts and user profiles. It provides a command-line interface, a local Flask web interface, and a small library API.

## Features

- Download media from individual Reddit posts.
- Download media from a Reddit user's recent posts, with a configurable limit.
- Supports Reddit-hosted images, direct image links, Reddit videos, and Reddit galleries.
- Merges Reddit video and audio streams when `ffmpeg` is available.
- Local web interface with background jobs, cancellation, progress polling, file listing, and ZIP or TAR.ZST archive downloads.
- Optional bearer-token protection for web API routes.
- Docker image with `ffmpeg` included and a non-root runtime user.
- Type-annotated codebase with pytest, Ruff, and mypy checks.

## Requirements

### Reddit API credentials

Create an app at <https://www.reddit.com/prefs/apps> and provide:

- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT` (optional but recommended)

For local development, copy the example environment file and edit it:

```bash
cp .env.example .env
```

### Local runtime

- Python 3.13 or newer
- [uv](https://github.com/astral-sh/uv)
- `ffmpeg` for videos with audio

Install `ffmpeg` with your system package manager, for example:

```bash
brew install ffmpeg          # macOS
sudo apt install ffmpeg      # Debian/Ubuntu
```

The Docker image already includes `ffmpeg`.

## Quick Start

### Docker Compose

```bash
git clone <repository-url>
cd reddit_downloader
cp .env.example .env
# Edit .env with your Reddit API credentials
docker compose up -d
```

Open <http://localhost:5000>.

By default, Docker Compose binds the web interface to `127.0.0.1`. Do not expose the web interface to untrusted networks unless you place it behind appropriate authentication and network controls.

Downloads are written to `./downloads` on the host. To change this, edit `docker-compose.yml` or create an override file from `docker-compose.override.yml.example`.

### Local installation

```bash
git clone <repository-url>
cd reddit_downloader
uv venv
uv sync --extra dev
cp .env.example .env
# Edit .env with your Reddit API credentials
uv run python -m reddit_downloader web
```

Open <http://127.0.0.1:5000>.

## Usage

### Web interface

Start the web interface locally:

```bash
uv run python -m reddit_downloader web
```

Useful options:

```bash
uv run python -m reddit_downloader web --host 127.0.0.1 --port 8080 --output ./downloads --no-open-browser
```

The web interface supports:

- Paste or drag-and-drop Reddit URLs.
- Background downloads with progress polling.
- Cancelling queued or running jobs.
- Downloading individual files after a job completes.
- Downloading all successful files from a job as `zip` or `tar.zst`.

Downloaded source files are retained until normal job cleanup. Completed, failed, and cancelled jobs are eligible for cleanup after 24 hours, and the in-memory job list is capped at 100 jobs. Temporary archive files are removed after the archive response closes.

### Command-line interface

Download a post:

```bash
uv run python -m reddit_downloader post "https://www.reddit.com/r/pics/comments/abc123/example/"
```

Download media from a user's posts:

```bash
uv run python -m reddit_downloader user example_user --limit 50
```

Choose an output directory and enable verbose logging:

```bash
uv run python -m reddit_downloader post <url> --output ./downloads --verbose
```

The user download limit must be between 1 and 1000 when provided.

With Docker Compose, run CLI commands through the CLI service:

```bash
docker compose run --rm reddit-downloader-cli post <url>
docker compose run --rm reddit-downloader-cli user example_user --limit 50
```

### Library API

```python
from pathlib import Path

from reddit_downloader.client import RedditClient
from reddit_downloader.downloader import MediaDownloader

client = RedditClient(
    client_id="your_client_id",
    client_secret="your_client_secret",
    user_agent="your_app_name/1.0 by u/your_username",
)

post = client.get_post("post_id")
downloader = MediaDownloader(Path("downloads"))

for result in downloader.download_post_media(post):
    if result.success:
        print(f"Downloaded: {result.file_path}")
    else:
        print(f"Failed: {result.error}")
```

## Configuration

### Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `REDDIT_CLIENT_ID` | Yes | Reddit API client ID. |
| `REDDIT_CLIENT_SECRET` | Yes | Reddit API client secret. |
| `REDDIT_USER_AGENT` | No | Custom Reddit API user agent. |
| `REDDIT_DOWNLOADER_AUTH_TOKEN` | No | If set, `/api/*` web routes require `Authorization: Bearer <token>`. |

Command-line `--client-id`, `--client-secret`, and `--user-agent` options override environment values for the current run.

### Web API authentication

Set `REDDIT_DOWNLOADER_AUTH_TOKEN` to require a bearer token for `/api/*` routes. The home page, static assets, and `/health` remain unauthenticated.

Example request:

```bash
curl -H "Authorization: Bearer $REDDIT_DOWNLOADER_AUTH_TOKEN" \
  http://127.0.0.1:5000/api/config
```

## Supported media

- Images: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`
- Reddit-hosted videos from `v.redd.it`
- Reddit image galleries
- Direct image links from public HTTP(S) hosts

The downloader rejects unsupported URL schemes and private, loopback, link-local, multicast, reserved, or unspecified network addresses for media downloads.

## Development

Install development dependencies:

```bash
uv sync --extra dev
```

Run the validation suite:

```bash
uv run pytest
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
```

Build the Docker image:

```bash
docker compose build
```

## Project layout

```text
src/reddit_downloader/
├── __main__.py          # CLI entry point
├── client.py            # Reddit API client wrapper
├── downloader.py        # Media download and video/audio merge logic
├── parser.py            # Reddit URL parsing and validation
├── security.py          # Download URL safety checks
├── types.py             # Shared dataclasses and enums
└── web/
    ├── app.py           # Flask application factory and routes
    └── jobs.py          # Background job manager
```

## Troubleshooting

### Reddit API credentials required

Verify `.env` contains valid credentials, or pass them with `--client-id` and `--client-secret`.

### Invalid Reddit URL

Use a Reddit post URL or user profile URL, for example:

- `https://www.reddit.com/r/subreddit/comments/post_id/title/`
- `https://www.reddit.com/user/username`
- `https://www.reddit.com/u/username`

Direct `v.redd.it/<id>` media URLs are not accepted as post URLs because those IDs are media IDs, not Reddit submission IDs.

### Videos download without audio

Install `ffmpeg`. Without it, the downloader falls back to video-only files when it cannot merge separate video and audio streams.

### Web interface does not start

Check that dependencies are installed and the port is available:

```bash
uv sync --extra dev
uv run python -m reddit_downloader web --port 8080
```

## License

MIT License. See [LICENSE](LICENSE) for details.

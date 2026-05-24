# Reddit Downloader

Reddit Downloader is a Python application for downloading media from Reddit posts and user profiles. It provides a terminal user interface (TUI), a command-line interface (CLI), a browser-based TUI web interface, and a library API.

## Features

- Modern Terminal User Interface (TUI) with real-time download queue management, progress bars, credentials setup wizard, and log alerts.
- Web-hosting mode to serve the TUI interface inside any standard web browser using `textual-serve`.
- Supports Reddit-hosted images, direct image links, Reddit videos, and Reddit galleries.
- Merges Reddit video and audio streams when `ffmpeg` is available.
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

## Quick Start

```bash
git clone <repository-url>
cd reddit_downloader
uv venv
uv sync --extra dev
cp .env.example .env
# Edit .env with your Reddit API credentials
uv run python -m reddit_downloader
```

## Usage

### Terminal User Interface (TUI) & Web mode

Start the terminal user interface locally:

```bash
uv run python -m reddit_downloader
```

Start the web interface locally (which hosts the TUI inside a web browser using `textual-serve`):

```bash
uv run python -m reddit_downloader web
```

Useful web options:

```bash
uv run python -m reddit_downloader web --host 127.0.0.1 --port 8080 --output ./downloads
```

The TUI/Web interface supports:

- pasting Reddit URL strings (posts or user profiles).
- real-time background downloads queue, active progress bars, and status logs.
- cancelling queued or running download jobs.
- viewing successfully downloaded files list and file sizes inside the app.
- opening the output downloads directory directly on your host machine from the TUI.
- setting up Reddit API keys securely from a credentials setup modal and writing them to your local `.env`.
- toggling browser hosting of the TUI directly from the terminal GUI by pressing `w`.

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

Command-line `--client-id`, `--client-secret`, and `--user-agent` options override environment values for the current run.

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

```

## Project layout

```text
src/reddit_downloader/
├── __main__.py          # CLI entry point
├── client.py            # Reddit API client wrapper
├── downloader.py        # Media download and video/audio merge logic
├── jobs.py              # Background job manager
├── parser.py            # Reddit URL parsing and validation
├── security.py          # Download URL safety checks
├── types.py             # Shared dataclasses and enums
└── tui/
    ├── __init__.py      # TUI runner entrypoint
    └── app.py           # Textual TUI Application code
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

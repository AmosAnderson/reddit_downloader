# Reddit Downloader

Download media from Reddit posts and user profiles with support for images, videos, and galleries.

## Features

- 📥 Download media from single Reddit posts
- 👤 Download all media from user profiles
- 🖼️ Support for images, videos (with audio), and galleries
- 🌐 **Web interface with drag-and-drop support**
- 💾 **Download via browser with ZIP or TAR.ZST compression**
- 🗑️ **Automatic cleanup of old completed jobs and files**
- 📚 Library API for programmatic use
- ⌨️ Command-line interface
- 🐳 **Docker support with configurable volumes**
- 🔒 Respects Reddit API rate limits
- 📝 Full type annotations

## Table of Contents

- [Quick Start](#quick-start)
  - [Docker (Recommended)](#docker-recommended)
  - [Local Installation](#local-installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

## Quick Start

Choose your preferred installation method:

### Docker (Recommended)

**Prerequisites:**
- Docker and Docker Compose
- Reddit API credentials ([get them here](https://www.reddit.com/prefs/apps))

**Steps:**

1. Clone the repository:
```bash
git clone https://github.com/yourusername/reddit_downloader.git
cd reddit_downloader
```

2. Create `.env` file with your Reddit API credentials:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Start the application:
```bash
docker-compose up -d
```

4. Open http://localhost:5000 in your browser

By default, Docker Compose binds the web interface to `127.0.0.1` only. Do not expose the web interface publicly unless you put it behind appropriate authentication/network controls.

**That's it!** No need to install Python, ffmpeg, or other dependencies - everything is included in the Docker image.

#### Customizing Download Location

Edit `docker-compose.yml` to change the download location:

```yaml
volumes:
  # Option 1: Bind mount to host directory
  - /your/custom/path:/downloads

  # Option 2: Use a named Docker volume
  - reddit-downloads:/downloads
```

Or create `docker-compose.override.yml`:
```bash
cp docker-compose.override.yml.example docker-compose.override.yml
# Edit docker-compose.override.yml with your custom settings
```

### Local Installation

**Prerequisites:**
- Python 3.13+ (or 3.14)
- [uv](https://github.com/astral-sh/uv) package manager
- Reddit API credentials ([get them here](https://www.reddit.com/prefs/apps))
- **ffmpeg** (required for downloading videos with audio)
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: Download from [ffmpeg.org](https://ffmpeg.org/download.html)

**Steps:**

1. Clone the repository:
```bash
git clone https://github.com/yourusername/reddit_downloader.git
cd reddit_downloader
```

2. Create virtual environment and install dependencies:
```bash
uv venv
uv sync --extra dev
```

3. Create `.env` file with your Reddit API credentials:
```bash
cp .env.example .env
# Edit .env and add your credentials
```

Example `.env` contents:
```env
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=reddit_downloader/0.1.0 (by /u/your_username)
```

4. Start the web interface:
```bash
uv run python -m reddit_downloader web
```

5. Open http://127.0.0.1:5000 in your browser

**Note:** The `.env` file will be automatically loaded by the application.

## Usage

### Web Interface (Recommended)

The web interface provides drag-and-drop support and real-time progress tracking.

**With Docker:**
```bash
# Already running if you used docker-compose up -d
# Access at http://localhost:5000
```

**Local Installation:**
```bash
uv run python -m reddit_downloader web
# Access at http://127.0.0.1:5000
```

**Features:**
- **Drag and drop** Reddit URLs directly into the browser
- **Paste** URLs anywhere on the page
- Real-time progress tracking
- Download multiple posts/users concurrently
- Automatic video/audio merging
- **Download files directly from web UI** - Files are served through your browser and retained until normal cleanup of old jobs/files
- **Bulk download options** - Download all media as ZIP or TAR.ZST archive
- **Individual file downloads** - Download specific files one at a time

#### Downloading Files from Web UI

Once a download job completes, you can download the media files directly through your browser:

1. **Individual Files**: Click the "Download" button next to any file to download it to your browser's download folder
2. **Bulk Download (ZIP)**: Click "Download All (ZIP)" to get all files in a standard ZIP archive
3. **Bulk Download (TAR.ZST)**: Click "Download All (TAR.ZST)" to get all files in a Zstandard-compressed tarball (smaller file size)

**Important**: Files are retained on the server after browser download and are removed by normal cleanup of old completed jobs/files. Avoid exposing the web interface or download directory to untrusted users.

### Command Line Interface

#### With Docker

```bash
# Download from a post
docker-compose run reddit-downloader-cli post "https://www.reddit.com/r/pics/comments/abc123/..."

# Download from a user (limit 50 posts)
docker-compose run reddit-downloader-cli user johndoe --limit 50

# Custom output location (relative to /downloads in container)
docker-compose run reddit-downloader-cli post <url> --verbose

# View all options
docker-compose run reddit-downloader-cli --help
```

#### Local Installation

```bash
# Download from a post
uv run python -m reddit_downloader post "https://www.reddit.com/r/pics/comments/abc123/..."

# Download from a user
uv run python -m reddit_downloader user johndoe --limit 50

# Custom output directory
uv run python -m reddit_downloader post <url> --output ./my_downloads

# Verbose mode
uv run python -m reddit_downloader post <url> --verbose
```

#### CLI Options:
- `-o, --output DIR` - Output directory (default: `./downloads`)
- `-l, --limit N` - Maximum number of posts to process (user mode only, 1-1000)
- `--client-id ID` - Reddit API client ID
- `--client-secret SECRET` - Reddit API client secret
- `--user-agent AGENT` - Custom user agent
- `-v, --verbose` - Verbose output
- `--port PORT` - Port for web server (web mode only, default: 5000)
- `--host HOST` - Host for web server (web mode only, default: 127.0.0.1)
- `--no-open-browser` - Do not automatically open a browser when starting the web server

### Library API

Use reddit_downloader programmatically in your Python code:

```python
from pathlib import Path
from reddit_downloader.client import RedditClient
from reddit_downloader.downloader import MediaDownloader
from reddit_downloader.parser import parse_url

# Initialize client
client = RedditClient(
    client_id="your_client_id",
    client_secret="your_client_secret",
    user_agent="your_app_name/1.0"
)

# Download from a post
post = client.get_post("post_id_here")
downloader = MediaDownloader(Path("downloads"))
results = downloader.download_post_media(post)

for result in results:
    if result.success:
        print(f"Downloaded: {result.file_path}")
    else:
        print(f"Failed: {result.error}")

# Download from user
for post in client.get_user_posts("username", limit=10):
    results = downloader.download_post_media(post)
    # Process results...
```

## Supported Media Types

- **Images**: JPG, PNG, GIF, WebP
- **Videos**: Reddit-hosted videos (v.redd.it) with audio (requires ffmpeg - included in Docker)
- **Galleries**: Reddit image galleries
- **External links**: Direct image links from supported domains

## Docker Management

### Container Operations

```bash
# Start the container
docker-compose up -d

# Stop the container
docker-compose stop

# View logs
docker-compose logs -f

# Restart the container
docker-compose restart

# Stop and remove the container
docker-compose down

# Rebuild the image (after code changes)
docker-compose build
docker-compose up -d
```

### Volume Management

```bash
# List Docker volumes
docker volume ls

# Inspect a volume
docker volume inspect reddit_downloader_reddit-downloads

# Remove unused volumes (careful!)
docker volume prune
```

### Manual Docker Commands

If not using docker-compose:

```bash
# Build the image
docker build -t reddit-downloader .

# Run web interface
docker run -d \
  --name reddit-downloader \
  -p 5000:5000 \
  -v $(pwd)/downloads:/downloads \
  --env-file .env \
  reddit-downloader

# Run CLI command
docker run --rm \
  -v $(pwd)/downloads:/downloads \
  --env-file .env \
  reddit-downloader \
  /app/.venv/bin/python -m reddit_downloader post <url>

# View logs
docker logs -f reddit-downloader

# Stop container
docker stop reddit-downloader

# Remove container
docker rm reddit-downloader
```

## Development

### Running Tests

```bash
uv run pytest
uv run pytest --cov=reddit_downloader
```

### Type Checking

```bash
uv run mypy src/
```

### Linting and Formatting

```bash
uv run ruff check src/
uv run ruff format src/
```

## Project Structure

```
reddit_downloader/
├── src/
│   └── reddit_downloader/
│       ├── __init__.py
│       ├── __main__.py          # CLI entry point
│       ├── client.py            # Reddit API client
│       ├── downloader.py        # Media downloader
│       ├── parser.py            # URL parser
│       ├── types.py             # Type definitions
│       └── web/                 # Web interface
│           ├── app.py           # Flask application
│           ├── jobs.py          # Background job manager
│           ├── static/          # CSS and JavaScript
│           └── templates/       # HTML templates
├── tests/                       # Test files
├── pyproject.toml              # Project configuration
└── README.md
```

## Configuration

### Environment Variables

- `REDDIT_CLIENT_ID` - Reddit API client ID (required)
- `REDDIT_CLIENT_SECRET` - Reddit API client secret (required)
- `REDDIT_USER_AGENT` - User agent string (optional)
- `REDDIT_DOWNLOADER_AUTH_TOKEN` - Optional bearer token required for `/api/*` routes. If set, API clients must send `Authorization: Bearer <token>`.

The web interface is intended for trusted/local use. Avoid exposing it directly to the public internet.

### Command-Line Arguments

All commands support `--client-id`, `--client-secret`, and `--user-agent` flags to override environment variables.

## Troubleshooting

### "Error: Reddit API credentials required"

Make sure you've set up your `.env` file with valid Reddit API credentials, or pass them via command-line arguments.

### "Invalid Reddit URL"

Ensure you're using a valid Reddit post or user profile URL. Examples:
- Post: `https://www.reddit.com/r/subreddit/comments/post_id/...`
- User: `https://www.reddit.com/user/username` or `https://www.reddit.com/u/username`

### Rate Limiting

The tool respects Reddit's API rate limits. PRAW handles most rate limiting automatically. For large downloads, use the `--limit` option to control batch sizes.

### Videos Downloading Without Audio

If videos are downloading without audio, you need to install ffmpeg:

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt install ffmpeg
```

**Windows:**
Download and install from [ffmpeg.org](https://ffmpeg.org/download.html)

After installing ffmpeg, the downloader will automatically merge video and audio streams.

**Note:** If ffmpeg is not available, the downloader will fall back to downloading video-only files.

### Web Interface Not Starting

Make sure Flask is installed:
```bash
uv sync --extra dev
```

Check if port 5000 is available, or use a different port:
```bash
uv run python -m reddit_downloader web --port 8080
```

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please open an issue or submit a pull request.

## Acknowledgments

- Built with [PRAW](https://praw.readthedocs.io/) - Python Reddit API Wrapper
- Uses [Flask](https://flask.palletsprojects.com/) for web interface
- Managed with [uv](https://github.com/astral-sh/uv) package manager

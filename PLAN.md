# Reddit Downloader - Implementation Plan

## Phase 1: Project Setup

### 1.1 Project Structure
```
reddit_downloader/
├── src/
│   └── reddit_downloader/
│       ├── __init__.py
│       ├── __main__.py          # CLI entry point
│       ├── client.py            # PRAW client wrapper
│       ├── downloader.py        # Media download logic
│       ├── parser.py            # URL parsing
│       ├── rate_limiter.py      # Rate limiting utilities
│       ├── types.py             # Type definitions
│       ├── web/
│       │   ├── __init__.py
│       │   ├── app.py           # Web server (Flask/FastAPI)
│       │   ├── routes.py        # API endpoints
│       │   ├── static/
│       │   │   ├── css/
│       │   │   │   └── style.css
│       │   │   └── js/
│       │   │       └── main.js  # Drag-drop & paste logic
│       │   └── templates/
│       │       └── index.html   # Main web interface
├── tests/
│   ├── __init__.py
│   ├── test_client.py
│   ├── test_downloader.py
│   ├── test_parser.py
│   └── test_web.py              # Web interface tests
├── pyproject.toml               # Project config & dependencies
├── README.md
├── CLAUDE.md
└── PLAN.md
```

### 1.2 Environment Management with `uv`

**Installation**:
```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Initialize project with uv
uv init

# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # On Unix/macOS
# or
.venv\Scripts\activate     # On Windows
```

**Working with uv**:
```bash
# Add dependencies
uv add praw requests flask

# Add development dependencies
uv add --dev pytest mypy ruff pytest-flask

# Install all dependencies from pyproject.toml
uv sync

# Run commands in the virtual environment (without activation)
uv run python -m reddit_downloader

# Run tests
uv run pytest

# Run type checking
uv run mypy src/

# Run linting
uv run ruff check src/
```

### 1.3 Dependencies
- `praw` - Reddit API wrapper
- `requests` - HTTP requests for media downloads
- `urllib3` - URL handling
- `flask` - Web framework for local web interface (alternative: `fastapi` + `uvicorn`)
- Development: `pytest`, `mypy`, `ruff` (linting/formatting), `pytest-flask` (web testing)

### 1.4 Configuration Files
- `pyproject.toml` - Define project metadata, dependencies, build system (managed by uv)
- `.python-version` - Pin Python version (created by uv)
- `.env.example` - Template for Reddit API credentials
- `README.md` - Usage instructions and setup guide

## Phase 2: Core Components

### 2.1 URL Parser (`parser.py`)
**Purpose**: Identify and validate Reddit URLs

**Functions**:
- `parse_url(url: str) -> URLType` - Determine if URL is post, user, or invalid
- `extract_username(url: str) -> str` - Extract username from user URL
- `extract_post_id(url: str) -> str` - Extract post ID from post URL
- `validate_reddit_url(url: str) -> bool` - Validate URL format

**Enums**:
- `URLType` - Enum for POST, USER, INVALID

### 2.2 PRAW Client Wrapper (`client.py`)
**Purpose**: Manage Reddit API connection and authentication

**Class**: `RedditClient`
- `__init__(client_id, client_secret, user_agent)` - Initialize PRAW
- `get_post(post_id: str) -> praw.models.Submission` - Fetch single post
- `get_user_posts(username: str, limit: int | None) -> Iterator[praw.models.Submission]` - Fetch user's posts
- `is_authenticated() -> bool` - Check connection status

**Configuration**:
- Load credentials from environment variables or config file
- Use read-only mode (no need for user authentication)
- Set appropriate user agent

### 2.3 Rate Limiter (`rate_limiter.py`)
**Purpose**: Ensure API compliance and prevent rate limit hits

**Class**: `RateLimiter`
- `__init__(requests_per_minute: int)` - Set rate limit
- `wait_if_needed()` - Block if rate limit reached
- `record_request()` - Log API call timestamp

**Strategy**:
- PRAW handles most rate limiting automatically
- Add additional throttling for batch operations
- Implement exponential backoff for retries

### 2.4 Media Downloader (`downloader.py`)
**Purpose**: Download media files from Reddit posts

**Class**: `MediaDownloader`
- `__init__(output_dir: Path)` - Set download directory
- `download_post_media(post: praw.models.Submission) -> list[Path]` - Download all media from post
- `download_image(url: str, filename: str) -> Path` - Download single image
- `download_video(url: str, filename: str) -> Path` - Download video with audio
- `download_gallery(post: praw.models.Submission) -> list[Path]` - Download Reddit gallery

**Media Types to Support**:
- Direct image links (jpg, png, gif)
- Reddit-hosted images (i.redd.it)
- Reddit-hosted videos (v.redd.it) - requires merging video + audio
- Reddit galleries
- Imgur links (single images and albums)
- Gfycat/Redgifs links

**File Naming**:
- Format: `{username}_{post_id}_{index}.{ext}`
- Sanitize filenames for filesystem compatibility
- Handle duplicate filenames

### 2.5 Type Definitions (`types.py`)
**Purpose**: Shared type definitions and data classes

**Types**:
- `URLType` - Enum for URL types
- `MediaType` - Enum for media types (IMAGE, VIDEO, GALLERY, etc.)
- `DownloadResult` - Data class for download outcomes
- `MediaInfo` - Data class for media metadata

## Phase 3: Library API

### 3.1 Main Library Interface (`__init__.py`)
**Purpose**: Provide clean API for library usage

**Public Functions**:
```python
def download_from_url(
    url: str,
    output_dir: str | Path,
    client_id: str,
    client_secret: str,
    user_agent: str,
    limit: int | None = None
) -> list[Path]:
    """Download media from Reddit URL (post or user)"""

def download_post(
    post_url: str,
    output_dir: str | Path,
    client: RedditClient
) -> list[Path]:
    """Download media from single post"""

def download_user_posts(
    username: str,
    output_dir: str | Path,
    client: RedditClient,
    limit: int | None = None
) -> list[Path]:
    """Download media from all user posts"""
```

### 3.2 Context Manager Support
```python
with RedditClient(client_id, client_secret, user_agent) as client:
    download_post(url, output_dir, client)
```

## Phase 4: CLI Interface

### 4.1 Command Structure (`__main__.py`)
**Purpose**: Command-line interface using `argparse` or `click`

**Commands**:
```bash
# Download from single post
uv run python -m reddit_downloader post <url> [--output DIR]

# Download from user
uv run python -m reddit_downloader user <username|url> [--output DIR] [--limit N]

# Start web interface
uv run python -m reddit_downloader web [--port PORT] [--host HOST]

# With credentials
uv run python -m reddit_downloader post <url> --client-id ID --client-secret SECRET

# Using environment variables (default)
uv run python -m reddit_downloader post <url>

# Or with activated virtual environment
python -m reddit_downloader post <url>
```

**Arguments**:
- `url` - Reddit URL (post or user)
- `--output`, `-o` - Output directory (default: ./downloads)
- `--limit`, `-l` - Max posts to process for user downloads
- `--client-id` - Reddit API client ID
- `--client-secret` - Reddit API client secret
- `--user-agent` - Custom user agent
- `--verbose`, `-v` - Verbose output
- `--port`, `-p` - Port for web server (default: 5000, web mode only)
- `--host` - Host address for web server (default: 127.0.0.1, web mode only)

### 4.2 Progress Display
- Show progress bar for multiple downloads
- Display current post being processed
- Show success/failure for each media item
- Summary statistics at end

## Phase 5: Web Interface

### 5.1 Web Server (`web/app.py`)
**Purpose**: Provide local web interface for easy URL submission

**Framework Choice**: Flask (lightweight) or FastAPI (modern, async)

**Server Configuration**:
- Run on localhost by default (127.0.0.1:5000)
- Allow custom port via command line argument
- Single-threaded is sufficient (personal use)
- Auto-open browser on startup (optional)

**Class**: `WebServer`
- `__init__(client: RedditClient, output_dir: Path, host: str, port: int)` - Initialize server
- `run()` - Start server
- `shutdown()` - Graceful shutdown

### 5.2 API Routes (`web/routes.py`)
**Purpose**: Handle API requests from the frontend

**Endpoints**:

**POST /api/download**
- Accept: `{"url": "...", "limit": null|int}`
- Validate URL using parser
- Start download in background thread/task
- Return job ID for status tracking

**GET /api/status/<job_id>**
- Return download progress/status
- Include: total items, completed, failed, current item

**GET /api/downloads**
- List recent download jobs
- Include status, URLs, file counts

**POST /api/cancel/<job_id>**
- Cancel ongoing download

**GET /api/config**
- Return server configuration (output directory, etc.)

**Response Format**:
```json
{
  "success": true,
  "job_id": "abc123",
  "message": "Download started",
  "data": {...}
}
```

### 5.3 Frontend (`web/templates/index.html`)
**Purpose**: User interface for drag-and-drop and paste operations

**Layout**:
- Header with app title and instructions
- Large drop zone for drag-and-drop
- Text input for paste/typing URLs
- Download button
- Progress display area
- Download history/status list
- Configuration panel (output directory, limits)

**Features**:
- Visual feedback on drag-over
- Multiple URL paste support (one per line)
- Real-time progress updates via polling or WebSockets
- Toast notifications for success/errors
- Dark/light theme toggle (optional)

### 5.4 JavaScript (`web/static/js/main.js`)
**Purpose**: Handle user interactions and API communication

**Functionality**:

**Drag-and-Drop**:
```javascript
// Prevent default browser behavior
dropZone.addEventListener('dragover', (e) => {
  e.preventDefault()
  // Add visual feedback
})

// Handle dropped content
dropZone.addEventListener('drop', (e) => {
  e.preventDefault()
  // Extract URLs from text/html
  // Submit to API
})
```

**Paste Detection**:
```javascript
// Listen for paste events
document.addEventListener('paste', (e) => {
  // Extract URLs from clipboard
  // Parse Reddit URLs
  // Submit to API
})
```

**Progress Polling**:
```javascript
// Poll status endpoint every 1-2 seconds
async function pollStatus(jobId) {
  const response = await fetch(`/api/status/${jobId}`)
  const data = await response.json()
  // Update UI with progress
}
```

**URL Validation**:
- Extract URLs from dropped text
- Validate Reddit URL format client-side
- Show immediate feedback

### 5.5 Styling (`web/static/css/style.css`)
**Purpose**: Clean, modern interface design

**Design Principles**:
- Minimalist, uncluttered layout
- Large, obvious drop zone
- Clear visual states (idle, hover, dropping, downloading)
- Progress bars and status indicators
- Responsive design (works on tablets/mobile)
- Accessibility considerations

**Color Scheme**:
- Reddit-inspired colors (optional)
- Clear contrast for readability
- Distinct colors for success/error/warning

### 5.6 Background Job Management
**Purpose**: Handle downloads without blocking web server

**Implementation Options**:

**Option 1: Threading**
```python
import threading
from queue import Queue

class DownloadJobManager:
    def __init__(self):
        self.jobs = {}
        self.queue = Queue()

    def submit_job(self, url: str, limit: int | None) -> str:
        job_id = generate_id()
        job = DownloadJob(job_id, url, limit)
        self.jobs[job_id] = job
        thread = threading.Thread(target=self._run_job, args=(job,))
        thread.start()
        return job_id
```

**Option 2: asyncio (if using FastAPI)**
```python
import asyncio

async def download_job(url: str, limit: int | None):
    # Async download implementation
```

**Job State Management**:
- Track job status (queued, running, completed, failed, cancelled)
- Store progress information
- Maintain download results
- Cleanup completed jobs after timeout

### 5.7 WebSocket Support (Optional Enhancement)
**Purpose**: Real-time progress updates without polling

**Implementation**:
- Use Flask-SocketIO or FastAPI WebSockets
- Push progress updates to client
- More efficient than polling
- Better user experience

## Phase 6: Error Handling & Edge Cases

### 6.1 Error Scenarios
- Invalid URLs
- Deleted/removed posts
- Private/suspended user accounts
- Network failures during download
- Missing API credentials
- Rate limit exceeded (despite throttling)
- Unsupported media types
- Insufficient disk space

### 6.2 Error Handling Strategy
- Custom exception hierarchy
- Graceful degradation (skip failed items, continue with others)
- Retry logic with exponential backoff
- Clear error messages with actionable guidance
- Logging for debugging

### 6.3 Edge Cases
- Posts with no media (text-only)
- Crossposted content
- Posts with external links only
- Deleted images in galleries
- NSFW content filtering (if needed)
- Very large files (add size limits?)

### 6.4 Web Interface Specific Errors
- Concurrent downloads from multiple browser tabs
- Server shutdown during active downloads
- Invalid JSON in API requests
- CORS issues (if accessed from non-localhost)

## Phase 7: Testing

### 7.1 Unit Tests
- Test URL parsing with various formats
- Test media type detection
- Test filename sanitization
- Mock PRAW responses for client tests
- Test rate limiter timing logic

**Running tests with uv**:
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_parser.py

# Run with coverage
uv run pytest --cov=reddit_downloader --cov-report=html

# Run with verbose output
uv run pytest -v
```

### 7.2 Integration Tests
- Test actual Reddit API calls (with test credentials)
- Test full download flow for known posts
- Test user post iteration
- Verify downloaded file integrity

### 7.3 Web Interface Tests
- Test API endpoints (POST /api/download, GET /api/status, etc.)
- Test job management and background downloads
- Test error responses
- Mock PRAW in web tests
- Test frontend JavaScript (optional, using Jest or similar)

### 7.4 Test Data
- Create fixtures for different post types
- Mock responses for deleted/private content
- Sample URLs for each media type

## Phase 8: Documentation

### 8.1 README.md
- Project description
- Installation instructions
- Reddit API setup guide
- Usage examples (CLI, library, and web interface)
- Web interface features and usage
- Configuration options
- Troubleshooting

### 8.2 Docstrings
- All public functions and classes
- Include type hints
- Usage examples in docstrings
- Parameter descriptions

### 8.3 API Documentation
- Consider using Sphinx for auto-generated docs
- Document web API endpoints
- Host on Read the Docs or GitHub Pages

## Phase 9: Polish & Distribution

### 9.1 Code Quality
**Type checking**:
```bash
uv run mypy src/reddit_downloader --strict
```

**Linting and formatting**:
```bash
# Check for issues
uv run ruff check src/

# Auto-fix issues
uv run ruff check --fix src/

# Format code
uv run ruff format src/
```

**Pre-commit checks**:
- Ensure all type annotations present
- Remove any debug code
- Verify all tests pass

### 9.2 Package Distribution
**Building the package**:
```bash
# Build with uv
uv build

# Install in development mode
uv pip install -e .
```

**Publishing to PyPI**:
```bash
# Build distribution
uv build

# Publish (using twine or uv publish when available)
uv publish
```

**CI/CD Integration**:
- Add GitHub Actions workflow
- Use uv in CI for faster dependency installation
- Run tests, type checking, and linting in CI

### 9.3 Additional Features (Future)
- Configuration file support (~/.reddit_downloader.conf)
- Duplicate detection (skip already downloaded)
- Resume interrupted downloads
- Parallel downloads
- Custom filename templates
- Subreddit download support
- Saved posts download
- **Web Interface Enhancements**:
  - WebSocket support for real-time updates (instead of polling)
  - Persistent download queue across server restarts
  - Download history with search/filter
  - Batch URL submission (paste multiple URLs at once)
  - User settings (default output dir, quality preferences)
  - Mobile-optimized interface

## Implementation Order

### Recommended Development Sequence:
1. **Setup** → Initialize with `uv init`, create project structure, configure pyproject.toml
2. **Parser** → Implement URL parsing (no API needed)
3. **Client** → Implement PRAW wrapper with basic connectivity
4. **Downloader** → Start with simple image downloads
5. **Integration** → Connect parser → client → downloader
6. **CLI** → Build basic CLI for single post downloads
7. **User Posts** → Add user post iteration support
8. **Media Types** → Expand to videos, galleries, etc.
9. **Rate Limiting** → Add proper rate limiting
10. **Web Interface** → Build web server, API routes, frontend with drag-and-drop
11. **Background Jobs** → Implement job management for web interface
12. **Error Handling** → Comprehensive error handling for all interfaces
13. **Testing** → Write tests throughout, comprehensive suite at end (including web tests)
14. **Documentation** → README and docstrings (include web interface usage)
15. **Polish** → Type checking with mypy, linting/formatting with ruff, cleanup

### Quick Start Commands:
```bash
# 1. Setup
uv init
uv venv
uv add praw requests flask
uv add --dev pytest mypy ruff pytest-cov pytest-flask

# 2. Development
uv run python -m reddit_downloader post <url>    # CLI mode
uv run python -m reddit_downloader web            # Web mode

# 3. Testing
uv run pytest

# 4. Code Quality
uv run mypy src/
uv run ruff check src/
uv run ruff format src/
```

## Success Criteria

The project is complete when:
- ✅ Can download media from single post URL
- ✅ Can download all media from user profile
- ✅ Respects Reddit API rate limits
- ✅ Works as library, CLI tool, AND web interface
- ✅ Web interface supports drag-and-drop of Reddit URLs
- ✅ Web interface supports paste of Reddit URLs
- ✅ Web interface shows real-time download progress
- ✅ Background job management for concurrent downloads
- ✅ Full type annotations throughout
- ✅ Comprehensive error handling (all interfaces)
- ✅ Test coverage for core functionality and web API
- ✅ Clear documentation for setup and usage (all interfaces)
- ✅ Clean, maintainable code

# Code Review: Security Issues and Bad Practices

## 🔴 Critical Security Issues

### 1. Global Mutable State in Web Application
**Location:** `src/reddit_downloader/web/app.py:19-22`

**Issue:**
```python
job_manager: JobManager | None = None
reddit_client: RedditClient | None = None
output_directory: Path | None = None
```

**Problem:**
- Not thread-safe for production WSGI servers (Gunicorn, uWSGI)
- Race conditions with multiple workers
- Security risk: credentials shared across all requests
- Cannot run multiple app instances

**Fix:**
```python
# Use Flask application factory pattern
def create_app(config: dict) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(config)
    
    # Store in app context
    app.job_manager = JobManager()
    app.reddit_client = RedditClient(...)
    app.output_directory = Path(config['OUTPUT_DIR'])
    
    # Access via current_app or g
    from flask import current_app
    job_manager = current_app.job_manager
```

### 2. Potential Path Traversal in Archive Creation
**Location:** `src/reddit_downloader/web/app.py:296, 305`

**Issue:**
```python
zf.write(str(file_path), arcname=file_path.name)
```

**Problem:** While files come from job results, there's no explicit validation that file_path is within output_directory.

**Fix:**
```python
# Validate path is within output_directory
if not file_path.resolve().is_relative_to(output_directory.resolve()):
    logger.warning(f"Skipping file outside output directory: {file_path}")
    continue
zf.write(str(file_path), arcname=file_path.name)
```

### 3. Module-Level Side Effect
**Location:** `src/reddit_downloader/client.py:12`

**Issue:**
```python
load_dotenv()
```

**Problem:** Side effect at module import. Makes testing difficult and can cause unexpected behavior.

**Fix:**
```python
# Remove from module level
# Call explicitly in main() and __init__ methods where needed
def __init__(self, ...):
    load_dotenv()  # Or make it optional with a parameter
    ...
```

## 🟡 High Priority Issues

### 4. Bare Exception Catching
**Location:** `src/reddit_downloader/client.py:72`

**Issue:**
```python
try:
    _ = self._reddit.read_only
    return True
except Exception:  # Too broad
    return False
```

**Problem:** Catches SystemExit, KeyboardInterrupt, etc. Masks real errors.

**Fix:**
```python
except (praw.exceptions.PRAWException, AttributeError, requests.RequestException) as e:
    logger.debug(f"Authentication check failed: {e}")
    return False
```

### 5. No Rate Limiting
**Locations:** `client.py`, `downloader.py`

**Problem:** 
- Reddit API rate limits (~60 requests/minute)
- No download rate limiting (bandwidth abuse)
- Could get IP banned

**Fix:**
```python
from ratelimit import limits, sleep_and_retry

class RedditClient:
    @sleep_and_retry
    @limits(calls=60, period=60)
    def get_post(self, post_id: str) -> Submission:
        return self._reddit.submission(id=post_id)
```

### 6. Incomplete Job Cancellation
**Location:** `src/reddit_downloader/web/jobs.py:222-238`

**Issue:** Job marked as cancelled but thread continues running.

**Problem:**
- Resource leak (threads, network connections)
- Misleading to users
- Wasted bandwidth

**Fix:**
```python
import threading

class JobManager:
    def __init__(self):
        self.jobs = {}
        self._lock = threading.Lock()
        self._stop_events = {}  # job_id -> threading.Event
    
    def start_job(self, job_id, ...):
        stop_event = threading.Event()
        self._stop_events[job_id] = stop_event
        thread = threading.Thread(
            target=self.run_job,
            args=(job_id, client, output_dir, limit, stop_event),
            daemon=True
        )
        thread.start()
    
    def run_job(self, job_id, client, output_dir, limit, stop_event):
        for post in client.get_user_posts(username, limit=limit):
            if stop_event.is_set():
                logger.info(f"Job {job_id} cancelled by user")
                return
            # ... rest of processing
    
    def cancel_job(self, job_id):
        if job_id in self._stop_events:
            self._stop_events[job_id].set()
            return True
        return False
```

### 7. No Request Retry Logic
**Location:** `src/reddit_downloader/downloader.py:170`

**Problem:** Single network failure causes download to fail.

**Fix:**
```python
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class MediaDownloader:
    def __init__(self, output_dir, *, verbose=False):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._verbose = verbose
        
        # Configure session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def _download_file(self, url, filepath):
        # Use self.session instead of requests.get
        with self.session.get(url, timeout=30, stream=True) as response:
            ...
```

## 🟢 Medium Priority Issues

### 8. Memory Usage in Archive Creation
**Location:** `src/reddit_downloader/web/app.py:302-310`

**Issue:** Entire archive loaded into memory before compression.

**Problem:** Could cause OOM for large downloads (>1GB).

**Fix:**
```python
# Stream compression instead
import tempfile

def api_download_archive(job_id):
    # ... validation ...
    
    # Create archive in temp file instead of memory
    with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{extension}') as tmp:
        if archive_format == "zip":
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in files:
                    zf.write(str(file_path), arcname=file_path.name)
        else:  # tar.zst
            with tarfile.open(fileobj=tmp, mode="w") as tar:
                for file_path in files:
                    tar.add(str(file_path), arcname=file_path.name)
        
        tmp_path = Path(tmp.name)
    
    # Send file and cleanup
    response = send_file(str(tmp_path), ...)
    
    @response.call_on_close
    def cleanup():
        try:
            tmp_path.unlink()
            # Delete original files
            for file_path in files:
                if file_path.exists():
                    file_path.unlink()
        except OSError as e:
            logger.error(f"Cleanup failed: {e}")
```

### 9. File Deletion on Failed Download
**Location:** `src/reddit_downloader/web/app.py:240-247`

**Problem:** File deleted even if client disconnects mid-download.

**Fix:**
```python
# Only delete if response completed successfully
@response.call_on_close
def cleanup():
    # Check if response was successful
    if response.status_code == 200:
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
```

### 10. Using print() Instead of Logging
**Location:** `src/reddit_downloader/web/app.py` (multiple places)

**Issue:**
```python
print(f"Deleted downloaded file: {file_path}")
print(f"Warning: Failed to delete file {file_path}: {e}")
```

**Fix:**
```python
import logging
logger = logging.getLogger(__name__)

# Replace all print() with appropriate log levels
logger.info(f"Deleted downloaded file: {file_path}")
logger.warning(f"Failed to delete file {file_path}: {e}")
```

### 11. No Input Validation on Limit Parameter
**Location:** `src/reddit_downloader/web/app.py:56`

**Issue:**
```python
limit = request.json.get("limit")  # No validation
```

**Fix:**
```python
limit = request.json.get("limit")
if limit is not None:
    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        return {"success": False, "error": "Limit must be between 1 and 1000"}, 400
```

### 12. Weak Error Messages
**Location:** Multiple files

**Problem:** Generic errors don't help users troubleshoot.

**Fix:**
```python
# Bad
return DownloadResult(success=False, error="Download failed")

# Good
return DownloadResult(
    success=False, 
    error=f"Download failed: HTTP {response.status_code} - {response.reason}"
)
```

### 13. No Timeout Configuration
**Location:** `src/reddit_downloader/downloader.py:170`

**Issue:** Hardcoded 30-second timeout might be too short for large files.

**Fix:**
```python
class MediaDownloader:
    def __init__(self, output_dir, *, verbose=False, timeout=300):
        self.timeout = timeout
    
    def _download_file(self, url, filepath):
        with requests.get(url, timeout=self.timeout, stream=True) as response:
            ...
```

## 🔵 Low Priority / Style Issues

### 14. Unused Variable in Iteration
**Location:** `src/reddit_downloader/downloader.py:410`

```python
for index, (_media_id, media_item) in enumerate(media_metadata.items(), start=1):
```

**Better:**
```python
for index, (media_id, media_item) in enumerate(media_metadata.items(), start=1):
    logger.debug(f"Processing gallery item {media_id}")
```

### 15. Inconsistent Error Handling
**Problem:** Some functions return None on error, others raise exceptions, some return bool.

**Fix:** Be consistent - either use exceptions or return Result types throughout.

## 📋 Additional Recommendations

### 16. Add Health Check Endpoint
```python
@app.route("/health")
def health():
    return {"status": "ok", "timestamp": time.time()}, 200
```

### 17. Add Request ID Tracking
```python
import uuid
from flask import g

@app.before_request
def before_request():
    g.request_id = str(uuid.uuid4())
    logger.info(f"Request {g.request_id}: {request.method} {request.path}")
```

### 18. Add File Size Limits
```python
# Prevent disk space exhaustion
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

def _download_file(self, url, filepath):
    with requests.get(url, timeout=30, stream=True) as response:
        response.raise_for_status()
        
        # Check content length
        content_length = response.headers.get('content-length')
        if content_length and int(content_length) > MAX_FILE_SIZE:
            raise ValueError(f"File too large: {content_length} bytes")
        
        # Track downloaded size
        downloaded = 0
        with tempfile.NamedTemporaryFile(...) as tmp_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    downloaded += len(chunk)
                    if downloaded > MAX_FILE_SIZE:
                        raise ValueError(f"File exceeded size limit: {downloaded} bytes")
                    tmp_file.write(chunk)
```

### 19. Add Metrics/Monitoring
```python
# Track download statistics
from dataclasses import dataclass
from datetime import datetime

@dataclass
class DownloadMetrics:
    total_downloads: int = 0
    failed_downloads: int = 0
    total_bytes: int = 0
    start_time: datetime = datetime.now()
```

### 20. Add Configuration File Support
Instead of environment variables only, support config files:
```python
# config.yaml
reddit:
  client_id: "..."
  client_secret: "..."
  user_agent: "..."

downloads:
  output_dir: "downloads"
  max_file_size: 104857600  # 100MB
  timeout: 300

server:
  host: "127.0.0.1"
  port: 5000
```

## Summary

**Critical:** 3 issues requiring immediate attention
**High:** 4 issues that should be fixed before production use
**Medium:** 6 issues to improve reliability and user experience
**Low:** 5 minor improvements for code quality

Priority order for fixes:
1. Fix global state in web app (breaks multi-worker deployments)
2. Add rate limiting (avoid API bans)
3. Implement proper job cancellation
4. Add retry logic for network requests
5. Fix memory issues in archive creation
6. Replace print() with logging
7. Add input validation
8. Improve error messages

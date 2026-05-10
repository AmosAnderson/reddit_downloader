# Implementation Plan

This document tracks the plan to address the code review recommendations for robustness, functional correctness, security, idiomatic Python, and operational reliability.

## Current Baseline

Verified checks:

- `uv sync --extra dev && uv run pytest` — 86 passed
- `uv run ruff check src/ tests/` — passed
- `uv run mypy src/` — passed

Note: the documented `uv sync --dev` does not install the optional dev dependencies as currently configured. Use `uv sync --extra dev`, or migrate dev dependencies to uv dependency groups.

---

## Phase 0 — Baseline and Housekeeping

**Status:** Complete.

### 0.1 Fix development setup documentation

**Files:**

- `README.md`
- `CLAUDE.md`
- optionally `pyproject.toml`

**Tasks:**

- [x] Replace documented `uv sync --dev` commands with `uv sync --extra dev`.
- [x] Keep dev dependencies under `[project.optional-dependencies]` for now.
- [x] Re-run the baseline checks after documentation changes.

**Validation:**

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

---

## Phase 1 — Functional Correctness

**Status:** Complete.

### 1.1 Harden Reddit URL parsing

**Files:**

- `src/reddit_downloader/parser.py`
- `tests/test_parser.py`

**Tasks:**

- [x] Require URLs to use `http` or `https`.
- [x] Decide and implement intended behavior for `v.redd.it` links.
  - `v.redd.it/<id>` is treated as invalid because those IDs are media IDs, not Reddit submission IDs.
- [x] Add tests for:
  - `ftp://reddit.com/...`
  - unsupported schemes
  - `v.redd.it/<media_id>` behavior
  - existing valid post/user/redd.it URLs

---

### 1.2 Fix media URL extension detection

**Files:**

- `src/reddit_downloader/downloader.py`
- `tests/test_downloader.py`

**Tasks:**

- [x] Use `urlparse(post.url).path.lower()` for extension checks instead of checking the full URL string.
- [x] Ensure direct image URLs with query strings are detected correctly.
- [x] Include `.webp` in external direct-image download handling.

**Tests to add:**

- Reddit-hosted image URL with query parameters.
- External `.webp` direct image URL.
- External direct image URL with query parameters.

---

### 1.3 Preserve Reddit gallery ordering and improve URL decoding

**Files:**

- `src/reddit_downloader/downloader.py`
- `tests/test_downloader.py`

**Tasks:**

- [x] Prefer gallery order from `post.gallery_data["items"]`.
- [x] Use item `media_id` values from `gallery_data` to look up `post.media_metadata` entries.
- [x] Fall back to `media_metadata.items()` when `gallery_data` is missing or malformed.
- [x] Replace manual `"&amp;"` replacement with `html.unescape()`.

**Tests to add:**

- Gallery downloads follow `gallery_data` order.
- Gallery URL HTML entities are decoded correctly.
- Missing `gallery_data` falls back safely.

---

### 1.4 Clarify authentication health behavior

**File:**

- `src/reddit_downloader/client.py`

**Tasks:**

- [x] Add `can_access_api()` to perform a lightweight actual Reddit API request and catch PRAW/prawcore exceptions.
- [x] Keep `is_authenticated()` as a backward-compatible alias with clarified docs.
- [x] Add/update tests to reflect the intended behavior.

---

## Phase 2 — Download Robustness and Cancellation

**Status:** Complete.

### 2.1 Avoid filename and temporary-file collisions

**Files:**

- `src/reddit_downloader/downloader.py`
- `src/reddit_downloader/web/jobs.py`
- `tests/test_downloader.py`
- `tests/test_web_jobs.py`

**Tasks:**

- [x] For web jobs, write files into a job-specific directory:

```text
<output_dir>/<job_id>/
```

- [x] Replace predictable video temp files such as `temp_video_<filename>` with unique `tempfile`-based paths.
- [x] Keep repeated CLI download behavior as overwrite-existing for now; web job isolation avoids concurrent job collisions.

**Tests to add:**

- Two web jobs for the same post do not collide.
- Video temp files are cleaned up.
- Duplicate filenames are handled according to the chosen policy.

---

### 2.2 Make downloads cancellation-aware

**Files:**

- `src/reddit_downloader/downloader.py`
- `src/reddit_downloader/web/jobs.py`
- `tests/test_downloader.py`
- `tests/test_web_jobs.py`

**Tasks:**

- [x] Add an optional `threading.Event` cancellation signal to `MediaDownloader`.
- [x] Check cancellation:
  - before starting each download,
  - during streamed chunk iteration,
  - before/after video/audio merge,
  - between user posts.
- [x] Remove partial files and temporary files when cancellation happens.
- [x] Ensure cancelled jobs are marked `JobStatus.CANCELLED`, not `FAILED`.

**Tests to add:**

- Cancellation during a chunked file download.
- Cancellation during a user download loop.
- Partial files are cleaned up.

---

### 2.3 Improve download error specificity

**Files:**

- `src/reddit_downloader/downloader.py`
- optionally `src/reddit_downloader/types.py`
- tests

**Tasks:**

- [x] Preserve richer internal download error detail via the downloader's last-error state while keeping the public `DownloadResult.error` string API.
- [x] Keep the public `DownloadResult.error` string.
- [x] Preserve error details for:
  - HTTP status failures,
  - timeouts,
  - file size limit failures,
  - filesystem errors,
  - cancellation,
  - unsupported media,
  - ffmpeg missing or merge failure.

**Tests to add:**

- Timeout/request exception returns useful error.
- HTTP error includes status/reason.
- Oversized file returns size-specific error.

---

## Phase 3 — Security Hardening

**Status:** Complete.

### 3.1 Add SSRF protection for downloads

**Files:**

- `src/reddit_downloader/downloader.py`
- optionally new helper module: `src/reddit_downloader/security.py`
- tests

**Tasks:**

- [x] Validate all download URLs before fetching.
- [x] Require `http` or `https`.
- [x] Require a hostname.
- [x] Resolve hostnames and reject resolved addresses that are:
  - private,
  - loopback,
  - link-local,
  - multicast,
  - reserved,
  - unspecified.
- [x] Consider a stricter allowlist mode for external media domains. Deferred; current implementation validates public routability while preserving broad media-host compatibility.
- [x] Decide how to handle DNS rebinding risks. Current implementation resolves and validates immediately before download; deeper redirect/rebinding handling remains a future hardening item.

**Tests to add:**

- Reject `http://127.0.0.1/...`.
- Reject `http://localhost/...`.
- Reject `http://169.254.169.254/...`.
- Accept representative public hosts.
- Reject unsupported schemes.

---

### 3.2 Harden web UI exposure and optional authentication

**Files:**

- `src/reddit_downloader/web/app.py`
- `src/reddit_downloader/__main__.py`
- `docker-compose.yml`
- `README.md`
- tests

**Tasks:**

- [x] Bind Docker port to localhost by default:

```yaml
ports:
  - "127.0.0.1:5000:5000"
```

- [x] Document that the web app should not be exposed publicly without authentication.
- [x] Add optional API authentication via environment variable, for example:

```text
REDDIT_DOWNLOADER_AUTH_TOKEN=<token>
```

- [x] If configured, require the token on API routes via header such as:

```text
Authorization: Bearer <token>
```

- [x] Decide whether static assets and `/health` require authentication. Only `/api/*` routes require the token; static assets, `/`, and `/health` remain public.

**Tests to add:**

- API request without token is rejected when auth is enabled.
- API request with token succeeds.
- Auth-disabled behavior remains unchanged.

---

## Phase 4 — Web Job Lifecycle and Consistency

**Status:** Complete.

### 4.1 Return thread-safe job snapshots

**Files:**

- `src/reddit_downloader/web/jobs.py`
- optionally `src/reddit_downloader/types.py`
- `tests/test_web_jobs.py`

**Tasks:**

- [x] Ensure `get_job()` and `list_jobs()` return snapshots/copies, not live mutable objects.
- [x] Keep all mutation inside `JobManager` while holding the lock.
- [x] Replace or harden `update_job(**kwargs)`:
  - validate field names strictly.

**Tests to add:**

- Mutating a returned job snapshot does not mutate manager state.
- Invalid update fields are rejected or logged.

---

### 4.2 Add job retention and cleanup

**Files:**

- `src/reddit_downloader/web/jobs.py`
- `src/reddit_downloader/web/app.py`
- `src/reddit_downloader/types.py`
- tests

**Tasks:**

- [x] Add `updated_at` to `DownloadJob`.
- [x] Add cleanup settings:
  - max job age,
  - max job count.
- [x] Implement `cleanup_jobs(...)` to remove old jobs and their job-specific output directories.
- [x] Trigger cleanup:
  - when starting API downloads,
  - when listing jobs.

**Tests to add:**

- Old completed jobs are removed.
- Old failed/cancelled jobs are removed.
- Job directories are cleaned up.
- Running jobs are not removed.

---

### 4.3 Avoid sharing one PRAW client across concurrent job threads

**Files:**

- `src/reddit_downloader/client.py`
- `src/reddit_downloader/web/app.py`
- `src/reddit_downloader/web/jobs.py`
- tests

**Recommended approach:**

- Store Reddit credentials/config in the app, not a single client instance.
- Create a new `RedditClient` per job.

**Tasks:**

- [x] Add a simple factory callable.
- [x] Update `run_web_server()` to pass a factory into the app.
- [x] Update `JobManager.start_job()`/`run_job()` to create/use a per-job client when a factory is supplied.
- [x] Preserve testability with injectable fake clients/factories.

---

### 4.4 Revisit file deletion after browser download

**Files:**

- `src/reddit_downloader/web/app.py`
- `src/reddit_downloader/web/jobs.py`
- frontend files if UI state changes are needed
- tests

**Recommended approach:**

- [x] Prefer TTL-based cleanup over immediate deletion after response close.
Deferred optional follow-up: add an explicit “delete now” endpoint in a later phase if desired.

**Implemented:**

- [x] Single-file downloads no longer delete source files immediately.
- [x] Archive downloads delete only the temporary archive after transfer; source files remain until old-job cleanup.
- [x] Documentation and frontend messages now state that files are retained until cleanup.

**Tests to add:**

- Single file cleanup behavior.
- Archive cleanup behavior.
- UI file list excludes deleted files.
- Cleanup does not delete files outside the output root.

---

## Phase 5 — CLI and User Experience

**Status:** Complete.

### 5.1 Configure logging for verbose mode

**File:**

- `src/reddit_downloader/__main__.py`

**Tasks:**

- [x] Add logging configuration.
- [x] Set DEBUG level when `--verbose` is used.
- [x] Keep human-readable CLI output with `print()`, but send internal diagnostics to logging.

---

### 5.2 Validate CLI limit values

**File:**

- `src/reddit_downloader/__main__.py`
- CLI tests

**Tasks:**

- [x] Reject `--limit <= 0`.
- [x] Match web behavior by capping at 1000.
- [x] Add tests for invalid limit values.

---

### 5.3 Add browser-opening control

**Files:**

- `src/reddit_downloader/__main__.py`
- `src/reddit_downloader/web/app.py`
- `Dockerfile`

**Tasks:**

- [x] Add CLI flag:

```bash
--no-open-browser
```

- [x] Pass `open_browser_on_start=not args.no_open_browser` into `run_web_server()`.
- [x] In Docker, pass `--no-open-browser`.
Deferred optional follow-up: auto-disable browser opening when not running interactively if desired.

---

## Phase 6 — Packaging and Docker

**Status:** Complete.

### 6.1 Make Docker builds reproducible

**File:**

- `Dockerfile`

**Tasks:**

- [x] Copy `uv.lock` into the image before syncing.
- [x] Use frozen dependency resolution:

```dockerfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
```

- [x] Ensure the command matches the actual uv behavior for this project.

---

### 6.2 Run Docker container as non-root

**File:**

- `Dockerfile`

**Tasks:**

- [x] Create an application user.
- [x] Make `/app` and `/downloads` writable where needed.
- [x] Switch to the non-root user with `USER`.
- [x] Verify Dockerfile structure supports writable `/downloads`; bind-mounted directory ownership may still need host-specific adjustment.

---

### 6.3 Remove unused dependency

**File:**

- `pyproject.toml`
- `uv.lock`

**Tasks:**

- [x] Remove `ffmpeg-python` unless the code is changed to use it.
- [x] Keep the system `ffmpeg` executable requirement documented.
- [x] Update lockfile:

```bash
uv lock
```

---

## Phase 7 — Test Expansion and Final Validation

**Status:** Complete, except Docker build could not be run because Docker is unavailable in this environment.

### 7.1 Add missing tests

Priority areas:

- [x] CLI command behavior.
- [x] URL validation schemes and `v.redd.it` behavior.
- [x] Media URLs with query strings.
- [x] External `.webp` downloads.
- [x] Gallery order and HTML entity decoding.
- [x] File collision/concurrent download behavior.
- [x] SSRF/private-IP blocking.
- [x] Cancellation during active chunked download.
- [x] Job snapshots and job cleanup.
- [x] Archive route behavior:
  - zip success,
  - invalid format,
  - path traversal/outside-output rejection,
  - source file retention.
- [x] Single-file download route behavior:
  - path traversal/outside-output rejection,
  - source file retention.
- [x] Optional auth behavior.

Deferred/future test items:

- TAR.ZST archive success path.
- Archive temporary-file cleanup error handling.
- Single-file invalid-index and unavailable-file cases beyond existing route coverage.

---

### 7.2 Final validation commands

Run:

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
docker compose build
```

Completed validation:

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest
```

Result: 124 tests passed; ruff and mypy passed.

Docker validation note: `docker compose build` could not be run because Docker is not installed/available in this environment (`docker: command not found`).

Manual smoke tests:

1. Web UI starts.
2. Single Reddit image post download works.
3. Reddit video download works with ffmpeg installed.
4. Gallery download preserves gallery order.
5. User download with a small limit works.
6. Cancelling a large download stops promptly and cleans partial files.
7. ZIP archive download works.
8. TAR.ZST archive download works.
9. Job cleanup removes stale metadata and files.
10. Docker container runs as non-root.
11. Auth/token behavior works if enabled.
12. Docker-localhost binding behaves as documented.

---

## Suggested Implementation Order

1. Fix docs/dev setup commands.
2. Fix URL parsing and media detection correctness.
3. Fix gallery ordering and HTML decoding.
4. Add per-job output directories and unique temp files.
5. Add cancellation-aware downloads.
6. Improve download error reporting.
7. Add SSRF protection.
8. Add web exposure/auth hardening.
9. Add job snapshots and job cleanup.
10. Avoid shared PRAW clients across job threads.
11. Revisit file deletion semantics.
12. Polish CLI logging, limit validation, and browser-opening behavior.
13. Improve Docker reproducibility and non-root runtime.
14. Remove unused dependency.
15. Expand tests and run final validation.

"""Textual TUI Application for reddit_downloader."""

import os
import sys
import threading
import subprocess
from pathlib import Path
from typing import ClassVar
from datetime import datetime

from dotenv import load_dotenv
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    Static,
    ListItem,
    ListView,
)
from textual.reactive import reactive

from reddit_downloader.client import RedditClient
from reddit_downloader.parser import validate_reddit_url, parse_url
from reddit_downloader.types import JobStatus, DownloadJob
from reddit_downloader.jobs import JobManager

# Cross-platform directory opener helper
def open_directory(path: Path) -> None:
    """Open a directory in the default system file manager."""
    if not path.exists():
        return
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=True)
        else:  # Linux/other
            subprocess.run(["xdg-open", str(path)], check=True)
    except Exception:
        pass


class CredentialsModal(ModalScreen[tuple[str, str, str] | None]):
    """Modal screen for entering Reddit API credentials."""

    DEFAULT_CSS = """
    CredentialsModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #modal_container {
        width: 60;
        height: auto;
        background: #1e1e1e;
        border: double #8a2be2;
        border-title-color: #00f0ff;
        padding: 1 2;
        content-align: center middle;
    }

    .modal-title {
        text-align: center;
        text-style: bold;
        color: #00f0ff;
        margin-bottom: 1;
    }

    .modal-label {
        color: #e0e0e0;
        margin-top: 1;
    }

    .modal-input {
        background: #121212;
        border: solid #444444;
        color: #ffffff;
        margin-bottom: 1;
    }
    
    .modal-input:focus {
        border: solid #00f0ff;
    }

    .modal-buttons {
        margin-top: 2;
        align: center middle;
    }

    .modal-btn {
        margin: 0 1;
        width: 15;
    }

    #save_btn {
        background: #8a2be2;
        color: white;
    }

    #cancel_btn {
        background: #444444;
        color: white;
    }
    """

    def __init__(self, client_id: str = "", client_secret: str = "", user_agent: str = "") -> None:
        super().__init__()
        self.initial_client_id = client_id
        self.initial_client_secret = client_secret
        self.initial_user_agent = user_agent or "reddit_downloader/0.1.0"

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_container"):
            yield Label("Reddit API Credentials Setup", classes="modal-title")
            
            yield Label("Client ID:", classes="modal-label")
            yield Input(
                value=self.initial_client_id,
                placeholder="Enter Reddit Client ID...",
                classes="modal-input",
                id="modal_client_id",
            )
            
            yield Label("Client Secret:", classes="modal-label")
            yield Input(
                value=self.initial_client_secret,
                placeholder="Enter Reddit Client Secret...",
                password=True,
                classes="modal-input",
                id="modal_client_secret",
            )
            
            yield Label("User Agent:", classes="modal-label")
            yield Input(
                value=self.initial_user_agent,
                placeholder="reddit_downloader/0.1.0",
                classes="modal-input",
                id="modal_user_agent",
            )
            
            with Horizontal(classes="modal-buttons"):
                yield Button("Save", id="save_btn", classes="modal-btn")
                yield Button("Cancel", id="cancel_btn", classes="modal-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save_btn":
            client_id = self.query_one("#modal_client_id", Input).value.strip()
            client_secret = self.query_one("#modal_client_secret", Input).value.strip()
            user_agent = self.query_one("#modal_user_agent", Input).value.strip()
            self.dismiss((client_id, client_secret, user_agent))
        elif event.button.id == "cancel_btn":
            self.dismiss(None)


class JobWidget(Static):
    """Widget to display the status and progress of a single download job."""

    DEFAULT_CSS = """
    JobWidget {
        background: #1e1e1e;
        border: solid #333333;
        margin: 0 0 1 0;
        padding: 1;
        height: auto;
    }

    JobWidget:hover {
        border: solid #8a2be2;
    }

    .job-title-row {
        height: auto;
        margin-bottom: 1;
    }

    .job-url-label {
        color: #00f0ff;
        text-style: bold;
        width: 1fr;
    }

    .job-status-badge {
        padding: 0 1;
        text-style: bold;
        background: #444444;
        color: #ffffff;
    }

    .status-queued { background: #555555; color: white; }
    .status-running { background: #8a2be2; color: white; }
    .status-completed { background: #2e8b57; color: white; }
    .status-failed { background: #dc143c; color: white; }
    .status-cancelled { background: #b22222; color: white; }

    .job-progress-info {
        color: #a0a0a0;
        margin-top: 1;
    }

    .job-current-post {
        color: #ffd700;
        text-style: italic;
        margin-top: 1;
    }

    .job-error-msg {
        color: #ff4500;
        margin-top: 1;
        text-style: bold;
    }

    .job-actions {
        margin-top: 1;
        align: right middle;
    }

    .job-action-btn {
        margin-left: 1;
        height: 3;
    }

    #job_cancel_btn {
        background: #dc143c;
        color: white;
    }

    #job_open_btn {
        background: #2e8b57;
        color: white;
    }
    """

    def __init__(self, job: DownloadJob, output_dir: Path) -> None:
        super().__init__()
        self.job_id = job.job_id
        self.url = job.url
        self.output_dir = output_dir
        self.status = job.status
        self.total_items = job.total_items
        self.completed_items = job.completed_items
        self.failed_items = job.failed_items
        self.current_item = job.current_item
        self.error = job.error

    def compose(self) -> ComposeResult:
        with Horizontal(classes="job-title-row"):
            yield Label(self.url, classes="job-url-label")
            status_text = self.status.value.upper()
            yield Label(status_text, id="status_badge", classes=f"job-status-badge status-{self.status.value}")

        yield ProgressBar(
            total=max(1, self.total_items),
            show_bar=True,
            show_percentage=True,
            id="job_progress",
        )

        progress_text = f"Downloaded {self.completed_items} of {self.total_items} posts" if self.total_items > 0 else "Preparing download..."
        if self.failed_items > 0:
            progress_text += f" ({self.failed_items} failed)"
            
        yield Label(progress_text, id="progress_label", classes="job-progress-info")
        yield Label(self.current_item or "", id="current_post_label", classes="job-current-post")
        yield Label(self.error or "", id="error_label", classes="job-error-msg")

        with Horizontal(classes="job-actions"):
            yield Button("Cancel", id="job_cancel_btn", classes="job-action-btn")
            yield Button("Open Folder", id="job_open_btn", classes="job-action-btn")

    def on_mount(self) -> None:
        self.update_widget_values()

    def update_job(self, job: DownloadJob) -> None:
        """Update widget parameters with new job state."""
        self.status = job.status
        self.total_items = job.total_items
        self.completed_items = job.completed_items
        self.failed_items = job.failed_items
        self.current_item = job.current_item
        self.error = job.error
        self.update_widget_values()

    def update_widget_values(self) -> None:
        """Apply state to visual sub-widgets."""
        if not self.is_mounted:
            return

        # Update badge
        badge = self.query_one("#status_badge", Label)
        badge.update(self.status.value.upper())
        badge.classes = f"job-status-badge status-{self.status.value}"

        # Update progress bar
        pb = self.query_one("#job_progress", ProgressBar)
        pb.total = max(1, self.total_items)
        pb.progress = self.completed_items

        # Update progress label
        progress_text = f"Downloaded {self.completed_items} of {self.total_items} posts" if self.total_items > 0 else "Preparing download..."
        if self.failed_items > 0:
            progress_text += f" ({self.failed_items} failed)"
        self.query_one("#progress_label", Label).update(progress_text)

        # Update current post
        cp_label = self.query_one("#current_post_label", Label)
        if self.current_item and self.status == JobStatus.RUNNING:
            cp_label.update(f"Current: {self.current_item}")
            cp_label.display = True
        else:
            cp_label.display = False

        # Update error
        err_label = self.query_one("#error_label", Label)
        if self.error:
            err_label.update(f"Error: {self.error}")
            err_label.display = True
        else:
            err_label.display = False

        # Manage buttons visibility
        cancel_btn = self.query_one("#job_cancel_btn", Button)
        open_btn = self.query_one("#job_open_btn", Button)

        if self.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            cancel_btn.display = True
            open_btn.display = False
        else:
            cancel_btn.display = False
            open_btn.display = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "job_cancel_btn":
            self.app.cancel_download_job(self.job_id)  # type: ignore[attr-defined]
        elif event.button.id == "job_open_btn":
            job_dir = self.output_dir / self.job_id
            open_directory(job_dir)


class RedditDownloaderTUI(App[int]):
    """Textual TUI Application for Reddit Media Downloader."""

    TITLE = "Reddit Downloader TUI"
    SUB_TITLE = "Download media from Reddit posts and users"

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit", show=True),
        Binding("c", "clear_finished", "Clear Finished", show=True),
        Binding("w", "toggle_web_server", "Toggle Web Server", show=True),
        Binding("s", "setup_api", "Settings (API Keys)", show=True),
    ]

    DEFAULT_CSS = """
    Screen {
        background: #121212;
    }

    #main_layout {
        layout: grid;
        grid-size: 2;
        grid-columns: 35 1fr;
        height: 1fr;
    }

    #sidebar {
        background: #1a1a1a;
        border-right: solid #333333;
        padding: 1 2;
    }

    #content_area {
        layout: grid;
        grid-size: 1;
        grid-rows: 2fr 1fr;
        background: #161616;
        padding: 1 2;
    }

    #jobs_container {
        border-bottom: solid #333333;
        padding-bottom: 1;
    }

    #details_container {
        padding-top: 1;
    }

    .section-title {
        color: #00f0ff;
        text-style: bold;
        margin-bottom: 1;
    }

    .form-label {
        color: #e0e0e0;
        margin-top: 1;
    }

    .form-input {
        background: #121212;
        border: solid #444444;
        color: #ffffff;
        margin-bottom: 1;
    }

    .form-input:focus {
        border: solid #00f0ff;
    }

    #download_btn {
        background: #8a2be2;
        color: white;
        margin-top: 2;
        width: 100%;
        text-style: bold;
    }

    #download_btn:hover {
        background: #9932cc;
    }

    .api-status-panel {
        background: #222222;
        border: solid #444444;
        padding: 1;
        margin-top: 2;
    }

    .status-indicator {
        text-style: bold;
    }
    
    .status-ok { color: #2e8b57; }
    .status-err { color: #dc143c; }

    #web_server_panel {
        background: #1e1e1e;
        border: solid #8a2be2;
        padding: 1;
        margin-top: 2;
    }

    .web-title {
        color: #00f0ff;
        text-style: bold;
    }

    .web-url {
        color: #ffd700;
        text-style: underline;
    }

    /* Selected job files list */
    #files_list {
        background: #121212;
        border: solid #333333;
        height: 1fr;
        margin-top: 1;
    }

    .file-item-label {
        padding: 0 1;
        color: #e0e0e0;
    }
    """

    def __init__(
        self,
        output_dir: Path,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        super().__init__()
        self.output_dir = output_dir
        
        # Load env vars first
        load_dotenv()
        self.client_id = client_id or os.getenv("REDDIT_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET", "")
        self.user_agent = user_agent or os.getenv("REDDIT_USER_AGENT", "reddit_downloader/0.1.0")

        self.job_manager = JobManager()
        self.reddit_client: RedditClient | None = None
        self.web_server_thread: threading.Thread | None = None
        self.web_server_running = False

        self.selected_job_id: str | None = None
        self.job_widgets_map: dict[str, JobWidget] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Horizontal(id="main_layout"):
            # Sidebar panel (Inputs and config status)
            with Vertical(id="sidebar"):
                yield Label("ADD NEW DOWNLOAD", classes="section-title")
                
                yield Label("Reddit URL (Post or User):", classes="form-label")
                yield Input(
                    placeholder="https://reddit.com/r/...",
                    id="input_url",
                    classes="form-input",
                )
                
                yield Label("Limit (For User posts only):", classes="form-label")
                yield Input(
                    placeholder="e.g. 50 (optional)",
                    id="input_limit",
                    classes="form-input",
                )
                
                yield Button("Start Download", id="download_btn")

                # API Status panel
                with Vertical(classes="api-status-panel"):
                    yield Label("REDDIT API CONFIG", classes="form-label")
                    yield Label("Status: Checking...", id="api_status_label", classes="status-indicator")
                    yield Button("Update API Keys", id="sidebar_api_btn", classes="form-input")

                # Web Server panel
                with Vertical(id="web_server_panel"):
                    yield Label("TEXTUAL WEB SERVER", classes="web-title")
                    yield Label("Status: Stopped", id="web_server_status")
                    yield Label("Address: http://127.0.0.1:8000", id="web_server_address")
                    
            # Content Area (Active Downloads and selected item details)
            with Vertical(id="content_area"):
                # Top section: Download Jobs List
                with Vertical(id="jobs_container"):
                    yield Label("DOWNLOAD QUEUE & PROGRESS", classes="section-title")
                    with ScrollableContainer(id="jobs_scroll"):
                        # Job widgets will be mounted dynamically here
                        pass

                # Bottom section: Details of selected download
                with Vertical(id="details_container"):
                    yield Label("DOWNLOADED FILES INFO", classes="section-title")
                    yield Label("Select a completed download to view files", id="details_instructions")
                    yield ListView(id="files_list")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize components and start timers."""
        self.query_one("#web_server_address", Label).display = False
        self.query_one("#files_list", ListView).display = False
        
        # Validate and configure Reddit Client
        self.update_api_status()

        # Start job refresh loop timer (every 1.0 second)
        self.set_interval(1.0, self.refresh_jobs_tui)

        # Trigger settings dialog immediately if credentials are empty
        if not self.client_id or not self.client_secret:
            self.action_setup_api()

    def get_reddit_client(self) -> RedditClient:
        """Factory method to get the current RedditClient."""
        if self.reddit_client is None:
            self.reddit_client = RedditClient(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent,
            )
        return self.reddit_client

    def update_api_status(self) -> None:
        """Validate current API credentials and update UI indicators."""
        label = self.query_one("#api_status_label", Label)
        
        if not self.client_id or not self.client_secret:
            label.update("Status: Missing Credentials ❌")
            label.classes = "status-indicator status-err"
            self.reddit_client = None
            return

        def check_status() -> None:
            try:
                client = RedditClient(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    user_agent=self.user_agent,
                )
                if client.can_access_api():
                    self.reddit_client = client
                    self.call_after_refresh(self._set_api_label, "Status: Connected ✅", "status-indicator status-ok")
                else:
                    self.reddit_client = None
                    self.call_after_refresh(self._set_api_label, "Status: Access Denied ❌", "status-indicator status-err")
            except Exception:
                self.reddit_client = None
                self.call_after_refresh(self._set_api_label, "Status: Connection Error ❌", "status-indicator status-err")

        threading.Thread(target=check_status, daemon=True).start()

    def _set_api_label(self, text: str, classes: str) -> None:
        label = self.query_one("#api_status_label", Label)
        label.update(text)
        label.classes = classes

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "download_btn":
            self.start_new_download()
        elif event.button.id == "sidebar_api_btn":
            self.action_setup_api()

    def start_new_download(self) -> None:
        """Verify inputs and queue a new background download job."""
        url_input = self.query_one("#input_url", Input)
        limit_input = self.query_one("#input_limit", Input)

        url = url_input.value.strip()
        if not url:
            self.notify("URL field is empty!", severity="warning")
            return

        if not validate_reddit_url(url):
            self.notify("Invalid Reddit URL!", severity="error")
            return

        # Check credentials
        if self.reddit_client is None:
            self.notify("Cannot download: Reddit API credentials are missing or invalid!", severity="error")
            return

        # Parse limit
        limit = None
        limit_str = limit_input.value.strip()
        if limit_str:
            try:
                limit = int(limit_str)
                if limit < 1 or limit > 1000:
                    self.notify("Limit must be between 1 and 1000!", severity="warning")
                    return
            except ValueError:
                self.notify("Limit must be a valid integer!", severity="warning")
                return

        # Create job
        try:
            job_id = self.job_manager.create_job(url, limit)
            self.job_manager.start_job(
                job_id,
                None,
                self.output_dir,
                limit,
                client_factory=self.get_reddit_client,
            )
            
            # Reset inputs
            url_input.value = ""
            limit_input.value = ""
            self.notify("Download job added to queue!", severity="information")

            # Force immediate TUI update to display new job widget
            self.refresh_jobs_tui()
        except Exception as e:
            self.notify(f"Failed to start download: {e}", severity="error")

    def cancel_download_job(self, job_id: str) -> None:
        """Cancel an active download job."""
        success = self.job_manager.cancel_job(job_id)
        if success:
            self.notify("Cancellation requested.", severity="information")
        else:
            self.notify("Could not cancel job.", severity="warning")

    def refresh_jobs_tui(self) -> None:
        """Refresh all job widgets with the latest state from JobManager."""
        jobs = self.job_manager.list_jobs()
        container = self.query_one("#jobs_scroll", ScrollableContainer)

        current_job_ids = {job.job_id for job in jobs}

        # Remove widgets for deleted jobs
        for job_id in list(self.job_widgets_map.keys()):
            if job_id not in current_job_ids:
                widget = self.job_widgets_map.pop(job_id)
                widget.remove()
                if self.selected_job_id == job_id:
                    self.selected_job_id = None
                    self.update_details_pane()

        # Update existing widgets and mount new ones
        for job in jobs:
            if job.job_id in self.job_widgets_map:
                # Update existing
                self.job_widgets_map[job.job_id].update_job(job)
            else:
                # Add new widget
                widget = JobWidget(job, self.output_dir)
                self.job_widgets_map[job.job_id] = widget
                # Mount it and make it clickable by binding on-click Focus/Select behavior
                container.mount(widget)
                
        # Update details pane for current selection
        self.update_details_pane()

    def update_details_pane(self) -> None:
        """Update downloaded files panel based on the selected job."""
        # Find if a completed job has been clicked or selected
        # In a simpler TUI, we can show files for the most recently completed job
        # or let users focus/select a job. Let's find the selected job or the latest completed one.
        selected_job = None
        
        if self.selected_job_id:
            selected_job = self.job_manager.get_job(self.selected_job_id)

        # Fallback to the latest completed job with downloads if none explicitly selected
        if not selected_job:
            completed_jobs = [
                j for j in self.job_manager.list_jobs()
                if j.status == JobStatus.COMPLETED and j.results
            ]
            if completed_jobs:
                selected_job = completed_jobs[0]
                self.selected_job_id = selected_job.job_id

        instructions = self.query_one("#details_instructions", Label)
        list_view = self.query_one("#files_list", ListView)

        if not selected_job or not selected_job.results:
            instructions.update("No completed job selected")
            instructions.display = True
            list_view.display = False
            return

        instructions.display = False
        list_view.display = True
        list_view.clear()

        # Group files
        files_data = []
        for index, result in enumerate(selected_job.results):
            if result.success and result.file_path and result.file_path.exists():
                files_data.append((result.file_path.name, result.file_path.stat().st_size))

        if not files_data:
            list_view.mount(ListItem(Label("No files downloaded or files were deleted.", classes="file-item-label")))
        else:
            header_lbl = Label(f"Files for Job ({selected_job.url[:30]}...):", classes="file-item-label")
            header_lbl.styles.color = "#ffd700"
            list_view.mount(ListItem(header_lbl))
            
            for filename, size_bytes in files_data:
                size_kb = size_bytes / 1024
                size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{(size_kb/1024):.1f} MB"
                item_text = f"📄 {filename} ({size_str})"
                list_view.mount(ListItem(Label(item_text, classes="file-item-label")))

    def action_clear_finished(self) -> None:
        """Clear all completed/failed/cancelled jobs from the list."""
        self.job_manager.cleanup_jobs(self.output_dir)
        self.refresh_jobs_tui()
        self.notify("Cleared finished jobs.", severity="information")

    def action_setup_api(self) -> None:
        """Open the Credentials setup modal screen."""
        def handle_credentials(creds: tuple[str, str, str] | None) -> None:
            if creds:
                client_id, client_secret, user_agent = creds
                self.client_id = client_id
                self.client_secret = client_secret
                self.user_agent = user_agent
                
                # Write to .env file
                self.save_credentials_to_env(client_id, client_secret, user_agent)
                
                # Re-validate
                self.update_api_status()
                self.notify("Credentials updated and saved to .env!", severity="information")

        modal = CredentialsModal(self.client_id, self.client_secret, self.user_agent)
        self.push_screen(modal, handle_credentials)

    def save_credentials_to_env(self, client_id: str, client_secret: str, user_agent: str) -> None:
        """Write Reddit API credentials to local .env file."""
        env_path = Path(".env")
        lines = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()
        
        updates = {
            "REDDIT_CLIENT_ID": client_id,
            "REDDIT_CLIENT_SECRET": client_secret,
            "REDDIT_USER_AGENT": user_agent,
        }
        
        new_lines = []
        seen = set()
        for line in lines:
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                if key in updates:
                    new_lines.append(f"{key}={updates[key]}")
                    seen.add(key)
                    continue
            new_lines.append(line)
            
        for key, val in updates.items():
            if key not in seen:
                new_lines.append(f"{key}={val}")
                
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    def action_toggle_web_server(self) -> None:
        """Start or stop the Textual Web Server in the background."""
        status_lbl = self.query_one("#web_server_status", Label)
        address_lbl = self.query_one("#web_server_address", Label)

        if self.web_server_running:
            self.notify("Web server runs continuously in background. Close TUI to stop.", severity="warning")
            return

        # Start web server thread
        def start_textual_serve() -> None:
            try:
                from textual_serve.server import Server
                cmd_parts = [sys.executable, "-m", "reddit_downloader", "tui"]
                if self.output_dir:
                    cmd_parts.extend(["-o", str(self.output_dir)])
                if self.client_id:
                    cmd_parts.extend(["--client-id", self.client_id])
                if self.client_secret:
                    cmd_parts.extend(["--client-secret", self.client_secret])
                if self.user_agent:
                    cmd_parts.extend(["--user-agent", self.user_agent])
                cmd = " ".join(f'"{p}"' if " " in str(p) else str(p) for p in cmd_parts)

                server = Server(
                    command=cmd,
                    host="127.0.0.1",
                    port=8000,
                    title="Reddit Downloader",
                )
                server.serve()
            except Exception as ex:
                self.notify(f"Web server error: {ex}", severity="error")

        self.web_server_thread = threading.Thread(target=start_textual_serve, daemon=True)
        self.web_server_thread.start()
        self.web_server_running = True

        status_lbl.update("Status: Running ✅")
        status_lbl.styles.color = "#2e8b57"
        address_lbl.display = True
        self.notify("Textual Web Server started at http://127.0.0.1:8000!", severity="information")


def run_tui(
    output_dir: Path | str,
    client_id: str | None = None,
    client_secret: str | None = None,
    user_agent: str | None = None,
) -> int:
    """Launch the Textual TUI Application."""
    app = RedditDownloaderTUI(
        output_dir=Path(output_dir),
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )
    return app.run()

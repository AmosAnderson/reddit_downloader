// Reddit Downloader - Frontend JavaScript

// State
const state = {
    activeJobs: new Set(),
    pollingInterval: null,
};

// DOM Elements
const dropZone = document.getElementById('dropZone');
const urlInput = document.getElementById('urlInput');
const limitInput = document.getElementById('limitInput');
const downloadBtn = document.getElementById('downloadBtn');
const jobsList = document.getElementById('jobsList');
const toast = document.getElementById('toast');
const outputDir = document.getElementById('outputDir');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    loadConfig();
    loadJobs();
    startPolling();
});

// Event Listeners
function setupEventListeners() {
    // Drop zone events
    dropZone.addEventListener('dragover', handleDragOver);
    dropZone.addEventListener('dragleave', handleDragLeave);
    dropZone.addEventListener('drop', handleDrop);

    // Paste detection
    document.addEventListener('paste', handlePaste);

    // Download button
    downloadBtn.addEventListener('click', handleDownload);

    // Enter key in URL input
    urlInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            handleDownload();
        }
    });
}

// Drag and Drop
function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.add('drag-over');
}

function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove('drag-over');

    // Get dropped content
    const text = e.dataTransfer.getData('text/plain');
    const url = extractRedditUrl(text);

    if (url) {
        urlInput.value = url;
        handleDownload();
    } else {
        showToast('No valid Reddit URL found', 'error');
    }
}

// Paste detection
function handlePaste(e) {
    // Only handle paste if not in an input field
    if (e.target.tagName === 'INPUT') {
        return;
    }

    const text = e.clipboardData.getData('text/plain');
    const url = extractRedditUrl(text);

    if (url) {
        urlInput.value = url;
        showToast('URL pasted! Click Download to start.', 'success');
    }
}

// URL Extraction
function extractRedditUrl(text) {
    // Try to find Reddit URL in text
    const urlPattern = /https?:\/\/(www\.)?(old\.|new\.)?reddit\.com\/[^\s]+/g;
    const matches = text.match(urlPattern);

    if (matches && matches.length > 0) {
        return matches[0];
    }

    // If text looks like a URL itself
    if (text.includes('reddit.com')) {
        return text.trim();
    }

    return null;
}

// Download
async function handleDownload() {
    const url = urlInput.value.trim();

    if (!url) {
        showToast('Please enter a Reddit URL', 'error');
        return;
    }

    if (!url.includes('reddit.com')) {
        showToast('Please enter a valid Reddit URL', 'error');
        return;
    }

    const limit = limitInput.value ? parseInt(limitInput.value) : null;

    downloadBtn.disabled = true;
    downloadBtn.textContent = 'Starting...';

    try {
        const response = await fetch('/api/download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url, limit }),
        });

        const data = await response.json();

        if (data.success) {
            showToast('Download started!', 'success');
            urlInput.value = '';
            limitInput.value = '';
            state.activeJobs.add(data.job_id);
            loadJobs();
        } else {
            showToast(data.error || 'Failed to start download', 'error');
        }
    } catch (error) {
        showToast('Error starting download: ' + error.message, 'error');
    } finally {
        downloadBtn.disabled = false;
        downloadBtn.textContent = 'Download';
    }
}

// Load configuration
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        const data = await response.json();

        if (data.success) {
            outputDir.textContent = data.output_dir;
        }
    } catch (error) {
        console.error('Error loading config:', error);
    }
}

// Load jobs
async function loadJobs() {
    try {
        const response = await fetch('/api/downloads');
        const data = await response.json();

        if (data.success) {
            renderJobs(data.jobs);
        }
    } catch (error) {
        console.error('Error loading jobs:', error);
    }
}

// Render jobs list
function renderJobs(jobs) {
    if (jobs.length === 0) {
        jobsList.innerHTML = '<p class="empty-message">No downloads yet</p>';
        return;
    }

    // Jobs are already sorted by server (newest first)
    jobsList.innerHTML = jobs.map(job => createJobElement(job)).join('');

    // Update active jobs
    state.activeJobs.clear();
    jobs.forEach(job => {
        if (job.status === 'running' || job.status === 'queued') {
            state.activeJobs.add(job.job_id);
        }
        // Load files for completed jobs
        if (job.status === 'completed' && job.completed_items > 0) {
            loadJobFiles(job.job_id);
        }
    });
}

// Create job element
function createJobElement(job) {
    const progress = job.total_items > 0
        ? (job.completed_items / job.total_items) * 100
        : 0;

    const progressText = job.total_items > 0
        ? `${job.completed_items} / ${job.total_items} items`
        : 'Preparing...';

    const currentItem = job.current_item
        ? `<div class="job-current">Current: ${escapeHtml(job.current_item)}</div>`
        : '';

    const error = job.error
        ? `<div class="job-error">Error: ${escapeHtml(job.error)}</div>`
        : '';

    // Show download buttons for completed jobs
    const downloadSection = job.status === 'completed' && job.completed_items > 0
        ? `<div class="job-downloads" id="downloads-${job.job_id}">
            <div class="download-loading">Loading files...</div>
           </div>`
        : '';

    return `
        <div class="job-item status-${job.status}">
            <div class="job-header">
                <div class="job-url">${escapeHtml(job.url)}</div>
                <div class="job-status ${job.status}">${job.status}</div>
            </div>
            <div class="job-progress">
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${progress}%"></div>
                </div>
                <div class="progress-text">${progressText}</div>
            </div>
            ${currentItem}
            ${error}
            ${downloadSection}
        </div>
    `;
}

// Polling for updates
function startPolling() {
    // Poll every 2 seconds
    state.pollingInterval = setInterval(async () => {
        if (state.activeJobs.size > 0) {
            await loadJobs();
        }
    }, 2000);
}

// Toast notifications
function showToast(message, type = 'info') {
    toast.textContent = message;
    toast.className = `toast show ${type}`;

    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Utility: Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Utility: Format file size
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

// Load files for a completed job
async function loadJobFiles(jobId) {
    try {
        console.log('Loading files for job:', jobId);
        const response = await fetch(`/api/files/${jobId}`);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log('Files data:', data);

        const container = document.getElementById(`downloads-${jobId}`);
        if (!container) {
            console.error('Container not found for job:', jobId);
            return;
        }

        if (data.success && data.files && data.files.length > 0) {
            console.log('Rendering download buttons for', data.files.length, 'files');
            renderDownloadButtons(jobId, data.files, container);
        } else {
            console.log('No files available for job:', jobId);
            container.innerHTML = '<div class="no-files">No files available</div>';
        }
    } catch (error) {
        console.error('Error loading files for job', jobId, ':', error);
        const container = document.getElementById(`downloads-${jobId}`);
        if (container) {
            container.innerHTML = `<div class="download-error">Failed to load files: ${error.message}</div>`;
        }
    }
}

// Render download buttons
function renderDownloadButtons(jobId, files, container) {
    const filesHtml = files.map(file => `
        <div class="file-item">
            <span class="file-name">${escapeHtml(file.filename)}</span>
            <span class="file-size">${formatFileSize(file.size)}</span>
            <button class="btn btn-small" onclick="downloadFile('${jobId}', ${file.index})">
                Download
            </button>
        </div>
    `).join('');

    container.innerHTML = `
        <div class="download-header">
            <h3>Downloaded Files (${files.length})</h3>
            <div class="bulk-actions">
                <button class="btn btn-primary" onclick="downloadArchive('${jobId}', 'zip')">
                    Download All (ZIP)
                </button>
                <button class="btn btn-secondary" onclick="downloadArchive('${jobId}', 'tar.zst')">
                    Download All (TAR.ZST)
                </button>
            </div>
        </div>
        <div class="files-list">
            ${filesHtml}
        </div>
    `;
}

// Download individual file
async function downloadFile(jobId, fileIndex) {
    try {
        const url = `/api/download-file/${jobId}/${fileIndex}`;

        // Create a hidden link and trigger download
        const link = document.createElement('a');
        link.href = url;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        showToast('File downloaded! It will be removed from the server.', 'success');

        // Reload files after a short delay
        setTimeout(() => loadJobFiles(jobId), 1000);
    } catch (error) {
        showToast('Error downloading file: ' + error.message, 'error');
    }
}

// Download archive
async function downloadArchive(jobId, format) {
    try {
        const url = `/api/download-archive/${jobId}?format=${format}`;

        // Create a hidden link and trigger download
        const link = document.createElement('a');
        link.href = url;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        showToast(`Archive downloaded! All files will be removed from the server.`, 'success');

        // Reload files after a short delay
        setTimeout(() => loadJobFiles(jobId), 1000);
    } catch (error) {
        showToast('Error downloading archive: ' + error.message, 'error');
    }
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (state.pollingInterval) {
        clearInterval(state.pollingInterval);
    }
});

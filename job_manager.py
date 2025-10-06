"""
Job Manager for handling asynchronous background processing.
This module allows long-running PDF processing tasks to run in the background
without blocking the HTTP request, preventing Azure Web App timeouts.
"""

import io
import json
import os
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path


class JobStatus:
    """Job status constants"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobManager:
    """
    Manages background jobs for PDF processing.
    Uses file-based storage for job state persistence.
    """

    def __init__(self, jobs_dir=".jobs"):
        """
        Initialize the job manager.

        Args:
            jobs_dir: Directory to store job state files
        """
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(exist_ok=True)
        self._lock = threading.Lock()

    def create_job(self, job_id=None, user_email=None):
        """
        Create a new job entry.

        Args:
            job_id: Optional job ID. If not provided, generates a UUID.
            user_email: Optional user email for job tracking.

        Returns:
            str: The job ID
        """
        if job_id is None:
            job_id = str(uuid.uuid4())

        job_data = {
            "job_id": job_id,
            "status": JobStatus.PENDING,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "user_email": user_email,
            "progress": {
                "current_pdf": 0,
                "total_pdfs": 0,
                "current_variable": 0,
                "total_variables": 0,
                "message": "Job created"
            },
            "result": None,
            "error": None
        }

        self._save_job(job_id, job_data)
        return job_id

    def get_job(self, job_id):
        """
        Get job data by ID.

        Args:
            job_id: The job ID

        Returns:
            dict: Job data or None if not found
        """
        job_file = self.jobs_dir / f"{job_id}.json"
        if not job_file.exists():
            return None

        with open(job_file, 'r') as f:
            return json.load(f)

    def update_job(self, job_id, updates):
        """
        Update job data.

        Args:
            job_id: The job ID
            updates: Dictionary of fields to update
        """
        with self._lock:
            job_data = self.get_job(job_id)
            if job_data is None:
                return

            job_data.update(updates)
            job_data["updated_at"] = datetime.utcnow().isoformat()
            self._save_job(job_id, job_data)

    def update_progress(self, job_id, message=None, current_pdf=None, total_pdfs=None,
                       current_variable=None, total_variables=None):
        """
        Update job progress.

        Args:
            job_id: The job ID
            message: Progress message
            current_pdf: Current PDF being processed
            total_pdfs: Total number of PDFs
            current_variable: Current variable being processed
            total_variables: Total number of variables
        """
        job_data = self.get_job(job_id)
        if job_data is None:
            return

        progress = job_data.get("progress", {})

        if message is not None:
            progress["message"] = message
        if current_pdf is not None:
            progress["current_pdf"] = current_pdf
        if total_pdfs is not None:
            progress["total_pdfs"] = total_pdfs
        if current_variable is not None:
            progress["current_variable"] = current_variable
        if total_variables is not None:
            progress["total_variables"] = total_variables

        self.update_job(job_id, {"progress": progress})

    def mark_running(self, job_id):
        """Mark a job as running."""
        self.update_job(job_id, {"status": JobStatus.RUNNING})

    def mark_completed(self, job_id, result=None):
        """
        Mark a job as completed.

        Args:
            job_id: The job ID
            result: Optional result data
        """
        self.update_job(job_id, {
            "status": JobStatus.COMPLETED,
            "result": result
        })

    def mark_failed(self, job_id, error):
        """
        Mark a job as failed.

        Args:
            job_id: The job ID
            error: Error message or traceback
        """
        self.update_job(job_id, {
            "status": JobStatus.FAILED,
            "error": str(error)
        })

    def _save_job(self, job_id, job_data):
        """Save job data to file."""
        job_file = self.jobs_dir / f"{job_id}.json"
        with open(job_file, 'w') as f:
            json.dump(job_data, f, indent=2)

    def find_jobs_by_email(self, email):
        """
        Find all jobs for a given email address.

        Args:
            email: User's email address

        Returns:
            list: List of job data dictionaries, sorted by created_at (newest first)
        """
        matching_jobs = []

        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file, 'r') as f:
                    job_data = json.load(f)
                    if job_data.get("user_email") == email:
                        matching_jobs.append(job_data)
            except Exception:
                pass  # Skip corrupted files

        # Sort by created_at, newest first
        matching_jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return matching_jobs

    def cleanup_old_jobs(self, max_age_hours=24):
        """
        Clean up old job files.

        Args:
            max_age_hours: Maximum age of job files to keep in hours
        """
        cutoff_time = time.time() - (max_age_hours * 3600)

        for job_file in self.jobs_dir.glob("*.json"):
            if job_file.stat().st_mtime < cutoff_time:
                try:
                    job_file.unlink()
                except Exception:
                    pass  # Ignore cleanup errors


# Global job manager instance
_job_manager = None


def get_job_manager():
    """Get or create the global job manager instance."""
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager


def run_job_async(job_id, target_func, args=(), kwargs=None):
    """
    Run a function asynchronously in a background thread.

    Args:
        job_id: The job ID
        target_func: Function to run
        args: Positional arguments for the function
        kwargs: Keyword arguments for the function
    """
    if kwargs is None:
        kwargs = {}

    def wrapper():
        job_manager = get_job_manager()
        try:
            job_manager.mark_running(job_id)
            result = target_func(*args, **kwargs)
            job_manager.mark_completed(job_id, result)
        except Exception as e:
            error_trace = traceback.format_exc()
            job_manager.mark_failed(job_id, error_trace)
            print(f"Job {job_id} failed: {e}")
            print(error_trace)

    thread = threading.Thread(target=wrapper, daemon=True)
    thread.start()
    return thread


def get_job_status(job_id):
    """
    Get the current status of a job.

    Args:
        job_id: The job ID

    Returns:
        dict: Job status information
    """
    job_manager = get_job_manager()
    return job_manager.get_job(job_id)

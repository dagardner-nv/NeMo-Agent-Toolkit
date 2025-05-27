# SPDX-FileCopyrightText: Copyright (c) 2025, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import logging
import os
import shutil
from collections.abc import Coroutine
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from enum import Enum
from operator import attrgetter
from uuid import uuid4

from pydantic import BaseModel
from pydantic import ConfigDict

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    SUBMITTED = "submitted"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    INTERRUPTED = "interrupted"
    NOT_FOUND = "not_found"


# pydantic model for the job status
class JobInfo(BaseModel):
    # needed for the task attribute
    model_config = ConfigDict(arbitrary_types_allowed=True)

    job_id: str
    task: asyncio.Task | None
    status: JobStatus
    config_file: str | None
    error: str | None
    output_path: str | None
    created_at: datetime
    updated_at: datetime
    expiry_seconds: int
    output: BaseModel | None = None


class JobStore:

    MIN_EXPIRY = 600  # 10 minutes
    MAX_EXPIRY = 86400  # 24 hours
    DEFAULT_EXPIRY = 3600  # 1 hour

    # active jobs are exempt from expiry
    ACTIVE_STATUS = {"running", "submitted"}

    def __init__(self):
        self._jobs = {}

    def ensure_job_id(self, job_id: str | None) -> str:
        if job_id is None:
            return str(uuid4())

        return job_id

    def create_job(self,
                   coro: Coroutine,
                   config_file: str | None = None,
                   job_id: str | None = None,
                   expiry_seconds: int = DEFAULT_EXPIRY) -> tuple[str, asyncio.Task]:
        job_id = self.ensure_job_id(job_id)

        clamped_expiry = max(self.MIN_EXPIRY, min(expiry_seconds, self.MAX_EXPIRY))
        if expiry_seconds != clamped_expiry:
            logger.info("Clamped expiry_seconds from %d to %d for job %s", expiry_seconds, clamped_expiry, job_id)

        task = asyncio.create_task(coro)
        job = JobInfo(job_id=job_id,
                      task=task,
                      status=JobStatus.SUBMITTED,
                      config_file=config_file,
                      created_at=datetime.now(UTC),
                      updated_at=datetime.now(UTC),
                      error=None,
                      output_path=None,
                      expiry_seconds=clamped_expiry)
        self._jobs[job_id] = job
        logger.info("Created new job %s with config %s", job_id, config_file)
        return (job_id, task)

    def update_status(self,
                      job_id: str,
                      status: str,
                      error: str | None = None,
                      output_path: str | None = None,
                      output: BaseModel | None = None):
        if job_id not in self._jobs:
            raise ValueError(f"Job {job_id} not found")

        job = self._jobs[job_id]
        job.status = status
        job.error = error
        job.output_path = output_path
        job.updated_at = datetime.now(UTC)
        job.output = output

    def get_status(self, job_id: str) -> JobInfo | None:
        return self._jobs.get(job_id)

    def list_jobs(self):
        return self._jobs

    def get_job(self, job_id: str) -> JobInfo | None:
        """Get a job by its ID."""
        return self._jobs.get(job_id)

    def get_last_job(self) -> JobInfo | None:
        """Get the last created job."""
        if not self._jobs:
            logger.info("No jobs found in job store")
            return None
        last_job = max(self._jobs.values(), key=lambda job: job.created_at)
        logger.info("Retrieved last job %s created at %s", last_job.job_id, last_job.created_at)
        return last_job

    def get_jobs_by_status(self, status: str) -> list[JobInfo]:
        """Get all jobs with the specified status."""
        return [job for job in self._jobs.values() if job.status == status]

    def get_all_jobs(self) -> list[JobInfo]:
        """Get all jobs in the store."""
        return list(self._jobs.values())

    def get_expires_at(self, job: JobInfo) -> datetime | None:
        """Get the time for a job to expire."""
        expired_delta = timedelta(seconds=job.expiry_seconds)
        if job.status == JobStatus.RUNNING:
            # Cancel a long running job if it has been running for 4x its expiry time. This prevents a job stuck in a
            # loop from preventing other jobs from running.
            expired_delta *= 4

        return job.updated_at + timedelta(seconds=job.expiry_seconds)

    def _cleanup_job(self, job: JobInfo):
        # Cancel the task if it is still running
        if job.task is not None and not job.task.done():
            logger.info("Cancelling task for expired job %s", job.job_id)
            job.task.cancel()

        # cleanup output dir if present
        if job.output_path:
            logger.info("Cleaning up output directory for job %s at %s", job.job_id, job.output_path)
            # If it is a file remove it
            if os.path.isfile(job.output_path):
                os.remove(job.output_path)
            # If it is a directory remove it
            elif os.path.isdir(job.output_path):
                shutil.rmtree(job.output_path)

    def cleanup_expired_jobs(self):
        """
        Cleanup expired jobs, keeping the most recent one.
        Updated_at is used instead of created_at to determine the most recent job.
        This is because jobs may not be processed in the order they are created.
        """
        now = datetime.now(UTC)
        logger.info("Cleaning up expired jobs at %s", now)

        # Filter out active jobs
        finished_jobs = []
        running_jobs = []

        for job_id, job in self._jobs.items():
            if job.status not in self.ACTIVE_STATUS:
                finished_jobs.append(job)
            else:
                running_jobs.append(job)

        # Sort finished jobs by updated_at descending
        sorted_finished = sorted(finished_jobs, key=attrgetter('updated_at'), reverse=True)
        sorted_running = sorted(running_jobs, key=attrgetter('updated_at'), reverse=True)

        # Always keep the most recent finished job
        jobs_to_check = sorted_finished[1:] + sorted_running

        expired_ids = []
        for job in jobs_to_check:
            expires_at = self.get_expires_at(job)
            if expires_at and now > expires_at:
                expired_ids.append(job.job_id)
                self._cleanup_job(job)

        for job_id in expired_ids:
            del self._jobs[job_id]

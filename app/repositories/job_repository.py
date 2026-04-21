"""
app/repositories/job_repository.py
Repository pattern implementation for Job and JobExecution models.
Centralizes all database operations for job-related entities.
"""
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.job import Job, JobExecution, JobStatus, ExecutionStatus
from .base_repository import BaseRepository


class JobRepository(BaseRepository[Job]):
    """
    Repository for Job model.
    Provides specialized query methods for job operations.
    """

    def __init__(self, db: Session):
        """Initialize JobRepository with Job model."""
        super().__init__(db, Job)

    def get_by_status(self, status: JobStatus) -> List[Job]:
        """
        Get all jobs with a specific status.

        Args:
            status: The JobStatus to filter by

        Returns:
            List of jobs with the specified status
        """
        stmt = select(Job).where(Job.status == status).order_by(Job.created_at.desc())
        return self.db.execute(stmt).scalars().all()

    def list_all(self, status: Optional[JobStatus] = None) -> List[Job]:
        """
        List all jobs, optionally filtered by status.

        Args:
            status: Optional JobStatus filter

        Returns:
            List of jobs ordered by creation date (newest first)
        """
        stmt = select(Job).order_by(Job.created_at.desc())
        if status:
            stmt = stmt.where(Job.status == status)
        return self.db.execute(stmt).scalars().all()

    def get_by_name(self, name: str) -> Optional[Job]:
        """
        Get a job by its name.

        Args:
            name: The job name

        Returns:
            The Job instance or None if not found
        """
        stmt = select(Job).where(Job.name == name)
        return self.db.execute(stmt).scalars().first()

    def get_active_jobs(self) -> List[Job]:
        """
        Get all active jobs.

        Returns:
            List of active jobs
        """
        return self.get_by_status(JobStatus.active)

    def get_paused_jobs(self) -> List[Job]:
        """
        Get all paused jobs.

        Returns:
            List of paused jobs
        """
        return self.get_by_status(JobStatus.paused)

    def update_status(self, job_id: str, status: JobStatus) -> Optional[Job]:
        """
        Update the status of a job.

        Args:
            job_id: The job ID
            status: The new JobStatus

        Returns:
            The updated Job instance or None if not found
        """
        db_job = self.get_by_id(job_id)
        if not db_job:
            return None
        db_job.status = status
        self.db.commit()
        self.db.refresh(db_job)
        return db_job

    def update_next_run_time(self, job_id: str, next_run_time) -> Optional[Job]:
        """
        Update the next run time of a job.

        Args:
            job_id: The job ID
            next_run_time: The new next run time (datetime or None)

        Returns:
            The updated Job instance or None if not found
        """
        db_job = self.get_by_id(job_id)
        if not db_job:
            return None
        db_job.next_run_time = next_run_time
        self.db.commit()
        self.db.refresh(db_job)
        return db_job

    def update_trigger_args(self, job_id: str, trigger_args: dict) -> Optional[Job]:
        """
        Update the trigger arguments of a job.

        Args:
            job_id: The job ID
            trigger_args: The new trigger arguments dictionary

        Returns:
            The updated Job instance or None if not found
        """
        db_job = self.get_by_id(job_id)
        if not db_job:
            return None
        db_job.trigger_args = trigger_args
        self.db.commit()
        self.db.refresh(db_job)
        return db_job

    def update_job_kwargs(self, job_id: str, job_kwargs: dict) -> Optional[Job]:
        """
        Update the job kwargs of a job.

        Args:
            job_id: The job ID
            job_kwargs: The new job kwargs dictionary

        Returns:
            The updated Job instance or None if not found
        """
        db_job = self.get_by_id(job_id)
        if not db_job:
            return None
        db_job.job_kwargs = job_kwargs
        self.db.commit()
        self.db.refresh(db_job)
        return db_job

    def update_job_details(self, job_id: str, name: str = None, description: str = None) -> Optional[Job]:
        """
        Update job name and/or description.

        Args:
            job_id: The job ID
            name: Optional new job name
            description: Optional new job description

        Returns:
            The updated Job instance or None if not found
        """
        db_job = self.get_by_id(job_id)
        if not db_job:
            return None
        if name is not None:
            db_job.name = name
        if description is not None:
            db_job.description = description
        self.db.commit()
        self.db.refresh(db_job)
        return db_job

    def count_jobs(self) -> int:
        """
        Get total count of jobs.

        Returns:
            Total number of jobs in the database
        """
        stmt = select(func.count()).select_from(Job)
        return self.db.execute(stmt).scalar()

    def count_by_status(self, status: JobStatus) -> int:
        """
        Get count of jobs with a specific status.

        Args:
            status: The JobStatus to count

        Returns:
            Number of jobs with the specified status
        """
        stmt = select(func.count()).select_from(Job).where(Job.status == status)
        return self.db.execute(stmt).scalar()


class JobExecutionRepository(BaseRepository[JobExecution]):
    """
    Repository for JobExecution model.
    Provides specialized query methods for job execution history.
    """

    def __init__(self, db: Session):
        """Initialize JobExecutionRepository with JobExecution model."""
        super().__init__(db, JobExecution)

    def get_by_job_id(self, job_id: str) -> List[JobExecution]:
        """
        Get all executions for a specific job, ordered by start time (newest first).

        Args:
            job_id: The job ID

        Returns:
            List of JobExecution instances
        """
        stmt = (
            select(JobExecution)
            .where(JobExecution.job_id == job_id)
            .order_by(JobExecution.started_at.desc())
        )
        return self.db.execute(stmt).scalars().all()

    def get_by_job_id_paginated(
        self, job_id: str, page: int = 1, page_size: int = 20
    ) -> dict:
        """
        Get executions for a specific job with pagination.

        Args:
            job_id: The job ID
            page: Page number (1-indexed)
            page_size: Number of items per page

        Returns:
            Dictionary with 'total', 'page', 'page_size', and 'items' keys
        """
        stmt = select(JobExecution).where(JobExecution.job_id == job_id)
        count_stmt = select(func.count()).select_from(JobExecution).where(JobExecution.job_id == job_id)

        total = self.db.execute(count_stmt).scalar()
        offset = (page - 1) * page_size
        query = stmt.order_by(JobExecution.started_at.desc()).offset(offset).limit(page_size)

        items = self.db.execute(query).scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        }

    def get_executions_paginated(
        self, job_id: Optional[str] = None, page: int = 1, page_size: int = 20
    ) -> dict:
        """
        Get all executions (or for a specific job) with pagination.

        Args:
            job_id: Optional job ID filter
            page: Page number (1-indexed)
            page_size: Number of items per page

        Returns:
            Dictionary with pagination info and items
        """
        stmt = select(JobExecution).order_by(JobExecution.started_at.desc())
        count_stmt = select(func.count()).select_from(JobExecution)

        if job_id:
            stmt = stmt.where(JobExecution.job_id == job_id)
            count_stmt = count_stmt.where(JobExecution.job_id == job_id)

        total = self.db.execute(count_stmt).scalar()
        offset = (page - 1) * page_size
        query = stmt.offset(offset).limit(page_size)

        items = self.db.execute(query).scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        }

    def get_recent_executions(self, job_id: str, limit: int = 10) -> List[JobExecution]:
        """
        Get the N most recent executions for a job.

        Args:
            job_id: The job ID
            limit: Number of recent executions to retrieve

        Returns:
            List of recent JobExecution instances
        """
        stmt = (
            select(JobExecution)
            .where(JobExecution.job_id == job_id)
            .order_by(JobExecution.started_at.desc())
            .limit(limit)
        )
        return self.db.execute(stmt).scalars().all()

    def get_failed_executions(self, job_id: str) -> List[JobExecution]:
        """
        Get all failed executions for a job.

        Args:
            job_id: The job ID

        Returns:
            List of failed JobExecution instances
        """
        stmt = (
            select(JobExecution)
            .where(JobExecution.job_id == job_id)
            .where(JobExecution.status == ExecutionStatus.failure)
            .order_by(JobExecution.started_at.desc())
        )
        return self.db.execute(stmt).scalars().all()

    def get_successful_executions(self, job_id: str) -> List[JobExecution]:
        """
        Get all successful executions for a job.

        Args:
            job_id: The job ID

        Returns:
            List of successful JobExecution instances
        """
        stmt = (
            select(JobExecution)
            .where(JobExecution.job_id == job_id)
            .where(JobExecution.status == ExecutionStatus.success)
            .order_by(JobExecution.started_at.desc())
        )
        return self.db.execute(stmt).scalars().all()

    def count_by_status(self, job_id: str, status: ExecutionStatus) -> int:
        """
        Count executions by status for a specific job.

        Args:
            job_id: The job ID
            status: The ExecutionStatus to count

        Returns:
            Number of executions with the specified status
        """
        stmt = (
            select(func.count())
            .select_from(JobExecution)
            .where(JobExecution.job_id == job_id)
            .where(JobExecution.status == status)
        )
        return self.db.execute(stmt).scalar()

    def get_job_execution_stats(self, job_id: str) -> dict:
        """
        Get execution statistics for a job.

        Args:
            job_id: The job ID

        Returns:
            Dictionary with execution statistics (total, success, failure, running counts)
        """
        total = self.count_by_status(job_id, ExecutionStatus.success) + \
                self.count_by_status(job_id, ExecutionStatus.failure)
        success = self.count_by_status(job_id, ExecutionStatus.success)
        failure = self.count_by_status(job_id, ExecutionStatus.failure)
        running = self.count_by_status(job_id, ExecutionStatus.running)

        return {
            "total": total,
            "success": success,
            "failure": failure,
            "running": running,
            "success_rate": (success / total * 100) if total > 0 else 0,
        }
"""Schedule-compute auto-disable notification.

``set_schedule_failure_notifier`` lets the embedding process register a hook
that fires when a job is auto-disabled after consecutive schedule-compute
errors, so the auto-disable is not silent (e.g. enqueue a system event or
post a channel message).
"""

from __future__ import annotations

from datetime import UTC, datetime

from opensquilla.scheduler.jobs import (
    _mark_schedule_compute_failed,
    set_schedule_failure_notifier,
)
from opensquilla.scheduler.types import CronJob, JobStatus


def test_notifier_called_when_schedule_compute_fails() -> None:
    calls: list[tuple[str, str]] = []

    def notifier(job: CronJob, error_text: str) -> None:
        calls.append((job.id, error_text))

    set_schedule_failure_notifier(notifier)
    try:
        job = CronJob(id="job-1", name="x", cron_expr="bad")
        _mark_schedule_compute_failed(
            job,
            ValueError("bad cron"),
            datetime.now(UTC),
            increment_error=True,
        )
        assert job.status == JobStatus.FAILED
        assert calls == [("job-1", "bad cron")]
    finally:
        set_schedule_failure_notifier(None)


def test_notifier_failure_is_swallowed() -> None:
    """Notifier crashes must NOT propagate out of the failure handler."""

    def boom(job: CronJob, _err: str) -> None:
        raise RuntimeError("notifier exploded")

    set_schedule_failure_notifier(boom)
    try:
        job = CronJob(id="job-1", name="x", cron_expr="bad")
        # Should not raise:
        _mark_schedule_compute_failed(
            job,
            ValueError("bad cron"),
            datetime.now(UTC),
            increment_error=True,
        )
        assert job.status == JobStatus.FAILED
    finally:
        set_schedule_failure_notifier(None)


def test_no_notifier_registered_is_a_noop() -> None:
    set_schedule_failure_notifier(None)
    job = CronJob(id="job-1", name="x", cron_expr="bad")
    _mark_schedule_compute_failed(
        job,
        ValueError("bad cron"),
        datetime.now(UTC),
        increment_error=False,
    )
    assert job.status == JobStatus.FAILED
    assert job.last_error == "schedule compute failed: bad cron"

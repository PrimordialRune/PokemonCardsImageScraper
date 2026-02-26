"""Job, queue-item, and event models used by both CLI and GUI."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Queue-item status
# ---------------------------------------------------------------------------


class ItemStatus(enum.Enum):
    QUEUED = "queued"
    RESOLVING = "resolving"
    FETCHING = "fetching"
    NORMALIZING = "normalizing"
    SAVED = "saved"
    SKIPPED = "skipped"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


class EventType(enum.Enum):
    JOB_STARTED = "job_started"
    ITEM_QUEUED = "item_queued"
    ITEM_RESOLVING = "item_resolving"
    ITEM_FETCHING = "item_fetching"
    ITEM_NORMALIZING = "item_normalizing"
    ITEM_SAVED = "item_saved"
    ITEM_SKIPPED = "item_skipped"
    ITEM_FAILED = "item_failed"
    JOB_FINISHED = "job_finished"
    JOB_CANCELLED = "job_cancelled"
    LOG = "log"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class JobConfig:
    """All parameters needed to run a scrape job."""

    provider: str = "pkmncards"
    output_dir: str = ""
    fmt: str = "png"
    concurrency: int = 8
    rate: float = 2.0
    retries: int = 3
    timeout: float = 20.0
    resume: bool = True
    overwrite: bool = False
    set_filter: str = ""
    limit: int = 0


@dataclass
class QueueItem:
    """A single card in the job queue."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    identifier: str = ""
    name: str = ""
    set_name: str = ""
    number: str = ""
    source_url: str = ""
    image_url: str = ""
    output_path: str = ""
    status: ItemStatus = ItemStatus.QUEUED
    progress: float = 0.0
    message: str = ""
    retries_left: int = 3
    provider: str = ""
    selected: bool = True


@dataclass
class JobEvent:
    """An event emitted by the scrape engine."""

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    item_id: str = ""
    event_type: EventType = EventType.LOG
    message: str = ""
    progress: float = 0.0
    data: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()


@dataclass
class JobSummary:
    """Final summary of a scrape job."""

    total: int = 0
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)

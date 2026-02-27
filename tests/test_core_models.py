"""Tests for core job models and event system."""

from __future__ import annotations

from ptcg_art_scraper.core.models import (
    EventType,
    ItemStatus,
    JobConfig,
    JobEvent,
    JobSummary,
    QueueItem,
)
from ptcg_art_scraper.core.engine import _decode_ref_metadata


class TestItemStatus:
    def test_all_values_are_strings(self) -> None:
        for status in ItemStatus:
            assert isinstance(status.value, str)

    def test_expected_members(self) -> None:
        names = {s.name for s in ItemStatus}
        assert "QUEUED" in names
        assert "SAVED" in names
        assert "FAILED" in names


class TestEventType:
    def test_all_values_are_strings(self) -> None:
        for et in EventType:
            assert isinstance(et.value, str)

    def test_expected_members(self) -> None:
        names = {e.name for e in EventType}
        assert "JOB_STARTED" in names
        assert "ITEM_SAVED" in names
        assert "JOB_FINISHED" in names


class TestJobConfig:
    def test_defaults(self) -> None:
        cfg = JobConfig()
        assert cfg.provider == "pkmncards"
        assert cfg.fmt == "png"
        assert cfg.concurrency == 8
        assert cfg.rate == 2.0
        assert cfg.retries == 3
        assert cfg.timeout == 20.0
        assert cfg.resume is True
        assert cfg.overwrite is False

    def test_custom_values(self) -> None:
        cfg = JobConfig(
            provider="custom",
            output_dir="/tmp/out",
            fmt="jpg",
            concurrency=4,
            rate=1.0,
        )
        assert cfg.provider == "custom"
        assert cfg.output_dir == "/tmp/out"
        assert cfg.fmt == "jpg"
        assert cfg.concurrency == 4
        assert cfg.rate == 1.0


class TestQueueItem:
    def test_auto_id(self) -> None:
        item = QueueItem()
        assert item.id  # not empty

    def test_unique_ids(self) -> None:
        items = [QueueItem() for _ in range(10)]
        ids = {i.id for i in items}
        assert len(ids) == 10

    def test_default_status(self) -> None:
        item = QueueItem()
        assert item.status == ItemStatus.QUEUED
        assert item.selected is True
        assert item.progress == 0.0

    def test_set_fields(self) -> None:
        item = QueueItem(
            identifier="https://example.com/card/1",
            name="Charizard",
            set_name="Base Set",
            number="4",
        )
        assert item.name == "Charizard"
        assert item.set_name == "Base Set"


class TestJobEvent:
    def test_defaults(self) -> None:
        evt = JobEvent()
        assert evt.event_type == EventType.LOG
        assert evt.item_id == ""
        assert evt.timestamp  # auto-set

    def test_now_returns_iso(self) -> None:
        ts = JobEvent.now()
        assert "T" in ts
        assert "+" in ts or "Z" in ts

    def test_custom_event(self) -> None:
        evt = JobEvent(
            event_type=EventType.ITEM_SAVED,
            item_id="abc123",
            message="Done",
            progress=1.0,
        )
        assert evt.event_type == EventType.ITEM_SAVED
        assert evt.item_id == "abc123"
        assert evt.progress == 1.0


class TestJobSummary:
    def test_defaults(self) -> None:
        s = JobSummary()
        assert s.total == 0
        assert s.succeeded == 0
        assert s.failed == 0
        assert s.errors == []

    def test_accumulate(self) -> None:
        s = JobSummary(total=5)
        s.succeeded += 3
        s.failed += 1
        s.skipped += 1
        assert s.succeeded + s.failed + s.skipped == 5


class TestRefMetadataDecode:
    def test_valid_payload(self) -> None:
        payload = '{"name":"Lunatone","set_name":"Sandstorm","number":"8"}'
        data = _decode_ref_metadata(payload)
        assert data["name"] == "Lunatone"
        assert data["set_name"] == "Sandstorm"
        assert data["number"] == "8"

    def test_invalid_payload_returns_empty(self) -> None:
        assert _decode_ref_metadata("not-json") == {}
        assert _decode_ref_metadata("") == {}

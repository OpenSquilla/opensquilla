"""Webhook delivery mode.

``DeliveryMode.WEBHOOK`` POSTs the finished-run event payload to
``DeliveryConfig.webhook_url``, optionally with a bearer token. URL is
validated up front and rejected at add time when malformed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opensquilla.scheduler.delivery import DeliveryChain, validate_webhook_url
from opensquilla.scheduler.ops import SchedulerOps
from opensquilla.scheduler.payloads import make_agent_turn_payload
from opensquilla.scheduler.persistence import JobStore
from opensquilla.scheduler.types import (
    CronJob,
    DeliveryConfig,
    DeliveryMode,
    SessionTarget,
)


# --- URL validation --------------------------------------------------------


def test_validate_webhook_url_accepts_http_and_https() -> None:
    validate_webhook_url("http://example.com/hook")
    validate_webhook_url("https://example.com/hook?x=1")


def test_validate_webhook_url_rejects_other_schemes() -> None:
    with pytest.raises(ValueError, match="http or https"):
        validate_webhook_url("ftp://example.com/x")
    with pytest.raises(ValueError, match="http or https"):
        validate_webhook_url("file:///tmp/x")


def test_validate_webhook_url_requires_hostname() -> None:
    with pytest.raises(ValueError, match="hostname"):
        validate_webhook_url("https:///nohost")


def test_validate_webhook_url_rejects_empty() -> None:
    with pytest.raises(ValueError, match="required"):
        validate_webhook_url("")


# --- ops.add validates webhook config -------------------------------------


async def test_ops_add_with_webhook_delivery_persists(tmp_path: Path) -> None:
    db = tmp_path / "cron.db"
    store = JobStore(str(db))
    await store.open()
    try:
        ops = SchedulerOps(store)
        delivery = DeliveryConfig(
            mode=DeliveryMode.WEBHOOK,
            webhook_url="https://hooks.example/cron",
            webhook_token="secret-bearer",
            best_effort=True,
        )
        job = await ops.add(
            name="hook",
            schedule_raw="*/5 * * * *",
            handler_key="agent_run",
            payload=make_agent_turn_payload("brief"),
            session_target=SessionTarget.ISOLATED,
            delivery=delivery,
        )
        assert job.delivery.mode == DeliveryMode.WEBHOOK
        assert job.delivery.webhook_url == "https://hooks.example/cron"
        assert job.delivery.webhook_token == "secret-bearer"
        assert job.delivery.best_effort is True

        reloaded = await store.get(job.id)
        assert reloaded is not None
        assert reloaded.delivery.mode == DeliveryMode.WEBHOOK
        assert reloaded.delivery.webhook_url == "https://hooks.example/cron"
        assert reloaded.delivery.webhook_token == "secret-bearer"
        assert reloaded.delivery.best_effort is True
    finally:
        await store.close()


async def test_ops_add_rejects_webhook_without_url(tmp_path: Path) -> None:
    db = tmp_path / "cron.db"
    store = JobStore(str(db))
    await store.open()
    try:
        ops = SchedulerOps(store)
        with pytest.raises(ValueError, match="webhook URL is required"):
            await ops.add(
                name="bad",
                schedule_raw="*/5 * * * *",
                handler_key="agent_run",
                payload=make_agent_turn_payload("x"),
                session_target=SessionTarget.ISOLATED,
                delivery=DeliveryConfig(mode=DeliveryMode.WEBHOOK, webhook_url=""),
            )
    finally:
        await store.close()


async def test_ops_add_rejects_webhook_with_bad_scheme(tmp_path: Path) -> None:
    db = tmp_path / "cron.db"
    store = JobStore(str(db))
    await store.open()
    try:
        ops = SchedulerOps(store)
        with pytest.raises(ValueError, match="http or https"):
            await ops.add(
                name="bad",
                schedule_raw="*/5 * * * *",
                handler_key="agent_run",
                payload=make_agent_turn_payload("x"),
                session_target=SessionTarget.ISOLATED,
                delivery=DeliveryConfig(
                    mode=DeliveryMode.WEBHOOK, webhook_url="ftp://example.com/x"
                ),
            )
    finally:
        await store.close()


async def test_ops_add_allows_webhook_on_main_target(tmp_path: Path) -> None:
    """Webhook delivery is permitted for any sessionTarget, including main."""
    db = tmp_path / "cron.db"
    store = JobStore(str(db))
    await store.open()
    try:
        from opensquilla.scheduler.payloads import make_system_event_payload

        ops = SchedulerOps(store)
        job = await ops.add(
            name="main-hook",
            schedule_raw="*/5 * * * *",
            handler_key="system_event",
            payload=make_system_event_payload("reminder"),
            session_target=SessionTarget.MAIN,
            delivery=DeliveryConfig(
                mode=DeliveryMode.WEBHOOK,
                webhook_url="https://hooks.example/main",
            ),
        )
        assert job.delivery.mode == DeliveryMode.WEBHOOK
        reloaded = await store.get(job.id)
        assert reloaded is not None
        assert reloaded.delivery.mode == DeliveryMode.WEBHOOK
        assert reloaded.delivery.webhook_url == "https://hooks.example/main"
    finally:
        await store.close()


# --- DeliveryChain webhook dispatch ---------------------------------------


def _webhook_job(url: str, token: str = "") -> CronJob:
    return CronJob(
        id="job-1",
        name="hook",
        cron_expr="*/5 * * * *",
        handler_key="agent_run",
        payload={"kind": "agent_turn", "task": "x", "agent_id": "main"},
        session_target=SessionTarget.ISOLATED,
        delivery=DeliveryConfig(
            mode=DeliveryMode.WEBHOOK,
            webhook_url=url,
            webhook_token=token,
        ),
    )


class _RecordingAsyncClient:
    """Capture httpx.AsyncClient.post calls for assertion."""

    instances: list["_RecordingAsyncClient"] = []

    def __init__(self, *, timeout=None, **_kw) -> None:
        self.timeout = timeout
        self.posts: list[dict] = []
        _RecordingAsyncClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        self.posts.append({"url": url, "json": json, "headers": headers or {}})

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                return None

        return _Resp()


async def test_deliver_webhook_posts_json_with_bearer(monkeypatch) -> None:
    _RecordingAsyncClient.instances.clear()
    import opensquilla.scheduler.delivery as delivery_mod

    class _FakeHttpx:
        AsyncClient = _RecordingAsyncClient

    monkeypatch.setitem(__import__("sys").modules, "httpx", _FakeHttpx)

    chain = DeliveryChain()
    status = await chain._deliver_webhook(
        _webhook_job("https://hooks.example/cron", token="abc"),
        text="summary text",
    )
    assert status == "delivered"
    assert _RecordingAsyncClient.instances, "AsyncClient was not constructed"
    inst = _RecordingAsyncClient.instances[-1]
    assert inst.posts, "no POST issued"
    post = inst.posts[-1]
    assert post["url"] == "https://hooks.example/cron"
    assert post["json"]["jobId"] == "job-1"
    assert post["json"]["summary"] == "summary text"
    assert post["headers"]["Content-Type"] == "application/json"
    assert post["headers"]["Authorization"] == "Bearer abc"


async def test_deliver_webhook_omits_authorization_when_no_token(monkeypatch) -> None:
    _RecordingAsyncClient.instances.clear()

    class _FakeHttpx:
        AsyncClient = _RecordingAsyncClient

    monkeypatch.setitem(__import__("sys").modules, "httpx", _FakeHttpx)

    chain = DeliveryChain()
    status = await chain._deliver_webhook(
        _webhook_job("https://hooks.example/cron"),
        text="x",
    )
    assert status == "delivered"
    inst = _RecordingAsyncClient.instances[-1]
    assert "Authorization" not in inst.posts[-1]["headers"]


async def test_deliver_webhook_returns_failed_on_http_error(monkeypatch) -> None:
    class _ErrorClient(_RecordingAsyncClient):
        async def post(self, url, json=None, headers=None):
            class _Resp:
                status_code = 500

                def raise_for_status(self):
                    raise RuntimeError("HTTP 500")

            return _Resp()

    class _FakeHttpx:
        AsyncClient = _ErrorClient

    monkeypatch.setitem(__import__("sys").modules, "httpx", _FakeHttpx)

    chain = DeliveryChain()
    status = await chain._deliver_webhook(
        _webhook_job("https://hooks.example/cron"),
        text="x",
    )
    assert status == "delivery_failed"

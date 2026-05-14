"""RPC layer must let users set webhook delivery on a cron job.

Webhook delivery is plumbed through ``scheduler.delivery``, but the RPC
``cron.add`` payload originally only parsed channel-mode overrides. These
tests assert the wire payload can carry webhook mode end-to-end.
"""

from __future__ import annotations

from typing import Any

import pytest

from opensquilla.gateway.rpc import RpcContext
from opensquilla.gateway.rpc_cron import _handle_cron_add, _job_to_wire
from opensquilla.scheduler.payloads import AGENT_TURN_KIND, SYSTEM_EVENT_KIND
from opensquilla.scheduler.types import (
    CronJob,
    DeliveryConfig,
    DeliveryMode,
    SessionTarget,
)


class _FakeScheduler:
    def __init__(self) -> None:
        self.added_kwargs: dict[str, Any] | None = None

    async def add_job(self, **kwargs):
        self.added_kwargs = kwargs
        return CronJob(
            id="job-w",
            name=kwargs["name"],
            cron_expr=kwargs["schedule_raw"],
            schedule_raw=kwargs["schedule_raw"],
            handler_key=kwargs["handler_key"],
            payload=kwargs["payload"],
            session_target=kwargs["session_target"],
            session_key=kwargs["session_key"],
            origin_session_key=kwargs["origin_session_key"],
            delivery=kwargs.get("delivery") or DeliveryConfig(),
        )

    async def update_job(self, job_id, **patch):
        return None


async def test_rpc_cron_add_webhook_delivery_is_reachable() -> None:
    scheduler = _FakeScheduler()
    result = await _handle_cron_add(
        {
            "name": "Webhook job",
            "expression": "*/5 * * * *",
            "payloadKind": AGENT_TURN_KIND,
            "text": "Run analysis",
            "sessionTarget": "isolated",
            "delivery": {
                "mode": "webhook",
                "webhookUrl": "https://hooks.example/cron",
                "webhookToken": "secret",
                "bestEffort": True,
            },
        },
        RpcContext(conn_id="test", cron_scheduler=scheduler),
    )
    assert scheduler.added_kwargs is not None
    delivery = scheduler.added_kwargs["delivery"]
    assert delivery.mode == DeliveryMode.WEBHOOK
    assert delivery.webhook_url == "https://hooks.example/cron"
    assert delivery.webhook_token == "secret"
    assert delivery.best_effort is True
    # Wire payload echoes the webhook target.
    assert result["delivery"]["mode"] == "webhook"
    assert result["delivery"]["webhookUrl"] == "https://hooks.example/cron"
    assert result["delivery"]["bestEffort"] is True


async def test_rpc_cron_add_webhook_accepts_to_alias() -> None:
    """The wire payload accepts `to` as an alias for the webhook URL."""
    scheduler = _FakeScheduler()
    await _handle_cron_add(
        {
            "name": "Alias",
            "expression": "*/5 * * * *",
            "payloadKind": AGENT_TURN_KIND,
            "text": "x",
            "sessionTarget": "isolated",
            "delivery": {"mode": "webhook", "to": "https://hooks.example/x"},
        },
        RpcContext(conn_id="test", cron_scheduler=scheduler),
    )
    delivery = scheduler.added_kwargs["delivery"]
    assert delivery.mode == DeliveryMode.WEBHOOK
    assert delivery.webhook_url == "https://hooks.example/x"


async def test_rpc_cron_add_webhook_allowed_for_main_target() -> None:
    """Webhook delivery is allowed for any sessionTarget, including main."""
    scheduler = _FakeScheduler()
    await _handle_cron_add(
        {
            "name": "Main hook",
            "expression": "0 9 * * *",
            "payloadKind": SYSTEM_EVENT_KIND,
            "text": "Reminder",
            "sessionTarget": "main",
            "delivery": {
                "mode": "webhook",
                "webhookUrl": "https://hooks.example/main",
            },
        },
        RpcContext(conn_id="test", cron_scheduler=scheduler),
    )
    assert scheduler.added_kwargs["delivery"].mode == DeliveryMode.WEBHOOK


async def test_rpc_cron_add_webhook_with_invalid_url_raises() -> None:
    scheduler = _FakeScheduler()
    with pytest.raises(ValueError, match="http or https"):
        await _handle_cron_add(
            {
                "name": "Bad",
                "expression": "*/5 * * * *",
                "payloadKind": AGENT_TURN_KIND,
                "text": "x",
                "sessionTarget": "isolated",
                "delivery": {"mode": "webhook", "webhookUrl": "ftp://bad/hook"},
            },
            RpcContext(conn_id="test", cron_scheduler=scheduler),
        )


def test_job_to_wire_includes_webhook_fields() -> None:
    job = CronJob(
        id="job-1",
        name="hook",
        cron_expr="*/5 * * * *",
        schedule_raw="*/5 * * * *",
        handler_key="agent_run",
        payload={"kind": AGENT_TURN_KIND, "task": "x", "agent_id": "main"},
        session_target=SessionTarget.ISOLATED,
        delivery=DeliveryConfig(
            mode=DeliveryMode.WEBHOOK,
            webhook_url="https://hooks.example/cron",
            best_effort=True,
        ),
    )
    wire = _job_to_wire(job)
    assert wire["delivery"]["mode"] == "webhook"
    assert wire["delivery"]["webhookUrl"] == "https://hooks.example/cron"
    assert wire["delivery"]["bestEffort"] is True

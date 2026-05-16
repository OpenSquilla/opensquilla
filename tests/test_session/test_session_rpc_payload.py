from __future__ import annotations

from types import SimpleNamespace

from opensquilla.session.rpc_payload import session_list_row, task_state_summary


def test_session_list_row_preserves_source_metadata_and_task_state() -> None:
    session = SimpleNamespace(
        session_key="agent:main:webchat:abc123",
        agent_id="main",
        status="running",
        model="gpt-test",
        updated_at=2000,
        display_name="WebChat",
        channel=None,
        chat_type="direct",
        group_id=None,
        subject=None,
        last_channel="slack",
        last_to="C123",
        last_account_id="acct-1",
        last_thread_id="1700.1",
        delivery_context={"channel_id": "C123"},
        parent_session_key=None,
        spawned_by=None,
        origin=None,
    )
    task = SimpleNamespace(
        task_id="task-1",
        status="running",
        queue_mode="followup",
        run_kind="web_turn",
        source_kind="webui",
        created_at=100,
        started_at=110,
        finished_at=None,
        terminal_reason=None,
    )

    row = session_list_row(session, entry_count=3, task_rows=[task], now_ms=9999)

    assert row["key"] == "agent:main:webchat:abc123"
    assert row["message_count"] == 3
    assert row["entry_count"] == 3
    assert row["source_kind"] == "webui"
    assert row["channel_kind"] == "slack"
    assert row["deliveryContext"] == {"channel_id": "C123"}
    assert row["tasks"][0]["task_id"] == "task-1"
    assert row["active_task"]["task_id"] == "task-1"
    assert row["last_task"]["task_id"] == "task-1"
    assert row["run_status"] == "running"


def test_task_state_summary_maps_abandoned_terminal_task_to_interrupted() -> None:
    task = SimpleNamespace(
        task_id="task-abandoned",
        status="abandoned",
        queue_mode="followup",
        run_kind="web_turn",
        source_kind="webui",
        created_at=100,
        started_at=110,
        finished_at=120,
        terminal_reason="runtime-restart",
        error_class="worker_lost",
        error_message="worker disappeared",
    )

    payload = task_state_summary([task])

    assert payload["active_task"] is None
    assert payload["last_task"]["task_id"] == "task-abandoned"
    assert payload["last_task"]["terminal_reason"] == "runtime-restart"
    assert payload["last_task"]["terminal_message"]
    assert payload["run_status"] == "interrupted"

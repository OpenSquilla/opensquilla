from __future__ import annotations

from opensquilla.agents.rpc_payload import agent_id_error_details, agents_list_response


def test_agents_list_response_owns_wire_shape() -> None:
    agents = [{"id": "main"}, {"id": "ops"}]

    assert agents_list_response(agents) == {"agents": agents}
    assert agents_list_response() == {"agents": []}


def test_agent_id_error_details_owns_wire_shape() -> None:
    assert agent_id_error_details("ops") == {"agentId": "ops"}

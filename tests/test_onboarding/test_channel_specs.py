"""Tests for the channel catalog."""

from __future__ import annotations

import pytest

from opensquilla.gateway.config import (
    DingTalkChannelEntry,
    DiscordChannelEntry,
    FeishuChannelEntry,
    MatrixChannelEntry,
    MSTeamsChannelEntry,
    QQChannelEntry,
    SlackChannelEntry,
    TelegramChannelEntry,
    WeComChannelEntry,
)
from opensquilla.onboarding.channel_specs import (
    ChannelSetupSpec,
    channel_catalog_payload,
    get_channel_setup_spec,
    list_channel_setup_specs,
)

ALL_TYPES = {
    "slack", "feishu", "discord", "dingtalk", "wecom", "qq",
    "msteams", "matrix", "telegram",
}

ENTRY_MODELS = {
    "slack": SlackChannelEntry,
    "feishu": FeishuChannelEntry,
    "discord": DiscordChannelEntry,
    "dingtalk": DingTalkChannelEntry,
    "wecom": WeComChannelEntry,
    "qq": QQChannelEntry,
    "msteams": MSTeamsChannelEntry,
    "matrix": MatrixChannelEntry,
    "telegram": TelegramChannelEntry,
}

EXPECTED_PUBLIC_URL = {"slack", "wecom", "msteams"}
CONDITIONAL_PUBLIC_URL = {"feishu", "telegram"}


def test_catalog_includes_all_channels():
    types = {s.type for s in list_channel_setup_specs()}
    assert types == ALL_TYPES


@pytest.mark.parametrize("type_name", sorted(ALL_TYPES))
def test_each_channel_has_common_fields(type_name: str):
    spec = get_channel_setup_spec(type_name)
    names = {f.name for f in spec.fields}
    assert {"name", "enabled", "agent_id"} <= names


@pytest.mark.parametrize("type_name", sorted(ALL_TYPES))
def test_spec_fields_align_with_pydantic_model(type_name: str):
    spec = get_channel_setup_spec(type_name)
    model = ENTRY_MODELS[type_name]
    pydantic_fields = set(model.model_fields.keys())
    spec_fields = {f.name for f in spec.fields}
    assert "type" not in spec_fields
    extra = spec_fields - pydantic_fields - {"type"}
    assert not extra, f"setup spec exposes unknown field(s): {extra}"


@pytest.mark.parametrize("type_name", sorted(ALL_TYPES))
def test_required_pydantic_fields_are_required_in_spec(type_name: str):
    spec = get_channel_setup_spec(type_name)
    model = ENTRY_MODELS[type_name]
    spec_required = {f.name for f in spec.fields if f.required}
    for fname, finfo in model.model_fields.items():
        if fname == "type":
            continue
        if finfo.is_required():
            assert fname in spec_required, (
                f"{type_name}.{fname} is required in pydantic but not in setup spec"
            )


def test_slack_secrets_are_marked_secret():
    spec = get_channel_setup_spec("slack")
    secrets = {f.name for f in spec.fields if f.secret}
    assert {"token", "signing_secret"} <= secrets


def test_telegram_secrets_are_marked_secret():
    spec = get_channel_setup_spec("telegram")
    secrets = {f.name for f in spec.fields if f.secret}
    assert {"token", "webhook_secret_token"} <= secrets


def test_feishu_connection_mode_choices():
    spec = get_channel_setup_spec("feishu")
    field = next(f for f in spec.fields if f.name == "connection_mode")
    assert field.field_type == "select"
    assert field.default == "websocket"
    assert field.choices == ("webhook", "websocket")


def test_feishu_webhook_fields_are_conditional():
    spec = get_channel_setup_spec("feishu")
    fields = {f.name: f for f in spec.fields}
    assert fields["webhook_path"].show_when == {"connection_mode": "webhook"}
    assert fields["verification_token"].show_when == {"connection_mode": "webhook"}
    assert fields["encrypt_key"].advanced is True


def test_telegram_webhook_fields_are_conditional():
    spec = get_channel_setup_spec("telegram")
    fields = {f.name: f for f in spec.fields}
    assert fields["transport_name"].default == "polling"
    assert fields["webhook_path"].show_when == {"transport_name": "webhook"}
    assert fields["webhook_url"].show_when == {"transport_name": "webhook"}
    assert fields["webhook_secret_token"].show_when == {"transport_name": "webhook"}
    assert fields["poll_timeout_s"].show_when == {"transport_name": "polling"}


def test_channel_catalog_payload_exposes_ui_metadata():
    payload = channel_catalog_payload()
    feishu = next(c for c in payload if c["type"] == "feishu")
    fields = {f["name"]: f for f in feishu["fields"]}
    assert fields["app_secret"]["group"] == "credentials"
    assert fields["app_secret"]["placeholder"]
    assert fields["webhook_path"]["showWhen"] == {"connection_mode": "webhook"}
    assert fields["encrypt_key"]["advanced"] is True
    slack = next(c for c in payload if c["type"] == "slack")
    assert "public URL" in slack["help"]


def test_matrix_encryption_choices():
    spec = get_channel_setup_spec("matrix")
    field = next(f for f in spec.fields if f.name == "encryption")
    assert field.choices == ("off", "required", "best_effort")


@pytest.mark.parametrize("type_name", sorted(EXPECTED_PUBLIC_URL))
def test_webhook_channels_require_public_url(type_name: str):
    spec = get_channel_setup_spec(type_name)
    assert spec.requires_public_url is True


@pytest.mark.parametrize("type_name", sorted(CONDITIONAL_PUBLIC_URL))
def test_conditional_webhook_channels_flagged(type_name: str):
    spec = get_channel_setup_spec(type_name)
    assert spec.transport in {"mixed", "webhook"}


def test_dependency_extras_are_set_for_optional_extras():
    expected = {
        "feishu": "feishu",
        "telegram": "telegram",
        "dingtalk": "dingtalk",
        "wecom": "wecom",
        "qq": "qq",
        "msteams": "msteams",
        "matrix": "matrix",
    }
    for type_name, extra in expected.items():
        spec = get_channel_setup_spec(type_name)
        assert spec.dependency_extra == extra


def test_unknown_channel_raises():
    with pytest.raises(KeyError):
        get_channel_setup_spec("not-a-channel")


def test_payload_redacts_secret_defaults():
    payload = channel_catalog_payload()
    for entry in payload:
        for f in entry["fields"]:
            if f.get("secret"):
                assert f["default"] in (None, "", False)


def test_catalog_is_sorted():
    types = [s.type for s in list_channel_setup_specs()]
    assert types == sorted(types)


def test_returns_setup_spec_instance():
    assert isinstance(get_channel_setup_spec("slack"), ChannelSetupSpec)

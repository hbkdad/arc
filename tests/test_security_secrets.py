"""Tests for acr.security.secrets (master §1181-1191)."""

from __future__ import annotations

from acr.security.secrets import contains_secret, redact_mapping, redact_secrets


def test_redacts_openai_style_key() -> None:
    text = "here is my key: sk-abcdefghijklmnopqrstuvwxyz012345"
    redacted = redact_secrets(text)
    assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in redacted
    assert "[REDACTED]" in redacted


def test_redacts_aws_access_key() -> None:
    redacted = redact_secrets("AKIA1234567890ABCDEF is my access key")
    assert "AKIA1234567890ABCDEF" not in redacted


def test_redacts_github_token() -> None:
    redacted = redact_secrets("token: ghp_abcdefghijklmnopqrstuvwxyz0123")
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123" not in redacted


def test_redacts_bearer_token() -> None:
    redacted = redact_secrets("Authorization: Bearer abcdef1234567890.xyz")
    assert "abcdef1234567890.xyz" not in redacted


def test_redacts_pem_private_key_block() -> None:
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIBogIBAAJ...\n-----END RSA PRIVATE KEY-----"
    redacted = redact_secrets(pem)
    assert "MIIBogIBAAJ" not in redacted


def test_leaves_benign_text_unchanged() -> None:
    text = "ACR persists data in a local SQLite file."
    assert redact_secrets(text) == text


def test_contains_secret_detects_and_rejects_benign_text() -> None:
    assert contains_secret("sk-abcdefghijklmnopqrstuvwxyz012345") is True
    assert contains_secret("just a normal sentence") is False


def test_redact_mapping_recurses_through_nested_structures() -> None:
    payload = {
        "note": "safe text",
        "nested": {"key": "sk-abcdefghijklmnopqrstuvwxyz012345"},
        "items": ["fine", "AKIA1234567890ABCDEF"],
    }
    redacted = redact_mapping(payload)
    assert redacted["note"] == "safe text"

    nested = redacted["nested"]
    assert isinstance(nested, dict)
    assert "sk-" not in nested["key"]

    items = redacted["items"]
    assert isinstance(items, list)
    assert "AKIA1234567890ABCDEF" not in items[1]


def test_redact_mapping_recurses_into_a_list_nested_inside_a_list() -> None:
    payload: dict[str, object] = {"outer": ["fine", ["AKIA1234567890ABCDEF", "also fine"]]}

    redacted = redact_mapping(payload)

    outer = redacted["outer"]
    assert isinstance(outer, list)
    inner = outer[1]
    assert isinstance(inner, list)
    assert "AKIA1234567890ABCDEF" not in inner[0]
    assert inner[1] == "also fine"

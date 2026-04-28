"""Tests for the audit_strictness script."""

import json
from pathlib import Path
from typing import Any

import pytest

import scripts.audit_strictness as audit
from scripts.audit_strictness import (
    audit_common,
    audit_factory,
    audit_ibc,
    audit_native,
    main,
)


######################################################################
# Fixtures
######################################################################


@pytest.fixture(autouse=True)
def reset_audit_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset module-level issues and stats before every test.

    audit_strictness.py accumulates results in two module-level globals
    that persist across calls within the same process.  Without this
    fixture every test would inherit issues left by the previous one.
    monkeypatch handles teardown automatically so no explicit restore is needed.
    """
    monkeypatch.setattr(audit, "issues", [])
    monkeypatch.setattr(audit, "stats", {"factory": 0, "ibc": 0, "native": 0})


@pytest.fixture
def fake_path() -> Path:
    """Return a sentinel Path used as the path argument to audit functions."""
    return Path("/fake/path/asset.json")


@pytest.fixture
def clean_factory_data() -> dict[str, Any]:
    """Minimal factory asset dict with no website or twitter fields."""
    return {
        "type": "factory",
        "symbol": "PANDA",
        "name": "Factory Panda Token",
    }


@pytest.fixture
def clean_ibc_data() -> dict[str, Any]:
    """IBC asset dict with one valid channel (channel-3 / channel-175) and one valid trace."""
    return {
        "type": "ibc",
        "channels": [
            {"zigchain_channel": "channel-3", "counterparty_channel": "channel-175"},
        ],
        "traces": [
            {"path": "transfer/channel-3/uusdc", "chain_name": "zigchain"},
        ],
    }


@pytest.fixture
def clean_native_data() -> dict[str, Any]:
    """Native asset dict with a single unique trace."""
    return {
        "type": "native",
        "traces": [
            {"type": "ibc", "chain_name": "zigchain", "base_denom": "uzig"},
        ],
    }


@pytest.fixture
def clean_common_data() -> dict[str, Any]:
    """Asset dict with all audited common fields set within their limits."""
    return {
        "images": [{"chain_name": "zigchain", "base_denom": "uzig"}],
        "denom_units": [{"denom": "uzig", "exponent": 6, "aliases": ["zig"]}],
        "extended_description": "A short description.",
        "socials": {"website": "https://zigchain.com"},
    }


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """Create a minimal repo skeleton with assets/{native,factory,ibc} directories."""
    (tmp_path / "assets" / "native").mkdir(parents=True)
    (tmp_path / "assets" / "factory").mkdir(parents=True)
    (tmp_path / "assets" / "ibc").mkdir(parents=True)
    return tmp_path


######################################################################
# Tests for audit_factory
######################################################################

# ----------------
# Positive tests for audit_factory
# ----------------


def test_audit_factory_clean_asset_adds_no_issues(
    clean_factory_data: dict[str, Any], fake_path: Path
) -> None:
    """audit_factory adds no issues and increments stats['factory'] for a clean asset.

    The stats counter drives the summary line printed by main():
    'Audited: N native, N factory, N ibc'.
    """
    # Act: run audit on a clean factory asset
    audit_factory(clean_factory_data, fake_path)

    # Assert: no issues recorded and the factory counter is incremented
    assert audit.issues == []
    assert audit.stats["factory"] == 1


# ----------------
# Negative tests for audit_factory
# ----------------


def test_audit_factory_website_field_present_appends_issue(
    clean_factory_data: dict[str, Any], fake_path: Path
) -> None:
    """audit_factory appends one issue containing the keyword and asset path when website is present."""
    # Arrange: inject the forbidden website field
    clean_factory_data["website"] = "https://example.com"

    # Act: run audit on the modified asset
    audit_factory(clean_factory_data, fake_path)

    # Assert: exactly one issue, message contains the keyword and the asset path
    assert len(audit.issues) == 1
    assert "FACTORY website field present:" in audit.issues[0]
    assert str(fake_path) in audit.issues[0]


def test_audit_factory_twitter_field_present_appends_issue(
    clean_factory_data: dict[str, Any], fake_path: Path
) -> None:
    """audit_factory appends one issue containing the keyword and asset path when twitter is present."""
    # Arrange: inject the forbidden twitter field
    clean_factory_data["twitter"] = "@example"

    # Act: run audit on the modified asset
    audit_factory(clean_factory_data, fake_path)

    # Assert: exactly one issue, message contains the keyword and the asset path
    assert len(audit.issues) == 1
    assert "FACTORY twitter field present:" in audit.issues[0]
    assert str(fake_path) in audit.issues[0]


def test_audit_factory_both_forbidden_fields_appends_two_issues(
    clean_factory_data: dict[str, Any], fake_path: Path
) -> None:
    """audit_factory appends exactly two issues when both website and twitter are present."""
    # Arrange: inject both forbidden fields
    clean_factory_data["website"] = "https://example.com"
    clean_factory_data["twitter"] = "@example"

    # Act: run audit on the modified asset
    audit_factory(clean_factory_data, fake_path)

    # Assert: one issue per forbidden field, in declaration order
    assert len(audit.issues) == 2
    assert "FACTORY website field present:" in audit.issues[0]
    assert "FACTORY twitter field present:" in audit.issues[1]



######################################################################
# Tests for audit_ibc
######################################################################

# ----------------
# Positive tests for audit_ibc
# ----------------


def test_audit_ibc_valid_channel_n_ids_add_no_issues(
    clean_ibc_data: dict[str, Any], fake_path: Path
) -> None:
    """audit_ibc adds no issues for valid channel-N / channel-M channel IDs.
    And audit_ibc increments stats['ibc'] by 1 on every call regardless of issues.
    """
    # Act: run audit on a clean IBC asset with channel-N format IDs
    audit_ibc(clean_ibc_data, fake_path)

    # Assert: no issues recorded and the ibc counter is incremented
    assert audit.issues == []
    assert audit.stats["ibc"] == 1


def test_audit_ibc_wasm_channel_ids_add_no_issues(fake_path: Path) -> None:
    """audit_ibc adds no issues when both channel IDs use the 08-wasm-N format."""
    # Arrange: both sides use the wasm light client channel format
    data: dict[str, Any] = {
        "channels": [
            {"zigchain_channel": "08-wasm-42", "counterparty_channel": "08-wasm-7"},
        ],
        "traces": [{"path": "transfer/channel-1/uatom"}],
    }

    # Act: run audit on the asset with wasm-format channel IDs
    audit_ibc(data, fake_path)

    # Assert: no issues recorded — 08-wasm-N is a valid pattern
    assert audit.issues == []


# ----------------
# Negative tests for audit_ibc
# ----------------


def test_audit_ibc_bad_zigchain_channel_appends_issue(fake_path: Path) -> None:
    """audit_ibc appends one issue containing the field name, bad ID, and asset path when zigchain_channel does not match the pattern."""
    # Arrange: channel ID uses "chan-" prefix instead of "channel-"
    bad_id = "chan-3"
    data: dict[str, Any] = {
        "channels": [{"zigchain_channel": bad_id, "counterparty_channel": "channel-175"}],
        "traces": [],
    }

    # Act: run audit on the asset with the malformed channel
    audit_ibc(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"IBC zigchain_channel '{bad_id}' doesn't match pattern: {fake_path}"


def test_audit_ibc_bad_counterparty_channel_appends_issue(fake_path: Path) -> None:
    """audit_ibc appends one issue containing the field name, bad ID, and asset path when counterparty_channel does not match the pattern."""
    # Arrange: counterparty channel ID is missing the required numeric suffix
    bad_id = "channel"
    data: dict[str, Any] = {
        "channels": [{"zigchain_channel": "channel-3", "counterparty_channel": bad_id}],
        "traces": [],
    }

    # Act: run audit on the asset with the malformed counterparty channel
    audit_ibc(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"IBC counterparty_channel '{bad_id}' doesn't match pattern: {fake_path}"


def test_audit_ibc_trace_path_missing_transfer_prefix_appends_issue(
    fake_path: Path,
) -> None:
    """audit_ibc appends one issue with the complete expected message when a trace path does not start with 'transfer/'."""
    # Arrange: trace path uses a non-transfer prefix
    bad_trace_path = "foo/channel-3/uusdc"
    data: dict[str, Any] = {
        "channels": [],
        "traces": [{"path": bad_trace_path}],
    }

    # Act: run audit on the asset with the invalid trace path
    audit_ibc(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"IBC trace path doesn't start with 'transfer/': '{bad_trace_path}' in {fake_path}"


def test_audit_ibc_traces_count_issue_message_includes_count_and_path(
    fake_path: Path,
) -> None:
    """audit_ibc appends one issue with the complete expected message when traces exceed the limit."""
    # Arrange: 11 valid traces, one over the limit of 10
    data: dict[str, Any] = {
        "channels": [],
        "traces": [{"path": f"transfer/channel-{i}/uatom"} for i in range(11)],
    }

    # Act: run audit on the asset with too many traces
    audit_ibc(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"IBC traces count 11 > 10: {fake_path}"


def test_audit_ibc_channels_count_issue_message_includes_count_and_path(
    fake_path: Path,
) -> None:
    """audit_ibc appends one issue with the complete expected message when channels exceed the limit."""
    # Arrange: 6 valid channels, one over the limit of 5
    data: dict[str, Any] = {
        "channels": [
            {"zigchain_channel": f"channel-{i}", "counterparty_channel": f"channel-{i + 100}"}
            for i in range(6)
        ],
        "traces": [],
    }

    # Act: run audit on the asset with too many channels
    audit_ibc(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"IBC channels count 6 > 5: {fake_path}"


# ----------------
# Boundary tests for audit_ibc
# ----------------


@pytest.mark.parametrize(
    "trace_count, expected_issues",
    [
        (10, 0),
        (11, 1),
    ],
    ids=["10_traces_passes", "11_traces_fails"],
)
def test_audit_ibc_trace_count_boundary(
    fake_path: Path, trace_count: int, expected_issues: int
) -> None:
    """audit_ibc allows up to 10 traces and rejects 11 or more."""
    # Arrange: build exactly trace_count valid traces (parametrized: 10 passes, 11 fails)
    data: dict[str, Any] = {
        "channels": [],
        "traces": [{"path": f"transfer/channel-{i}/uatom"} for i in range(trace_count)],
    }

    # Act: run audit on the asset with trace_count traces
    audit_ibc(data, fake_path)

    # Assert: issue count matches expectation for this boundary value
    assert len(audit.issues) == expected_issues


@pytest.mark.parametrize(
    "channel_count, expected_issues",
    [
        (5, 0),
        (6, 1),
    ],
    ids=["5_channels_passes", "6_channels_fails"],
)
def test_audit_ibc_channel_count_boundary(
    fake_path: Path, channel_count: int, expected_issues: int
) -> None:
    """audit_ibc allows up to 5 channels and rejects 6 or more."""
    # Arrange: build exactly channel_count valid channels (parametrized: 5 passes, 6 fails)
    data: dict[str, Any] = {
        "channels": [
            {
                "zigchain_channel": f"channel-{i}",
                "counterparty_channel": f"channel-{i + 100}",
            }
            for i in range(channel_count)
        ],
        "traces": [],
    }

    # Act: run audit on the asset with channel_count channels
    audit_ibc(data, fake_path)

    # Assert: issue count matches expectation for this boundary value
    assert len(audit.issues) == expected_issues


def test_audit_ibc_channel_id_path_traversal_flagged(fake_path: Path) -> None:
    """audit_ibc flags a channel ID containing path traversal characters as a pattern mismatch."""
    # Arrange: zigchain_channel contains a path traversal sequence
    bad_id = "../../../../etc/passwd"
    data: dict[str, Any] = {
        "channels": [
            {
                "zigchain_channel": bad_id,
                "counterparty_channel": "channel-1",
            },
        ],
        "traces": [],
    }

    # Act: run audit on the asset with the traversal channel ID
    audit_ibc(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"IBC zigchain_channel '{bad_id}' doesn't match pattern: {fake_path}"


@pytest.mark.parametrize(
    "malicious_path",
    [
        "transfer/../../../etc/passwd",       # path traversal via ".." after valid prefix
        "transfer/channel-1\x00/uusdc",       # null byte (control char, ord < 0x20)
        "transfer/channel-1 ; rm -rf /",      # shell metacharacters (space, semicolon)
    ],
    ids=["path-traversal", "null-byte", "shell-metacharacters"],
)
def test_audit_ibc_transfer_path_with_unsafe_content_flagged(
    fake_path: Path,
    malicious_path: str,
) -> None:
    """audit_ibc flags paths that start with 'transfer/' but contain unsafe sequences or characters."""
    # Arrange: path passes the startswith("transfer/") check but hits the elif guard
    data: dict[str, Any] = {
        "channels": [],
        "traces": [{"path": malicious_path}],
    }

    # Act
    audit_ibc(data, fake_path)

    # Assert: one issue with the unsafe-characters message
    assert len(audit.issues) == 1
    assert "IBC trace path contains unsafe characters or sequences" in audit.issues[0]


######################################################################
# Tests for audit_native
######################################################################

# ----------------
# Positive tests for audit_native
# ----------------


def test_audit_native_single_unique_trace_adds_no_issues(
    clean_native_data: dict[str, Any], fake_path: Path
) -> None:
    """audit_native adds no issues and increments stats['native'] for a clean asset."""
    # Act: run audit on a clean native asset with one unique trace
    audit_native(clean_native_data, fake_path)

    # Assert: no issues recorded and the native counter is incremented
    assert audit.issues == []
    assert audit.stats["native"] == 1


def test_audit_native_empty_traces_adds_no_issues(fake_path: Path) -> None:
    """audit_native adds no issues when the traces list is empty."""
    # Act: run audit on an asset with an explicit empty traces list
    audit_native({"traces": []}, fake_path)

    # Assert: no issues recorded — nothing to check with zero traces
    assert audit.issues == []


def test_audit_native_two_different_traces_add_no_issues(fake_path: Path) -> None:
    """audit_native adds no issues when two distinct trace dicts are present."""
    # Arrange: two traces with different chain_name values — not duplicates
    data: dict[str, Any] = {
        "traces": [
            {"type": "ibc", "chain_name": "zigchain"},
            {"type": "ibc", "chain_name": "noble"},
        ]
    }

    # Act: run audit on the asset with two distinct traces
    audit_native(data, fake_path)

    # Assert: no issues recorded — distinct traces are allowed
    assert audit.issues == []


# ----------------
# Negative tests for audit_native
# ----------------


def test_audit_native_duplicate_traces_appends_issue(fake_path: Path) -> None:
    """audit_native appends one issue with the complete expected message when two identical trace objects are present."""
    # Arrange: two copies of the same trace dict
    trace = {"type": "ibc", "chain_name": "zigchain", "base_denom": "uzig"}
    data: dict[str, Any] = {"traces": [trace, trace.copy()]}

    # Act: run audit on the asset with the duplicated trace
    audit_native(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"NATIVE duplicate trace entry: {fake_path}"


def test_audit_native_duplicate_detected_regardless_of_key_order(fake_path: Path) -> None:
    """audit_native detects duplicates even when dict key order differs (relies on sort_keys=True)."""
    # Arrange: same key-value pairs, different insertion order
    trace_a = {"chain_name": "zigchain", "type": "ibc"}
    trace_b = {"type": "ibc", "chain_name": "zigchain"}

    # Act: run audit — json.dumps(sort_keys=True) normalises both to the same string
    audit_native({"traces": [trace_a, trace_b]}, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"NATIVE duplicate trace entry: {fake_path}"


def test_audit_native_count_issue_message_includes_count_and_path(fake_path: Path) -> None:
    """audit_native appends one issue with the complete expected message when traces exceed the limit."""
    # Arrange: 11 unique traces, one over the limit of 10
    data: dict[str, Any] = {
        "traces": [{"type": "ibc", "chain_name": f"chain-{i}"} for i in range(11)]
    }

    # Act: run audit on the asset with too many traces
    audit_native(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"NATIVE traces count 11 > 10: {fake_path}"


# ----------------
# Boundary tests for audit_native
# ----------------


@pytest.mark.parametrize(
    "trace_count, expected_issues",
    [
        (10, 0),
        (11, 1),
    ],
    ids=["10_traces_passes", "11_traces_fails"],
)
def test_audit_native_trace_count_boundary(
    fake_path: Path, trace_count: int, expected_issues: int
) -> None:
    """audit_native allows up to 10 traces and rejects 11 or more."""
    # Arrange: build exactly trace_count unique traces (parametrized: 10 passes, 11 fails)
    data: dict[str, Any] = {
        "traces": [{"type": "ibc", "chain_name": f"chain-{i}"} for i in range(trace_count)]
    }

    # Act: run audit on the asset with trace_count traces
    audit_native(data, fake_path)

    # Assert: issue count matches expectation for this boundary value
    assert len(audit.issues) == expected_issues


######################################################################
# Tests for audit_common
######################################################################

# ----------------
# Positive tests for audit_common
# ----------------


def test_audit_common_clean_data_adds_no_issues(
    clean_common_data: dict[str, Any], fake_path: Path
) -> None:
    """audit_common adds no issues when all optional fields are within their limits."""
    # Act: run audit on a clean asset with all fields within limits
    audit_common(clean_common_data, fake_path)

    # Assert: no issues recorded
    assert audit.issues == []


def test_audit_common_no_optional_fields_adds_no_issues(fake_path: Path) -> None:
    """audit_common adds no issues when the data dict contains no audited fields."""
    # Act: run audit on a minimal asset with none of the optional audited fields
    audit_common({}, fake_path)

    # Assert: no issues recorded — nothing to check
    assert audit.issues == []


# ----------------
# Boundary tests for audit_common
# ----------------


@pytest.mark.parametrize(
    "chain_name_len, expected_issues",
    [
        (64, 0),
        (65, 1),
    ],
    ids=["64_chars_passes", "65_chars_fails"],
)
def test_audit_common_chain_name_length_boundary(
    fake_path: Path, chain_name_len: int, expected_issues: int
) -> None:
    """audit_common allows images[].chain_name up to 64 characters and rejects longer values."""
    # Arrange: build an image entry with exactly chain_name_len characters (parametrized: 64 passes, 65 fails)
    data: dict[str, Any] = {"images": [{"chain_name": "a" * chain_name_len, "base_denom": "uzig"}]}

    # Act: run audit on the asset with the given chain_name length
    audit_common(data, fake_path)

    # Assert: issue count matches expectation for this boundary value
    assert len(audit.issues) == expected_issues


@pytest.mark.parametrize(
    "base_denom_len, expected_issues",
    [
        (256, 0),
        (257, 1),
    ],
    ids=["256_chars_passes", "257_chars_fails"],
)
def test_audit_common_base_denom_length_boundary(
    fake_path: Path, base_denom_len: int, expected_issues: int
) -> None:
    """audit_common allows images[].base_denom up to 256 characters and rejects longer values."""
    # Arrange: build an image entry with exactly base_denom_len characters (parametrized: 256 passes, 257 fails)
    data: dict[str, Any] = {"images": [{"chain_name": "zigchain", "base_denom": "a" * base_denom_len}]}

    # Act: run audit on the asset with the given base_denom length
    audit_common(data, fake_path)

    # Assert: issue count matches expectation for this boundary value
    assert len(audit.issues) == expected_issues


@pytest.mark.parametrize(
    "exponent, expected_issues",
    [
        (18, 0),
        (19, 1),
    ],
    ids=["exponent_18_passes", "exponent_19_fails"],
)
def test_audit_common_denom_unit_exponent_boundary(
    fake_path: Path, exponent: int, expected_issues: int
) -> None:
    """audit_common allows denom_unit exponent up to 18 and rejects values above."""
    # Arrange: build a denom_unit with the given exponent (parametrized: 18 passes, 19 fails)
    data: dict[str, Any] = {"denom_units": [{"denom": "uzig", "exponent": exponent}]}

    # Act: run audit on the asset with the given exponent value
    audit_common(data, fake_path)

    # Assert: issue count matches expectation for this boundary value
    assert len(audit.issues) == expected_issues


@pytest.mark.parametrize(
    "alias_count, expected_issues",
    [
        (10, 0),
        (11, 1),
    ],
    ids=["10_aliases_passes", "11_aliases_fails"],
)
def test_audit_common_denom_unit_aliases_count_boundary(
    fake_path: Path, alias_count: int, expected_issues: int
) -> None:
    """audit_common allows up to 10 aliases per denom_unit and rejects more."""
    # Arrange: build a denom_unit with exactly alias_count aliases (parametrized: 10 passes, 11 fails)
    data: dict[str, Any] = {
        "denom_units": [
            {"denom": "uzig", "exponent": 0, "aliases": [f"alias{i}" for i in range(alias_count)]}
        ]
    }

    # Act: run audit on the asset with the given alias count
    audit_common(data, fake_path)

    # Assert: issue count matches expectation for this boundary value
    assert len(audit.issues) == expected_issues


@pytest.mark.parametrize(
    "desc_len, expected_issues",
    [
        (8192, 0),
        (8193, 1),
    ],
    ids=["8192_chars_passes", "8193_chars_fails"],
)
def test_audit_common_extended_description_length_boundary(
    fake_path: Path, desc_len: int, expected_issues: int
) -> None:
    """audit_common allows extended_description up to 8192 characters and rejects longer."""
    # Arrange: build an extended_description of exactly desc_len characters (parametrized: 8192 passes, 8193 fails)
    data: dict[str, Any] = {"extended_description": "x" * desc_len}

    # Act: run audit on the asset with the given description length
    audit_common(data, fake_path)

    # Assert: issue count matches expectation for this boundary value
    assert len(audit.issues) == expected_issues


# ----------------
# Negative tests for audit_common (issue message format)
# ----------------


def test_audit_common_chain_name_issue_message_includes_path(fake_path: Path) -> None:
    """audit_common appends one issue with the complete expected message when chain_name exceeds 64 chars."""
    # Arrange: chain_name is 65 characters — one over the limit
    data: dict[str, Any] = {"images": [{"chain_name": "a" * 65, "base_denom": "uzig"}]}

    # Act: run audit on the asset with the oversized chain_name
    audit_common(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"ImageSyncPointer chain_name > 64 chars: {fake_path}"


def test_audit_common_base_denom_issue_message_includes_path(fake_path: Path) -> None:
    """audit_common appends one issue with the complete expected message when base_denom exceeds 256 chars."""
    # Arrange: base_denom is 257 characters — one over the limit
    data: dict[str, Any] = {"images": [{"chain_name": "zigchain", "base_denom": "a" * 257}]}

    # Act: run audit on the asset with the oversized base_denom
    audit_common(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"ImageSyncPointer base_denom > 256 chars: {fake_path}"


def test_audit_common_aliases_count_issue_message_includes_count_and_path(
    fake_path: Path,
) -> None:
    """audit_common appends one issue with the complete expected message when aliases exceed 10."""
    # Arrange: 11 aliases — one over the limit
    data: dict[str, Any] = {
        "denom_units": [
            {"denom": "uzig", "exponent": 0, "aliases": [f"a{i}" for i in range(11)]}
        ]
    }

    # Act: run audit on the asset with too many aliases
    audit_common(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"DenomUnit aliases count 11 > 10: {fake_path}"


def test_audit_common_exponent_issue_message_includes_exponent_and_path(
    fake_path: Path,
) -> None:
    """audit_common appends one issue with the complete expected message when exponent exceeds 18."""
    # Arrange: exponent is 19 — one over the limit
    data: dict[str, Any] = {"denom_units": [{"denom": "uzig", "exponent": 19}]}

    # Act: run audit on the asset with the oversized exponent
    audit_common(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"DenomUnit exponent 19 > 18: {fake_path}"


def test_audit_common_extended_description_issue_message_includes_path(
    fake_path: Path,
) -> None:
    """audit_common appends one issue with the complete expected message when extended_description exceeds 8192 chars."""
    # Arrange: description is 8193 characters — one over the limit
    data: dict[str, Any] = {"extended_description": "x" * 8193}

    # Act: run audit on the asset with the oversized description
    audit_common(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"extended_description > 8192 chars: {fake_path}"


# ----------------
# Positive tests for audit_common (socials)
# ----------------


def test_audit_common_socials_http_url_passes(fake_path: Path) -> None:
    """audit_common adds no issues for a valid http:// socials URL."""
    # Act: run audit with an http:// URL in socials
    audit_common({"socials": {"website": "http://example.com"}}, fake_path)

    # Assert: no issues recorded — http:// is an accepted scheme
    assert audit.issues == []


def test_audit_common_socials_https_url_passes(fake_path: Path) -> None:
    """audit_common adds no issues for a valid https:// socials URL."""
    # Act: run audit with an https:// URL in socials
    audit_common({"socials": {"website": "https://zigchain.com"}}, fake_path)

    # Assert: no issues recorded — https:// is an accepted scheme
    assert audit.issues == []


# ----------------
# Negative tests for audit_common (socials)
# ----------------


def test_audit_common_socials_ftp_url_appends_issue(fake_path: Path) -> None:
    """audit_common appends one issue with the complete expected message when a socials URL uses the ftp:// scheme."""
    # Arrange: website URL uses ftp:// instead of http/https
    bad_url = "ftp://files.example.com"
    data: dict[str, Any] = {"socials": {"website": bad_url}}

    # Act: run audit on the asset with the invalid socials URL
    audit_common(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"Socials.website not http/https: '{bad_url}' in {fake_path}"


def test_audit_common_socials_javascript_url_appends_issue(fake_path: Path) -> None:
    """audit_common appends one issue with the complete expected message for a javascript: URL in socials."""
    # Arrange: website URL uses the javascript: scheme — a common XSS vector
    bad_url = "javascript:alert(1)"
    data: dict[str, Any] = {"socials": {"website": bad_url}}

    # Act: run audit on the asset with the invalid socials URL
    audit_common(data, fake_path)

    # Assert: exactly one issue with the complete expected message
    assert len(audit.issues) == 1
    assert audit.issues[0] == f"Socials.website not http/https: '{bad_url}' in {fake_path}"


######################################################################
# Tests for main
######################################################################

# ----------------
# Positive tests for main
# ----------------


def test_main_no_asset_directories_exits_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main exits 0 when no asset directories exist under assets_dir."""
    # Arrange: point assets_dir at an empty tmp directory — no native/factory/ibc subdirs
    monkeypatch.setattr(audit, "assets_dir", tmp_path / "assets")

    # Act: run main — every dir_path.exists() check returns False, loop body never executes
    with pytest.raises(SystemExit) as excinfo:
        main()

    # Assert: no issues, clean exit; summary shows all-zero counts and the success message
    out = capsys.readouterr().out
    assert excinfo.value.code == 0
    assert out.startswith("Audited: 0 native, 0 factory, 0 IBC")
    assert "✅ No issues found — all assets are compatible with proposed strict rules." in out


def test_main_existing_empty_asset_directories_exits_zero(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main exits 0 when asset directories exist but contain no JSON files."""
    # Arrange: repo_root fixture creates the native/factory/ibc dirs but writes no files
    monkeypatch.setattr(audit, "assets_dir", repo_root / "assets")

    # Act: run main — dirs are found but rglob yields no JSON files
    with pytest.raises(SystemExit) as excinfo:
        main()

    # Assert: no issues, clean exit; summary shows all-zero counts and the success message
    out = capsys.readouterr().out
    assert excinfo.value.code == 0
    assert out.startswith("Audited: 0 native, 0 factory, 0 IBC")
    assert "✅ No issues found — all assets are compatible with proposed strict rules." in out


def test_main_clean_native_asset_exits_zero(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main exits 0 and prints the correct summary line when the only asset is a valid native JSON file."""
    # Arrange: write one clean native asset
    asset = {
        "type": "native",
        "traces": [{"type": "ibc", "chain_name": "zigchain"}],
    }
    (repo_root / "assets" / "native" / "zig.json").write_text(
        json.dumps(asset), encoding="utf-8"
    )
    monkeypatch.setattr(audit, "assets_dir", repo_root / "assets")

    # Act: run main against the single clean asset
    with pytest.raises(SystemExit) as excinfo:
        main()

    # Assert: exit 0, summary reflects 1 native asset audited, and the success message is printed
    out = capsys.readouterr().out
    assert excinfo.value.code == 0
    assert out.startswith("Audited: 1 native, 0 factory, 0 IBC")
    assert "✅ No issues found — all assets are compatible with proposed strict rules." in out


def test_main_clean_factory_asset_exits_zero(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main exits 0 and prints the correct summary line when the only asset is a valid factory JSON file."""
    # Arrange: write one clean factory asset
    asset = {"type": "factory", "symbol": "PANDA"}
    (repo_root / "assets" / "factory" / "panda.json").write_text(
        json.dumps(asset), encoding="utf-8"
    )
    monkeypatch.setattr(audit, "assets_dir", repo_root / "assets")

    # Act: run main against the single clean asset
    with pytest.raises(SystemExit) as excinfo:
        main()

    # Assert: exit 0, summary reflects 1 factory asset audited, and the success message is printed
    out = capsys.readouterr().out
    assert excinfo.value.code == 0
    assert out.startswith("Audited: 0 native, 1 factory, 0 IBC")
    assert "✅ No issues found — all assets are compatible with proposed strict rules." in out


def test_main_clean_ibc_asset_exits_zero(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main exits 0 and prints the correct summary line when the only asset is a valid IBC JSON file."""
    # Arrange: write one clean IBC asset with a valid channel and trace
    asset = {
        "type": "ibc",
        "channels": [
            {"zigchain_channel": "channel-3", "counterparty_channel": "channel-175"},
        ],
        "traces": [{"path": "transfer/channel-3/uusdc"}],
    }
    (repo_root / "assets" / "ibc" / "usdc.json").write_text(
        json.dumps(asset), encoding="utf-8"
    )
    monkeypatch.setattr(audit, "assets_dir", repo_root / "assets")

    # Act: run main against the single clean asset
    with pytest.raises(SystemExit) as excinfo:
        main()

    # Assert: exit 0, summary reflects 1 IBC asset audited, and the success message is printed
    out = capsys.readouterr().out
    assert excinfo.value.code == 0
    assert out.startswith("Audited: 0 native, 0 factory, 1 IBC")
    assert "✅ No issues found — all assets are compatible with proposed strict rules." in out


# ----------------
# Negative tests for main
# ----------------


def test_main_factory_asset_with_website_exits_one(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main exits 1 when a factory JSON contains the forbidden website field."""
    # Arrange: write a factory asset with the legacy website field
    asset = {"type": "factory", "symbol": "PANDA", "website": "https://panda.com"}
    asset_path = repo_root / "assets" / "factory" / "panda.json"
    asset_path.write_text(json.dumps(asset), encoding="utf-8")
    monkeypatch.setattr(audit, "assets_dir", repo_root / "assets")

    # Act: run main — audit_factory appends an issue for the website field
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: non-zero exit, issue count line, and full issue message with ⚠️ prefix
    out = capsys.readouterr().out
    assert exc.value.code == 1
    assert "1 issue(s) found:" in out
    assert f"  ⚠️  FACTORY website field present: {asset_path}" in out


def test_main_continues_processing_after_parse_error(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main processes remaining files after a JSON parse error instead of aborting.

    The try/except in main() appends a parse error to issues and calls continue,
    so files in subsequent directories are still audited.
    """
    # Arrange: one unparseable file in native/ and one factory file with a known issue
    bad_path = repo_root / "assets" / "native" / "bad.json"
    bad_path.write_text("{ not valid json }", encoding="utf-8")
    factory_path = repo_root / "assets" / "factory" / "panda.json"
    factory_path.write_text(
        json.dumps({"type": "factory", "symbol": "PANDA", "website": "https://panda.com"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(audit, "assets_dir", repo_root / "assets")

    # Act: run main — parse error on bad.json, then panda.json still audited
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: both files processed — parse error and factory issue both in output;
    # stats['factory'] == 1 confirms the factory file was reached after the parse error
    out = capsys.readouterr().out
    assert exc.value.code == 1
    assert "2 issue(s) found:" in out
    assert f"  ⚠️  JSON parse error: {bad_path}:" in out
    assert f"  ⚠️  FACTORY website field present: {factory_path}" in out
    assert audit.stats["factory"] == 1


def test_main_accumulates_issues_across_multiple_files(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main accumulates issues from all files and reports the total count.

    The "N issue(s) found:" line uses len(issues) at print time, so it must
    reflect every issue appended across all files — not just the last one.
    """
    # Arrange: two factory files each with the forbidden website field
    path_a = repo_root / "assets" / "factory" / "panda.json"
    path_b = repo_root / "assets" / "factory" / "bear.json"
    for p in (path_a, path_b):
        p.write_text(
            json.dumps({"type": "factory", "symbol": "TKN", "website": "https://example.com"}),
            encoding="utf-8",
        )
    monkeypatch.setattr(audit, "assets_dir", repo_root / "assets")

    # Act: run main against two files that each produce one issue
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: count line shows 2, both ⚠️ messages appear, stats reflect both files audited
    out = capsys.readouterr().out
    assert exc.value.code == 1
    assert "2 issue(s) found:" in out
    assert f"  ⚠️  FACTORY website field present: {path_a}" in out
    assert f"  ⚠️  FACTORY website field present: {path_b}" in out
    assert audit.stats["factory"] == 2


def test_main_malformed_json_exits_one(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main exits 1 when a .json file cannot be parsed."""
    # Arrange: write a file with invalid JSON content
    asset_path = repo_root / "assets" / "native" / "bad.json"
    asset_path.write_text("{ not valid json }", encoding="utf-8")
    monkeypatch.setattr(audit, "assets_dir", repo_root / "assets")

    # Act: run main — the JSON parse error is appended to issues
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: non-zero exit, issue count line, and the JSON parse error prefix in the output
    # The full exception message varies by Python version, so we only assert the stable prefix.
    out = capsys.readouterr().out
    assert exc.value.code == 1
    assert "1 issue(s) found:" in out
    assert f"  ⚠️  JSON parse error: {asset_path}:" in out


"""Tests for the EvmChain Pydantic model."""

import warnings
from typing import Any, Dict

import pytest
from pydantic import ValidationError

from models import EvmChain, Explorer, NativeCurrency
from . import check_model_error


######################################################################
# Fixtures
######################################################################


@pytest.fixture
def valid_mainnet_data() -> Dict[str, Any]:
    """Minimal valid EvmChain payload for ZIGChain mainnet (944)."""
    return {
        "chain_id": 944,
        "network_id": 944,
        "name": "ZIGChain",
        "short_name": "zigchain",
        "chain": "ZIG",
        "native_currency": {"name": "ZIG", "symbol": "ZIG", "decimals": 18},
        "rpc": ["https://evm-rpc.zigchain.com"],
        "info_url": "https://zigchain.com",
    }


@pytest.fixture
def valid_testnet_data() -> Dict[str, Any]:
    """Valid EvmChain payload for ZIGChain testnet (2061) with faucet + explorer."""
    return {
        "chain_id": 2061,
        "network_id": 2061,
        "name": "ZIGChain Testnet",
        "short_name": "zigchain-testnet",
        "chain": "ZIG",
        "native_currency": {"name": "ZIG", "symbol": "ZIG", "decimals": 18},
        "rpc": ["https://evm-rpc-testnet.zigchain.com"],
        "faucets": ["https://faucet-testnet.zigchain.com"],
        "explorers": [
            {
                "name": "ZIGChain Testnet Explorer",
                "url": "https://explorer-testnet.zigchain.com",
                "standard": "EIP3091",
            }
        ],
        "info_url": "https://zigchain.com",
        "status": "incubating",
        "cosmos_chain_id": "zig-test-2",
    }


######################################################################
# Happy path
######################################################################


def test_valid_mainnet_loads(valid_mainnet_data: Dict[str, Any]) -> None:
    chain = EvmChain.model_validate(valid_mainnet_data)
    assert chain.chain_id == 944
    assert chain.short_name == "zigchain"
    assert chain.status == "active"  # default
    assert chain.is_verified is True  # default
    assert chain.cosmos_chain_id is None  # optional
    assert chain.faucets == []  # default empty list


def test_valid_testnet_loads(valid_testnet_data: Dict[str, Any]) -> None:
    chain = EvmChain.model_validate(valid_testnet_data)
    assert chain.chain_id == 2061
    assert chain.status == "incubating"
    assert chain.cosmos_chain_id == "zig-test-2"
    assert len(chain.faucets) == 1
    assert len(chain.explorers) == 1
    assert chain.explorers[0].standard == "EIP3091"


def test_schema_ref_alias_accepted(valid_mainnet_data: Dict[str, Any]) -> None:
    """`$schema` key (with dollar) is accepted via the alias."""
    valid_mainnet_data["$schema"] = "../../schemas/chain.evm.schema.json"
    chain = EvmChain.model_validate(valid_mainnet_data)
    assert chain.schema_ref == "../../schemas/chain.evm.schema.json"


######################################################################
# extra="forbid"
######################################################################


def test_unknown_field_rejected(valid_mainnet_data: Dict[str, Any]) -> None:
    valid_mainnet_data["unknown_field"] = "noise"
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    check_model_error(exc, [{"type": "extra_forbidden", "loc": ("unknown_field",)}])


def test_unknown_field_rejected_in_nested_native_currency(valid_mainnet_data: Dict[str, Any]) -> None:
    valid_mainnet_data["native_currency"]["extra_key"] = "noise"
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    check_model_error(exc, [{"type": "extra_forbidden", "loc": ("native_currency", "extra_key")}])


######################################################################
# Field-level validation
######################################################################


def test_short_name_regex_rejects_invalid_chars(valid_mainnet_data: Dict[str, Any]) -> None:
    valid_mainnet_data["short_name"] = "zig chain"  # space invalid
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    check_model_error(exc, [{"type": "string_pattern_mismatch", "loc": ("short_name",)}])


def test_short_name_too_long_rejected(valid_mainnet_data: Dict[str, Any]) -> None:
    valid_mainnet_data["short_name"] = "a" * 65
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    # too-long short_name fails the pattern (which caps at 64) or max_length — both are valid signals
    actual_types = {e["type"] for e in exc.value.errors() if e["loc"] == ("short_name",)}
    assert actual_types & {"string_pattern_mismatch", "string_too_long"}, (
        f"expected pattern or length error, got {actual_types}"
    )


def test_chain_id_must_be_positive(valid_mainnet_data: Dict[str, Any]) -> None:
    valid_mainnet_data["chain_id"] = 0
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    check_model_error(exc, [{"type": "greater_than", "loc": ("chain_id",)}])


def test_chain_id_bool_rejected(valid_mainnet_data: Dict[str, Any]) -> None:
    valid_mainnet_data["chain_id"] = True
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    # rejected in mode=before validator with a ValueError → pydantic surfaces as value_error
    check_model_error(exc, [{"loc": ("chain_id",)}])


def test_is_verified_strict_bool(valid_mainnet_data: Dict[str, Any]) -> None:
    valid_mainnet_data["is_verified"] = 1  # int, not bool
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    check_model_error(exc, [{"loc": ("is_verified",)}])


def test_decimals_bounds_enforced(valid_mainnet_data: Dict[str, Any]) -> None:
    valid_mainnet_data["native_currency"]["decimals"] = 37  # > max 36
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    check_model_error(exc, [{"type": "less_than_equal", "loc": ("native_currency", "decimals")}])


def test_decimals_bool_rejected(valid_mainnet_data: Dict[str, Any]) -> None:
    valid_mainnet_data["native_currency"]["decimals"] = True
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    check_model_error(exc, [{"loc": ("native_currency", "decimals")}])


def test_status_enum_enforced(valid_mainnet_data: Dict[str, Any]) -> None:
    valid_mainnet_data["status"] = "live"  # not in enum
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    check_model_error(exc, [{"type": "literal_error", "loc": ("status",)}])


def test_explorer_standard_enum_enforced(valid_testnet_data: Dict[str, Any]) -> None:
    valid_testnet_data["explorers"][0]["standard"] = "EIP1234"
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_testnet_data)
    check_model_error(exc, [{"type": "literal_error", "loc": ("explorers", 0, "standard")}])


def test_chain_charset_rejected(valid_mainnet_data: Dict[str, Any]) -> None:
    valid_mainnet_data["chain"] = "ZIG!"
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    check_model_error(exc, [{"loc": ("chain",)}])


def test_rpc_empty_allowed_when_incubating(valid_mainnet_data: Dict[str, Any]) -> None:
    """Empty rpc[] is the chainId-locking pattern: register early to reserve the ID
    before EVM infra is deployed. See eip155-152 Redbelly Devnet for upstream precedent.
    """
    valid_mainnet_data["rpc"] = []
    valid_mainnet_data["status"] = "incubating"
    # Avoid the unrelated testnet-naming warning by giving it a non-testnet name
    valid_mainnet_data["name"] = "ZIGChain"
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        chain = EvmChain.model_validate(valid_mainnet_data)
    assert chain.rpc == []
    assert chain.status == "incubating"


def test_rpc_empty_warns_when_active(valid_mainnet_data: Dict[str, Any]) -> None:
    """Empty rpc[] + status='active' is almost certainly a mistake — warn loudly."""
    valid_mainnet_data["rpc"] = []
    # status defaults to "active"
    assert valid_mainnet_data.get("status", "active") == "active"
    with pytest.warns(UserWarning, match="status='active' but rpc.*empty"):
        EvmChain.model_validate(valid_mainnet_data)


def test_rpc_field_can_be_omitted_entirely(valid_mainnet_data: Dict[str, Any]) -> None:
    """rpc has a default of []; omitting the key entirely should not raise."""
    valid_mainnet_data.pop("rpc")
    valid_mainnet_data["status"] = "incubating"  # avoid the active+empty-rpc warning
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        chain = EvmChain.model_validate(valid_mainnet_data)
    assert chain.rpc == []


def test_rpc_rejects_tuple_not_list(valid_mainnet_data: Dict[str, Any]) -> None:
    valid_mainnet_data["rpc"] = ("https://evm-rpc.zigchain.com",)
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    check_model_error(exc, [{"loc": ("rpc",)}])


def test_invalid_rpc_url_rejected(valid_mainnet_data: Dict[str, Any]) -> None:
    valid_mainnet_data["rpc"] = ["not-a-url"]
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    check_model_error(exc, [{"loc": ("rpc", 0)}])


def test_icon_slug_pattern(valid_mainnet_data: Dict[str, Any]) -> None:
    """icon (slug for upstream icon submission) must be lowercase kebab/snake."""
    valid_mainnet_data["icon"] = "Has Spaces"
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    check_model_error(exc, [{"type": "string_pattern_mismatch", "loc": ("icon",)}])


######################################################################
# model_validator warnings (network_id divergence, testnet naming)
######################################################################


def test_network_id_divergence_warns(valid_mainnet_data: Dict[str, Any]) -> None:
    valid_mainnet_data["network_id"] = 999  # diverges from chain_id=944
    with pytest.warns(UserWarning, match="network_id .* != chain_id"):
        EvmChain.model_validate(valid_mainnet_data)


def test_network_id_equal_does_not_warn(valid_mainnet_data: Dict[str, Any]) -> None:
    """When network_id == chain_id (the normal case), no divergence warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        EvmChain.model_validate(valid_mainnet_data)  # would raise if any warning fired


def test_testnet_naming_warns_when_faucets_present_but_no_testnet_in_name(
    valid_mainnet_data: Dict[str, Any],
) -> None:
    """Testnet heuristic: has faucets but name lacks 'Testnet' → warn.

    Faucet presence is the testnet signal — status='incubating' alone is NOT a
    testnet signal (mainnet chains can reserve a chainId via incubating; see
    eip155-152 Redbelly Devnet).
    """
    valid_mainnet_data["faucets"] = ["https://faucet.zigchain.com"]
    # name remains "ZIGChain" — no 'Testnet' substring
    with pytest.warns(UserWarning, match="does not contain 'Testnet'"):
        EvmChain.model_validate(valid_mainnet_data)


def test_status_incubating_alone_does_not_trigger_testnet_naming_warning(
    valid_mainnet_data: Dict[str, Any],
) -> None:
    """A mainnet using status='incubating' to reserve a chainId before EVM infra is
    deployed must NOT trigger the testnet-naming warning. The trigger is faucet
    presence, not status."""
    valid_mainnet_data["status"] = "incubating"
    valid_mainnet_data["rpc"] = []  # also empty, the chainId-locking pattern
    valid_mainnet_data["faucets"] = []  # no faucets
    # name remains "ZIGChain" (no "Testnet") — should NOT warn
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        EvmChain.model_validate(valid_mainnet_data)


def test_testnet_with_correct_name_no_warning(valid_testnet_data: Dict[str, Any]) -> None:
    """A testnet whose name actually includes 'Testnet' should not warn."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        EvmChain.model_validate(valid_testnet_data)


def test_incubating_without_faucets_warns(valid_mainnet_data: Dict[str, Any]) -> None:
    """status=incubating without any faucet URL warns (testnets usually list a faucet)."""
    valid_mainnet_data["name"] = "ZIGChain Testnet"  # avoid testnet-naming warning
    valid_mainnet_data["status"] = "incubating"
    with pytest.warns(UserWarning, match="no faucets are configured"):
        EvmChain.model_validate(valid_mainnet_data)


######################################################################
# Required-field omission
######################################################################


@pytest.mark.parametrize(
    # rpc has a default of [] so omitting it no longer raises — see
    # test_rpc_field_can_be_omitted_entirely for that case.
    "missing_key",
    ["chain_id", "network_id", "name", "short_name", "chain", "native_currency", "info_url"],
)
def test_required_field_missing(valid_mainnet_data: Dict[str, Any], missing_key: str) -> None:
    valid_mainnet_data.pop(missing_key)
    with pytest.raises(ValidationError) as exc:
        EvmChain.model_validate(valid_mainnet_data)
    check_model_error(exc, [{"type": "missing", "loc": (missing_key,)}])

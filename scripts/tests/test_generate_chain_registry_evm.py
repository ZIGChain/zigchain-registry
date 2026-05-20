"""Tests for the EVM chain registry transform.

Scope: the pure function ``evm_chain_to_eip155_payload`` and the
``load_evm_chains`` helper. The sync-to-fork bash flow has its own
integration test (``test_evm_sync.sh``).
"""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from models import EvmChain
from scripts.generate_chain_registry import (
    evm_chain_to_eip155_payload,
    load_evm_chains,
)


######################################################################
# Fixtures
######################################################################


@pytest.fixture
def mainnet_chain() -> EvmChain:
    """A valid ZIGChain mainnet EvmChain with cosmos_chain_id + is_verified set."""
    return EvmChain.model_validate({
        "chain_id": 944,
        "network_id": 944,
        "name": "ZIGChain",
        "short_name": "zigchain",
        "chain": "ZIG",
        "native_currency": {"name": "ZIG", "symbol": "ZIG", "decimals": 18},
        "rpc": ["https://evm-rpc.zigchain.com"],
        "info_url": "https://zigchain.com",
        "explorers": [{
            "name": "ZIGChain Explorer",
            "url": "https://explorer.zigchain.com",
            "standard": "EIP3091",
        }],
        "cosmos_chain_id": "zigchain-1",
        "icon_path": "logos/zigchain.svg",
        "is_verified": True,
    })


@pytest.fixture
def testnet_chain() -> EvmChain:
    """A valid ZIGChain testnet EvmChain with faucets + status=incubating."""
    return EvmChain.model_validate({
        "chain_id": 2061,
        "network_id": 2061,
        "name": "ZIGChain Testnet",
        "short_name": "zigchain-testnet",
        "chain": "ZIG",
        "native_currency": {"name": "ZIG", "symbol": "ZIG", "decimals": 18},
        "rpc": ["https://evm-rpc-testnet.zigchain.com"],
        "faucets": ["https://faucet-testnet.zigchain.com"],
        "info_url": "https://zigchain.com",
        "explorers": [{
            "name": "ZIGChain Testnet Explorer",
            "url": "https://explorer-testnet.zigchain.com",
            "standard": "EIP3091",
        }],
        "status": "incubating",
        "cosmos_chain_id": "zig-test-2",
    })


######################################################################
# Transform: snake_case → camelCase
######################################################################


def test_camel_case_keys_emitted(mainnet_chain: EvmChain) -> None:
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    # Required camelCase keys for ethereum-lists/chains
    for key in ("chainId", "networkId", "shortName", "nativeCurrency", "infoURL"):
        assert key in payload, f"missing camelCase key: {key}"
    # And the snake_case originals must NOT appear
    for snake in ("chain_id", "network_id", "short_name", "native_currency", "info_url"):
        assert snake not in payload, f"raw snake_case key leaked: {snake}"


def test_chain_id_and_network_id_are_int(mainnet_chain: EvmChain) -> None:
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    assert payload["chainId"] == 944
    assert payload["networkId"] == 944
    assert isinstance(payload["chainId"], int)
    assert isinstance(payload["networkId"], int)


######################################################################
# Transform: repo-local extensions stripped
######################################################################


def test_cosmos_chain_id_stripped(mainnet_chain: EvmChain) -> None:
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    assert "cosmos_chain_id" not in payload
    assert "cosmosChainId" not in payload  # also not camelCased


def test_icon_path_stripped(mainnet_chain: EvmChain) -> None:
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    assert "icon_path" not in payload
    assert "iconPath" not in payload


def test_is_verified_stripped(mainnet_chain: EvmChain) -> None:
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    assert "is_verified" not in payload
    assert "isVerified" not in payload


def test_schema_ref_stripped() -> None:
    chain = EvmChain.model_validate({
        "$schema": "../../schemas/chain.evm.schema.json",
        "chain_id": 944,
        "network_id": 944,
        "name": "ZIGChain",
        "short_name": "zigchain",
        "chain": "ZIG",
        "native_currency": {"name": "ZIG", "symbol": "ZIG", "decimals": 18},
        "rpc": ["https://evm-rpc.zigchain.com"],
        "info_url": "https://zigchain.com",
    })
    payload = evm_chain_to_eip155_payload(chain)
    assert "$schema" not in payload
    assert "schema_ref" not in payload


######################################################################
# Transform: HttpUrl → str coercion
######################################################################


def test_rpc_emitted_as_strings(mainnet_chain: EvmChain) -> None:
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    assert all(isinstance(u, str) for u in payload["rpc"])
    # Roundtrip via json — pydantic HttpUrl is not JSON-serializable directly.
    json.dumps(payload)  # would raise if any value is non-serializable


def test_info_url_emitted_as_string(mainnet_chain: EvmChain) -> None:
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    assert isinstance(payload["infoURL"], str)
    assert payload["infoURL"].startswith("https://")


def test_explorer_url_emitted_as_string(mainnet_chain: EvmChain) -> None:
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    explorer = payload["explorers"][0]
    assert isinstance(explorer["url"], str)
    assert explorer["url"].startswith("https://")


def test_faucets_default_to_empty_list_in_payload(mainnet_chain: EvmChain) -> None:
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    assert payload["faucets"] == []


def test_testnet_faucets_emitted_as_strings(testnet_chain: EvmChain) -> None:
    payload = evm_chain_to_eip155_payload(testnet_chain)
    # pydantic HttpUrl normalises bare hosts with a trailing slash on str().
    # ethereum-lists accepts either form — match reality so tests don't lie.
    assert payload["faucets"] == ["https://faucet-testnet.zigchain.com/"]
    assert all(isinstance(u, str) for u in payload["faucets"])


######################################################################
# Transform: optional fields
######################################################################


def test_icon_omitted_when_unset(mainnet_chain: EvmChain) -> None:
    """When the upstream icon slug is unset, the key is dropped entirely (not emitted as null).

    ethereum-lists' chainSchema sets additionalProperties:false but also accepts
    icon as optional — omitting it is safer than emitting null.
    """
    assert mainnet_chain.icon is None
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    assert "icon" not in payload


def test_icon_emitted_when_set() -> None:
    chain = EvmChain.model_validate({
        "chain_id": 944,
        "network_id": 944,
        "name": "ZIGChain",
        "short_name": "zigchain",
        "chain": "ZIG",
        "icon": "zigchain",
        "native_currency": {"name": "ZIG", "symbol": "ZIG", "decimals": 18},
        "rpc": ["https://evm-rpc.zigchain.com"],
        "info_url": "https://zigchain.com",
    })
    payload = evm_chain_to_eip155_payload(chain)
    assert payload["icon"] == "zigchain"


def test_status_emitted_always(mainnet_chain: EvmChain, testnet_chain: EvmChain) -> None:
    """status has a default ("active") — always emit so the upstream record is explicit."""
    assert evm_chain_to_eip155_payload(mainnet_chain)["status"] == "active"
    assert evm_chain_to_eip155_payload(testnet_chain)["status"] == "incubating"


def test_explorers_omitted_when_unset() -> None:
    chain = EvmChain.model_validate({
        "chain_id": 944,
        "network_id": 944,
        "name": "ZIGChain",
        "short_name": "zigchain",
        "chain": "ZIG",
        "native_currency": {"name": "ZIG", "symbol": "ZIG", "decimals": 18},
        "rpc": ["https://evm-rpc.zigchain.com"],
        "info_url": "https://zigchain.com",
    })
    payload = evm_chain_to_eip155_payload(chain)
    assert "explorers" not in payload


def test_explorer_icon_omitted_when_unset(mainnet_chain: EvmChain) -> None:
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    assert "icon" not in payload["explorers"][0]


######################################################################
# Transform: payload shape vs ethereum-lists/chains conventions
######################################################################


def test_payload_only_camelcase_or_known_optionals(mainnet_chain: EvmChain) -> None:
    """Verify no surprise keys leak. Upstream schema is additionalProperties:false."""
    allowed = {
        "name", "chain", "icon", "rpc", "faucets", "nativeCurrency", "infoURL",
        "shortName", "chainId", "networkId", "slip44", "title", "status",
        "explorers", "features", "parent", "ens", "redFlags",
    }
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    extras = set(payload.keys()) - allowed
    assert not extras, f"unexpected keys in payload: {sorted(extras)}"


def test_native_currency_has_only_three_keys(mainnet_chain: EvmChain) -> None:
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    assert set(payload["nativeCurrency"].keys()) == {"name", "symbol", "decimals"}


def test_explorer_has_only_known_keys(mainnet_chain: EvmChain) -> None:
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    allowed = {"name", "url", "standard", "icon"}
    extras = set(payload["explorers"][0].keys()) - allowed
    assert not extras, f"unexpected keys in explorer: {sorted(extras)}"


def test_payload_round_trips_through_json(mainnet_chain: EvmChain) -> None:
    payload = evm_chain_to_eip155_payload(mainnet_chain)
    serialized = json.dumps(payload, indent=2)
    deserialized = json.loads(serialized)
    assert deserialized == payload  # idempotent


######################################################################
# load_evm_chains helper
######################################################################


def test_load_evm_chains_returns_empty_when_dir_missing(tmp_path: Path) -> None:
    """Graceful behavior when chains/evm/ does not exist."""
    # tmp_path has no chains/ subdir at all
    result = load_evm_chains(tmp_path)
    assert result == []


def test_load_evm_chains_returns_empty_when_dir_present_no_files(tmp_path: Path) -> None:
    (tmp_path / "chains" / "evm").mkdir(parents=True)
    result = load_evm_chains(tmp_path)
    assert result == []


def test_load_evm_chains_validates_each_file(tmp_path: Path) -> None:
    evm_dir = tmp_path / "chains" / "evm"
    evm_dir.mkdir(parents=True)
    payload: Dict[str, Any] = {
        "chain_id": 944,
        "network_id": 944,
        "name": "ZIGChain",
        "short_name": "zigchain",
        "chain": "ZIG",
        "native_currency": {"name": "ZIG", "symbol": "ZIG", "decimals": 18},
        "rpc": ["https://evm-rpc.zigchain.com"],
        "info_url": "https://zigchain.com",
    }
    (evm_dir / "zigchain-mainnet.json").write_text(json.dumps(payload))

    result = load_evm_chains(tmp_path)
    assert len(result) == 1
    assert isinstance(result[0], EvmChain)
    assert result[0].chain_id == 944


def test_load_evm_chains_raises_on_invalid_file(tmp_path: Path) -> None:
    """A malformed file should raise — surface validation errors loudly."""
    from pydantic import ValidationError

    evm_dir = tmp_path / "chains" / "evm"
    evm_dir.mkdir(parents=True)
    (evm_dir / "bad.json").write_text(json.dumps({"chain_id": -1}))  # missing required + invalid

    with pytest.raises(ValidationError):
        load_evm_chains(tmp_path)

"""Tests for the import_factory_assets script."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from models.factory import FactoryAsset
from models.native import DenomUnit
from scripts.import_factory_assets import (
    check_zigchaind,
    create_factory_asset,
    derive_metadata_from_subdenom,
    detect_collisions,
    detect_network,
    fetch_all_denoms,
    import_factory_assets,
    load_existing_factory_assets,
    main,
    normalize_display_denom,
    parse_denom,
    run_zigchaind_query,
    write_asset_file,
)


######################################################################
# Fixtures
######################################################################

CREATOR_A = "zig1mcvwss65nk0yl7mvh3d83vw48dq7ue20ey3aa790ku5a96dkk9kqldcx2z"
CREATOR_B = "zig1lp5zex6685kd22agzskhqsylpnssxnweyuvsz4edr4p4ta92qf3q0jdnz9"


@pytest.fixture
def factory_page_1() -> dict[str, Any]:
    """First page of factory denoms from zigchaind list-denom (has next_key for pagination)."""
    return {
        "denom": [
            {
                "denom": f"coin.{CREATOR_A}.mdfta",
                "creator": CREATOR_A,
                "can_change_minting_cap": True,
                "max_supply": "10000",
                "minting_cap": "10000",
                "total_burned": "0",
                "total_minted": "100",
                "total_supply": "100",
            },
            {
                "denom": f"coin.{CREATOR_B}.bunny",
                "creator": CREATOR_B,
                "can_change_minting_cap": True,
                "max_supply": "12300",
                "minting_cap": "12300",
                "total_burned": "0",
                "total_minted": "10",
                "total_supply": "10",
            },
        ],
        "pagination": {"next_key": "page2", "total": "4"},
    }


@pytest.fixture
def factory_page_2() -> dict[str, Any]:
    """Second page of factory denoms (next_key is None to stop pagination)."""
    creator_c = "zig1kt33w2ztud5duv0e6sc05y2xk046dtv4n8tfg38h4x2ryj5td9kq804928"
    return {
        "denom": [
            {
                "denom": f"coin.{creator_c}.oroswaplptoken",
                "creator": creator_c,
                "can_change_minting_cap": True,
                "max_supply": "200",
                "minting_cap": "200",
                "total_burned": "0",
                "total_minted": "1",
                "total_supply": "1",
            },
        ],
        "pagination": {"next_key": None, "total": "4"},
    }


@pytest.fixture
def valid_factory_asset() -> FactoryAsset:
    """A valid FactoryAsset instance for use in write/load/collision tests."""
    base_denom = f"coin.{CREATOR_A}.mdfta"
    return FactoryAsset.model_validate({
        "network": "mainnet",
        "asset_id": base_denom,
        "type": "factory",
        "symbol": "MDFTA",
        "name": "Mdfta",
        "decimals": 6,
        "display_denom": "MDFTA",
        "base_denom": base_denom,
        "creator": CREATOR_A,
        "subdenom": "mdfta",
        "denom_units": [{"denom": base_denom, "exponent": 0}],
    })


@pytest.fixture
def valid_factory_asset_b() -> FactoryAsset:
    """A second valid FactoryAsset (different creator/subdenom) for collision tests."""
    base_denom = f"coin.{CREATOR_B}.bunny"
    return FactoryAsset.model_validate({
        "network": "mainnet",
        "asset_id": base_denom,
        "type": "factory",
        "symbol": "BUNNY",
        "name": "Bunny",
        "decimals": 6,
        "display_denom": "BUNNY",
        "base_denom": base_denom,
        "creator": CREATOR_B,
        "subdenom": "bunny",
        "denom_units": [{"denom": base_denom, "exponent": 0}],
    })


@pytest.fixture
def patch_get_rpc_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch get_rpc_endpoint so tests don't depend on real chain config."""
    monkeypatch.setattr(
        "scripts.import_factory_assets.get_rpc_endpoint",
        lambda network: "https://rpc.example.com:443",
    )



######################################################################
# Tests for load_existing_factory_assets
######################################################################

# ----------------
# Positive tests for load_existing_factory_assets
# ----------------

def test_load_existing_factory_assets_loads_valid_files(
    tmp_path: Path,
    valid_factory_asset: FactoryAsset,
) -> None:
    """load_existing_factory_assets loads valid JSON files into network→asset_id→FactoryAsset dict."""
    # Arrange: write a valid factory asset file
    assets_dir = tmp_path / "assets" / "factory"
    assets_dir.mkdir(parents=True)
    file_path = assets_dir / f"{valid_factory_asset.asset_id}.mainnet.json"
    asset_dict = valid_factory_asset.model_dump(mode="json", exclude_none=True)
    file_path.write_text(json.dumps(asset_dict, indent=2), encoding="utf-8")

    # Act
    result = load_existing_factory_assets(tmp_path)

    # Assert: asset loaded under correct network and asset_id
    assert valid_factory_asset.asset_id in result["mainnet"]
    loaded = result["mainnet"][valid_factory_asset.asset_id]
    assert loaded.creator == valid_factory_asset.creator


def test_load_existing_factory_assets_returns_empty_when_dir_missing(
    tmp_path: Path,
) -> None:
    """load_existing_factory_assets returns empty dicts when assets/factory/ doesn't exist."""
    # Act: no assets/factory/ directory
    result = load_existing_factory_assets(tmp_path)

    # Assert: both networks empty
    assert result == {"mainnet": {}, "testnet": {}}


def test_load_existing_factory_assets_returns_empty_when_dir_is_empty(
    tmp_path: Path,
) -> None:
    """load_existing_factory_assets returns empty dicts when assets/factory/ has no JSON files."""
    # Arrange: create empty directory
    (tmp_path / "assets" / "factory").mkdir(parents=True)

    # Act
    result = load_existing_factory_assets(tmp_path)

    # Assert
    assert result == {"mainnet": {}, "testnet": {}}


def test_load_existing_factory_assets_skips_symlinks(
    tmp_path: Path,
    valid_factory_asset: FactoryAsset,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Symlinks inside assets/factory/ are rejected — blocks arbitrary file-read via PR-supplied symlinks."""
    # Arrange: one valid factory asset file + one symlink to an outside file.
    assets_dir = tmp_path / "assets" / "factory"
    assets_dir.mkdir(parents=True)
    asset_dict = valid_factory_asset.model_dump(mode="json", exclude_none=True)
    real_path = assets_dir / f"{valid_factory_asset.asset_id}.mainnet.json"
    real_path.write_text(json.dumps(asset_dict, indent=2), encoding="utf-8")

    outside_file = tmp_path.parent / "outside.json"
    outside_file.write_text(json.dumps(asset_dict), encoding="utf-8")
    symlink_path = assets_dir / "evil.json"
    symlink_path.symlink_to(outside_file)

    # Act
    result = load_existing_factory_assets(tmp_path)

    # Assert: the real asset loaded; the symlink was skipped with a stderr warning.
    assert valid_factory_asset.asset_id in result["mainnet"]
    assert "skipping symlink" in capsys.readouterr().err


def test_load_existing_factory_assets_pops_schema_before_validate(
    tmp_path: Path,
    valid_factory_asset: FactoryAsset,
) -> None:
    """load_existing_factory_assets strips $schema before Pydantic validation (extra=forbid would reject it)."""
    # Arrange: write file with $schema key
    assets_dir = tmp_path / "assets" / "factory"
    assets_dir.mkdir(parents=True)
    asset_dict = valid_factory_asset.model_dump(mode="json", exclude_none=True)
    asset_dict["$schema"] = "../../schemas/asset.factory.schema.json"
    file_path = assets_dir / "with-schema.json"
    file_path.write_text(json.dumps(asset_dict, indent=2), encoding="utf-8")

    # Act
    result = load_existing_factory_assets(tmp_path)

    # Assert: loaded successfully despite $schema in file
    assert valid_factory_asset.asset_id in result["mainnet"]


def test_load_existing_factory_assets_groups_by_network(
    tmp_path: Path,
    valid_factory_asset: FactoryAsset,
) -> None:
    """Assets are grouped by their network field (mainnet and testnet in separate dicts)."""
    # Arrange: write one mainnet asset and one testnet asset
    assets_dir = tmp_path / "assets" / "factory"
    assets_dir.mkdir(parents=True)

    mainnet_dict = valid_factory_asset.model_dump(mode="json", exclude_none=True)
    (assets_dir / "mainnet.json").write_text(json.dumps(mainnet_dict, indent=2), encoding="utf-8")

    testnet_asset = valid_factory_asset.model_copy(update={"network": "testnet"})
    testnet_dict = testnet_asset.model_dump(mode="json", exclude_none=True)
    (assets_dir / "testnet.json").write_text(json.dumps(testnet_dict, indent=2), encoding="utf-8")

    # Act
    result = load_existing_factory_assets(tmp_path)

    # Assert: same asset_id appears under both networks
    assert valid_factory_asset.asset_id in result["mainnet"]
    assert valid_factory_asset.asset_id in result["testnet"]

# ----------------
# Negative tests for load_existing_factory_assets
# ----------------

def test_load_existing_factory_assets_warns_and_skips_corrupt_file(
    tmp_path: Path,
    valid_factory_asset: FactoryAsset,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Corrupt files are skipped with a warning; valid files still load."""
    # Arrange: one valid file, one corrupt file
    assets_dir = tmp_path / "assets" / "factory"
    assets_dir.mkdir(parents=True)

    valid_dict = valid_factory_asset.model_dump(mode="json", exclude_none=True)
    (assets_dir / "good.json").write_text(json.dumps(valid_dict, indent=2), encoding="utf-8")
    (assets_dir / "bad.json").write_text("{ broken json", encoding="utf-8")

    # Act
    result = load_existing_factory_assets(tmp_path)

    # Assert: valid file loaded, warning printed for corrupt file
    assert valid_factory_asset.asset_id in result["mainnet"]
    err = capsys.readouterr().err
    assert "Warning: failed to load existing factory asset" in err
    assert "bad.json" in err


def test_load_existing_factory_assets_warns_and_skips_invalid_pydantic_data(
    tmp_path: Path,
    valid_factory_asset: FactoryAsset,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Valid JSON but invalid Pydantic data is skipped with a warning."""
    # Arrange: one valid file, one with valid JSON but missing required fields
    assets_dir = tmp_path / "assets" / "factory"
    assets_dir.mkdir(parents=True)

    valid_dict = valid_factory_asset.model_dump(mode="json", exclude_none=True)
    (assets_dir / "good.json").write_text(json.dumps(valid_dict, indent=2), encoding="utf-8")
    (assets_dir / "invalid.json").write_text(
        json.dumps({"type": "factory", "network": "mainnet"}, indent=2), encoding="utf-8"
    )

    # Act
    result = load_existing_factory_assets(tmp_path)

    # Assert: valid file loaded, warning printed for invalid Pydantic data
    assert valid_factory_asset.asset_id in result["mainnet"]
    err = capsys.readouterr().err
    assert "Warning: failed to load existing factory asset" in err
    assert "invalid.json" in err



######################################################################
# Tests for detect_collisions
######################################################################

def test_detect_collisions_no_collisions_returns_empty(
    valid_factory_asset: FactoryAsset,
    valid_factory_asset_b: FactoryAsset,
) -> None:
    """When no two assets share a display_denom, returns empty collision groups."""
    # Arrange: two assets with different display_denoms (MDFTA vs BUNNY)
    by_network = {
        "mainnet": {
            valid_factory_asset.asset_id: valid_factory_asset,
            valid_factory_asset_b.asset_id: valid_factory_asset_b,
        }
    }

    # Act
    result = detect_collisions(by_network)

    # Assert: no collisions
    assert result["mainnet"] == {}


def test_detect_collisions_two_assets_same_display_denom(
    valid_factory_asset: FactoryAsset,
    valid_factory_asset_b: FactoryAsset,
) -> None:
    """Two assets with the same display_denom are grouped as a collision."""
    # Arrange: force both to same display_denom
    asset_b = valid_factory_asset_b.model_copy(update={"display_denom": "MDFTA"})
    by_network = {
        "mainnet": {
            valid_factory_asset.asset_id: valid_factory_asset,
            asset_b.asset_id: asset_b,
        }
    }

    # Act
    result = detect_collisions(by_network)

    # Assert: one collision group with 2 assets
    assert "mdfta" in result["mainnet"]
    assert len(result["mainnet"]["mdfta"]) == 2


def test_detect_collisions_case_insensitive(
    valid_factory_asset: FactoryAsset,
    valid_factory_asset_b: FactoryAsset,
) -> None:
    """Collision detection is case-insensitive (MDFTA and mdfta collide)."""
    # Arrange: one uppercase, one with base_denom as display (contains lowercase)
    asset_b = valid_factory_asset_b.model_copy(update={"display_denom": "mdfta"})
    by_network = {
        "mainnet": {
            valid_factory_asset.asset_id: valid_factory_asset,  # display_denom="MDFTA"
            asset_b.asset_id: asset_b,  # display_denom="mdfta"
        }
    }

    # Act
    result = detect_collisions(by_network)

    # Assert: grouped under same lowercase key
    assert "mdfta" in result["mainnet"]
    assert len(result["mainnet"]["mdfta"]) == 2



######################################################################
# Tests for normalize_display_denom
######################################################################


def test_normalize_display_denom_no_collision_verified_keeps_display(
    valid_factory_asset: FactoryAsset,
) -> None:
    """Verified asset with no collision keeps its display_denom."""
    # Arrange: mark as verified
    asset = valid_factory_asset.model_copy(update={"is_verified": True})

    # Act
    display, units = normalize_display_denom(asset=asset, collision_group=None)

    # Assert: keeps original display_denom
    assert display == asset.display_denom


def test_normalize_display_denom_no_collision_unverified_uses_base(
    valid_factory_asset: FactoryAsset,
) -> None:
    """Unverified asset with no collision uses base_denom as display."""
    # Arrange: unverified (default)
    asset = valid_factory_asset

    # Act
    display, units = normalize_display_denom(asset=asset, collision_group=None)

    # Assert: falls back to base_denom
    assert display == asset.base_denom


def test_normalize_display_denom_collision_verified_keeps_display(
    valid_factory_asset: FactoryAsset,
    valid_factory_asset_b: FactoryAsset,
) -> None:
    """In a collision group, the one verified asset keeps its display_denom."""
    # Arrange: asset A is verified, asset B is not; both in collision group
    asset_a = valid_factory_asset.model_copy(update={"is_verified": True})
    group = [asset_a, valid_factory_asset_b]

    # Act
    display, units = normalize_display_denom(asset=asset_a, collision_group=group)

    # Assert: verified keeps friendly name, unverified gets demoted to base_denom
    assert display == asset_a.display_denom                                      # "MDFTA"
    display_b, _ = normalize_display_denom(asset=valid_factory_asset_b, collision_group=group)
    assert display != display_b                                                  # "MDFTA" != "coin.zig1...bunny"
    assert display_b == valid_factory_asset_b.base_denom                         # "coin.zig1...bunny"


def test_normalize_display_denom_collision_unverified_uses_base(
    valid_factory_asset: FactoryAsset,
    valid_factory_asset_b: FactoryAsset,
) -> None:
    """In a collision group, unverified assets use base_denom."""
    # Arrange: asset A is verified, asset B (target) is not
    asset_a = valid_factory_asset.model_copy(update={"is_verified": True})
    group = [asset_a, valid_factory_asset_b]

    # Act: normalize the unverified asset
    display, units = normalize_display_denom(asset=valid_factory_asset_b, collision_group=group)

    # Assert: unverified uses base_denom
    assert display == valid_factory_asset_b.base_denom


def test_normalize_display_denom_collision_all_unverified_uses_base(
    valid_factory_asset: FactoryAsset,
    valid_factory_asset_b: FactoryAsset,
) -> None:
    """When all assets in a collision group are unverified, all use base_denom."""
    # Arrange: neither verified
    group = [valid_factory_asset, valid_factory_asset_b]

    # Act
    display, units = normalize_display_denom(asset=valid_factory_asset, collision_group=group)

    # Assert: all-unverified scenario C → base_denom
    assert display == valid_factory_asset.base_denom


def test_normalize_display_denom_always_returns_single_base_unit(
    valid_factory_asset: FactoryAsset,
) -> None:
    """normalize_display_denom always returns a single denom_unit (base at exponent 0)."""
    # Act
    display, units = normalize_display_denom(asset=valid_factory_asset, collision_group=None)

    # Assert: minimal denom_units
    assert len(units) == 1
    assert units[0].denom == valid_factory_asset.base_denom
    assert units[0].exponent == 0


######################################################################
# Tests for detect_network
######################################################################


@pytest.mark.parametrize(
    "chain_id,expected",
    [
        ("zig-test-2", "testnet"),
        ("zigchain-1", "mainnet"),
        ("", "mainnet"),
        ("  zig-test-2  ", "testnet"),
        ("unknown", "mainnet"),
    ],
    ids=["testnet", "mainnet", "empty-defaults-mainnet", "strip-whitespace", "unknown-defaults-mainnet"],
)
def test_detect_network(
    chain_id: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """detect_network returns testnet or mainnet based on ZIGCHAIN_CHAIN_ID env var."""
    # Arrange: set env var
    monkeypatch.setenv("ZIGCHAIN_CHAIN_ID", chain_id)

    # Act
    result = detect_network()

    # Assert
    assert result == expected


def test_detect_network_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """detect_network defaults to mainnet when ZIGCHAIN_CHAIN_ID is not set."""
    # Arrange: ensure env var is absent
    monkeypatch.delenv("ZIGCHAIN_CHAIN_ID", raising=False)

    # Act
    result = detect_network()

    # Assert
    assert result == "mainnet"



######################################################################
# Tests for run_zigchaind_query
######################################################################

# ----------------
# Positive tests for run_zigchaind_query
# ----------------

def test_run_zigchaind_query_returns_parsed_dict(
    patch_get_rpc_endpoint: None,
    monkeypatch: pytest.MonkeyPatch,
    factory_page_1: dict[str, Any],
) -> None:
    """Valid zigchaind output is parsed and returned as a dict."""
    # Arrange: simulate successful zigchaind CLI returning JSON
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(factory_page_1))

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Act
    result = run_zigchaind_query("zigchaind", "mainnet")

    # Assert: parsed response matches fixture data
    assert isinstance(result, dict)
    assert len(result["denom"]) == len(factory_page_1["denom"])
    assert result["denom"][0]["denom"] == factory_page_1["denom"][0]["denom"]


def test_run_zigchaind_query_passes_page_key_in_command(
    patch_get_rpc_endpoint: None,
    monkeypatch: pytest.MonkeyPatch,
    factory_page_1: dict[str, Any],
) -> None:
    """When page_key is provided, --page-key flag is appended to the command."""
    # Arrange: capture the command that subprocess.run receives
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=json.dumps(factory_page_1))

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Act
    run_zigchaind_query("zigchaind", "mainnet", page_key="abc123")

    # Assert: --page-key and its value present in the command
    assert "--page-key" in captured_cmd
    assert "abc123" in captured_cmd


# ----------------
# Negative tests for run_zigchaind_query
# ----------------

def test_run_zigchaind_query_reraises_subprocess_failure(
    patch_get_rpc_endpoint: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Subprocess failures are logged to stderr and re-raised."""
    # Arrange: simulate zigchaind failing
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=["zigchaind", "q"], stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Act + Assert
    with pytest.raises(subprocess.CalledProcessError):
        run_zigchaind_query("zigchaind", "mainnet")

    # Assert: error details printed to stderr
    err = capsys.readouterr().err
    assert "Error executing zigchaind command" in err
    assert "Error output: boom" in err


def test_run_zigchaind_query_subprocess_failure_no_stderr(
    patch_get_rpc_endpoint: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When subprocess fails with no stderr, 'Error output' line is not printed."""
    # Arrange: CalledProcessError with empty stderr
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=["zigchaind", "q"], stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Act + Assert
    with pytest.raises(subprocess.CalledProcessError):
        run_zigchaind_query("zigchaind", "mainnet")

    # Assert: error logged but no "Error output" line (stderr is empty/falsy)
    err = capsys.readouterr().err
    assert "Error executing zigchaind command" in err
    assert "Error output" not in err


def test_run_zigchaind_query_reraises_invalid_json(
    patch_get_rpc_endpoint: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Invalid JSON output triggers a parsing error with diagnostics on stderr."""
    # Arrange: simulate zigchaind returning malformed JSON
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="{ broken json")

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Act + Assert
    with pytest.raises(json.JSONDecodeError):
        run_zigchaind_query("zigchaind", "mainnet")

    # Assert: error context printed to stderr
    err = capsys.readouterr().err
    assert "Error parsing JSON response" in err




######################################################################
# Tests for fetch_all_denoms
######################################################################

# ----------------
# Positive tests for fetch_all_denoms
# ----------------

def test_fetch_all_denoms_aggregates_multiple_pages(
    monkeypatch: pytest.MonkeyPatch,
    factory_page_1: dict[str, Any],
    factory_page_2: dict[str, Any],
) -> None:
    """Denoms from multiple pages are combined into one list."""
    # Arrange: two pages
    responses = iter([factory_page_1, factory_page_2])
    monkeypatch.setattr(
        "scripts.import_factory_assets.run_zigchaind_query",
        lambda *a, **kw: next(responses),
    )

    # Act
    denoms = fetch_all_denoms("zigchaind", "mainnet")

    # Assert: all denoms from both pages
    assert len(denoms) == len(factory_page_1["denom"]) + len(factory_page_2["denom"])


def test_fetch_all_denoms_uses_next_key_for_pagination(
    monkeypatch: pytest.MonkeyPatch,
    factory_page_1: dict[str, Any],
    factory_page_2: dict[str, Any],
) -> None:
    """Second request uses next_key from the first page's pagination response."""
    # Arrange: track page_key per call
    responses = iter([factory_page_1, factory_page_2])
    page_keys: list[str | None] = []

    def fake_query(zigchaind_path, network, page_key=None):
        page_keys.append(page_key)
        return next(responses)

    monkeypatch.setattr("scripts.import_factory_assets.run_zigchaind_query", fake_query)

    # Act
    fetch_all_denoms("zigchaind", "mainnet")

    # Assert: first call has no key, second uses page1's next_key
    assert page_keys[0] is None
    assert page_keys[1] == factory_page_1["pagination"]["next_key"]


def test_fetch_all_denoms_prints_progress(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    factory_page_1: dict[str, Any],
    factory_page_2: dict[str, Any],
) -> None:
    """Progress messages show per-page and total counts."""
    # Arrange
    responses = iter([factory_page_1, factory_page_2])
    monkeypatch.setattr(
        "scripts.import_factory_assets.run_zigchaind_query",
        lambda *a, **kw: next(responses),
    )

    # Act
    fetch_all_denoms("zigchaind", "mainnet")

    # Assert: start, per-page, and final messages
    out = capsys.readouterr().out
    n1 = len(factory_page_1["denom"])
    n2 = len(factory_page_2["denom"])
    total = n1 + n2
    assert "Fetching factory denoms from mainnet..." in out
    assert f"Fetched {n1} denoms (total: {n1})" in out
    assert f"Fetched {n2} denoms (total: {total})" in out
    assert f"Total denoms fetched: {total}" in out


def test_fetch_all_denoms_stops_when_denoms_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loop breaks immediately when response has empty denom list."""
    # Arrange: response with empty denom array
    def fake_query(zigchaind_path, network, page_key=None):
        return {"denom": [], "pagination": {"next_key": "should-not-be-used"}}

    monkeypatch.setattr("scripts.import_factory_assets.run_zigchaind_query", fake_query)

    # Act
    denoms = fetch_all_denoms("zigchaind", "mainnet")

    # Assert: empty result, loop stopped before using next_key
    assert denoms == []


def test_fetch_all_denoms_stops_when_next_key_missing(
    monkeypatch: pytest.MonkeyPatch,
    factory_page_2: dict[str, Any],
) -> None:
    """Loop terminates after one page when next_key is None."""
    # Arrange: single page with next_key=None
    call_count = 0

    # Track how many times the query is called; factory_page_2 has next_key=None
    def fake_query(zigchaind_path, network, page_key=None):
        nonlocal call_count
        call_count += 1
        return factory_page_2

    monkeypatch.setattr("scripts.import_factory_assets.run_zigchaind_query", fake_query)

    # Act
    denoms = fetch_all_denoms("zigchaind", "mainnet")

    # Assert: only one call, got all denoms from that page
    assert call_count == 1
    assert len(denoms) == len(factory_page_2["denom"])


# ----------------
# Negative tests for fetch_all_denoms
# ----------------

def test_fetch_all_denoms_reraises_and_logs_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    factory_page_1: dict[str, Any],
) -> None:
    """Errors during pagination are logged to stderr and re-raised."""
    # Arrange: first page ok, second call raises
    responses = iter([factory_page_1, Exception("boom")])

    # First call returns page data normally; second call raises the Exception
    def fake_query(zigchaind_path, network, page_key=None):
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("scripts.import_factory_assets.run_zigchaind_query", fake_query)

    # Act + Assert
    with pytest.raises(Exception, match="boom"):
        fetch_all_denoms("zigchaind", "mainnet")

    assert "Error fetching denoms: boom" in capsys.readouterr().err


######################################################################
# Tests for parse_denom
######################################################################

# ----------------
# Positive tests for parse_denom
# ----------------

@pytest.mark.parametrize(
    "denom,expected_creator,expected_subdenom",
    [
        (f"coin.{CREATOR_A}.mdfta", CREATOR_A, "mdfta"),
        ("coin.zig1abc123.def-ghi", "zig1abc123", "def-ghi"),
    ],
)
def test_parse_denom_valid(
    denom: str,
    expected_creator: str,
    expected_subdenom: str,
) -> None:
    """Valid denom strings return (creator, subdenom)."""
    # Act
    creator, subdenom = parse_denom(denom)

    # Assert
    assert creator == expected_creator
    assert subdenom == expected_subdenom


# ----------------
# Negative tests for parse_denom
# ----------------

@pytest.mark.parametrize(
    "bad_denom",
    [
        "coin.qa123",
        "coin.zig1abc123",
        "coin.zig1ABC123.mdfta",
        "coin.zig1abc123.mdfta!",
        "zig1abc123.mdfta",
        "",
        "coin..mdfta",
        "coin.zig1abc123.",
        "coin.zig1abc123.UPPERCASE",
    ],
    ids=[
        "missing-creator-subdenom",
        "missing-subdenom",
        "uppercase-creator",
        "invalid-char-exclamation",
        "missing-coin-prefix",
        "empty",
        "empty-creator",
        "empty-subdenom",
        "uppercase-subdenom",
    ],
)
def test_parse_denom_invalid_raises_error(bad_denom: str) -> None:
    """Invalid denom strings raise ValueError with format hint."""
    # Act + Assert
    with pytest.raises(ValueError) as exc:
        parse_denom(bad_denom)

    assert exc.value.args[0] == f"Invalid denom format: {bad_denom}. Expected format: coin.{{creator}}.{{subdenom}}"


######################################################################
# Tests for derive_metadata_from_subdenom
######################################################################

@pytest.mark.parametrize(
    "subdenom,expected_symbol,expected_name,expected_display",
    [
        ("mdfta", "MDFTA", "Mdfta", "MDFTA"),
        ("bunny", "BUNNY", "Bunny", "BUNNY"),
        ("oroswaplptoken", "OROSWAPLPTOKEN", "Oroswaplptoken", "OROSWAPLPTOKEN"),
        ("abc-def", "ABC-DEF", "Abc-def", "ABC-DEF"),
    ],
    ids=["lowercase", "short", "long", "hyphenated"],
)
def test_derive_metadata_from_subdenom(
    subdenom: str,
    expected_symbol: str,
    expected_name: str,
    expected_display: str,
) -> None:
    """derive_metadata_from_subdenom returns symbol (upper), name (capitalized), display_denom (upper)."""
    # Act
    result = derive_metadata_from_subdenom(subdenom)

    # Assert: all three derived fields
    assert result == {
        "symbol": expected_symbol,
        "name": expected_name,
        "display_denom": expected_display,
    }


######################################################################
# Tests for create_factory_asset
######################################################################

# ----------------
# Positive tests for create_factory_asset
# ----------------

def test_create_factory_asset_success(factory_page_1: dict[str, Any]) -> None:
    """create_factory_asset returns a valid FactoryAsset with correct identifiers."""
    # Arrange: first denom from fixture (mdfta)
    denom_data = factory_page_1["denom"][0]

    # Act
    asset = create_factory_asset(denom_data, network="mainnet")

    # Assert: valid FactoryAsset with correct fields
    assert isinstance(asset, FactoryAsset)
    assert asset.network == "mainnet"
    assert asset.type == "factory"
    assert asset.creator == CREATOR_A
    assert asset.subdenom == "mdfta"
    assert asset.base_denom == f"coin.{CREATOR_A}.mdfta"
    assert asset.asset_id == asset.base_denom
    assert asset.description is None


def test_create_factory_asset_derives_metadata(factory_page_1: dict[str, Any]) -> None:
    """create_factory_asset derives symbol, name, display_denom from subdenom."""
    # Arrange: second denom from fixture (bunny)
    denom_data = factory_page_1["denom"][1]

    # Act
    asset = create_factory_asset(denom_data, network="mainnet")

    # Assert: metadata derived from "bunny"
    assert asset.symbol == "BUNNY"
    assert asset.name == "Bunny"
    assert asset.display_denom == "BUNNY"


def test_create_factory_asset_denom_units_minimal(factory_page_1: dict[str, Any]) -> None:
    """create_factory_asset creates a single denom_unit (base only, exponent 0)."""
    # Arrange
    denom_data = factory_page_1["denom"][0]

    # Act
    asset = create_factory_asset(denom_data, network="mainnet")

    # Assert: only base unit, decimals=6
    assert asset.decimals == 6
    assert len(asset.denom_units) == 1
    assert asset.denom_units[0].denom == asset.base_denom
    assert asset.denom_units[0].exponent == 0


def test_create_factory_asset_creator_missing_uses_parsed(factory_page_1: dict[str, Any]) -> None:
    """When creator field is absent, create_factory_asset infers it from the denom string."""
    # Arrange: remove creator key
    denom_data = dict(factory_page_1["denom"][0])
    del denom_data["creator"]

    # Act
    asset = create_factory_asset(denom_data, network="mainnet")

    # Assert: creator parsed from denom string
    assert asset.creator == CREATOR_A
    assert asset.creator in asset.base_denom


# ----------------
# Negative tests for create_factory_asset
# ----------------

@pytest.mark.parametrize(
    "bad_denom",
    [
        "coin.badformat",
        "coin.zig1abc",
        "zig1abc.subdenom",
        "coin..subdenom",
        "coin.zig1abc.",
        "",
    ],
    ids=["no-creator-subdenom", "missing-subdenom", "missing-coin", "empty-creator", "empty-subdenom", "empty"],
)
def test_create_factory_asset_invalid_denom_raises(bad_denom: str) -> None:
    """create_factory_asset raises ValueError when denom format is invalid."""
    # Arrange
    bad = {"denom": bad_denom, "creator": "zig1abc"}

    # Act + Assert
    with pytest.raises(ValueError) as exc:
        create_factory_asset(bad, network="mainnet")

    assert "Invalid denom format" in str(exc.value)


def test_create_factory_asset_creator_mismatch_warns(
    factory_page_1: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """create_factory_asset prints a warning to stderr when parsed and provided creators differ."""
    # Arrange: set creator to a different address than what's in the denom
    denom_data = dict(factory_page_1["denom"][0])
    wrong_creator = CREATOR_B
    denom_data["creator"] = wrong_creator

    # Act
    asset = create_factory_asset(denom_data, network="mainnet")

    # Assert: warning printed, asset uses data creator (not parsed)
    err = capsys.readouterr().err
    assert f"Warning: Creator mismatch for {denom_data['denom']}: parsed={CREATOR_A}, data={wrong_creator}" == err.strip()
    assert asset.creator == wrong_creator


def test_create_factory_asset_invalid_network_raises(factory_page_1: dict[str, Any]) -> None:
    """create_factory_asset raises when an unsupported network is provided (Pydantic rejects it)."""
    # Arrange
    denom_data = factory_page_1["denom"][0]

    # Act + Assert: Pydantic validation fails on network field
    with pytest.raises(Exception):
        create_factory_asset(denom_data, network="devnet")


######################################################################
# Tests for write_asset_file
######################################################################

# ----------------
# Positive tests for write_asset_file
# ----------------

def test_write_asset_file_creates_json_with_schema_ref(
    tmp_path: Path,
    valid_factory_asset: FactoryAsset,
) -> None:
    """write_asset_file writes JSON with $schema ref and trailing newline."""
    # Arrange
    output_path = tmp_path / "assets" / "factory" / f"{valid_factory_asset.asset_id}.mainnet.json"

    # Act
    result = write_asset_file(valid_factory_asset, output_path, overwrite=False)

    # Assert: write succeeded and file exists on disk
    assert result is True
    assert output_path.exists()
    # Assert: file ends with trailing newline
    content = output_path.read_text(encoding="utf-8")
    assert content.endswith("\n")
    # Assert: JSON content has $schema ref and matches the asset's fields
    data = json.loads(content)
    assert data["$schema"] == "../../schemas/asset.factory.schema.json"
    assert data["asset_id"] == valid_factory_asset.asset_id
    assert data["creator"] == valid_factory_asset.creator


def test_write_asset_file_overwrites_when_enabled(
    tmp_path: Path,
    valid_factory_asset: FactoryAsset,
) -> None:
    """Existing file is overwritten when overwrite=True."""
    # Arrange: create existing file
    output_path = tmp_path / "assets" / "factory" / "old.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text('{"old": true}\n', encoding="utf-8")

    # Act
    result = write_asset_file(valid_factory_asset, output_path, overwrite=True)

    # Assert: overwritten with new content
    assert result is True
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert "old" not in data
    assert data["asset_id"] == valid_factory_asset.asset_id


def test_write_asset_file_excludes_none_fields(
    tmp_path: Path,
    valid_factory_asset: FactoryAsset,
) -> None:
    """write_asset_file uses exclude_none=True so None fields are absent from the JSON."""
    # Arrange: asset has description=None, uri=None, etc.
    output_path = tmp_path / "asset.json"

    # Act
    write_asset_file(valid_factory_asset, output_path, overwrite=False)

    # Assert: None fields not present in JSON output
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert "description" not in data
    assert "uri" not in data
    assert "uri_hash" not in data


def test_write_asset_file_creates_parent_directories(
    tmp_path: Path,
    valid_factory_asset: FactoryAsset,
) -> None:
    """write_asset_file creates parent directories if they don't exist."""
    # Arrange: deeply nested path with no pre-existing dirs
    output_path = tmp_path / "new" / "deep" / "path" / "asset.json"
    assert not output_path.parent.exists()

    # Act
    result = write_asset_file(valid_factory_asset, output_path, overwrite=False)

    # Assert: directories created and file written
    assert result is True
    assert output_path.exists()


# ----------------
# Negative tests for write_asset_file
# ----------------

def test_write_asset_file_returns_false_when_exists_and_no_overwrite(
    tmp_path: Path,
    valid_factory_asset: FactoryAsset,
) -> None:
    """When file exists and overwrite=False, returns False and leaves file unchanged."""
    # Arrange: create existing file with known content
    output_path = tmp_path / "asset.json"
    original_content = '{"keep": "me"}\n'
    output_path.write_text(original_content, encoding="utf-8")

    # Act
    result = write_asset_file(valid_factory_asset, output_path, overwrite=False)

    # Assert: not overwritten
    assert result is False
    assert output_path.read_text(encoding="utf-8") == original_content


######################################################################
# Tests for import_factory_assets
######################################################################

# ----------------
# Positive tests for import_factory_assets
# ----------------

def test_import_factory_assets_creates_files_and_returns_counts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    factory_page_1: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """import_factory_assets creates files for all denoms and returns (created, skipped)."""
    # Arrange: mock only fetch_all_denoms (everything else runs for real)
    monkeypatch.setattr(
        "scripts.import_factory_assets.fetch_all_denoms",
        lambda *a, **kw: factory_page_1["denom"],
    )

    # Act
    created, skipped = import_factory_assets("zigchaind", "mainnet", tmp_path, overwrite=False)

    # Assert: both denoms created
    assert created == 2
    assert skipped == 0
    out = capsys.readouterr().out
    assert "Processing 2 denoms..." in out
    assert "Created: 2" in out


def test_import_factory_assets_skips_existing_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    factory_page_1: dict[str, Any],
) -> None:
    """When files already exist and overwrite=False, they are skipped."""
    # Arrange: create files on first run
    monkeypatch.setattr(
        "scripts.import_factory_assets.fetch_all_denoms",
        lambda *a, **kw: factory_page_1["denom"],
    )
    import_factory_assets("zigchaind", "mainnet", tmp_path, overwrite=False)

    # Act: run again without overwrite
    created, skipped = import_factory_assets("zigchaind", "mainnet", tmp_path, overwrite=False)

    # Assert: all skipped on second run
    assert created == 0
    assert skipped == 2


def test_import_factory_assets_no_denoms_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When no denoms are fetched, returns (0, 0)."""
    # Arrange: empty fetch result
    monkeypatch.setattr(
        "scripts.import_factory_assets.fetch_all_denoms",
        lambda *a, **kw: [],
    )

    # Act
    created, skipped = import_factory_assets("zigchaind", "mainnet", tmp_path)

    # Assert
    assert created == 0
    assert skipped == 0
    assert "No factory denoms found." in capsys.readouterr().out


def test_import_factory_assets_preserves_existing_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    factory_page_1: dict[str, Any],
    valid_factory_asset: FactoryAsset,
) -> None:
    """When an existing asset has is_verified and description, they carry over via model_copy."""
    # Arrange: write an existing asset with is_verified=True and a description
    assets_dir = tmp_path / "assets" / "factory"
    assets_dir.mkdir(parents=True)
    existing = valid_factory_asset.model_copy(update={
        "is_verified": True,
        "description": "Existing description",
    })
    existing_dict = existing.model_dump(mode="json", exclude_none=True)
    (assets_dir / f"{existing.asset_id}.mainnet.json").write_text(
        json.dumps(existing_dict, indent=2), encoding="utf-8"
    )

    # Only fetch the matching denom (first in fixture)
    monkeypatch.setattr(
        "scripts.import_factory_assets.fetch_all_denoms",
        lambda *a, **kw: [factory_page_1["denom"][0]],
    )

    # Act: import with overwrite to replace the file
    import_factory_assets("zigchaind", "mainnet", tmp_path, overwrite=True)

    # Assert: re-read the written file — is_verified and description preserved
    written = json.loads(
        (assets_dir / f"{existing.asset_id}.mainnet.json").read_text(encoding="utf-8")
    )
    assert written["is_verified"] is True
    assert written["description"] == "Existing description"


# ----------------
# Negative tests for import_factory_assets
# ----------------

def test_import_factory_assets_error_continues_processing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    factory_page_1: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When one denom fails, error is logged and remaining denoms are still processed."""
    # Arrange: first denom has invalid format, second is valid
    denoms = list(factory_page_1["denom"])
    denoms[0] = dict(denoms[0])
    denoms[0]["denom"] = "invalid-format"

    # Mock fetch to return one bad denom followed by one valid denom
    monkeypatch.setattr(
        "scripts.import_factory_assets.fetch_all_denoms",
        lambda *a, **kw: denoms,
    )

    # Act
    created, skipped = import_factory_assets("zigchaind", "mainnet", tmp_path)

    # Assert: one error, one created; capsys.readouterr() captures both out and err at once
    assert created == 1
    captured = capsys.readouterr()
    assert "Error processing invalid-format" in captured.err
    assert "Errors: 1" in captured.out


def test_import_factory_assets_warns_on_unresolved_collision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When pre-existing unverified assets collide on display_denom, a warning is printed to stderr."""
    # Arrange: pre-write two existing assets with the same display_denom "PANDA" (neither verified)
    # The collision is detected from existing files on disk at the start of import_factory_assets.
    assets_dir = tmp_path / "assets" / "factory"
    assets_dir.mkdir(parents=True)

    base_a = f"coin.{CREATOR_A}.panda"
    asset_a = FactoryAsset.model_validate({
        "network": "mainnet", "asset_id": base_a, "type": "factory",
        "symbol": "PANDA", "name": "Panda", "decimals": 6,
        "display_denom": "PANDA", "base_denom": base_a,
        "creator": CREATOR_A, "subdenom": "panda",
        "denom_units": [{"denom": base_a, "exponent": 0}],
    })
    base_b = f"coin.{CREATOR_B}.panda"
    asset_b = FactoryAsset.model_validate({
        "network": "mainnet", "asset_id": base_b, "type": "factory",
        "symbol": "PANDA", "name": "Panda", "decimals": 6,
        "display_denom": "PANDA", "base_denom": base_b,
        "creator": CREATOR_B, "subdenom": "panda",
        "denom_units": [{"denom": base_b, "exponent": 0}],
    })
    for asset in (asset_a, asset_b):
        d = asset.model_dump(mode="json", exclude_none=True)
        (assets_dir / f"{asset.asset_id}.mainnet.json").write_text(
            json.dumps(d, indent=2), encoding="utf-8"
        )

    # Fetch one of the colliding denoms
    monkeypatch.setattr(
        "scripts.import_factory_assets.fetch_all_denoms",
        lambda *a, **kw: [{"denom": base_a, "creator": CREATOR_A}],
    )

    # Act
    import_factory_assets("zigchaind", "mainnet", tmp_path, overwrite=True)

    # Assert: full unresolved collision warning printed (neither asset is verified)
    err = capsys.readouterr().err
    sorted_ids = ", ".join(sorted([base_a, base_b]))
    expected_warning = (
        f"Warning: unresolved display_denom collision for 'PANDA' "
        f"(2 assets). Maintainer should verify one authoritative asset. "
        f"asset_ids: {sorted_ids}"
    )
    assert expected_warning in err


######################################################################
# Tests for check_zigchaind
######################################################################

# ----------------
# Positive tests for check_zigchaind
# ----------------

def test_check_zigchaind_returns_true_when_command_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returns True when zigchaind executes successfully (returncode 0)."""
    # Arrange: simulate successful subprocess
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(args=[], returncode=0),
    )

    # Act
    result = check_zigchaind("zigchaind")

    # Assert
    assert result is True


# ----------------
# Negative tests for check_zigchaind
# ----------------

@pytest.mark.parametrize(
    "exception",
    [
        FileNotFoundError(),
        subprocess.TimeoutExpired(cmd="zigchaind", timeout=5),
        OSError("permission denied"),
    ],
    ids=["not-found", "timeout", "os-error"],
)
def test_check_zigchaind_returns_false_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
) -> None:
    """check_zigchaind returns False when the binary can't be executed."""
    # Arrange: simulate failure
    def raise_exc(*args, **kwargs):
        raise exception

    monkeypatch.setattr(subprocess, "run", raise_exc)

    # Act
    result = check_zigchaind("zigchaind")

    # Assert
    assert result is False


######################################################################
# Tests for main
######################################################################

# ----------------
# Positive tests for main
# ----------------

def test_main_success_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    factory_page_1: dict[str, Any],
) -> None:
    """main exits 0 on successful import."""
    # Arrange: set CLI args — no --network flag, so detect_network() defaults to mainnet
    monkeypatch.setattr(sys, "argv", ["prog", "--repo-root", str(tmp_path)])
    # Skip the real zigchaind binary check — pretend it's installed
    monkeypatch.setattr("scripts.import_factory_assets.check_zigchaind", lambda p: True)
    # Skip the real chain query — return fixture denoms directly
    monkeypatch.setattr(
        "scripts.import_factory_assets.fetch_all_denoms",
        lambda *a, **kw: factory_page_1["denom"],
    )

    # Act: main() always calls sys.exit() — wrap in pytest.raises to catch it
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: exit code 0 signals success (import_factory_assets completed without errors)
    assert exc.value.code == 0


def test_main_network_flag_overrides_env_var(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--network flag takes precedence over ZIGCHAIN_CHAIN_ID env var."""
    # Arrange: env says mainnet, flag says testnet
    monkeypatch.setenv("ZIGCHAIN_CHAIN_ID", "zigchain-1")
    monkeypatch.setattr(sys, "argv", ["prog", "--network", "testnet", "--repo-root", str(tmp_path)])
    monkeypatch.setattr("scripts.import_factory_assets.check_zigchaind", lambda p: True)
    monkeypatch.setattr("scripts.import_factory_assets.fetch_all_denoms", lambda *a, **kw: [])

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: flag wins — "testnet" used (readouterr() returns captured stdout)
    assert exc.value.code == 0
    assert "Using network: testnet" in capsys.readouterr().out


def test_main_uses_detect_network_when_no_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When --network is not passed, main falls back to detect_network()."""
    # Arrange: env var says testnet, no --network flag
    monkeypatch.setenv("ZIGCHAIN_CHAIN_ID", "zig-test-2")
    monkeypatch.setattr(sys, "argv", ["prog", "--repo-root", str(tmp_path)])
    monkeypatch.setattr("scripts.import_factory_assets.check_zigchaind", lambda p: True)
    monkeypatch.setattr("scripts.import_factory_assets.fetch_all_denoms", lambda *a, **kw: [])

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: detect_network returns testnet from env var
    assert exc.value.code == 0
    assert "Using network: testnet" in capsys.readouterr().out


def test_main_custom_zigchaind_path_is_forwarded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--zigchaind-path value is forwarded to check_zigchaind and import_factory_assets."""
    # Arrange: pass a non-default zigchaind path
    custom_path = "/custom/bin/zigchaind"
    monkeypatch.setattr(sys, "argv", ["prog", "--repo-root", str(tmp_path), "--zigchaind-path", custom_path])

    # Both fakes append the path they receive so we can verify forwarding order
    received_paths: list[str] = []

    # Fake: records the path, pretends zigchaind is installed
    def fake_check_zigchaind(path: str) -> bool:
        received_paths.append(path)
        return True

    # Fake: records the path, returns (created=0, skipped=0) so main() can unpack the tuple
    def fake_import(zigchaind_path: str, network: str, repo_root: Path, overwrite: bool) -> tuple[int, int]:
        received_paths.append(zigchaind_path)
        return 0, 0

    # Swap the real functions with the fakes for this test only
    monkeypatch.setattr("scripts.import_factory_assets.check_zigchaind", fake_check_zigchaind)
    monkeypatch.setattr("scripts.import_factory_assets.import_factory_assets", fake_import)

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: two entries — first from check_zigchaind, second from import_factory_assets; both must be the custom path
    assert exc.value.code == 0
    assert received_paths == [custom_path, custom_path]


def test_main_overwrite_flag_is_forwarded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--overwrite flag is forwarded to import_factory_assets as True."""
    # Arrange: pass --overwrite
    monkeypatch.setattr(sys, "argv", ["prog", "--repo-root", str(tmp_path), "--overwrite"])
    monkeypatch.setattr("scripts.import_factory_assets.check_zigchaind", lambda p: True)

    # Capture the overwrite argument passed to import_factory_assets
    received_overwrite: list[bool] = []

    def fake_import(zigchaind_path, network, repo_root, overwrite):
        received_overwrite.append(overwrite)
        return 0, 0

    monkeypatch.setattr("scripts.import_factory_assets.import_factory_assets", fake_import)

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: overwrite=True reached import_factory_assets
    assert exc.value.code == 0
    assert received_overwrite == [True]


# ----------------
# Negative tests for main
# ----------------

def test_main_zigchaind_not_found_prints_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When zigchaind is not available, prints error and exits 1."""
    # Arrange
    monkeypatch.setattr(sys, "argv", ["prog"])
    monkeypatch.setattr("scripts.import_factory_assets.check_zigchaind", lambda p: False)

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: exit 1 with error message
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "Error: zigchaind not found" in err
    assert "Make sure zigchaind is installed and in your PATH, or specify --zigchaind-path" in err


def test_main_keyboard_interrupt_exits_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """On KeyboardInterrupt (Ctrl+C), prints message and exits 1."""
    # Arrange: minimal argv and pretend zigchaind is installed
    monkeypatch.setattr(sys, "argv", ["prog"])
    monkeypatch.setattr("scripts.import_factory_assets.check_zigchaind", lambda p: True)
    # Simulate the user pressing Ctrl+C during import — the generator expression
    # `(_ for _ in ()).throw(...)` is a compact way to raise an exception from a lambda
    monkeypatch.setattr(
        "scripts.import_factory_assets.import_factory_assets",
        lambda *a, **kw: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    # Act: main() catches KeyboardInterrupt and calls sys.exit(1)
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: exit code 1 and user-friendly message printed to stderr
    assert exc.value.code == 1
    assert "Interrupted by user" in capsys.readouterr().err


def test_main_fatal_error_exits_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """On unexpected exception, prints 'Fatal error: ...' and exits 1."""
    # Arrange: minimal argv and pretend zigchaind is installed
    monkeypatch.setattr(sys, "argv", ["prog"])
    monkeypatch.setattr("scripts.import_factory_assets.check_zigchaind", lambda p: True)

    # Stand-alone function (not a lambda) so we can raise RuntimeError cleanly
    def raise_boom(*args, **kwargs):
        raise RuntimeError("boom")

    # Replace import_factory_assets so calling it triggers our RuntimeError
    monkeypatch.setattr("scripts.import_factory_assets.import_factory_assets", raise_boom)

    # Act: main()'s generic except Exception catches it and calls sys.exit(1)
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: exit code 1 and the original exception message is included in stderr
    assert exc.value.code == 1
    assert "Fatal error: boom" in capsys.readouterr().err


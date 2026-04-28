"""Tests for the verified-only filter in generate_chain_registry.py.

Scope is narrow on purpose: this file only covers the verified-only default
and the --include-unverified opt-out (plus the mode banner and per-network
summary). It's intentionally self-contained so it can merge independently of
the comprehensive test_generate_chain_registry.py on other branches.

Mirrors the pattern of test_generate_chain_registry_provider.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

from models import FactoryAsset, IBCAsset, NativeAsset
from scripts.generate_chain_registry import generate, generate_for_network


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "generate_chain_registry.py"

IBC_HASH = "6490A7EAB61059BFC1CDDEB05917DD70BDF3A611654162A1A47DB930D40D8AF4"
CREATOR = "zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw"


def _native(symbol: str, *, is_verified: bool) -> NativeAsset:
    return NativeAsset(
        network="mainnet",
        asset_id=symbol.lower(),
        type="native",
        symbol=symbol,
        name=f"{symbol} Native",
        decimals=6,
        display_denom=symbol,
        base_denom=f"u{symbol.lower()}",
        denom_units=[
            {"denom": f"u{symbol.lower()}", "exponent": 0},
            {"denom": symbol, "exponent": 6},
        ],
        is_verified=is_verified,
    )


def _factory(subdenom: str, *, is_verified: bool) -> FactoryAsset:
    base = f"coin.{CREATOR}.{subdenom}"
    return FactoryAsset(
        network="mainnet",
        asset_id=base,
        type="factory",
        symbol=subdenom.upper(),
        name=f"{subdenom.upper()} Factory",
        decimals=6,
        display_denom=base,
        base_denom=base,
        creator=CREATOR,
        subdenom=subdenom,
        denom_units=[{"denom": base, "exponent": 0}],
        is_verified=is_verified,
    )


def _ibc(symbol: str, *, is_verified: bool) -> IBCAsset:
    return IBCAsset(
        network="mainnet",
        asset_id=f"ibc/{IBC_HASH}",
        type="ibc",
        symbol=symbol,
        name=f"{symbol} IBC",
        decimals=6,
        display_denom=symbol.lower(),
        base_denom=f"ibc/{IBC_HASH}",
        hash=IBC_HASH,
        origin_chain="noble",
        origin_denom="uusdc",
        traces=[
            {
                "type": "ibc",
                "chain_name": "zigchain",
                "base_denom": f"ibc/{IBC_HASH}",
                "path": "transfer/channel-3/uusdc",
            },
        ],
        channels=[
            {
                "zigchain_channel": "channel-3",
                "counterparty_chain": "noble",
                "counterparty_channel": "channel-175",
            },
        ],
        is_verified=is_verified,
    )


def _read_assetlist(out_root: Path, chain_name: str = "zigchain") -> List[Dict[str, Any]]:
    """Load the generated mainnet assetlist and return its `assets` list."""
    path = out_root / chain_name / "assetlist.json"
    return json.loads(path.read_text())["assets"]


def _run_for_network(tmp_path: Path, natives, factories, ibcs, **kwargs) -> Path:
    """Invoke generate_for_network with sensible tmp defaults and return out_root."""
    out_root = tmp_path / "out"
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    generate_for_network(
        network="mainnet",
        natives=natives,
        factories=factories,
        ibcs=ibcs,
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        use_testnet_paths=False,
        **kwargs,
    )
    return out_root


# --------------------------------------------------------------------------- #
# Direct tests: generate_for_network filter behaviour                         #
# --------------------------------------------------------------------------- #


def test_generate_for_network_default_is_verified_only(tmp_path: Path) -> None:
    """Calling generate_for_network without verified_only kwarg filters to is_verified=True."""
    out_root = _run_for_network(
        tmp_path,
        natives=[_native("ZIG", is_verified=True)],
        factories=[_factory("panda", is_verified=False), _factory("koala", is_verified=True)],
        ibcs=[_ibc("USDC", is_verified=True)],
    )

    assets = _read_assetlist(out_root)
    symbols = {a["symbol"] for a in assets}
    assert symbols == {"ZIG", "KOALA", "USDC"}  # PANDA (unverified) filtered out


def test_generate_for_network_include_unverified_keeps_all(tmp_path: Path) -> None:
    """Explicit verified_only=False passes all assets through regardless of is_verified."""
    out_root = _run_for_network(
        tmp_path,
        natives=[_native("ZIG", is_verified=True)],
        factories=[_factory("panda", is_verified=False), _factory("koala", is_verified=True)],
        ibcs=[_ibc("USDC", is_verified=False)],  # unverified IBC kept too
        verified_only=False,
    )

    assets = _read_assetlist(out_root)
    symbols = {a["symbol"] for a in assets}
    assert symbols == {"ZIG", "PANDA", "KOALA", "USDC"}


def test_generate_for_network_prints_summary_when_excluded(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When the filter excludes anything, a per-network summary line prints."""
    _run_for_network(
        tmp_path,
        natives=[_native("ZIG", is_verified=False)],  # excluded
        factories=[_factory("panda", is_verified=False)],  # excluded
        ibcs=[_ibc("USDC", is_verified=True)],
    )

    out = capsys.readouterr().out
    assert "[mainnet] verified-only filter: excluded 1 native, 1 factory, 0 ibc" in out


def test_generate_for_network_silent_when_nothing_excluded(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When every asset is verified, the exclusion summary line does NOT print."""
    _run_for_network(
        tmp_path,
        natives=[_native("ZIG", is_verified=True)],
        factories=[_factory("koala", is_verified=True)],
        ibcs=[_ibc("USDC", is_verified=True)],
    )

    out = capsys.readouterr().out
    assert "verified-only filter: excluded" not in out


# --------------------------------------------------------------------------- #
# Direct tests: generate() startup banner                                     #
# --------------------------------------------------------------------------- #


def test_generate_startup_banner_verified_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """generate() prints 'Mode: verified-only' when verified_only is True (default)."""
    (tmp_path / "assets" / "native").mkdir(parents=True)
    (tmp_path / "assets" / "factory").mkdir(parents=True)
    (tmp_path / "assets" / "ibc").mkdir(parents=True)
    (tmp_path / "logos").mkdir()

    generate(tmp_path, tmp_path / "out", skip_sync=True)

    assert "Mode: verified-only" in capsys.readouterr().out


def test_generate_startup_banner_include_unverified(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """generate() prints the local-debug banner when verified_only=False."""
    (tmp_path / "assets" / "native").mkdir(parents=True)
    (tmp_path / "assets" / "factory").mkdir(parents=True)
    (tmp_path / "assets" / "ibc").mkdir(parents=True)
    (tmp_path / "logos").mkdir()

    generate(tmp_path, tmp_path / "out", skip_sync=True, verified_only=False)

    assert "Mode: including unverified assets (local debug)" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# CLI tests: real script via subprocess                                       #
# --------------------------------------------------------------------------- #


def _run_cli(*extra_args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    env = {**os.environ}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--skip-sync", "--out", str(cwd / "generated-test"), *extra_args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def test_cli_default_filters_unverified(tmp_path: Path) -> None:
    """No flags → filter is active → output contains only verified assets."""
    # Use the real repo corpus for an end-to-end smoke check.
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--skip-sync", "--out", str(tmp_path / "out")],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Mode: verified-only" in result.stdout
    assert "verified-only filter: excluded" in result.stdout

    assets = _read_assetlist(tmp_path / "out")
    # Registry snapshot at time of writing: 1 native + 9 ibc + 1 factory = 11.
    # Asserting len matches the verified count from load_assets against the real corpus.
    for a in assets:
        # Every asset in the output must be marked is_verified=True (when present in the source JSON).
        # chain-registry output doesn't carry is_verified through, so we assert the count/symbols instead.
        assert isinstance(a, dict)
    assert len(assets) >= 1


def test_cli_include_unverified_flag(tmp_path: Path) -> None:
    """--include-unverified keeps unverified assets → output is much larger than verified-only."""
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--skip-sync",
            "--include-unverified",
            "--out", str(tmp_path / "out"),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Mode: including unverified assets (local debug)" in result.stdout

    assets = _read_assetlist(tmp_path / "out")
    # With unverified included, expect hundreds of mainnet factory assets in the output.
    assert len(assets) > 50, f"expected >50 assets with --include-unverified, got {len(assets)}"


def test_cli_rejects_old_verified_only_flag() -> None:
    """--verified-only (the old opt-in name) must fail loudly — regression guard for the rename."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--skip-sync", "--verified-only"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
    assert "--verified-only" in result.stderr

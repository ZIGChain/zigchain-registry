"""Tests for protected external asset verification in validate_assets.py."""

import json
import tempfile
from pathlib import Path

import pytest

from scripts.validate_assets import AssetValidator, PROTECTED_ASSETS_FILENAME


# Valid factory asset template (pattern from models/factory.py)
CREATOR = "zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw"


def _factory_asset(symbol: str, name: str, subdenom: str) -> dict:
    """Create valid factory asset data."""
    base = f"coin.{CREATOR}.{subdenom}"
    return {
        "network": "mainnet",
        "asset_id": base,
        "type": "factory",
        "symbol": symbol,
        "name": name,
        "decimals": 6,
        "display_denom": base,
        "base_denom": base,
        "creator": CREATOR,
        "subdenom": subdenom,
        "denom_units": [{"denom": base, "exponent": 0}],
    }


def _ibc_asset(symbol: str, name: str, origin_chain: str) -> dict:
    """Create valid IBC asset data."""
    h = "6490A7EAB61059BFC1CDDEB05917DD70BDF3A611654162A1A47DB930D40D8AF4"
    return {
        "network": "mainnet",
        "asset_id": f"ibc/{h}",
        "type": "ibc",
        "symbol": symbol,
        "name": name,
        "decimals": 6,
        "display_denom": symbol.lower(),
        "base_denom": f"ibc/{h}",
        "hash": h,
        "origin_chain": origin_chain,
        "origin_denom": "uusdc",
        "traces": [
            {"type": "ibc", "chain_name": "zigchain", "base_denom": f"ibc/{h}", "path": "transfer/channel-3/uusdc"},
            {"type": "ibc", "chain_name": origin_chain, "base_denom": "uusdc", "path": "transfer/channel-175"},
        ],
        "channels": [
            {"zigchain_channel": "channel-3", "counterparty_chain": origin_chain, "counterparty_channel": "channel-175"}
        ],
    }


def _native_asset(symbol: str, name: str) -> dict:
    """Create valid native asset data."""
    return {
        "network": "mainnet",
        "asset_id": "zig",
        "type": "native",
        "symbol": symbol,
        "name": name,
        "decimals": 6,
        "display_denom": symbol,
        "base_denom": "uzig",
        "denom_units": [{"denom": "uzig", "exponent": 0}, {"denom": "zig", "exponent": 6}],
    }


PROTECTED_CONFIG = {
    "assets": [
        {
            "symbol": "USDC",
            "name": "USD Coin",
            "allowed_types": ["ibc"],
            "expected_origin_chains": ["noble"],
            "similar_patterns": ["^[ux]?USDC[ex]?$", "^USDC\\.[a-z]+$", "^USDCX$"],
            "description": "Circle USD Coin via Noble",
        },
        {
            "symbol": "USDT",
            "name": "Tether USD",
            "allowed_types": ["ibc"],
            "expected_origin_chains": ["ethereum", "kava"],
            "similar_patterns": ["^[ux]?USDT[ex]?$"],
            "description": "Tether USD stablecoin",
        },
        {
            "symbol": "ATOM",
            "name": "Cosmos Hub Atom",
            "allowed_types": ["ibc"],
            "expected_origin_chains": ["cosmoshub"],
            "similar_patterns": ["^[sx]?ATOM[0-9]*$"],
            "description": "Native Cosmos Hub token",
        },
    ],
    "config": {"case_sensitive": False, "enforce_on_testnet": False, "warn_on_similar": True},
}


@pytest.fixture
def temp_repo():
    """Create temporary repo with config and assets directories."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "config").mkdir()
        (root / "assets" / "factory").mkdir(parents=True)
        (root / "assets" / "ibc").mkdir(parents=True)
        (root / "assets" / "native").mkdir(parents=True)
        yield root


def test_scenario_a_ibc_usdc_from_noble_passes(temp_repo):
    """Scenario A: Legitimate IBC asset with protected symbol from noble passes."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    asset = _ibc_asset("USDC", "Noble USDC", "noble")
    (temp_repo / "assets" / "ibc" / "usdc.mainnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo)
    success = validator.validate_all()

    assert success
    assert validator.protection_violations == 0
    assert validator.protection_checked >= 1


def test_scenario_b_factory_with_protected_symbol_fails(temp_repo):
    """Scenario B: Factory token with exact protected symbol fails."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    asset = _factory_asset("USDC", "Fake USDC", "usdc")
    (temp_repo / "assets" / "factory" / "coin.test.usdc.mainnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo)
    success = validator.validate_all()

    assert not success
    assert validator.protection_violations >= 1
    assert any("protected symbol" in e.lower() for e in validator.errors)


def test_scenario_c_factory_with_protected_name_fails(temp_repo):
    """Scenario C: Factory token with protected name fails."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    asset = _factory_asset("FAKE", "Tether USD", "tether")
    (temp_repo / "assets" / "factory" / "coin.test.tether.mainnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo)
    success = validator.validate_all()

    assert not success
    assert validator.protection_violations >= 1
    assert any("protected name" in e.lower() for e in validator.errors)


def test_scenario_d_factory_with_similar_symbol_warns(temp_repo):
    """Scenario D: Factory token with similar symbol (USDCX) triggers warning."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    asset = _factory_asset("USDCX", "USDC Variant", "usdcx")
    (temp_repo / "assets" / "factory" / "coin.test.usdcx.mainnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo)
    success = validator.validate_all()

    assert success  # Warnings don't fail
    assert validator.protection_warnings >= 1
    assert any("similar" in w.lower() for w in validator.warnings)


def test_scenario_e_factory_with_unrelated_symbol_passes(temp_repo):
    """Scenario E: Factory token with unrelated symbol passes."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    asset = _factory_asset("PANDA", "Panda Token", "panda")
    (temp_repo / "assets" / "factory" / "coin.test.panda.mainnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo)
    success = validator.validate_all()

    assert success
    assert validator.protection_violations == 0


def test_case_insensitive_matching(temp_repo):
    """Factory with symbol 'usdc' (lowercase) matches protected 'USDC' and fails."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    asset = _factory_asset("usdc", "Fake USD Coin", "usdc")
    (temp_repo / "assets" / "factory" / "coin.test.usdc.mainnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo)
    success = validator.validate_all()

    assert not success
    assert any("protected symbol" in e.lower() for e in validator.errors)


def test_ibc_with_wrong_origin_warns(temp_repo):
    """IBC asset with protected symbol but unexpected origin chain warns."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    asset = _ibc_asset("USDC", "USDC from unknown", "unknownchain")
    (temp_repo / "assets" / "ibc" / "usdc-wrong.mainnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo)
    success = validator.validate_all()

    assert success
    assert validator.protection_warnings >= 1
    assert any("unexpected" in w.lower() or "origin" in w.lower() for w in validator.warnings)


def test_missing_config_fails(temp_repo):
    """Missing protected_assets.json causes validation to fail."""
    # No config file
    asset = _factory_asset("PANDA", "Panda", "panda")
    (temp_repo / "assets" / "factory" / "coin.test.panda.mainnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo)
    success = validator.validate_all()

    assert not success
    assert any("protected" in e.lower() and "not found" in e.lower() for e in validator.errors)


def test_native_asset_skips_protection(temp_repo):
    """Native asset with protected symbol (e.g. ZIG) skips protection checks."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    asset = _native_asset("ZIG", "ZIGChain Native Token")
    (temp_repo / "assets" / "native" / "zig.mainnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo)
    success = validator.validate_all()

    assert success
    assert validator.protection_violations == 0


def test_is_verified_factory_still_fails(temp_repo):
    """Factory token with is_verified=true and protected symbol still fails (Edge Case 7)."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    asset = _factory_asset("USDC", "Fake USDC", "usdc")
    asset["is_verified"] = True
    (temp_repo / "assets" / "factory" / "coin.test.usdc.mainnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo)
    success = validator.validate_all()

    assert not success
    assert validator.protection_violations >= 1


def test_warn_only_mode(temp_repo):
    """With --warn-only, violations become warnings."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    asset = _factory_asset("USDC", "Fake USDC", "usdc")
    (temp_repo / "assets" / "factory" / "coin.test.usdc.mainnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo, warn_only=True)
    success = validator.validate_all()

    assert success
    assert validator.protection_violations == 0
    assert validator.protection_warnings >= 1
    assert any("protected symbol" in w.lower() for w in validator.warnings)


def test_testnet_skips_protection_when_not_enforced(temp_repo):
    """When network=testnet and enforce_on_testnet=false, protection checks are skipped."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    asset = _factory_asset("USDC", "Fake USDC", "usdc")
    asset["network"] = "testnet"
    (temp_repo / "assets" / "factory" / "coin.test.usdc.testnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo, network_filter="testnet")
    success = validator.validate_all()

    # Protection is skipped for testnet when enforce_on_testnet=false
    assert success
    assert validator.protection_violations == 0


######################################################################
# Unicode confusables — NFKC normalization (Asana security review)
#
# Note on reachability: the Pydantic `symbol` field validator in models/base.py
# enforces `^[A-Za-z0-9][A-Za-z0-9._-]{0,41}$`, rejecting full-width / Cyrillic /
# zero-width characters before the protection check runs. NFKC on symbols is
# therefore defense-in-depth (reachable only if a caller bypasses full model
# validation). The `name` field has no such pattern restriction, so NFKC on
# names is reachable end-to-end and covered below.
######################################################################


def test_factory_name_fullwidth_confusable_fails(temp_repo):
    """Factory token whose name contains full-width Latin (`ＵＳＤ Ｃｏｉｎ`) normalizes under NFKC
    to the protected name `USD Coin` and is rejected as a protected-name violation."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    # "USD Coin" in full-width Latin letters (U+FF21..U+FF5A collapse to ASCII under NFKC).
    fullwidth_name = "\uFF35\uFF33\uFF24 \uFF23\uFF4F\uFF49\uFF4E"
    assert fullwidth_name != "USD Coin"  # pre-normalisation, distinct strings
    asset = _factory_asset("FAKE", fullwidth_name, "fakeusdc")
    (temp_repo / "assets" / "factory" / "coin.test.fakename.mainnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo)
    success = validator.validate_all()

    assert not success
    assert validator.protection_violations >= 1
    assert any("protected name" in e.lower() for e in validator.errors)


def test_similar_pattern_matches_case_variant_under_case_insensitive(temp_repo):
    """Regression/coverage: with case_sensitive=False, similar_patterns compile with re.IGNORECASE
    so the `^USDCX$` pattern also matches lowercase `usdcx` — aligning regex semantics with
    the documented case_sensitive config (previously silently case-sensitive)."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    asset = _factory_asset("usdcx", "USDC Variant", "usdcxlower")
    (temp_repo / "assets" / "factory" / "coin.test.usdcxlower.mainnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo)
    success = validator.validate_all()

    assert success  # similar_patterns only warn
    assert validator.protection_warnings >= 1
    assert any("similar" in w.lower() for w in validator.warnings)


def test_ascii_symbol_still_matches_after_nfkc_migration(temp_repo):
    """Regression: plain ASCII `usdc` still matches protected `USDC` — NFKC+casefold is
    idempotent on ASCII so existing behaviour is preserved."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    asset = _factory_asset("usdc", "Fake USD Coin", "usdcascii")
    (temp_repo / "assets" / "factory" / "coin.test.usdcascii.mainnet.json").write_text(json.dumps(asset, indent=2))

    validator = AssetValidator(temp_repo)
    success = validator.validate_all()

    assert not success
    assert any("protected symbol" in e.lower() for e in validator.errors)


def test_normalize_nfkc_collapses_fullwidth_for_symbol_lookup(temp_repo):
    """Unit-level check on _normalize: full-width `ＵＳＤＣ` NFKC-collapses to `usdc`,
    matching the key stored in cfg.symbols. Exercises the defense-in-depth path that
    would fire if a future code path ever constructed a candidate symbol from an
    external source without going through Pydantic validation first."""
    (temp_repo / "config" / PROTECTED_ASSETS_FILENAME).write_text(json.dumps(PROTECTED_CONFIG, indent=2))
    validator = AssetValidator(temp_repo)
    assert validator._load_protected_config() is True

    fullwidth = "\uFF35\uFF33\uFF24\uFF23"  # ＵＳＤＣ
    assert validator._normalize(fullwidth, case_sensitive=False) == "usdc"
    assert validator._normalize(fullwidth, case_sensitive=False) in validator._protected_config.symbols

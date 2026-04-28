"""Tests for the validate_assets script."""

import json
import re
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from models import FactoryAsset, IBCAsset, NativeAsset
from scripts.validate_assets import (
    PROTECTED_ASSETS_FILENAME,
    AssetValidator,
    main,
)


######################################################################
# Fixtures
######################################################################

HASH = "6490A7EAB61059BFC1CDDEB05917DD70BDF3A611654162A1A47DB930D40D8AF4"


@pytest.fixture
def valid_native_asset_data() -> dict[str, Any]:
    """Fixture providing valid native asset data for validation."""
    return {
        "network": "mainnet",
        "asset_id": "zig",
        "type": "native",
        "symbol": "ZIG",
        "name": "ZIGChain Native Token",
        "decimals": 6,
        "display_denom": "ZIG",
        "base_denom": "uzig",
        "denom_units": [
            {"denom": "uzig", "exponent": 0},
            {"denom": "zig", "exponent": 6},
        ],
    }


@pytest.fixture
def valid_factory_asset_data() -> dict[str, Any]:
    """Fixture providing valid factory asset data for validation."""
    creator = "zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw"
    subdenom = "panda01"
    base = f"coin.{creator}.{subdenom}"
    return {
        "network": "mainnet",
        "asset_id": base,
        "type": "factory",
        "symbol": "PANDA",
        "name": "Factory Panda Token",
        "decimals": 6,
        "display_denom": "Panda",
        "base_denom": base,
        "creator": creator,
        "subdenom": subdenom,
        "denom_units": [
            {"denom": base, "exponent": 0},
            {"denom": "panda", "exponent": 6},
        ],
    }


@pytest.fixture
def valid_ibc_asset_data() -> dict[str, Any]:
    """Fixture providing valid IBC asset data for validation."""
    return {
        "network": "mainnet",
        "asset_id": f"ibc/{HASH}",
        "type": "ibc",
        "symbol": "USDC",
        "name": "Noble USDC",
        "decimals": 6,
        "display_denom": "usdc",
        "base_denom": f"ibc/{HASH}",
        "hash": HASH,
        "origin_chain": "noble",
        "origin_denom": "uusdc",
        "traces": [
            {
                "type": "ibc",
                "chain_name": "zigchain",
                "base_denom": f"ibc/{HASH}",
                "path": "transfer/channel-3/uusdc",
            }
        ],
        "channels": [
            {
                "zigchain_channel": "channel-3",
                "counterparty_chain": "noble",
                "counterparty_channel": "channel-175",
            }
        ],
    }


@pytest.fixture
def assets_dir(tmp_path: Path) -> Path:
    """Fixture creating assets/native, assets/factory, assets/ibc under tmp_path."""
    for subdir in ("native", "factory", "ibc"):
        (tmp_path / "assets" / subdir).mkdir(parents=True, exist_ok=True)
    return tmp_path / "assets"


@pytest.fixture
def validator(tmp_path: Path) -> AssetValidator:
    """Fixture providing an AssetValidator with repo_root at tmp_path."""
    return AssetValidator(tmp_path, network_filter=None)


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Fixture creating config/ under tmp_path."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    return tmp_path / "config"


@pytest.fixture
def protected_assets_data() -> dict[str, Any]:
    """Fixture providing valid protected_assets data for validation."""
    return {
        "assets": [
            {
                "symbol": "USDC",
                "name": "USD Coin",
                "allowed_types": ["ibc"],
                "expected_origin_chains": ["noble"],
                "similar_patterns": ["^[ux]?USDC[ex]?$", "^USDC\\.[a-z]+$"],
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
        "config": {
            "case_sensitive": False,
            "enforce_on_testnet": False,
            "warn_on_similar": True,
        },
    }


@pytest.fixture
def protected_assets_config_file(
    config_dir: Path,
    protected_assets_data: dict[str, Any],
) -> Path:
    """Write default protected_assets_data to config/protected_assets.json and return the path."""
    config_file = config_dir / "protected_assets.json"
    config_file.write_text(json.dumps(protected_assets_data, indent=2), encoding="utf-8")
    return config_file


######################################################################
# Tests for _get_model_for_type
######################################################################


@pytest.mark.parametrize(
    "asset_type,expected",
    [
        ("native", NativeAsset),
        ("factory", FactoryAsset),
        ("ibc", IBCAsset),
        ("unknown", None),
        ("", None),
        ("other", None),
        ("NATIVE", None),
        ("Ibc", None),
    ],
    ids=["native", "factory", "ibc", "unknown", "empty", "other", "uppercase", "mixed_case"],
)
def test_get_model_for_type(
    validator: AssetValidator,
    asset_type: str,
    expected: Any,
) -> None:
    """_get_model_for_type returns the correct Pydantic model for known types, None otherwise."""
    # Act:
    result = validator._get_model_for_type(asset_type)

    # Assert:
    assert result is expected


######################################################################
# Tests for _load_protected_config
######################################################################

# ----------------
# Positive tests for _load_protected_config
# ----------------

def test_load_protected_config_validate_protected_asset_file(
    validator: AssetValidator,
    protected_assets_config_file: Path,
) -> None:
    """_load_protected_config returns True when config/protected_assets.json exists and is valid."""
    # Act: load the config written by the protected_assets_config_file fixture
    result = validator._load_protected_config()

    # Assert: successful load, no errors recorded
    assert result is True
    assert len(validator.errors) == 0


def test_load_protected_config_loads_from_config_subdir_only(
    validator: AssetValidator,
    config_dir: Path,
    protected_assets_data: dict[str, Any],
) -> None:
    """_load_protected_config reads only from repo_root/config/protected_assets.json, not from repo root."""
    # Arrange: place a decoy config at repo_root/protected_assets.json (wrong location)
    wrong_path = validator.repo_root / PROTECTED_ASSETS_FILENAME
    wrong_data = dict(protected_assets_data)
    wrong_data["assets"] = [{"symbol": "WRONG", "name": "Wrong", "allowed_types": ["native"],
                              "expected_origin_chains": [], "similar_patterns": [], "description": ""}]
    wrong_path.write_text(json.dumps(wrong_data, indent=2), encoding="utf-8")

    # Arrange: place the real config at repo_root/config/protected_assets.json (correct location)
    correct_path = validator.repo_root / "config" / PROTECTED_ASSETS_FILENAME
    assert correct_path == config_dir / PROTECTED_ASSETS_FILENAME
    correct_data = dict(protected_assets_data)
    correct_data["assets"] = [{"symbol": "CORRECT", "name": "Correct", "allowed_types": ["native"],
                                "expected_origin_chains": [], "similar_patterns": [], "description": ""}]
    correct_path.write_text(json.dumps(correct_data, indent=2), encoding="utf-8")

    # Act
    result = validator._load_protected_config()

    # Assert: loaded from config/ subdir, not repo root
    assert result is True
    config = validator._protected_config
    assert config is not None
    # "correct" present (lowercased — case_sensitive=False), "wrong" absent
    assert "correct" in config.symbols
    assert config.symbols["correct"].symbol == "CORRECT"
    assert "wrong" not in config.symbols


def test_load_protected_config_populates_config_flags(
    validator: AssetValidator,
    config_dir: Path,
    protected_assets_data: dict[str, Any],
) -> None:
    """_load_protected_config reads config section into _protected_config (case_sensitive, enforce_on_testnet, warn_on_similar)."""
    # Arrange: override all three config flags to non-default values
    protected_assets_data["config"] = {
        "case_sensitive": True,
        "enforce_on_testnet": True,
        "warn_on_similar": False,
    }
    (config_dir / "protected_assets.json").write_text(
        json.dumps(protected_assets_data, indent=2), encoding="utf-8"
    )

    # Act
    result = validator._load_protected_config()

    # Assert: all three flags reflect the overridden values
    assert result is True
    config = validator._protected_config
    assert config is not None
    assert config.case_sensitive is True
    assert config.enforce_on_testnet is True
    assert config.warn_on_similar is False


def test_load_protected_config_populates_symbols_and_names(
    validator: AssetValidator,
    protected_assets_config_file: Path,
) -> None:
    """_load_protected_config builds symbols and names lookup dicts (normalized by case_sensitive)."""
    # Act: fixture has 3 assets (USDC, USDT, ATOM) with case_sensitive=False
    result = validator._load_protected_config()

    # Assert: all 3 assets loaded
    assert result is True
    config = validator._protected_config
    assert config is not None
    assert len(config.assets) == 3
    # symbols dict keyed by lowercase (case_sensitive=False)
    assert "usdc" in config.symbols
    assert "usdt" in config.symbols
    assert "atom" in config.symbols
    # original casing preserved on the entry itself
    assert config.symbols["usdc"].symbol == "USDC"
    assert config.symbols["usdc"].name == "USD Coin"
    assert config.symbols["atom"].symbol == "ATOM"
    # names dict also keyed by lowercase
    assert "usd coin" in config.names
    assert "cosmos hub atom" in config.names
    # reverse lookup: name → entry → original symbol
    assert config.names["usd coin"].symbol == "USDC"


def test_load_protected_config_symbols_names_case_sensitive(
    validator: AssetValidator,
    config_dir: Path,
    protected_assets_data: dict[str, Any],
) -> None:
    """_load_protected_config uses raw symbol/name as key when case_sensitive is True."""
    # Arrange: enable case_sensitive so keys stay in original casing
    protected_assets_data["config"]["case_sensitive"] = True
    (config_dir / "protected_assets.json").write_text(
        json.dumps(protected_assets_data, indent=2), encoding="utf-8"
    )

    # Act
    result = validator._load_protected_config()

    # Assert: keys use original casing, not lowercased
    assert result is True
    config = validator._protected_config
    assert config is not None
    assert config.case_sensitive is True
    assert "USDC" in config.symbols     # original casing used as key
    assert "usdc" not in config.symbols  # lowercase key absent
    assert "USD Coin" in config.names    # name key also preserves casing


def test_load_protected_config_compiles_similar_patterns(
    validator: AssetValidator,
    protected_assets_config_file: Path,
) -> None:
    """_load_protected_config compiles similar_patterns into (re.Pattern, ProtectedAssetEntry) list."""
    # Act: fixture has regex patterns like "^[ux]?USDC[ex]?$" across 3 assets
    result = validator._load_protected_config()

    # Assert: patterns compiled and linked back to their source entry
    assert result is True
    config = validator._protected_config
    assert config is not None
    assert len(config.assets) == 3
    assert len(config.similar_patterns) >= 1
    for pattern, asset in config.similar_patterns:
        assert asset in config.assets       # each pattern maps to a known asset
        assert isinstance(pattern, re.Pattern)  # raw string compiled to regex

    # Assert: both USDC patterns from the fixture were compiled
    usdc_entry = config.symbols["usdc"]
    usdc_patterns = []
    for p, a in config.similar_patterns:
        if a is usdc_entry:
            usdc_patterns.append(p)
    # match() returns truthy if the compiled regex matches the test string
    assert any(p.match("xUSDC") for p in usdc_patterns)       # hits "^[ux]?USDC[ex]?$"
    assert any(p.match("USDC.noble") for p in usdc_patterns)   # hits "^USDC\.[a-z]+$"


def test_load_protected_config_config_defaults(
    validator: AssetValidator,
    config_dir: Path,
    protected_assets_data: dict[str, Any],
) -> None:
    """_load_protected_config uses defaults when config section is missing or empty."""
    # Arrange: remove "config" key so config_raw falls back to {}
    data = dict(protected_assets_data)
    del data["config"]
    (config_dir / "protected_assets.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )

    # Act
    result = validator._load_protected_config()

    # Assert: all three flags use their default values
    assert result is True
    config = validator._protected_config
    assert config is not None
    assert config.case_sensitive is False      # default: case-insensitive matching
    assert config.enforce_on_testnet is False  # default: skip protection on testnet
    assert config.warn_on_similar is True      # default: warn on similar symbol patterns


def test_load_protected_config_skips_non_dict_items_in_assets(
    validator: AssetValidator,
    config_dir: Path,
) -> None:
    """Non-dict elements in assets array are skipped; only dict items with symbol/name are loaded."""
    # Arrange: mix one valid dict with string, int, and None entries
    data = {
        "assets": [
            {"symbol": "USDC", "name": "USD Coin", "allowed_types": ["ibc"],
             "expected_origin_chains": ["noble"], "similar_patterns": [], "description": ""},
            "not a dict",  # skipped by isinstance(item, dict)
            42,            # skipped
            None,          # skipped
        ],
        "config": {},
    }
    (config_dir / "protected_assets.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Act
    result = validator._load_protected_config()

    # Assert: only the valid dict item loaded; non-dict items silently skipped
    assert result is True
    config = validator._protected_config
    assert config is not None
    assert len(config.assets) == 1
    assert config.assets[0].symbol == "USDC"
    assert "usdc" in config.symbols


def test_load_protected_config_skips_items_with_missing_or_empty_symbol_name(
    validator: AssetValidator,
    config_dir: Path,
) -> None:
    """Items with missing or empty symbol/name are skipped; valid items are loaded."""
    # Arrange: first item has empty symbol, third has empty name — both should be skipped
    data = {
        "assets": [
            {"symbol": "", "name": "No Symbol", "allowed_types": [], "expected_origin_chains": [],
             "similar_patterns": [], "description": ""},        # skipped: empty symbol
            {"symbol": "USDC", "name": "USD Coin", "allowed_types": ["ibc"],
             "expected_origin_chains": ["noble"], "similar_patterns": [], "description": ""},  # kept
            {"symbol": "ATOM", "name": "", "allowed_types": [], "expected_origin_chains": [],
             "similar_patterns": [], "description": ""},        # skipped: empty name
        ],
        "config": {},
    }
    (config_dir / "protected_assets.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Act
    result = validator._load_protected_config()

    # Assert: only USDC loaded; items with empty symbol/name silently skipped
    assert result is True
    config = validator._protected_config
    assert config is not None
    assert len(config.assets) == 1
    assert config.assets[0].symbol == "USDC"
    assert "usdc" in config.symbols


def test_load_protected_config_wrong_type_fields_default_to_empty_list(
    validator: AssetValidator,
    config_dir: Path,
) -> None:
    """When allowed_types, expected_origin_chains or similar_patterns are not lists, they default to [] and entry is still created."""
    # Arrange: all three list fields set to plain strings instead of lists
    data = {
        "assets": [
            {
                "symbol": "USDC",
                "name": "USD Coin",
                "allowed_types": "ibc",       # string, not list → defaults to []
                "expected_origin_chains": "noble",  # string → []
                "similar_patterns": "^USDC$",       # string → []
                "description": "",
            },
        ],
        "config": {},
    }
    (config_dir / "protected_assets.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Act
    result = validator._load_protected_config()

    # Assert: entry created; all three non-list fields coerced to empty lists
    assert result is True
    config = validator._protected_config
    assert config is not None
    assert len(config.assets) == 1
    entry = config.assets[0]
    assert entry.allowed_types == []
    assert entry.expected_origin_chains == []
    assert entry.similar_patterns == []


def test_load_protected_config_expected_origin_chains_lowercased(
    validator: AssetValidator,
    config_dir: Path,
) -> None:
    """expected_origin_chains are normalized to lowercase on each entry."""
    # Arrange: mixed-case origin chains "Noble" and "CosmosHub"
    data = {
        "assets": [
            {
                "symbol": "USDC",
                "name": "USD Coin",
                "allowed_types": ["ibc"],
                "expected_origin_chains": ["Noble", "CosmosHub"],
                "similar_patterns": [],
                "description": "",
            },
        ],
        "config": {},
    }
    (config_dir / "protected_assets.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Act
    result = validator._load_protected_config()

    # Assert: origin chains stored as lowercase for case-insensitive matching
    assert result is True
    config = validator._protected_config
    assert config is not None
    assert config.assets[0].expected_origin_chains == ["noble", "cosmoshub"]


def test_load_protected_config_skips_non_string_in_similar_patterns(
    validator: AssetValidator,
    config_dir: Path,
) -> None:
    """Non-string elements in similar_patterns (number, null) are skipped; string elements are compiled."""
    # Arrange: similar_patterns has int 42, valid regex "^USDC$", and None
    data = {
        "assets": [
            {
                "symbol": "USDC",
                "name": "USD Coin",
                "allowed_types": ["ibc"],
                "expected_origin_chains": ["noble"],
                "similar_patterns": [42, "^USDC$", None],  # only "^USDC$" is a string
                "description": "",
            },
        ],
        "config": {},
    }
    (config_dir / "protected_assets.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Act
    result = validator._load_protected_config()

    # Assert: only the string element compiled; non-strings silently skipped
    assert result is True
    config = validator._protected_config
    assert config is not None
    assert len(config.similar_patterns) == 1  # 42 and None skipped
    pattern, entry = config.similar_patterns[0]
    assert pattern.match("USDC")  # the compiled regex works


def test_load_protected_config_invalid_regex_appends_warning_and_skips_pattern(
    validator: AssetValidator,
    config_dir: Path,
) -> None:
    """When similar_patterns contains an invalid regex, a warning is appended and that pattern is skipped; valid patterns compile normally."""
    # Arrange: 3 patterns — valid, broken regex, valid
    data = {
        "assets": [
            {
                "symbol": "USDC",
                "name": "USD Coin",
                "allowed_types": ["ibc"],
                "expected_origin_chains": ["noble"],
                "similar_patterns": ["^USDC$", "[invalid(regex", "^xUSDC$"],
                "description": "",
            },
        ],
        "config": {},
    }
    (config_dir / "protected_assets.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Act
    result = validator._load_protected_config()

    # Assert: load succeeds despite the broken regex
    assert result is True
    # warning recorded for the invalid regex with the offending pattern text
    assert len(validator.warnings) == 1
    assert validator.warnings[0] == "Invalid regex in protected_assets.json similar_patterns: '[invalid(regex' — skipped"

    # only the 2 valid patterns compiled; broken one skipped
    config = validator._protected_config
    assert config is not None
    assert len(config.similar_patterns) == 2

    patterns = []
    for p, _ in config.similar_patterns:
        patterns.append(p.pattern)
    assert "^USDC$" in patterns
    assert "^xUSDC$" in patterns


# ----------------
# Negative tests for _load_protected_config
# ----------------

def test_load_protected_config_missing_file(validator: AssetValidator) -> None:
    """_load_protected_config returns False and appends error when protected_assets.json is missing."""
    # Arrange: no config/ directory or file created; build expected path for assertion
    expected_path = validator.repo_root / "config" / PROTECTED_ASSETS_FILENAME

    # Act
    result = validator._load_protected_config()

    # Assert: fails with the full error including the expected path
    assert result is False
    assert len(validator.errors) == 1
    assert validator.errors[0] == f"Invalid or empty protected_assets.json: config file not found at {expected_path}"


def test_load_protected_config_invalid_json(
    validator: AssetValidator,
    config_dir: Path,
) -> None:
    """_load_protected_config returns False when file contains invalid JSON."""
    # Arrange: write malformed JSON that triggers json.JSONDecodeError
    (config_dir / "protected_assets.json").write_text("{ invalid json }", encoding="utf-8")

    # Act
    result = validator._load_protected_config()

    # Assert: fails with error message
    assert result is False
    assert len(validator.errors) == 1
    assert validator.errors[0].startswith("Invalid or empty protected_assets.json: invalid JSON:")


@pytest.mark.parametrize(
    "content,description",
    [
        ("{}", "empty dict"),
        ("null", "null"),
        ("[]", "JSON array not dict"),
    ],
)
def test_load_protected_config_empty_or_not_dict(
    validator: AssetValidator,
    config_dir: Path,
    content: str,
    description: str,
) -> None:
    """_load_protected_config returns False when data is empty or not a dict."""
    # Arrange: write content that is valid JSON but not a non-empty dict
    (config_dir / "protected_assets.json").write_text(content, encoding="utf-8")

    # Act:
    result = validator._load_protected_config()

    # Assert: fails because `not data or not isinstance(data, dict)` is True
    assert result is False
    assert len(validator.errors) == 1
    assert validator.errors[0] == "Invalid or empty protected_assets.json"


def test_load_protected_config_assets_not_present(
    validator: AssetValidator,
    config_dir: Path,
    protected_assets_data: dict[str, Any],
) -> None:
    """_load_protected_config returns False when 'assets' key is missing."""
    # Arrange: remove the "assets" key entirely from an otherwise valid config
    del protected_assets_data["assets"]
    (config_dir / "protected_assets.json").write_text(
        json.dumps(protected_assets_data, indent=2), encoding="utf-8"
    )

    # Act:
    result = validator._load_protected_config()

    # Assert: fails because data.get("assets") returns None → falsy
    assert result is False
    assert len(validator.errors) == 1
    assert validator.errors[0] == "Invalid or empty protected_assets.json: 'assets' must be a non-empty array"


def test_load_protected_config_assets_wrong_type(
    validator: AssetValidator,
    config_dir: Path,
    protected_assets_data: dict[str, Any],
) -> None:
    """_load_protected_config returns False when 'assets' is not a list."""
    # Arrange: set "assets" to a string instead of a list
    protected_assets_data["assets"] = "wrong_data"
    (config_dir / "protected_assets.json").write_text(
        json.dumps(protected_assets_data, indent=2), encoding="utf-8"
    )

    # Act:
    result = validator._load_protected_config()

    # Assert: fails because isinstance("wrong_data", list) is False
    assert result is False
    assert len(validator.errors) == 1
    assert validator.errors[0] == "Invalid or empty protected_assets.json: 'assets' must be a non-empty array"


def test_load_protected_config_all_items_skipped_no_valid_assets(
    validator: AssetValidator,
    config_dir: Path,
) -> None:
    """_load_protected_config returns False when every item in assets is skipped (non-dict or missing symbol/name)."""
    # Arrange: all items are invalid — missing symbol, missing name, empty dict, or not a dict
    data = {
        "assets": [
            {"name": "No symbol"},           # skipped: no "symbol" key
            {"symbol": "No name only"},      # skipped: no "name" key
            {},                              # skipped: neither symbol nor name
            "string",                        # skipped: not a dict
        ],
        "config": {},
    }
    (config_dir / "protected_assets.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Act:
    result = validator._load_protected_config()

    # Assert: fails because assets list is empty after all items are skipped
    assert result is False
    assert len(validator.errors) == 1
    assert validator.errors[0] == "Invalid or empty protected_assets.json: no valid assets defined"


######################################################################
# Tests for _normalize
######################################################################

@pytest.mark.parametrize(
    "value,case_sensitive,expected",
    [
        ("USDC", True, "USDC"),
        ("USDC", False, "usdc"),
        ("usdc", False, "usdc"),
        ("Atom", True, "Atom"),
        ("Atom", False, "atom"),
        ("", True, ""),
        ("", False, ""),
    ],
)
def test_normalize(
    validator: AssetValidator,
    value: str,
    case_sensitive: bool,
    expected: str,
) -> None:
    """_normalize returns value unchanged when case_sensitive, else lowercased."""
    # Act
    result = validator._normalize(value, case_sensitive)

    # Assert
    assert result == expected


######################################################################
# Tests for _validate_protected_assets
######################################################################

@pytest.fixture
def validator_with_protected_config(
    validator: AssetValidator,
    protected_assets_config_file: Path,
) -> AssetValidator:
    """Validator with protected_assets config already loaded (so _protected_config is set)."""
    validator._load_protected_config()
    return validator


@pytest.fixture
def validator_with_protected_config_warn_only(
    tmp_path: Path,
    config_dir: Path,
    protected_assets_data: dict[str, Any],
) -> AssetValidator:
    """Validator with protected_assets config loaded and warn_only=True."""
    (config_dir / "protected_assets.json").write_text(
        json.dumps(protected_assets_data, indent=2), encoding="utf-8"
    )
    v = AssetValidator(tmp_path, network_filter=None, warn_only=True)
    v._load_protected_config()
    return v


# ----------------
# Positive tests for _validate_protected_assets
# ----------------

def test_validate_protected_assets_returns_true_when_no_config_loaded(
    validator: AssetValidator,
) -> None:
    """When _protected_config is not loaded, _validate_protected_assets skips checks and returns True."""
    # Arrange: factory asset with a protected symbol, but no config loaded
    asset_data = {"type": "factory", "network": "mainnet", "symbol": "USDC", "name": "USD Coin"}
    file_path = Path("factory/coin.mainnet.json")

    # Act
    result = validator._validate_protected_assets(asset_data, file_path)

    # Assert: skips all checks, no errors or warnings
    assert result is True
    assert len(validator.errors) == 0
    assert len(validator.warnings) == 0


def test_validate_protected_assets_skips_testnet_when_enforce_on_testnet_false(
    validator_with_protected_config: AssetValidator,
) -> None:
    """On testnet, when config has enforce_on_testnet False, protection is skipped and returns True."""
    # Arrange: USDC would normally fail for factory, but testnet + enforce_on_testnet=False → skip
    asset_data = {"type": "factory", "network": "testnet", "symbol": "USDC", "name": "USD Coin"}
    file_path = Path("factory/coin.testnet.json")

    # Act
    result = validator_with_protected_config._validate_protected_assets(asset_data, file_path)

    # Assert: protection skipped entirely on testnet
    assert result is True
    assert len(validator_with_protected_config.errors) == 0


def test_validate_protected_assets_skips_native_assets(
    validator_with_protected_config: AssetValidator,
) -> None:
    """Native assets skip protected-asset checks and always return True."""
    # Arrange: native asset — protection never applies regardless of symbol
    asset_data = {"type": "native", "network": "mainnet", "symbol": "ZIG", "name": "ZIG Chain"}
    file_path = Path("native/zig.mainnet.json")

    # Act
    result = validator_with_protected_config._validate_protected_assets(asset_data, file_path)

    # Assert
    assert result is True


def test_validate_protected_assets_factory_non_protected_symbol_returns_true(
    validator_with_protected_config: AssetValidator,
) -> None:
    """Factory asset with a symbol not in the protected list passes and returns True."""
    # Arrange: PANDA is not in the protected symbols (USDC, USDT, ATOM)
    asset_data = {
        "type": "factory",
        "network": "mainnet",
        "symbol": "PANDA",
        "name": "Panda Token",
    }
    file_path = Path("factory/coin.creator.panda.mainnet.json")

    # Act
    result = validator_with_protected_config._validate_protected_assets(asset_data, file_path)

    # Assert: passes — no symbol/name match, no similar pattern match
    assert result is True
    assert len(validator_with_protected_config.errors) == 0


def test_validate_protected_assets_factory_protected_symbol_warn_only_adds_warning_returns_true(
    validator_with_protected_config_warn_only: AssetValidator,
) -> None:
    """When warn_only is True, factory using protected symbol adds a warning but returns True."""
    # Arrange: factory uses USDC (protected), but warn_only downgrades violation to warning
    validator = validator_with_protected_config_warn_only
    asset_data = {
        "type": "factory",
        "network": "mainnet",
        "symbol": "USDC",
        "name": "Fake USDC",
    }
    file_path = Path("factory/coin.creator.usdc.mainnet.json")

    # Act
    result = validator._validate_protected_assets(asset_data, file_path)

    # Assert: returns True (not blocked), but warning recorded
    assert result is True
    assert validator.protection_warnings == 1
    assert len(validator.warnings) == 1
    assert validator.warnings[0] == (
        f"{file_path}: Factory token cannot use protected symbol '{asset_data['symbol']}' — this symbol is reserved "
        f"for canonical noble assets. Use a different symbol or ensure your asset is "
        f"the legitimate IBC representation."
    )


def test_validate_protected_assets_factory_protected_name_warn_only_adds_warning_returns_true(
    validator_with_protected_config_warn_only: AssetValidator,
) -> None:
    """When warn_only is True, factory using protected name adds a warning but returns True."""
    # Arrange: factory uses "USD Coin" (protected name), warn_only downgrades to warning
    validator = validator_with_protected_config_warn_only
    asset_data = {
        "type": "factory",
        "network": "mainnet",
        "symbol": "FAKE",
        "name": "USD Coin",
    }
    file_path = Path("factory/coin.creator.fake.mainnet.json")

    # Act
    result = validator._validate_protected_assets(asset_data, file_path)

    # Assert: returns True (not blocked), but warning recorded for the name match
    assert result is True
    assert validator.protection_warnings == 1
    assert len(validator.warnings) == 1
    assert validator.warnings[0] == (
        f"{file_path}: Factory token cannot use protected name '{asset_data['name']}' — this name is reserved. "
        f"Use a different name or ensure your asset is the legitimate IBC representation from ['noble']."
    )


def test_validate_protected_assets_factory_similar_symbol_adds_warning_returns_true(
    validator_with_protected_config: AssetValidator,
) -> None:
    """Factory with symbol similar to protected (e.g. xUSDC) adds a warning when warn_on_similar True."""
    # Arrange: fixture config has similar_patterns "^[ux]?USDC[ex]?$" so "xUSDC" matches
    asset_data = {
        "type": "factory",
        "network": "mainnet",
        "symbol": "xUSDC",
        "name": "Wrapped USDC",
    }
    file_path = Path("factory/coin.creator.xusdc.mainnet.json")

    # Act
    result = validator_with_protected_config._validate_protected_assets(asset_data, file_path)

    # Assert: passes but a "similar to protected" warning is recorded
    assert result is True
    assert validator_with_protected_config.protection_warnings == 1
    assert len(validator_with_protected_config.warnings) == 1
    assert validator_with_protected_config.warnings[0] == (
        f"{file_path}: Symbol '{asset_data['symbol']}' is similar to protected asset 'USDC' — manual review required"
    )


def test_validate_protected_assets_ibc_protected_symbol_correct_origin_returns_true(
    validator_with_protected_config: AssetValidator,
) -> None:
    """IBC asset with protected symbol and expected origin_chain passes and returns True."""
    # Arrange: USDC from noble — matches protected symbol AND expected origin chain
    asset_data = {
        "type": "ibc",
        "network": "mainnet",
        "symbol": "USDC",
        "name": "USD Coin",
        "origin_chain": "noble",
    }
    file_path = Path("ibc/ibc_usdc.mainnet.json")

    # Act
    result = validator_with_protected_config._validate_protected_assets(asset_data, file_path)

    # Assert: legitimate IBC asset passes cleanly
    assert result is True
    assert len(validator_with_protected_config.errors) == 0


def test_validate_protected_assets_ibc_non_protected_symbol_returns_true(
    validator_with_protected_config: AssetValidator,
) -> None:
    """IBC asset with a symbol not in the protected list passes and returns True."""
    # Arrange: OTHER is not a protected symbol — no checks apply
    asset_data = {
        "type": "ibc",
        "network": "mainnet",
        "symbol": "OTHER",
        "name": "Other Token",
        "origin_chain": "somechain",
    }
    file_path = Path("ibc/ibc_other.mainnet.json")

    # Act
    result = validator_with_protected_config._validate_protected_assets(asset_data, file_path)

    # Assert
    assert result is True


def test_validate_protected_assets_ibc_protected_symbol_wrong_origin_adds_warning_returns_true(
    validator_with_protected_config: AssetValidator,
) -> None:
    """IBC asset with protected symbol but unexpected origin_chain adds a warning but returns True."""
    # Arrange: USDC is protected and expected from noble; we pass a different origin
    asset_data = {
        "type": "ibc",
        "network": "mainnet",
        "symbol": "USDC",
        "name": "USD Coin",
        "origin_chain": "otherchain",
    }
    file_path = Path("ibc/ibc_usdc.mainnet.json")

    # Act
    result = validator_with_protected_config._validate_protected_assets(asset_data, file_path)

    # Assert: passes but warning about unexpected origin chain
    assert result is True
    assert len(validator_with_protected_config.warnings) == 1
    assert validator_with_protected_config.warnings[0] == (
        f"{file_path}: IBC asset with protected symbol '{asset_data['symbol']}' has unexpected "
        f"origin chain '{asset_data['origin_chain']}' (expected: ['noble']) — review required"
    )


def test_validate_protected_assets_factory_similar_symbol_warn_on_similar_false_no_warning_returns_true(
    tmp_path: Path,
    config_dir: Path,
) -> None:
    """When warn_on_similar is False, factory with symbol similar to protected does not add a warning."""
    # Arrange: config with warn_on_similar=False; xUSDC would match the similar pattern
    data = {
        "assets": [
            {
                "symbol": "USDC",
                "name": "USD Coin",
                "allowed_types": ["ibc"],
                "expected_origin_chains": ["noble"],
                "similar_patterns": ["^[ux]?USDC[ex]?$"],
                "description": "Circle USD Coin",
            },
        ],
        "config": {"warn_on_similar": False},
    }
    (config_dir / "protected_assets.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    v = AssetValidator(tmp_path, network_filter=None)
    v._load_protected_config()

    # xUSDC matches similar pattern but warn_on_similar is False → no warning
    asset_data = {
        "type": "factory",
        "network": "mainnet",
        "symbol": "xUSDC",
        "name": "Wrapped USDC",
    }
    file_path = Path("factory/coin.creator.xusdc.mainnet.json")

    # Act
    result = v._validate_protected_assets(asset_data, file_path)

    # Assert: no warning added because warn_on_similar is disabled
    assert result is True
    assert len(v.warnings) == 0


# ----------------
# Negative tests for _validate_protected_assets
# ----------------

def test_validate_protected_assets_testnet_enforce_on_testnet_true_adds_error_returns_false(
    tmp_path: Path,
    config_dir: Path,
) -> None:
    """When enforce_on_testnet is True, testnet factory with protected symbol adds error and returns False."""
    # Arrange: enforce_on_testnet=True so testnet assets ARE checked
    data = {
        "assets": [
            {
                "symbol": "USDC",
                "name": "USD Coin",
                "allowed_types": ["ibc"],
                "expected_origin_chains": ["noble"],
                "similar_patterns": [],
                "description": "Circle USD Coin",
            },
        ],
        "config": {"enforce_on_testnet": True},
    }
    (config_dir / "protected_assets.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    v = AssetValidator(tmp_path, network_filter=None, warn_only=False)
    v._load_protected_config()

    # testnet factory using protected symbol USDC
    asset_data = {
        "type": "factory",
        "network": "testnet",
        "symbol": "USDC",
        "name": "Fake USDC",
    }
    file_path = Path("factory/coin.creator.usdc.testnet.json")

    # Act
    result = v._validate_protected_assets(asset_data, file_path)

    # Assert: blocked — testnet enforcement catches the violation
    assert result is False
    assert len(v.errors) == 1
    assert v.errors[0] == (
        f"{file_path}: Factory token cannot use protected symbol '{asset_data['symbol']}' — this symbol is reserved "
        f"for canonical noble assets. Use a different symbol or ensure your asset is "
        f"the legitimate IBC representation."
    )


def test_validate_protected_assets_factory_protected_symbol_warn_only_false_adds_error_returns_false(
    validator_with_protected_config: AssetValidator,
) -> None:
    """When warn_only is False, factory using protected symbol adds error and returns False."""
    # Arrange: factory uses USDC (protected), validator has warn_only=False (default)
    asset_data = {
        "type": "factory",
        "network": "mainnet",
        "symbol": "USDC",
        "name": "Fake USDC",
    }
    file_path = Path("factory/coin.creator.usdc.mainnet.json")

    # Act
    result = validator_with_protected_config._validate_protected_assets(asset_data, file_path)

    # Assert: blocked with error
    assert result is False
    assert len(validator_with_protected_config.errors) == 1
    assert validator_with_protected_config.errors[0] == (
        f"{file_path}: Factory token cannot use protected symbol '{asset_data['symbol']}' — this symbol is reserved "
        f"for canonical noble assets. Use a different symbol or ensure your asset is "
        f"the legitimate IBC representation."
    )


def test_validate_protected_assets_factory_protected_name_warn_only_false_adds_error_returns_false(
    validator_with_protected_config: AssetValidator,
) -> None:
    """When warn_only is False, factory using protected name adds error and returns False."""
    # Arrange: factory uses "USD Coin" (protected name), symbol is non-protected
    asset_data = {
        "type": "factory",
        "network": "mainnet",
        "symbol": "FAKE",
        "name": "USD Coin",
    }
    file_path = Path("factory/coin.creator.fake.mainnet.json")

    # Act
    result = validator_with_protected_config._validate_protected_assets(asset_data, file_path)

    # Assert: blocked with error for name match
    assert result is False
    assert len(validator_with_protected_config.errors) == 1
    assert validator_with_protected_config.errors[0] == (
        f"{file_path}: Factory token cannot use protected name '{asset_data['name']}' — this name is reserved. "
        f"Use a different name or ensure your asset is the legitimate IBC representation from ['noble']."
    )


######################################################################
# Tests for validate_asset_file
######################################################################

# ----------------
# Positive tests for validate_asset_file
# ----------------

def test_validate_asset_file_valid_native(
    validator: AssetValidator,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """validate_asset_file returns True for valid native asset JSON."""
    # Arrange: write valid native asset to disk
    file_path = assets_dir / "native" / "zig.mainnet.json"
    file_path.write_text(json.dumps(valid_native_asset_data, indent=2), encoding="utf-8")

    # Act
    result = validator.validate_asset_file(file_path)

    # Assert: passes with no errors
    assert result is True
    assert len(validator.errors) == 0


def test_validate_asset_file_valid_factory(
    validator: AssetValidator,
    assets_dir: Path,
    valid_factory_asset_data: dict[str, Any],
) -> None:
    """validate_asset_file returns True for valid factory asset JSON."""
    # Arrange: write valid factory asset to disk
    file_path = assets_dir / "factory" / "coin.zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw.panda01.mainnet.json"
    file_path.write_text(json.dumps(valid_factory_asset_data, indent=2), encoding="utf-8")

    # Act
    result = validator.validate_asset_file(file_path)

    # Assert: passes with no errors
    assert result is True
    assert len(validator.errors) == 0


def test_validate_asset_file_valid_ibc(
    validator: AssetValidator,
    assets_dir: Path,
    valid_ibc_asset_data: dict[str, Any],
) -> None:
    """validate_asset_file returns True for valid IBC asset JSON."""
    # Arrange: write valid IBC asset to disk
    file_path = assets_dir / "ibc" / "ibc_usdc.mainnet.json"
    file_path.write_text(json.dumps(valid_ibc_asset_data, indent=2), encoding="utf-8")

    # Act
    result = validator.validate_asset_file(file_path)

    # Assert: passes with no errors
    assert result is True
    assert len(validator.errors) == 0


def test_validate_asset_file_ignores_schema_key(
    validator: AssetValidator,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """validate_asset_file accepts file with $schema key (stripped before Pydantic validation)."""
    # Arrange: inject $schema so we exercise the strip path
    schema_ref = "../../schemas/asset.native.schema.json"
    valid_native_asset_data["$schema"] = schema_ref
    file_path = assets_dir / "native" / "zig.mainnet.json"
    file_path.write_text(json.dumps(valid_native_asset_data, indent=2), encoding="utf-8")

    on_disk = json.loads(file_path.read_text(encoding="utf-8"))
    assert "$schema" in on_disk  # confirm the file on disk contains $schema

    # Act
    result = validator.validate_asset_file(file_path)

    # Assert: passes because $schema was stripped before Pydantic validation (extra="forbid" would reject it)
    assert result is True
    assert len(validator.errors) == 0


def test_validate_asset_file_network_filter_skips_other(
    tmp_path: Path,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """When network_filter is set, file with other network is skipped and returns True (no error)."""
    # Arrange: testnet file, but validator filters for mainnet only
    valid_native_asset_data["network"] = "testnet"
    file_path = assets_dir / "native" / "zig.testnet.json"
    file_path.write_text(json.dumps(valid_native_asset_data, indent=2), encoding="utf-8")
    validator_filtered = AssetValidator(tmp_path, network_filter="mainnet")

    # Act
    result = validator_filtered.validate_asset_file(file_path)

    # Assert: skipped (not an error), returns True
    assert result is True
    assert len(validator_filtered.errors) == 0


def test_validate_asset_file_network_filter_matches_proceeds_with_validation(
    tmp_path: Path,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """When network_filter is set and file's network matches, validation proceeds normally."""
    # Arrange: mainnet file, validator filters for mainnet — should validate, not skip
    file_path = assets_dir / "native" / "zig.mainnet.json"
    file_path.write_text(json.dumps(valid_native_asset_data, indent=2), encoding="utf-8")
    validator_filtered = AssetValidator(tmp_path, network_filter="mainnet")

    # Act
    result = validator_filtered.validate_asset_file(file_path)

    # Assert: not skipped — asset was validated and tracked
    assert result is True
    assert len(validator_filtered.errors) == 0
    assert "mainnet" in validator_filtered.asset_ids
    assert "zig" in validator_filtered.asset_ids["mainnet"]


# ----------------
# Negative tests for validate_asset_file
# ----------------

def test_validate_asset_file_invalid_json(
    validator: AssetValidator,
    assets_dir: Path,
) -> None:
    """validate_asset_file returns False and appends error for invalid JSON."""
    # Arrange: write malformed JSON
    file_path = assets_dir / "native" / "bad.json"
    file_path.write_text("{ invalid json ", encoding="utf-8")

    # Act
    result = validator.validate_asset_file(file_path)

    # Assert: fails with JSON parse error (suffix varies, so use startswith)
    assert result is False
    assert len(validator.errors) == 1
    assert validator.errors[0].startswith(f"{file_path}: Invalid JSON:")


def test_validate_asset_file_read_exception_appends_error_returns_false(
    validator: AssetValidator,
    assets_dir: Path,
) -> None:
    """validate_asset_file returns False and appends error when file cannot be read (non-JSON error)."""
    # Arrange: valid path that raises OSError on open
    file_path = assets_dir / "native" / "unreadable.json"
    file_path.touch()

    # Act: patch open to raise OSError simulating a permission error
    with patch("builtins.open", side_effect=OSError("permission denied")):
        result = validator.validate_asset_file(file_path)

    # Assert: fails with file-read error
    assert result is False
    assert len(validator.errors) == 1
    assert validator.errors[0] == f"{file_path}: Error reading file: permission denied"


def test_validate_asset_file_missing_network(
    validator: AssetValidator,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """validate_asset_file returns False when network is missing."""
    # Arrange: remove network field from an otherwise valid asset
    del valid_native_asset_data["network"]
    file_path = assets_dir / "native" / "zig.mainnet.json"
    file_path.write_text(json.dumps(valid_native_asset_data, indent=2), encoding="utf-8")

    # Act
    result = validator.validate_asset_file(file_path)

    # Assert: fails with missing network error
    assert result is False
    assert len(validator.errors) == 1
    assert validator.errors[0] == f"{file_path}: Missing required field 'network'"


def test_validate_asset_file_unknown_type(
    validator: AssetValidator,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """validate_asset_file returns False for unknown asset type."""
    # Arrange: change type to "unknown" which has no Pydantic model
    valid_native_asset_data["type"] = "unknown"
    file_path = assets_dir / "native" / "zig.mainnet.json"
    file_path.write_text(json.dumps(valid_native_asset_data, indent=2), encoding="utf-8")

    # Act
    result = validator.validate_asset_file(file_path)

    # Assert: fails because _get_model_for_type returns None
    assert result is False
    assert len(validator.errors) == 1
    assert validator.errors[0] == f"{file_path}: Unknown asset type 'unknown'"


def test_validate_asset_file_validation_error(
    validator: AssetValidator,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """validate_asset_file returns False and appends error when Pydantic validation fails."""
    # Arrange: set decimals to -1, which fails Pydantic's constraint
    valid_native_asset_data["decimals"] = -1
    file_path = assets_dir / "native" / "zig.mainnet.json"
    file_path.write_text(json.dumps(valid_native_asset_data, indent=2), encoding="utf-8")

    # Act
    result = validator.validate_asset_file(file_path)

    # Assert: Pydantic ValidationError formatted (suffix varies by Pydantic version)
    assert result is False
    assert len(validator.errors) == 1
    assert validator.errors[0].startswith(f"{file_path}: Validation error at 'decimals'")


def test_validate_asset_file_unexpected_validation_exception_appends_error_returns_false(
    validator: AssetValidator,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """validate_asset_file returns False when model_validate raises an unexpected Exception."""
    # Arrange: write a valid file; patch model_validate to raise RuntimeError
    file_path = assets_dir / "native" / "zig.mainnet.json"
    file_path.write_text(json.dumps(valid_native_asset_data, indent=2), encoding="utf-8")

    # Act: patch model_validate to raise RuntimeError (simulates unexpected failure)
    with patch.object(NativeAsset, "model_validate", side_effect=RuntimeError("unexpected")):
        result = validator.validate_asset_file(file_path)

    # Assert: caught by the generic except Exception handler
    assert result is False
    assert len(validator.errors) == 1
    assert validator.errors[0] == f"{file_path}: Unexpected validation error: unexpected"


def test_validate_asset_file_duplicate_asset_id(
    validator: AssetValidator,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """validate_asset_file returns False when asset_id is duplicate in same network."""
    # Arrange: two files with identical asset data (same asset_id "zig" on mainnet)
    file1 = assets_dir / "native" / "zig.mainnet.json"
    file2 = assets_dir / "native" / "zig_dup.mainnet.json"
    file1.write_text(json.dumps(valid_native_asset_data, indent=2), encoding="utf-8")
    file2.write_text(json.dumps(valid_native_asset_data, indent=2), encoding="utf-8")

    # Act: validate first, then second (duplicate)
    result1 = validator.validate_asset_file(file1)
    result2 = validator.validate_asset_file(file2)

    # Assert: first passes, second fails on duplicate asset_id
    assert result1 is True
    assert result2 is False
    assert len(validator.errors) == 1
    assert validator.errors[0] == f"{file2}: Duplicate asset_id 'zig' (also in {file1})"


def test_validate_asset_file_duplicate_base_denom(
    validator: AssetValidator,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """validate_asset_file returns False when base_denom is duplicate in same network."""
    # Arrange: two assets with different asset_id but same base_denom
    valid_native_asset_data["asset_id"] = "zig"
    file1 = assets_dir / "native" / "zig.mainnet.json"
    valid_native_asset_data_copy = {**valid_native_asset_data, "asset_id": "zig2"}
    file2 = assets_dir / "native" / "zig2.mainnet.json"
    file1.write_text(json.dumps(valid_native_asset_data, indent=2), encoding="utf-8")
    file2.write_text(json.dumps(valid_native_asset_data_copy, indent=2), encoding="utf-8")

    # Act: validate first, then second (same base_denom "uzig")
    result1 = validator.validate_asset_file(file1)
    result2 = validator.validate_asset_file(file2)

    # Assert: first passes, second fails on duplicate base_denom
    assert result1 is True
    assert result2 is False
    assert len(validator.errors) == 1
    assert validator.errors[0] == f"{file2}: Duplicate base_denom 'uzig' (also in {file1})"


def test_validate_asset_file_protection_violation_returns_false(
    tmp_path: Path,
    config_dir: Path,
    assets_dir: Path,
    valid_factory_asset_data: dict[str, Any],
) -> None:
    """validate_asset_file returns False when _protected_config is loaded and protection check fails."""
    # Arrange: protect PANDA; load config so _protected_config is set; factory asset uses PANDA
    protected = {
        "assets": [{"symbol": "PANDA", "name": "Panda Token", "allowed_types": ["ibc"],
                    "expected_origin_chains": ["noble"], "similar_patterns": [], "description": ""}],
        "config": {},
    }
    (config_dir / "protected_assets.json").write_text(json.dumps(protected), encoding="utf-8")
    v = AssetValidator(tmp_path, network_filter=None, warn_only=False)
    v._load_protected_config()

    file_path = assets_dir / "factory" / "panda.mainnet.json"
    file_path.write_text(json.dumps(valid_factory_asset_data, indent=2), encoding="utf-8")

    # Act
    result = v.validate_asset_file(file_path)

    # Assert: blocked by protection check within validate_asset_file
    assert result is False
    assert len(v.errors) == 1
    assert v.errors[0] == (
        f"{file_path}: Factory token cannot use protected symbol '{valid_factory_asset_data['symbol']}' — this symbol is reserved "
        f"for canonical noble assets. Use a different symbol or ensure your asset is "
        f"the legitimate IBC representation."
    )


######################################################################
# Tests for validate_all
######################################################################

# ----------------
# Positive tests for validate_all
# ----------------

def test_validate_all_success(
    validator: AssetValidator,
    protected_assets_config_file: Path,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
    valid_factory_asset_data: dict[str, Any],
) -> None:
    """validate_all returns True when all asset files are valid."""
    # Arrange: write one valid native and one valid factory asset
    (assets_dir / "native" / "zig.mainnet.json").write_text(
        json.dumps(valid_native_asset_data, indent=2), encoding="utf-8"
    )
    base = valid_factory_asset_data["asset_id"]
    (assets_dir / "factory" / f"{base}.mainnet.json").write_text(
        json.dumps(valid_factory_asset_data, indent=2), encoding="utf-8"
    )

    # Act
    result = validator.validate_all()

    # Assert: all files pass validation
    assert result is True
    assert len(validator.errors) == 0


def test_validate_all_empty_dirs(
    validator: AssetValidator,
    protected_assets_config_file: Path,
) -> None:
    """validate_all returns True when asset dirs exist but have no JSON files."""
    # Act: dirs exist (via assets_dir dependency) but are empty
    result = validator.validate_all()

    # Assert: nothing to validate, no errors
    assert result is True
    assert len(validator.errors) == 0


def test_validate_all_skips_missing_asset_subdirs(
    validator: AssetValidator,
    protected_assets_config_file: Path,
    tmp_path: Path,
) -> None:
    """validate_all skips subdirs that don't exist without error."""
    # Arrange: create only native/ — factory/ and ibc/ are absent
    (tmp_path / "assets" / "native").mkdir(parents=True)

    # Act
    result = validator.validate_all()

    # Assert: absent dirs are silently skipped, not treated as errors
    assert result is True
    assert len(validator.errors) == 0


def test_validate_all_finds_files_in_nested_subdirs(
    validator: AssetValidator,
    protected_assets_config_file: Path,
    assets_dir: Path,
    valid_ibc_asset_data: dict[str, Any],
) -> None:
    """validate_all uses rglob so files in nested subdirs (e.g. ibc/cosmoshub/) are found and validated."""
    # Arrange: place IBC asset inside ibc/noble/ nested subdir
    nested_dir = assets_dir / "ibc" / "noble"
    nested_dir.mkdir(parents=True, exist_ok=True)
    file_path = nested_dir / "usdc.mainnet.json"
    file_path.write_text(json.dumps(valid_ibc_asset_data, indent=2), encoding="utf-8")

    # Act
    result = validator.validate_all()

    # Assert: file was discovered and validated via rglob
    assert result is True
    assert len(validator.errors) == 0
    assert "mainnet" in validator.asset_ids
    assert valid_ibc_asset_data["asset_id"] in validator.asset_ids["mainnet"]


# ----------------
# Negative tests for validate_all
# ----------------

def test_validate_all_returns_false_when_protected_config_missing(
    validator: AssetValidator,
) -> None:
    """validate_all returns False immediately when protected_assets.json does not exist."""
    # Arrange: no protected_assets_config_file created; config/ dir is absent

    # Act
    result = validator.validate_all()

    # Assert: fails immediately on missing config before processing any assets
    assert result is False
    assert len(validator.errors) == 1
    assert "Invalid or empty protected_assets.json: config file not found" in validator.errors[0]


def test_validate_all_fails_on_invalid_file(
    validator: AssetValidator,
    protected_assets_config_file: Path,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """validate_all returns False when at least one file is invalid."""
    # Arrange: one valid file and one malformed JSON file
    (assets_dir / "native" / "zig.mainnet.json").write_text(
        json.dumps(valid_native_asset_data, indent=2), encoding="utf-8"
    )
    (assets_dir / "native" / "bad.mainnet.json").write_text("{ broken ", encoding="utf-8")

    # Act
    result = validator.validate_all()

    # Assert: fails because at least one file has errors
    assert result is False
    assert len(validator.errors) == 1



######################################################################
# Tests for _warn_on_display_collisions
######################################################################

def _make_native_asset(
    base: dict[str, Any],
    asset_id: str,
    display_denom: str,
    symbol: str,
    name: str,
    base_denom: str,
    is_verified: bool = False,
) -> dict[str, Any]:
    """Build a native asset dict from base with overrides; denom_units use base_denom and human part."""
    data = dict(base)
    data["asset_id"] = asset_id
    data["display_denom"] = display_denom
    data["symbol"] = symbol
    data["name"] = name
    data["base_denom"] = base_denom
    human = base_denom.lstrip("u") if base_denom.startswith("u") else base_denom
    data["denom_units"] = [
        {"denom": base_denom, "exponent": 0},
        {"denom": human, "exponent": 6},
    ]
    if is_verified:
        data["is_verified"] = True
    return data


@pytest.fixture
def two_colliding_zig_assets(
    validator: AssetValidator,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> tuple[AssetValidator, Path, Path]:
    """Two native assets with display_denom 'ZIG', written to disk and validated (collision ready)."""
    data1 = _make_native_asset(
        valid_native_asset_data,
        asset_id="first",
        display_denom="ZIG",
        symbol="ZIG",
        name="First Token",
        base_denom="ufirst",
    )
    data2 = _make_native_asset(
        valid_native_asset_data,
        asset_id="second",
        display_denom="ZIG",
        symbol="ZIG",
        name="Second Token",
        base_denom="usecond",
    )
    file1 = assets_dir / "native" / "first.mainnet.json"
    file2 = assets_dir / "native" / "second.mainnet.json"
    file1.write_text(json.dumps(data1, indent=2), encoding="utf-8")
    file2.write_text(json.dumps(data2, indent=2), encoding="utf-8")
    validator.validate_asset_file(file1)
    validator.validate_asset_file(file2)
    return validator, file1, file2


# ----------------
# Positive tests for _warn_on_display_collisions
# ----------------

@pytest.mark.parametrize(
    "assets_spec",
    [
        [],                                        # no assets → no warnings
        [("zig", "ZIG")],                          # single asset → no collision
        [("zig", "ZIG"), ("other", "OTHER")],      # two different display_denom → no collision
    ],
    ids=["empty_asset_ids", "single_asset", "two_assets_different_denom"],
)
def test_warn_on_display_collisions_no_collision_no_warning(
    validator: AssetValidator,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
    assets_spec: list,
) -> None:
    """When no two assets share the same display_denom (case-insensitive), no collision warning is added."""
    # Arrange:
    for asset_id, display_denom in assets_spec:
        data = _make_native_asset(
            valid_native_asset_data,
            asset_id=asset_id,
            display_denom=display_denom,
            symbol=display_denom,
            name=f"{display_denom} Token",
            base_denom=f"u{asset_id}",
        )
        file_path = assets_dir / "native" / f"{asset_id}.mainnet.json"
        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        validator.validate_asset_file(file_path)

    # Act
    validator._warn_on_display_collisions()

    # Assert
    collision_warnings = [w for w in validator.warnings if "display_denom collision" in w]
    assert len(collision_warnings) == 0


# ----------------
# Negative tests for _warn_on_display_collisions
# ----------------

@pytest.mark.parametrize(
    "display_denom_1,display_denom_2,both_verified",
    [
        ("ZIG", "ZIG", False),
        ("USDC", "usdc", False),
        ("ZIG", "ZIG", True),
    ],
    ids=["same_denom", "case_insensitive", "multiple_verified"],
)
def test_warn_on_display_collisions_collision_adds_warning(
    validator: AssetValidator,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
    display_denom_1: str,
    display_denom_2: str,
    both_verified: bool,
) -> None:
    """When two assets share the same display_denom (case-insensitive), a collision warning is added; both verified adds an extra warning."""
    # Arrange:
    data1 = _make_native_asset(
        valid_native_asset_data,
        asset_id="first",
        display_denom=display_denom_1,
        symbol=display_denom_1,
        name="First Token",
        base_denom="ufirst",
        is_verified=both_verified,
    )
    data2 = _make_native_asset(
        valid_native_asset_data,
        asset_id="second",
        display_denom=display_denom_2,
        symbol=display_denom_2,
        name="Second Token",
        base_denom="usecond",
        is_verified=both_verified,
    )
    file1 = assets_dir / "native" / "first.mainnet.json"
    file2 = assets_dir / "native" / "second.mainnet.json"
    file1.write_text(json.dumps(data1, indent=2), encoding="utf-8")
    file2.write_text(json.dumps(data2, indent=2), encoding="utf-8")
    validator.validate_asset_file(file1)
    validator.validate_asset_file(file2)

    # Act
    validator._warn_on_display_collisions()

    # Assert
    assert len(validator.warnings) >= 1
    all_warnings = " ".join(validator.warnings)
    assert "display_denom collision" in all_warnings
    if both_verified:
        assert len(validator.warnings) == 2
        assert "multiple verified assets share display_denom 'zig' (2 verified)." in all_warnings.lower()


def test_warn_on_display_collisions_ignores_schema_key_in_payload(
    two_colliding_zig_assets: tuple[AssetValidator, Path, Path],
) -> None:
    """_warn_on_display_collisions pops $schema from payload so it doesn't interfere with collision indexing."""
    # Arrange: overwrite files on disk to include $schema (collision func re-reads from disk)
    validator, file1, file2 = two_colliding_zig_assets
    for f in (file1, file2):
        data = json.loads(f.read_text(encoding="utf-8"))
        data["$schema"] = "../../schemas/asset.native.schema.json"
        f.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Act
    validator._warn_on_display_collisions()

    # Assert: $schema doesn't break collision detection — collision still found
    assert len(validator.warnings) == 1
    assert "display_denom collision for 'zig': 2 assets" in validator.warnings[0]


def test_warn_on_display_collisions_skips_file_on_read_exception(
    two_colliding_zig_assets: tuple[AssetValidator, Path, Path],
    assets_dir: Path,
) -> None:
    """When one entry in asset_ids points to a missing file, that entry is skipped and the rest are still processed."""
    # Arrange: add a third entry pointing to a nonexistent path; should be skipped, not crash
    validator, file1, file2 = two_colliding_zig_assets
    validator.asset_ids["mainnet"]["nonexistent"] = str(assets_dir / "native" / "nonexistent.json")

    # Act
    validator._warn_on_display_collisions()

    # Assert: nonexistent file skipped, collision between the two real files still detected
    assert len(validator.warnings) == 1
    assert "display_denom collision for 'zig': 2 assets" in validator.warnings[0]


def test_warn_on_display_collisions_skips_empty_display_denom(
    validator: AssetValidator,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """Assets with empty or missing display_denom are skipped and do not contribute to the collision index."""
    # Arrange: one valid asset with display_denom "ZIG"
    data_zig = _make_native_asset(
        valid_native_asset_data,
        asset_id="zig",
        display_denom="ZIG",
        symbol="ZIG",
        name="ZIG Token",
        base_denom="uzig",
    )
    file_zig = assets_dir / "native" / "zig.mainnet.json"
    file_zig.write_text(json.dumps(data_zig, indent=2), encoding="utf-8")
    validator.validate_asset_file(file_zig)

    # Add a file with display_denom "" manually to asset_ids (bypasses Pydantic validation)
    file_empty = assets_dir / "native" / "empty_display.mainnet.json"
    file_empty.write_text(
        json.dumps({"network": "mainnet", "asset_id": "empty_display", "display_denom": ""}, indent=2),
        encoding="utf-8",
    )
    validator.asset_ids["mainnet"]["empty_display"] = str(file_empty)

    # Act:
    validator._warn_on_display_collisions()

    # Assert: no collision with empty display_denom
    assert len(validator.warnings) == 0


def test_warn_on_display_collisions_skips_missing_display_denom_key(
    validator: AssetValidator,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """When display_denom key is entirely absent from the payload, the asset is skipped."""
    # Arrange: one valid ZIG asset, plus a file with no display_denom key at all
    data_zig = _make_native_asset(
        valid_native_asset_data,
        asset_id="zig",
        display_denom="ZIG",
        symbol="ZIG",
        name="ZIG Token",
        base_denom="uzig",
    )
    file_zig = assets_dir / "native" / "zig.mainnet.json"
    file_zig.write_text(json.dumps(data_zig, indent=2), encoding="utf-8")
    validator.validate_asset_file(file_zig)

    # Manually add an asset whose file has no display_denom key (bypasses Pydantic)
    file_no_key = assets_dir / "native" / "no_display_key.mainnet.json"
    file_no_key.write_text(
        json.dumps({"network": "mainnet", "asset_id": "no_display_key"}, indent=2),
        encoding="utf-8",
    )
    validator.asset_ids["mainnet"]["no_display_key"] = str(file_no_key)

    # Act
    validator._warn_on_display_collisions()

    # Assert: missing key treated as empty → skipped, no collision
    assert len(validator.warnings) == 0


def test_warn_on_display_collisions_strips_whitespace_from_display_denom(
    validator: AssetValidator,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """display_denom with leading/trailing whitespace is stripped before comparison."""
    # Arrange: two assets — one with "ZIG", one with " ZIG " (should collide after strip)
    data1 = _make_native_asset(
        valid_native_asset_data,
        asset_id="first",
        display_denom="ZIG",
        symbol="ZIG",
        name="First Token",
        base_denom="ufirst",
    )
    file1 = assets_dir / "native" / "first.mainnet.json"
    file1.write_text(json.dumps(data1, indent=2), encoding="utf-8")
    validator.validate_asset_file(file1)

    # Manually write a file with padded display_denom (bypasses Pydantic)
    padded_data = dict(data1)
    padded_data["asset_id"] = "second"
    padded_data["base_denom"] = "usecond"
    padded_data["display_denom"] = "  ZIG  "
    padded_data["name"] = "Second Token"
    padded_data["denom_units"] = [
        {"denom": "usecond", "exponent": 0},
        {"denom": "second", "exponent": 6},
    ]
    file2 = assets_dir / "native" / "second.mainnet.json"
    file2.write_text(json.dumps(padded_data, indent=2), encoding="utf-8")
    validator.asset_ids["mainnet"]["second"] = str(file2)

    # Act
    validator._warn_on_display_collisions()

    # Assert: whitespace stripped → "ZIG" and " ZIG " collide
    assert len(validator.warnings) == 1
    assert "display_denom collision for 'zig'" in validator.warnings[0]


def test_warn_on_display_collisions_one_verified_no_extra_warning(
    two_colliding_zig_assets: tuple[AssetValidator, Path, Path],
) -> None:
    """When two assets collide but only one is verified, no 'multiple verified' warning is added."""
    # Arrange: overwrite first file to add is_verified=True, second stays unverified
    validator, file1, file2 = two_colliding_zig_assets
    data1 = json.loads(file1.read_text(encoding="utf-8"))
    data1["is_verified"] = True
    file1.write_text(json.dumps(data1, indent=2), encoding="utf-8")

    # Act
    validator._warn_on_display_collisions()

    # Assert: collision warning present, but NO "multiple verified" warning
    assert len(validator.warnings) == 1
    assert "display_denom collision" in validator.warnings[0]


def test_warn_on_display_collisions_per_network(
    two_colliding_zig_assets: tuple[AssetValidator, Path, Path],
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
) -> None:
    """Collisions are reported per network; mainnet collision does not mix with testnet assets."""
    # Arrange: fixture provides two mainnet ZIG assets; add a testnet ZIG asset (single → no collision)
    validator, file1, file2 = two_colliding_zig_assets
    data_test = _make_native_asset(
        valid_native_asset_data,
        asset_id="test1",
        display_denom="ZIG",
        symbol="ZIG",
        name="ZIG Token",
        base_denom="utest1",
    )
    data_test["network"] = "testnet"
    file_test = assets_dir / "native" / "test1.testnet.json"
    file_test.write_text(json.dumps(data_test, indent=2), encoding="utf-8")
    validator.validate_asset_file(file_test)

    # Act
    validator._warn_on_display_collisions()

    # Assert: only mainnet collision reported — testnet has one asset so no collision
    assert len(validator.warnings) == 1
    assert "[mainnet] display_denom collision for 'zig': 2 assets -> " in validator.warnings[0]
    assert str(file1) in validator.warnings[0]
    assert str(file2) in validator.warnings[0]


######################################################################
# Tests for print_results
######################################################################

# ----------------
# Positive tests for print_results
# ----------------

def test_print_results_success_no_network_filter(
    validator: AssetValidator,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """print_results prints success message when no errors or warnings."""
    # Act: no errors or warnings on this validator
    validator.print_results()

    # Assert: success message printed, no error/warning sections
    out, _ = capsys.readouterr()
    assert "All assets validated successfully!" in out
    assert "Validation Errors:" not in out
    assert "Validation Warnings:" not in out


def test_print_results_success_with_network_filter(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """print_results includes network in success message when network_filter is set."""
    # Arrange: validator with network_filter="mainnet"
    v = AssetValidator(tmp_path, network_filter="mainnet")

    # Act
    v.print_results()

    # Assert: success message includes the network name
    out, _ = capsys.readouterr()
    assert "All assets validated successfully for network 'mainnet'!" in out


def test_print_results_warnings_only(
    validator: AssetValidator,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """print_results prints warnings and no-errors message when only warnings present."""
    # Arrange: add a warning but no errors
    validator.warnings.append("Some warning")

    # Act
    validator.print_results()

    # Assert: warnings section shown, no errors section, "no errors found" message
    out, _ = capsys.readouterr()
    assert "Validation Warnings:" in out
    assert "⚠️" in out
    assert "Some warning" in out
    assert "No validation errors found (warnings may be present)" in out
    assert "Validation Errors:" not in out


def test_print_results_shows_protection_stats_when_config_loaded(
    validator: AssetValidator,
    protected_assets_config_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """print_results prints protection stats line when _protected_config is loaded."""
    # Arrange: load config so _protected_config is set, then set stats counters
    validator._load_protected_config()
    validator.protection_checked = 3
    validator.protection_violations = 1
    validator.protection_warnings = 2

    # Act
    validator.print_results()

    # Assert: stats line includes all three counters
    out, _ = capsys.readouterr()
    assert "Protection validation:" in out
    assert "3 assets checked" in out
    assert "1 violations" in out
    assert "2 warnings" in out


def test_print_results_protection_stats_zero_counters(
    validator: AssetValidator,
    protected_assets_config_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """print_results shows stats line with all zeroes when config loaded but no assets checked."""
    # Arrange: load config but don't validate any assets — counters stay at 0
    validator._load_protected_config()

    # Act
    validator.print_results()

    # Assert: stats line with zeroes AND success message (no errors/warnings)
    out, _ = capsys.readouterr()
    assert "Protection validation: 0 assets checked, 0 violations, 0 warnings" in out
    assert "All assets validated successfully!" in out


def test_print_results_multiple_errors_each_printed(
    validator: AssetValidator,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """print_results prints each error on its own line with ❌ prefix."""
    # Arrange: add three errors
    validator.errors.append("file1.json: Invalid JSON")
    validator.errors.append("file2.json: Missing network")
    validator.errors.append("file3.json: Unknown asset type")

    # Act
    validator.print_results()

    # Assert: all three errors appear in output
    out, _ = capsys.readouterr()
    assert "❌ file1.json: Invalid JSON" in out
    assert "❌ file2.json: Missing network" in out
    assert "❌ file3.json: Unknown asset type" in out


def test_print_results_multiple_warnings_each_printed(
    validator: AssetValidator,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """print_results prints each warning on its own line with ⚠️ prefix."""
    # Arrange: add two warnings
    validator.warnings.append("warning one")
    validator.warnings.append("warning two")

    # Act
    validator.print_results()

    # Assert: both warnings appear in output
    out, _ = capsys.readouterr()
    assert "⚠️  warning one" in out
    assert "⚠️  warning two" in out


# ----------------
# Negative tests for print_results
# ----------------

def test_print_results_prints_errors(
    validator: AssetValidator,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """print_results prints errors when present."""
    # Arrange: add one error
    validator.errors.append("path/to/file.json: Invalid JSON")

    # Act
    validator.print_results()

    # Assert: errors section shown with ❌ prefix, no success message
    out, _ = capsys.readouterr()
    assert "Validation Errors:" in out
    assert "❌" in out
    assert "path/to/file.json: Invalid JSON" in out
    assert "All assets validated successfully" not in out


def test_print_results_errors_and_warnings(
    validator: AssetValidator,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """print_results prints both errors and warnings when present."""
    # Arrange: add one error and one warning
    validator.errors.append("error one")
    validator.warnings.append("warning one")

    # Act
    validator.print_results()

    # Assert: both sections shown, no success or "no errors" message
    out, _ = capsys.readouterr()
    assert "Validation Errors:" in out
    assert "error one" in out
    assert "Validation Warnings:" in out
    assert "warning one" in out
    assert "All assets validated successfully" not in out
    assert "No validation errors found" not in out


######################################################################
# Tests for main
######################################################################

# ----------------
# Positive tests for main
# ----------------

def test_main_success(
    tmp_path: Path,
    protected_assets_config_file: Path,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main exits 0 when validation passes."""
    # Arrange: write a valid asset and set CLI args
    (assets_dir / "native" / "zig.mainnet.json").write_text(
        json.dumps(valid_native_asset_data, indent=2), encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["validate_assets", "--repo-root", str(tmp_path)])

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: clean exit
    assert exc.value.code == 0


def test_main_default_repo_root_uses_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main uses current working directory when --repo-root is not passed."""
    # Arrange: set cwd to tmp_path, create config and empty asset dirs there
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "protected_assets.json").write_text(
        json.dumps({
            "assets": [{"symbol": "USDC", "name": "USD Coin", "allowed_types": ["ibc"],
                        "expected_origin_chains": ["noble"], "similar_patterns": [], "description": ""}],
            "config": {},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["validate_assets"])

    # Act: no --repo-root flag → defaults to "."
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: resolves cwd as repo root and exits cleanly
    assert exc.value.code == 0


def test_main_with_network_filter_exits_zero(
    tmp_path: Path,
    protected_assets_config_file: Path,
    assets_dir: Path,
    valid_native_asset_data: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main exits 0 when --network filter is passed and matching assets are valid."""
    # Arrange: write a mainnet asset and pass --network mainnet
    (assets_dir / "native" / "zig.mainnet.json").write_text(
        json.dumps(valid_native_asset_data, indent=2), encoding="utf-8"
    )
    monkeypatch.setattr(
        sys, "argv", ["validate_assets", "--repo-root", str(tmp_path), "--network", "mainnet"]
    )

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: clean exit with network filter applied
    assert exc.value.code == 0


def test_main_with_warn_only_exits_zero_on_protection_violation(
    tmp_path: Path,
    config_dir: Path,
    assets_dir: Path,
    valid_factory_asset_data: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main exits 0 with --warn-only even when a protected-asset violation occurs."""
    # Arrange: protect PANDA as an IBC-only symbol; factory asset uses PANDA → violation downgraded to warning
    protected = {
        "assets": [
            {
                "symbol": "PANDA",
                "name": "Panda Token",
                "allowed_types": ["ibc"],
                "expected_origin_chains": ["noble"],
                "similar_patterns": [],
                "description": "",
            }
        ],
        "config": {},
    }
    (config_dir / "protected_assets.json").write_text(json.dumps(protected), encoding="utf-8")
    base = valid_factory_asset_data["asset_id"]
    (assets_dir / "factory" / f"{base}.json").write_text(
        json.dumps(valid_factory_asset_data, indent=2), encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["validate_assets", "--repo-root", str(tmp_path), "--warn-only"])

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: violation downgraded to warning by --warn-only → exit 0
    assert exc.value.code == 0


# ----------------
# Negative tests for main
# ----------------

def test_main_repo_root_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main exits 1 when repo root does not exist."""
    # Arrange: point to a nonexistent directory
    monkeypatch.setattr(sys, "argv", ["validate_assets", "--repo-root", "/nonexistent/path/12345"])

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: exits 1 with error message about missing repo root
    assert exc.value.code == 1
    out, _ = capsys.readouterr()
    assert "Error: Repository root does not exist: /nonexistent/path/12345" in out


def test_main_exits_one_when_validation_fails(
    tmp_path: Path,
    protected_assets_config_file: Path,
    assets_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main exits 1 when one or more asset files fail validation."""
    # Arrange: write a malformed JSON file
    bad_file = assets_dir / "native" / "bad.mainnet.json"
    bad_file.write_text("{ broken", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["validate_assets", "--repo-root", str(tmp_path)])

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: validation failure → exit 1 with error output
    assert exc.value.code == 1
    out, _ = capsys.readouterr()
    assert "Validation Errors:" in out
    assert f"{bad_file}: Invalid JSON:" in out


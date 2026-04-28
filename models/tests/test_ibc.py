"""Tests for IBCAsset model."""

from typing import Any, Dict

import pytest
from pydantic import HttpUrl, ValidationError

from models import IBCAsset, IBCChannel, IBCTrace, NativeTrace
from . import check_model_error

######################################################################
# Fixtures
######################################################################

HASH = "6490A7EAB61059BFC1CDDEB05917DD70BDF3A611654162A1A47DB930D40D8AF4"


@pytest.fixture
def ibc_asset_data() -> Dict[str, Any]:
    """Fixture providing valid IBCAsset data with all fields (inherited + IBC-specific)."""
    return {
        "$schema": "../../schemas/asset.ibc.schema.json",
        "network": "mainnet",
        "asset_id": f"ibc/{HASH}",
        "order": 1,
        "type": "ibc",
        "symbol": "USDC",
        "name": "Noble USDC",
        "decimals": 6,
        "denom_units": None,
        "display_denom": "usdc",
        "description": "Noble USDC bridged to ZIGChain",
        "extended_description": "IBC-wrapped USDC from Noble chain.",
        "keywords": ["usdc", "noble", "ibc"],
        "images": [{"png": "https://raw.githubusercontent.com/test/usdc.png"}],
        "logo_uris": {"png": "https://raw.githubusercontent.com/test/logo.png"},
        "socials": {
            "website": "https://example.com",
            "x": "https://x.com/example",
        },
        "coingecko_id": "usd-coin",
        "is_verified": True,
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
def ibc_asset_data_minimal() -> Dict[str, Any]:
    """Fixture providing minimal valid IBCAsset data (required fields only)."""
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


######################################################################
# Positive tests for IBCAsset models.
######################################################################

# ----------------
# Positive tests for IBCAsset class
# ----------------


def test_ibc_asset(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset class with all fields; assert field count to detect model changes."""
    asset = IBCAsset(**ibc_asset_data)
    assert len(IBCAsset.model_fields) == 24

    # Inherited from AssetBase
    assert asset.schema_ref == ibc_asset_data["$schema"]
    assert asset.network == ibc_asset_data["network"]
    assert asset.asset_id == ibc_asset_data["asset_id"]
    assert asset.order == ibc_asset_data["order"]
    assert asset.type == ibc_asset_data["type"]
    assert asset.symbol == ibc_asset_data["symbol"]
    assert asset.name == ibc_asset_data["name"]
    assert asset.decimals == ibc_asset_data["decimals"]
    assert asset.denom_units == ibc_asset_data["denom_units"]
    assert asset.display_denom == ibc_asset_data["display_denom"]
    assert asset.description == ibc_asset_data["description"]
    assert asset.extended_description == ibc_asset_data["extended_description"]
    assert asset.keywords == ibc_asset_data["keywords"]
    assert len(asset.images) == len(ibc_asset_data["images"])
    assert str(asset.logo_uris.png) == ibc_asset_data["logo_uris"]["png"]
    assert str(asset.socials.website) == str(
        HttpUrl(ibc_asset_data["socials"]["website"])
    )
    assert str(asset.socials.x) == ibc_asset_data["socials"]["x"]
    assert asset.coingecko_id == ibc_asset_data["coingecko_id"]
    assert asset.is_verified == ibc_asset_data["is_verified"]

    # IBC-specific
    assert asset.base_denom == ibc_asset_data["base_denom"]
    assert asset.hash == ibc_asset_data["hash"]
    assert asset.origin_chain == ibc_asset_data["origin_chain"]
    assert asset.origin_denom == ibc_asset_data["origin_denom"]
    assert len(asset.traces) == len(ibc_asset_data["traces"])
    first_trace_data = ibc_asset_data["traces"][0]
    assert asset.traces[0].chain_name == first_trace_data["chain_name"]
    assert asset.traces[0].base_denom == first_trace_data["base_denom"]
    assert asset.traces[0].path == first_trace_data["path"]
    assert len(asset.channels) == len(ibc_asset_data["channels"])
    for i, ch in enumerate(asset.channels):
        assert ch.zigchain_channel == ibc_asset_data["channels"][i]["zigchain_channel"]
        assert (
            ch.counterparty_chain == ibc_asset_data["channels"][i]["counterparty_chain"]
        )
        assert (
            ch.counterparty_channel
            == ibc_asset_data["channels"][i]["counterparty_channel"]
        )


def test_ibc_asset_minimal(
    ibc_asset_data_minimal: Dict[str, Any],
) -> None:
    """Test IBCAsset class with only required fields (optional inherited fields default to None)."""
    asset = IBCAsset(**ibc_asset_data_minimal)
    assert asset.network == ibc_asset_data_minimal["network"]
    assert asset.asset_id == ibc_asset_data_minimal["asset_id"]
    assert asset.type == ibc_asset_data_minimal["type"]
    assert asset.symbol == ibc_asset_data_minimal["symbol"]
    assert asset.name == ibc_asset_data_minimal["name"]
    assert asset.decimals == ibc_asset_data_minimal["decimals"]
    assert asset.display_denom == ibc_asset_data_minimal["display_denom"]
    assert asset.base_denom == ibc_asset_data_minimal["base_denom"]
    assert asset.hash == ibc_asset_data_minimal["hash"]
    assert asset.origin_chain == ibc_asset_data_minimal["origin_chain"]
    assert asset.origin_denom == ibc_asset_data_minimal["origin_denom"]
    assert len(asset.traces) == len(ibc_asset_data_minimal["traces"])
    assert len(asset.channels) == len(ibc_asset_data_minimal["channels"])
    assert asset.schema_ref is None
    assert asset.order is None
    assert asset.denom_units is None
    assert asset.description is None
    assert asset.extended_description is None
    assert asset.keywords is None
    assert asset.images is None
    assert asset.logo_uris is None
    assert asset.socials is None
    assert asset.coingecko_id is None
    assert asset.is_verified is None


# NOTE: Inherited AssetBase fields (network, symbol, name, decimals, order,
# display_denom, description, extended_description, keywords, images, logo_uris,
# socials, coingecko_id, is_verified) are tested in test_base.py.
# Only IBC-specific constraints and overrides are tested here.

# ----------------
# Positive tests for IBCAsset.asset_id field (inherited)
# ----------------


@pytest.mark.parametrize(
    "asset_id_hash",
    [
        HASH,  # fixture default
        "0" * 64,  # all zeros
        "f" * 64,  # lowercase hex
        "A" * 64,  # uppercase hex
        "a1B2c3D4e5F67890" * 4,  # mixed case (64 chars)
    ],
)
def test_ibc_asset_asset_id_valid(
    ibc_asset_data: Dict[str, Any],
    asset_id_hash: str,
) -> None:
    """Test IBCAsset.asset_id with valid ibc/<64 hex> values; must align with hash and base_denom."""
    asset_id = f"ibc/{asset_id_hash}"
    ibc_asset_data["asset_id"] = asset_id
    ibc_asset_data["hash"] = asset_id_hash
    ibc_asset_data["base_denom"] = asset_id
    ibc_asset_data["traces"][0]["base_denom"] = asset_id
    asset = IBCAsset(**ibc_asset_data)
    assert asset.asset_id == asset_id


# ----------------
# Positive test for IBCAsset.type field
# ----------------


def test_ibc_asset_type_valid(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.type accepts literal 'ibc'."""
    ibc_asset_data["type"] = "ibc"
    asset = IBCAsset(**ibc_asset_data)
    assert asset.type == "ibc"


def test_ibc_asset_type_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.type missing defaults to 'ibc'."""
    del ibc_asset_data["type"]
    asset = IBCAsset(**ibc_asset_data)
    assert asset.type == "ibc"


# ----------------
# Positive test for IBCAsset.denom_units field (inherited)
# ----------------


@pytest.mark.parametrize(
    "denom_units",
    [
        None,
        [{"denom": f"ibc/{HASH}", "exponent": 0}],  # base only
        [
            {"denom": f"ibc/{HASH}", "exponent": 0},
            {"denom": "usdc", "exponent": 6},
        ],  # base + display
    ],
)
def test_ibc_asset_denom_units_valid(
    ibc_asset_data: Dict[str, Any],
    denom_units: Any,
) -> None:
    """Test IBCAsset.denom_units with valid values (None or list of DenomUnit)."""
    if denom_units is None:
        ibc_asset_data["denom_units"] = None
    else:
        ibc_asset_data["denom_units"] = denom_units
    asset = IBCAsset(**ibc_asset_data)
    if denom_units is None:
        assert asset.denom_units is None
    else:
        assert asset.denom_units is not None
        assert len(asset.denom_units) == len(denom_units)
        for i, expected in enumerate(denom_units):
            assert asset.denom_units[i].denom == expected["denom"]
            assert asset.denom_units[i].exponent == expected["exponent"]


# ----------------
# Positive tests for IBCAsset.base_denom field
# ----------------


@pytest.mark.parametrize(
    "hash_value",
    [
        HASH,
        "A" * 64,
        "0" * 64,  # all zeros
        "F" * 64,
        "a" * 64,  # lowercase also valid
        "1" * 64,  # number
    ],
)
def test_ibc_asset_base_denom_valid(
    ibc_asset_data: Dict[str, Any],
    hash_value: str,
) -> None:
    """Test IBCAsset.base_denom field with valid values."""
    base_denom = f"ibc/{hash_value}"
    ibc_asset_data["base_denom"] = base_denom
    ibc_asset_data["asset_id"] = base_denom
    ibc_asset_data["hash"] = hash_value
    ibc_asset_data["traces"][0]["base_denom"] = base_denom
    asset = IBCAsset(**ibc_asset_data)
    assert asset.base_denom == base_denom


# ----------------
# Positive tests for IBCAsset.hash field
# ----------------


@pytest.mark.parametrize(
    "hash_value",
    [
        HASH,
        "A" * 64,
        "0" * 64,  # number
        "F" * 64,
        "a" * 64,  # lowercase
        "f" * 64,
    ],
)
def test_ibc_asset_hash_valid(
    ibc_asset_data: Dict[str, Any],
    hash_value: str,
) -> None:
    """Test IBCAsset.hash field with valid values."""
    base_denom = f"ibc/{hash_value}"
    ibc_asset_data["hash"] = hash_value
    ibc_asset_data["base_denom"] = base_denom
    ibc_asset_data["asset_id"] = base_denom
    ibc_asset_data["traces"][0]["base_denom"] = base_denom
    asset = IBCAsset(**ibc_asset_data)
    assert asset.hash == hash_value


# ----------------
# Positive tests for IBCAsset.origin_chain field
# ----------------


@pytest.mark.parametrize(
    "origin_chain",
    [
        "noble",
        "cosmos",
        "osmosis",
        "zigchain",
        "ethereum",
        "a",  # min length
        "a" * 64,  # max length
        "chain-1",  # hyphen
    ],
)
def test_ibc_asset_origin_chain_valid(
    ibc_asset_data: Dict[str, Any],
    origin_chain: str,
) -> None:
    """Test IBCAsset.origin_chain field with valid values."""
    ibc_asset_data["origin_chain"] = origin_chain
    asset = IBCAsset(**ibc_asset_data)
    assert asset.origin_chain == origin_chain


# ----------------
# Positive tests for IBCAsset.origin_denom field
# ----------------


@pytest.mark.parametrize(
    "origin_denom",
    [
        "uusdc",
        "uatom",
        "uosmo",
        "a" * 128,  # max length
        "a",  # min length
        "OriginDenom",  # mixed case
        "123",  # starts with digit (EVM-like)
    ],
)
def test_ibc_asset_origin_denom_valid(
    ibc_asset_data: Dict[str, Any],
    origin_denom: str,
) -> None:
    """Test IBCAsset.origin_denom field with valid values."""
    ibc_asset_data["origin_denom"] = origin_denom
    asset = IBCAsset(**ibc_asset_data)
    assert asset.origin_denom == origin_denom


# ----------------
# Positive tests for IBCAsset.traces field
# ----------------

def test_ibc_asset_traces_valid(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.traces accepts a valid single-entry IBCTrace list."""
    asset = IBCAsset(**ibc_asset_data)
    assert len(asset.traces) == 1
    assert isinstance(asset.traces[0], IBCTrace)
    assert asset.traces[0].type == ibc_asset_data["traces"][0]["type"]
    assert asset.traces[0].chain_name == ibc_asset_data["traces"][0]["chain_name"]
    assert asset.traces[0].base_denom == ibc_asset_data["traces"][0]["base_denom"]
    assert asset.traces[0].path == ibc_asset_data["traces"][0]["path"]


# ----------------
# Positive tests for IBCAsset.channels field
# ----------------

def test_ibc_asset_channels_valid(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.channels accepts a valid single-entry IBCChannel list."""
    asset = IBCAsset(**ibc_asset_data)
    assert len(asset.channels) == 1
    assert isinstance(asset.channels[0], IBCChannel)
    assert asset.channels[0].zigchain_channel == ibc_asset_data["channels"][0]["zigchain_channel"]
    assert asset.channels[0].counterparty_chain == ibc_asset_data["channels"][0]["counterparty_chain"]
    assert asset.channels[0].counterparty_channel == ibc_asset_data["channels"][0]["counterparty_channel"]


######################################################################
# Negative tests for IBCAsset models.
######################################################################

# ----------------
# Negative test for IBCAsset class
# ----------------


def test_ibc_asset_extra_forbidden(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset rejects unknown fields (model_config extra='forbid')."""
    ibc_asset_data["unknown_field"] = "value"
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "extra_forbidden",
                "loc": ("unknown_field",),
                "msg": "Extra inputs are not permitted",
            }
        ],
    )


# ----------------
# Negative tests for IBCAsset.type field
# ----------------


@pytest.mark.parametrize(
    "asset_type",
    [
        "native",  # different type
        "IBC",  # capitalized
        "valid",  # non 'ibc' string
        "",  # empty str
        123,  # int
        ["ibc"],  # list
        {"type": "ibc"},  # dict
        True,  # bool
        None,  # none
    ],
)
def test_ibc_asset_type_bad_type(
    ibc_asset_data: Dict[str, Any],
    asset_type: Any,
) -> None:
    """Test IBCAsset.type must be literal 'ibc'."""
    ibc_asset_data["type"] = asset_type
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "literal_error",
                "loc": ("type",),
                "msg": "Input should be 'ibc'",
            }
        ],
    )


# ----------------
# Negative tests for IBCAsset.base_denom field
# ----------------


def test_ibc_asset_base_denom_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.base_denom field is missing."""
    del ibc_asset_data["base_denom"]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("base_denom",),
                "msg": "Field required",
            }
        ],
    )


def test_ibc_asset_base_denom_bad_type_none(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.base_denom field with None value."""
    ibc_asset_data["base_denom"] = None
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("base_denom",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_ibc_asset_base_denom_bad_type_bool(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.base_denom field with bool value."""
    ibc_asset_data["base_denom"] = True
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    # Field-level type validation runs before custom validator
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("base_denom",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_ibc_asset_base_denom_too_short(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.base_denom field is too short."""
    ibc_asset_data["base_denom"] = "ibc/" + "A" * 62
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("base_denom",),
                "msg": "String should have at least 68 characters",
            }
        ],
    )


def test_ibc_asset_base_denom_too_long(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.base_denom field is too long."""
    ibc_asset_data["base_denom"] = "ibc/" + "A" * 65
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("base_denom",),
                "msg": "String should have at most 68 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "base_denom",
    [
        123,  # int
        0,  # int zero
        3.14,  # float
        True,  # bool
        False,  # bool
        ["ibc/" + "A" * 64],  # list
        [],  # empty list
        {"base_denom": "ibc/" + "A" * 64},  # dict
        (),  # empty tuple
        ("ibc/" + "A" * 64,),  # tuple
    ],
)
def test_ibc_asset_base_denom_bad_type(
    ibc_asset_data: Dict[str, Any],
    base_denom: Any,
) -> None:
    """Test IBCAsset.base_denom rejects non-string types."""
    ibc_asset_data["base_denom"] = base_denom
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("base_denom",),
                "msg": "Input should be a valid string",
            }
        ],
    )


@pytest.mark.parametrize(
    "base_denom",
    [
        "invalid" + "A" * 61,  # 68 chars, no ibc/ prefix
        "ibc/" + "G" * 64,  # invalid hex char G
        "ibc/" + "g" * 64,  # invalid hex char g (lowercase)
        "ibc/" + "Z" * 64,  # invalid hex char Z
        "IBC/" + "A" * 64,  # uppercase prefix
        "iBc/" + "A" * 64,  # mixed case prefix
        "ubc/" + "A" * 64,  # typo prefix
        "ibc/" + " " * 64,  # spaces instead of hex
        "ibc/" + "A" * 63 + "G",  # invalid hex in last position
        "ibc/" + "0x" + "A" * 62,  # 0x in hash part
    ],
)
def test_ibc_asset_base_denom_bad_pattern(
    ibc_asset_data: Dict[str, Any],
    base_denom: str,
) -> None:
    """Test IBCAsset.base_denom field with invalid pattern (must be ibc/<64 hex chars>)."""
    ibc_asset_data["base_denom"] = base_denom
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    # Field-level validation (pattern, min_length) runs before custom validator
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_pattern_mismatch",
                "loc": ("base_denom",),
                "msg": "String should match pattern '^ibc/[A-Fa-f0-9]{64}$'",
            }
        ],
    )


# ----------------
# Negative tests for IBCAsset.hash field
# ----------------


def test_ibc_asset_hash_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.hash field is missing."""
    del ibc_asset_data["hash"]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("hash",),
                "msg": "Field required",
            }
        ],
    )


def test_ibc_asset_hash_bad_type_none(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.hash field with None value."""
    ibc_asset_data["hash"] = None
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("hash",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_ibc_asset_hash_bad_type_bool(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.hash field with bool value."""
    ibc_asset_data["hash"] = True
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    # Field-level type validation runs before custom validator
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("hash",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_ibc_asset_hash_too_short(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.hash field is too short."""
    ibc_asset_data["hash"] = "A" * 63
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("hash",),
                "msg": "String should have at least 64 characters",
            }
        ],
    )


def test_ibc_asset_hash_too_long(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.hash field is too long."""
    ibc_asset_data["hash"] = "A" * 65
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("hash",),
                "msg": "String should have at most 64 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "hash_value",
    [
        "G" * 64,  # invalid hex char
        "g" * 64,  # invalid hex char
        "!" * 64,  # invalid chars
    ],
)
def test_ibc_asset_hash_bad_pattern(
    ibc_asset_data: Dict[str, Any],
    hash_value: str,
) -> None:
    """Test IBCAsset.hash field with invalid pattern."""
    ibc_asset_data["hash"] = hash_value
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    # Field-level pattern validation runs before custom validator
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_pattern_mismatch",
                "loc": ("hash",),
                "msg": "String should match pattern '^[A-Fa-f0-9]{64}$'",
            }
        ],
    )


@pytest.mark.parametrize(
    "hash_value",
    [
        123,  # int
        0,  # int zero
        3.14,  # float
        True,  # bool
        False,  # bool
        ["A" * 64],  # list
        [],  # empty list
        {"hash": "A" * 64},  # dict
        (),  # empty tuple
        ("A" * 64,),  # tuple
    ],
)
def test_ibc_asset_hash_bad_type(
    ibc_asset_data: Dict[str, Any],
    hash_value: Any,
) -> None:
    """Test IBCAsset.hash rejects non-string types."""
    ibc_asset_data["hash"] = hash_value
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("hash",),
                "msg": "Input should be a valid string",
            }
        ],
    )


# ----------------
# Negative tests for IBCAsset.origin_chain field
# ----------------


def test_ibc_asset_origin_chain_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.origin_chain field is missing."""
    del ibc_asset_data["origin_chain"]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("origin_chain",),
                "msg": "Field required",
            }
        ],
    )


def test_ibc_asset_origin_chain_bad_type_none(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.origin_chain field with None value."""
    ibc_asset_data["origin_chain"] = None
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("origin_chain",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_ibc_asset_origin_chain_too_short(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.origin_chain field is too short."""
    ibc_asset_data["origin_chain"] = ""
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("origin_chain",),
                "msg": "String should have at least 1 character",
            }
        ],
    )


def test_ibc_asset_origin_chain_too_long(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.origin_chain field is too long."""
    ibc_asset_data["origin_chain"] = "a" * 65
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("origin_chain",),
                "msg": "String should have at most 64 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "origin_chain",
    [
        123,  # int
        0,  # int zero
        3.14,  # float
        True,  # bool
        False,  # bool
        ["noble"],  # list
        [],  # empty list
        {"origin_chain": "noble"},  # dict
        (),  # empty tuple
        ("noble",),  # tuple
    ],
)
def test_ibc_asset_origin_chain_bad_type(
    ibc_asset_data: Dict[str, Any],
    origin_chain: Any,
) -> None:
    """Test IBCAsset.origin_chain rejects non-string types."""
    ibc_asset_data["origin_chain"] = origin_chain
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("origin_chain",),
                "msg": "Input should be a valid string",
            }
        ],
    )


# ----------------
# Negative tests for IBCAsset.origin_denom field
# ----------------


def test_ibc_asset_origin_denom_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.origin_denom field is missing."""
    del ibc_asset_data["origin_denom"]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("origin_denom",),
                "msg": "Field required",
            }
        ],
    )


def test_ibc_asset_origin_denom_bad_type_none(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.origin_denom field with None value."""
    ibc_asset_data["origin_denom"] = None
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("origin_denom",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_ibc_asset_origin_denom_too_short(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.origin_denom field is too short."""
    ibc_asset_data["origin_denom"] = ""
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("origin_denom",),
                "msg": "String should have at least 1 character",
            }
        ],
    )


def test_ibc_asset_origin_denom_too_long(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.origin_denom field is too long."""
    ibc_asset_data["origin_denom"] = "a" * 129
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("origin_denom",),
                "msg": "String should have at most 128 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "origin_denom",
    [
        123,  # int
        0,  # int zero
        3.14,  # float
        True,  # bool
        False,  # bool
        ["uusdc"],  # list
        [],  # empty list
        {"origin_denom": "uusdc"},  # dict
        (),  # empty tuple
        ("uusdc",),  # tuple
    ],
)
def test_ibc_asset_origin_denom_bad_type(
    ibc_asset_data: Dict[str, Any],
    origin_denom: Any,
) -> None:
    """Test IBCAsset.origin_denom rejects non-string types."""
    ibc_asset_data["origin_denom"] = origin_denom
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("origin_denom",),
                "msg": "Input should be a valid string",
            }
        ],
    )


# ----------------
# Negative tests for IBCAsset.traces field
# ----------------


def test_ibc_asset_traces_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.traces field is missing."""
    del ibc_asset_data["traces"]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("traces",),
                "msg": "Field required",
            }
        ],
    )


def test_ibc_asset_traces_empty(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.traces field with empty list."""
    ibc_asset_data["traces"] = []
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "too_short",
                "loc": ("traces",),
                "msg": "List should have at least 1 item after validation, not 0",
            }
        ],
    )


def test_ibc_asset_traces_too_many(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.traces rejects more than 10 entries (max_length=10)."""
    valid_trace = ibc_asset_data["traces"][0]
    ibc_asset_data["traces"] = [valid_trace] * 11
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "too_long",
                "loc": ("traces",),
                "msg": "List should have at most 10 items after validation, not 11",
            }
        ],
    )


def test_ibc_asset_traces_duplicate_entries_rejected(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.traces rejects duplicate entries."""
    valid_trace = ibc_asset_data["traces"][0]
    ibc_asset_data["traces"] = [valid_trace, valid_trace]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": "Value error, traces must not contain duplicate entries",
            }
        ],
    )


def test_ibc_asset_traces_bad_type_none(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.traces field with None value."""
    ibc_asset_data["traces"] = None
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "list_type",
                "loc": ("traces",),
                "msg": "Input should be a valid list",
            }
        ],
    )


@pytest.mark.parametrize(
    "traces",
    [
        "ibc",  # string
        123,  # int
        True,  # bool
        {"type": "ibc"},  # dict
    ],
)
def test_ibc_asset_traces_bad_type(
    ibc_asset_data: Dict[str, Any],
    traces: Any,
) -> None:
    """Test IBCAsset.traces rejects non-list values."""
    ibc_asset_data["traces"] = traces
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "list_type",
                "loc": ("traces",),
                "msg": "Input should be a valid list",
            }
        ],
    )


# ----------------
# Negative tests for IBCAsset.channels field
# ----------------


def test_ibc_asset_channels_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.channels field is missing."""
    del ibc_asset_data["channels"]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("channels",),
                "msg": "Field required",
            }
        ],
    )


def test_ibc_asset_channels_empty(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.channels field with empty list."""
    ibc_asset_data["channels"] = []
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "too_short",
                "loc": ("channels",),
                "msg": "List should have at least 1 item after validation, not 0",
            }
        ],
    )


def test_ibc_asset_channels_too_many(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.channels rejects more than 5 entries (max_length=5)."""
    valid_channel = ibc_asset_data["channels"][0]
    ibc_asset_data["channels"] = [valid_channel] * 6
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "too_long",
                "loc": ("channels",),
                "msg": "List should have at most 5 items after validation, not 6",
            }
        ],
    )


def test_ibc_asset_channels_duplicate_entries_rejected(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.channels rejects duplicate entries."""
    valid_channel = ibc_asset_data["channels"][0]
    ibc_asset_data["channels"] = [valid_channel, valid_channel]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": "Value error, channels must not contain duplicate entries",
            }
        ],
    )


def test_ibc_asset_channels_bad_type_none(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.channels field with None value."""
    ibc_asset_data["channels"] = None
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "list_type",
                "loc": ("channels",),
                "msg": "Input should be a valid list",
            }
        ],
    )


@pytest.mark.parametrize(
    "channels",
    [
        "noble",
        123,
        True,
        {"zigchain_channel": "channel-3"},
    ],
)
def test_ibc_asset_channels_bad_type(
    ibc_asset_data: Dict[str, Any],
    channels: Any,
) -> None:
    """Test IBCAsset.channels rejects non-list values."""
    ibc_asset_data["channels"] = channels
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "list_type",
                "loc": ("channels",),
                "msg": "Input should be a valid list",
            }
        ],
    )


# ----------------
# Negative tests for IBCAsset model validators
# ----------------


def test_ibc_asset_asset_id_must_match_hash(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.asset_id must align with hash."""
    wrong_hash = "A" * 64
    ibc_asset_data["hash"] = wrong_hash
    ibc_asset_data["base_denom"] = f"ibc/{wrong_hash}"
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": f"Value error, asset_id must be 'ibc/{wrong_hash}' derived from hash",
            }
        ],
    )


def test_ibc_asset_base_denom_must_match_hash(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.base_denom must align with hash."""
    wrong_hash = "A" * 64
    ibc_asset_data["hash"] = wrong_hash
    ibc_asset_data["asset_id"] = f"ibc/{wrong_hash}"
    ibc_asset_data["base_denom"] = f"ibc/{HASH}"
    ibc_asset_data["traces"][0]["base_denom"] = f"ibc/{wrong_hash}"
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": f"Value error, base_denom must be 'ibc/{wrong_hash}' derived from hash",
            }
        ],
    )


def test_ibc_asset_asset_id_bad_format(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.asset_id with invalid format."""
    ibc_asset_data["asset_id"] = f"ibc:{HASH}"  # colon instead of slash
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("asset_id",),
                "msg": "Value error, asset_id must match format ibc/<64 hex chars>",
            }
        ],
    )


######################################################################
# Positive tests for IBCTraces models
######################################################################

# ----------------
# Positive tests for IBCTrace class
# ----------------


def test_ibc_trace_valid() -> None:
    """Test IBCTrace class with valid data."""
    trace = IBCTrace(
        type="ibc",
        chain_name="zigchain",
        base_denom=f"ibc/{HASH}",
        path="transfer/channel-3/uusdc",
    )
    assert trace.type == "ibc"
    assert trace.chain_name == "zigchain"
    assert trace.base_denom == f"ibc/{HASH}"
    assert trace.path == "transfer/channel-3/uusdc"


def test_ibc_asset_allows_supplemental_traces(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """IBC assets may include additional non-routing trace metadata entries."""
    ibc_asset_data["traces"].append(
        {
            "type": "synthetic",
            "counterparty": {"chain_name": "forex", "base_denom": "USD"},
            "provider": "Circle",
        }
    )
    asset = IBCAsset(**ibc_asset_data)
    assert len(asset.traces) == 2
    assert asset.traces[1].type == "synthetic"
    assert asset.traces[1].counterparty.chain_name == "forex"
    assert asset.traces[1].counterparty.base_denom == "USD"
    assert asset.traces[1].provider == "Circle"

    # Verify the original IBC hop trace (traces[0]) is still intact
    assert isinstance(asset.traces[0], IBCTrace)
    assert asset.traces[0].chain_name == ibc_asset_data["traces"][0]["chain_name"]
    assert asset.traces[0].base_denom == ibc_asset_data["traces"][0]["base_denom"]

    # Verify the supplemental trace (traces[1]) routed to the correct union arm
    assert isinstance(asset.traces[1], NativeTrace)


# ----------------
# Positive tests for IBCTrace.type field
# ----------------


def test_ibc_traces_type_valid(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace.type is literal 'ibc'."""
    ibc_asset_data["traces"][0]["type"] = "ibc"
    asset = IBCAsset(**ibc_asset_data)
    assert asset.traces[0].type == "ibc"


# ----------------
# Positive tests for IBCTrace.chain_name
# ----------------


@pytest.mark.parametrize(
    "chain_name",
    [
        "zigchain",
        "noble",
        "cosmos",
        "osmosis",
        "a",  # min length
        "a" * 64,  # max length
        "chain-1",  # hyphen
        "ChainName",  # mixed case
        "ethereum",
        "@@@",  # only symbols
        "12345",  # only numbers
        "1zig",  # starting with number
        "!ZIG",  # starting with symbol
        "资产",  # unicode
        "[name]",
    ],
)
def test_ibc_traces_chain_name_valid(
    ibc_asset_data: Dict[str, Any],
    chain_name: str,
) -> None:
    """Test IBCTrace.chain_name with valid values."""
    ibc_asset_data["traces"][0]["chain_name"] = chain_name
    asset = IBCAsset(**ibc_asset_data)
    assert asset.traces[0].chain_name == chain_name


# ----------------
# Positive tests for IBCTrace.base_denom field
# ----------------


@pytest.mark.parametrize(
    "base_denom",
    [
        f"ibc/{HASH}",  # IBC denom format
        "uatom",  # native denom
        "uusdc",  # native denom
        "a",  # min length
        "a" * 128,  # max length
        "ibc/" + "A" * 64,  # uppercase hex
        "stake",  # short native
        "@@@",  # only symbols
        "12345",  # only numbers
        "1zig",  # starting with number
        "!ZIG",  # starting with symbol
        "资产",  # unicode
        "[name]",
    ],
)
def test_ibc_traces_base_denom_valid(
    ibc_asset_data: Dict[str, Any],
    base_denom: str,
) -> None:
    """Test IBCTrace.base_denom with valid values."""
    ibc_asset_data["traces"][0]["base_denom"] = base_denom
    asset = IBCAsset(**ibc_asset_data)
    assert asset.traces[0].base_denom == base_denom


# ----------------
# Positive tests for IBCTrace.path field
# ----------------


@pytest.mark.parametrize(
    "path",
    [
        "transfer/channel-3/uusdc",
        "transfer/channel-0/uatom",
        "transfer/channel-1/ibc/6490A7EAB61059BFC1CDDEB05917DD70BDF3A611654162A1A47DB930D40D8AF4",
        "transfer/channel-42/stake",
    ],
)
def test_ibc_traces_path_valid(
    ibc_asset_data: Dict[str, Any],
    path: str,
) -> None:
    """Test IBCAsset trace path (IBCTrace.path) with valid values (must start with transfer/)."""
    ibc_asset_data["traces"][0]["path"] = path
    asset = IBCAsset(**ibc_asset_data)
    assert asset.traces[0].path == path



# ----------------
# Positive tests for IBCTrace.provider field
# ----------------


def test_ibc_trace_provider_eureka_normalized() -> None:
    """Test IBCTrace.provider accepts eureka and normalizes casing."""
    trace = IBCTrace(
        type="ibc-bridge",
        chain_name="ethereum",
        base_denom="0x0000000000000000000000000000000000000000",
        path="transfer/08-wasm-1369/0x0000000000000000000000000000000000000000",
        provider="Eureka",
    )
    assert trace.provider == "eureka"


def test_ibc_trace_provider_ibc_normalized() -> None:
    """Test IBCTrace.provider accepts IBC and normalizes casing."""
    trace = IBCTrace(
        type="ibc",
        chain_name="zigchain",
        base_denom=f"ibc/{HASH}",
        path="transfer/channel-3/uusdc",
        provider="IBC",
    )
    assert trace.provider == "ibc"


@pytest.mark.parametrize(
    "provider",
    [
        "eureka",
        "ibc",
        "Eureka",  # normalized to lowercase
        "IBC",  # capitalized
        " EUREKA ",  # stripped and lower
    ],
)
def test_ibc_traces_provider_valid(
    ibc_asset_data: Dict[str, Any],
    provider: str,
) -> None:
    """Test IBCTrace.provider with valid values; normalized to lowercase."""
    ibc_asset_data["traces"][0]["provider"] = provider
    asset = IBCAsset(**ibc_asset_data)
    assert asset.traces[0].provider == provider.strip().lower()


def test_ibc_traces_provider_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace.provider defaults to None when key is missing."""
    ibc_asset_data["traces"][0].pop("provider", None)
    asset = IBCAsset(**ibc_asset_data)
    assert asset.traces[0].provider is None


def test_ibc_traces_provider_none(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace.provider accepts None (optional field)."""
    ibc_asset_data["traces"][0]["provider"] = None
    asset = IBCAsset(**ibc_asset_data)
    assert asset.traces[0].provider is None


######################################################################
# Negative tests for IBCTrace model
######################################################################


def test_ibc_asset_traces_must_include_ibc_hop(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Supplemental traces are allowed, but cannot replace required IBC hop trace entries."""
    ibc_asset_data["traces"] = [
        {
            "type": "synthetic",
            "counterparty": {"chain_name": "forex", "base_denom": "USD"},
            "provider": "Circle",
        }
    ]

    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": "Value error, traces must include at least one IBC hop trace entry",
            }
        ],
    )


# ----------------
# Negative tests for IBCTrace.type field
# ----------------


def test_ibc_traces_type_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset trace requires type; missing type raises ValidationError."""
    del ibc_asset_data["traces"][0]["type"]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("traces", 0, "IBCTrace", "type"),
                "msg": "Field required",
            }
        ],
    )


def test_ibc_traces_type_bad_type_bool(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset trace type rejects bool (str field, string_type error)."""
    ibc_asset_data["traces"][0]["type"] = True
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("traces", 0, "IBCTrace", "type"),
                "msg": "Input should be a valid string",
            }
        ],
    )


@pytest.mark.parametrize(
    "trace_type",
    [
        123,  # int
        0,  # int zero
        3.14,  # float
        ["ibc"],  # list
        [],  # empty list
        {"type": "ibc"},  # dict
        (),  # empty tuple
        ("ibc",),  # tuple
        None,
    ],
)
def test_ibc_traces_type_bad_type(
    ibc_asset_data: Dict[str, Any],
    trace_type: Any,
) -> None:
    """Test IBCAsset trace type rejects non-string types."""
    ibc_asset_data["traces"][0]["type"] = trace_type
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("traces", 0, "IBCTrace", "type"),
                "msg": "Input should be a valid string",
            }
        ],
    )


# ----------------
# Negative tests for IBCTrace.chain_name
# ----------------


def test_ibc_traces_chain_name_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace chain_name missing."""
    del ibc_asset_data["traces"][0]["chain_name"]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("traces", 0, "IBCTrace", "chain_name"),
                "msg": "Field required",
            }
        ],
    )


def test_ibc_traces_chain_name_too_short(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace chain_name empty (min_length=1)."""
    ibc_asset_data["traces"][0]["chain_name"] = ""
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("traces", 0, "IBCTrace", "chain_name"),
                "msg": "String should have at least 1 character",
            }
        ],
    )


def test_ibc_traces_chain_name_too_long(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace chain_name over 64 chars (max_length=64)."""
    ibc_asset_data["traces"][0]["chain_name"] = "a" * 65
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("traces", 0, "IBCTrace", "chain_name"),
                "msg": "String should have at most 64 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "chain_name",
    [
        123,  # int
        12.3,  # float
        True,  # bool
        ["zigchain"],  # list
        {"chain_name": "zigchain"},  # dict
        None,
    ],
)
def test_ibc_traces_chain_name_bad_type(
    ibc_asset_data: Dict[str, Any],
    chain_name: Any,
) -> None:
    """Test IBCTrace chain_name rejects non-string types."""
    ibc_asset_data["traces"][0]["chain_name"] = chain_name
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("traces", 0, "IBCTrace", "chain_name"),
                "msg": "Input should be a valid string",
            }
        ],
    )


# ----------------
# Negative tests for IBCTrace.base_denom field
# ----------------


def test_ibc_traces_base_denom_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace base_denom missing."""
    del ibc_asset_data["traces"][0]["base_denom"]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("traces", 0, "IBCTrace", "base_denom"),
                "msg": "Field required",
            }
        ],
    )


def test_ibc_traces_base_denom_bad_type_bool(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace base_denom rejects bool (custom validator)."""
    ibc_asset_data["traces"][0]["base_denom"] = True
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("traces", 0, "IBCTrace", "base_denom"),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_ibc_traces_base_denom_too_short(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace base_denom empty (min_length=1)."""
    ibc_asset_data["traces"][0]["base_denom"] = ""
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("traces", 0, "IBCTrace", "base_denom"),
                "msg": "String should have at least 1 character",
            }
        ],
    )


def test_ibc_traces_base_denom_whitespace_only(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace base_denom rejects whitespace-only (custom validator)."""
    ibc_asset_data["traces"][0]["base_denom"] = "   "
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("traces", 0, "IBCTrace", "base_denom"),
                "msg": "Value error, base_denom must be a non-empty string",
            }
        ],
    )


def test_ibc_traces_base_denom_too_long(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace base_denom over 128 chars (max_length=128)."""
    ibc_asset_data["traces"][0]["base_denom"] = "a" * 129
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("traces", 0, "IBCTrace", "base_denom"),
                "msg": "String should have at most 128 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "base_denom",
    [
        123,  # int
        3.14,  # float
        ["uatom"],  # list
        {"base_denom": "uatom"},  # dict
        None,
    ],
)
def test_ibc_traces_base_denom_bad_type(
    ibc_asset_data: Dict[str, Any],
    base_denom: Any,
) -> None:
    """Test IBCTrace base_denom rejects non-string types."""
    ibc_asset_data["traces"][0]["base_denom"] = base_denom
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("traces", 0, "IBCTrace", "base_denom"),
                "msg": "Input should be a valid string",
            }
        ],
    )


# ----------------
# Negative tests for IBCTrace.path field
# ----------------


def test_ibc_traces_path_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace path missing."""
    del ibc_asset_data["traces"][0]["path"]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("traces", 0, "IBCTrace", "path"),
                "msg": "Field required",
            }
        ],
    )


def test_ibc_traces_path_bad_type_bool(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace path rejects bool (custom validator)."""
    ibc_asset_data["traces"][0]["path"] = True
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("traces", 0, "IBCTrace", "path"),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_ibc_traces_path_too_short(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace path empty (min_length=1)."""
    ibc_asset_data["traces"][0]["path"] = ""
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("traces", 0, "IBCTrace", "path"),
                "msg": "String should have at least 1 character",
            }
        ],
    )


def test_ibc_traces_path_too_long(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace path over 256 chars (max_length=256)."""
    ibc_asset_data["traces"][0]["path"] = "a" * 257
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("traces", 0, "IBCTrace", "path"),
                "msg": "String should have at most 256 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "path",
    [
        123,  # int
        12.3,  # float
        ["transfer/channel-3/uusdc"],  # list
        {"path": "transfer/channel-3/uusdc"},  # dict
    ],
)
def test_ibc_traces_path_bad_type(
    ibc_asset_data: Dict[str, Any],
    path: Any,
) -> None:
    """Test IBCTrace path rejects non-string types."""
    ibc_asset_data["traces"][0]["path"] = path
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("traces", 0, "IBCTrace", "path"),
                "msg": "Input should be a valid string",
            }
        ],
    )

@pytest.mark.parametrize(
    "path",
    [
        "a",  # no transfer/ prefix
        "a" * 256,  # max length but no transfer/ prefix
        "@@@",  # only symbols
        "12345",  # only numbers
        "1zig",  # starting with number
        "!ZIG",  # starting with symbol
        "资产",  # unicode
        "[name]",  # brackets
    ],
)
def test_ibc_traces_path_bad_pattern(
    ibc_asset_data: Dict[str, Any],
    path: str,
) -> None:
    """Test IBCAsset trace path rejects values that don't start with 'transfer/'."""
    ibc_asset_data["traces"][0]["path"] = path
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("traces", 0, "IBCTrace", "path"),
                "msg": "Value error, path must start with 'transfer/'",
            }
        ],
    )

@pytest.mark.parametrize(
    "path",
    [
        "transfer/../etc/passwd",
        "transfer/\x00channel-0",
        "transfer/'; DROP TABLE traces; --",
    ],
)
def test_ibc_traces_path_traversal_rejected(
    ibc_asset_data: Dict[str, Any],
    path: str,
) -> None:
    """Test IBCTrace.path rejects traversal and injection payloads."""
    ibc_asset_data["traces"][0]["path"] = path
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("traces", 0, "IBCTrace", "path"),
                "msg": "Value error, path contains unsafe characters or sequences",
            }
        ],
    )


# ----------------
# Negative tests for IBCTrace.provider field
# ----------------


def test_ibc_traces_provider_bad_type_bool(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace provider rejects bool when provided (str field, string_type)."""
    ibc_asset_data["traces"][0]["provider"] = True
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("traces", 0, "IBCTrace", "provider"),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_ibc_traces_provider_empty_string(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace provider rejects empty string when provided."""
    ibc_asset_data["traces"][0]["provider"] = ""
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("traces", 0, "IBCTrace", "provider"),
                "msg": "Value error, provider must be a non-empty string when provided",
            }
        ],
    )


def test_ibc_traces_provider_whitespace_only(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCTrace provider rejects whitespace-only when provided."""
    ibc_asset_data["traces"][0]["provider"] = "   "
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("traces", 0, "IBCTrace", "provider"),
                "msg": "Value error, provider must be a non-empty string when provided",
            }
        ],
    )


@pytest.mark.parametrize(
    "provider",
    [
        "circle",  # invalid value
        "other",  # invalid value
        "cosmos",  # invalid
    ],
)
def test_ibc_traces_provider_invalid_value(
    ibc_asset_data: Dict[str, Any],
    provider: str,
) -> None:
    """Test IBCTrace provider rejects values other than eureka or ibc."""
    ibc_asset_data["traces"][0]["provider"] = provider
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("traces", 0, "IBCTrace", "provider"),
                "msg": "Value error, provider must be 'eureka' or 'ibc' when provided",
            }
        ],
    )


@pytest.mark.parametrize(
    "provider",
    [
        123,  # int
        ["eureka"],  # list
        {"provider": "eureka"},  # dict
    ],
)
def test_ibc_traces_provider_bad_type(
    ibc_asset_data: Dict[str, Any],
    provider: Any,
) -> None:
    """Test IBCTrace provider rejects non-string types when provided."""
    ibc_asset_data["traces"][0]["provider"] = provider
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("traces", 0, "IBCTrace", "provider"),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_ibc_trace_provider_invalid() -> None:
    """Test IBCTrace.provider rejects unknown values."""
    with pytest.raises(ValidationError) as exc:
        IBCTrace(
            type="ibc",
            chain_name="zigchain",
            base_denom=f"ibc/{HASH}",
            path="transfer/channel-3/uusdc",
            provider="axelar",
        )

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("provider",),
                "msg": "Value error, provider must be 'eureka' or 'ibc' when provided",
            }
        ],
    )


######################################################################
# Positive tests for IBCChannel models
######################################################################

# ----------------
# Positive tests for IBCChannel class
# ----------------


def test_ibc_channel_valid() -> None:
    """Test IBCChannel class with valid data."""
    channel = IBCChannel(
        zigchain_channel="channel-3",
        counterparty_chain="noble",
        counterparty_channel="channel-175",
    )
    assert channel.zigchain_channel == "channel-3"
    assert channel.counterparty_chain == "noble"
    assert channel.counterparty_channel == "channel-175"


def test_ibc_channels_multiples(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset accepts multiple channels; add a second IBCChannel."""
    second_channel = {
        "zigchain_channel": "channel-5",
        "counterparty_chain": "cosmos",
        "counterparty_channel": "channel-200",
    }
    ibc_asset_data["channels"].append(second_channel)
    asset = IBCAsset(**ibc_asset_data)

    assert len(asset.channels) == 2
    assert asset.channels[0].zigchain_channel == "channel-3"
    assert asset.channels[0].counterparty_chain == "noble"
    assert asset.channels[0].counterparty_channel == "channel-175"
    assert asset.channels[1].zigchain_channel == "channel-5"
    assert asset.channels[1].counterparty_chain == "cosmos"
    assert asset.channels[1].counterparty_channel == "channel-200"


# ----------------
# Positive tests for IBCChannel.zigchain_channel
# ----------------


@pytest.mark.parametrize(
    "zigchain_channel",
    [
        "channel-3",
        "channel-0",
        "channel-100",
        "08-wasm-1369",
    ],
)
def test_ibc_channel_zigchain_channel_valid(
    ibc_asset_data: Dict[str, Any],
    zigchain_channel: str,
) -> None:
    """Test IBCChannel.zigchain_channel with valid values."""
    ibc_asset_data["channels"][0]["zigchain_channel"] = zigchain_channel
    asset = IBCAsset(**ibc_asset_data)
    assert asset.channels[0].zigchain_channel == zigchain_channel



# ----------------
# Positive tests for IBCChannel.counterparty_chain
# ----------------


@pytest.mark.parametrize(
    "counterparty_chain",
    [
        "noble",
        "cosmos",
        "osmosis",
        "a",  # min length
        "a" * 64,  # max length
        "chain-1",
        "ethereum",
    ],
)
def test_ibc_channel_counterparty_chain_valid(
    ibc_asset_data: Dict[str, Any],
    counterparty_chain: str,
) -> None:
    """Test IBCChannel.counterparty_chain with valid values when inside IBCAsset."""
    ibc_asset_data["channels"][0]["counterparty_chain"] = counterparty_chain
    asset = IBCAsset(**ibc_asset_data)
    assert asset.channels[0].counterparty_chain == counterparty_chain


# ----------------
# Positive tests for IBCChannel.counterparty_channel
# ----------------


@pytest.mark.parametrize(
    "counterparty_channel",
    [
        "channel-175",
        "channel-0",
        "channel-3",
        "channel-42",
        "08-wasm-100",
    ],
)
def test_ibc_channel_counterparty_channel_valid(
    ibc_asset_data: Dict[str, Any],
    counterparty_channel: str,
) -> None:
    """Test IBCChannel.counterparty_channel with valid channel-N and 08-wasm-N values."""
    ibc_asset_data["channels"][0]["counterparty_channel"] = counterparty_channel
    asset = IBCAsset(**ibc_asset_data)
    assert asset.channels[0].counterparty_channel == counterparty_channel



######################################################################
# Negative tests for IBCChannel models
######################################################################

# ----------------
# Negative tests for IBCChannel.zigchain_channel
# ----------------


def test_ibc_channel_zigchain_channel_bad_type_bool() -> None:
    """Test IBCChannel.zigchain_channel field with bool value."""
    with pytest.raises(ValidationError) as exc:
        IBCChannel(
            zigchain_channel=True,  # type: ignore
            counterparty_chain="noble",
            counterparty_channel="channel-175",
        )

    # Field-level type validation runs before custom validator
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("zigchain_channel",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_ibc_channel_zigchain_channel_empty() -> None:
    """Test IBCChannel.zigchain_channel field with empty string."""
    with pytest.raises(ValidationError) as exc:
        IBCChannel(
            zigchain_channel="",
            counterparty_chain="noble",
            counterparty_channel="channel-175",
        )

    # Field-level min_length validation runs before custom validator
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("zigchain_channel",),
                "msg": "String should have at least 1 character",
            }
        ],
    )


@pytest.mark.parametrize(
    "zigchain_channel",
    [
        123,  # int
        12.3,  # float
        ["channel-3"],  # list
        {"zigchain-channel": "channel"},  # dict
        None,
    ],
)
def test_ibc_channel_zigchain_channel_bad_type(
    ibc_asset_data: Dict[str, Any],
    zigchain_channel: Any,
) -> None:
    """Test IBCChannel.zigchain_channel rejects non-string types when inside IBCAsset."""
    ibc_asset_data["channels"][0]["zigchain_channel"] = zigchain_channel
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("channels", 0, "zigchain_channel"),
                "msg": "Input should be a valid string",
            }
        ],
    )

@pytest.mark.parametrize(
    "zigchain_channel",
    [
        "a",  # no channel- prefix
        "a" * 64,  # max-length string but wrong format
        "channel-2 ",  # trailing space
        "123",  # only numbers
        "@@@",  # only symbols
    ],
)
def test_ibc_channel_zigchain_channel_bad_pattern(
    ibc_asset_data: Dict[str, Any],
    zigchain_channel: str,
) -> None:
    """Test IBCChannel.zigchain_channel rejects values not matching channel-N or 08-wasm-N."""
    ibc_asset_data["channels"][0]["zigchain_channel"] = zigchain_channel
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("channels", 0, "zigchain_channel"),
                "msg": "Value error, channel must match 'channel-<number>' or '08-wasm-<number>' format",
            }
        ],
    )

def test_ibc_channel_zigchain_channel_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCChannel.zigchain_channel missing when inside IBCAsset."""
    del ibc_asset_data["channels"][0]["zigchain_channel"]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("channels", 0, "zigchain_channel"),
                "msg": "Field required",
            }
        ],
    )


# ----------------
# Negative tests for IBCChannel.counterparty_chain
# ----------------


def test_ibc_channel_counterparty_chain_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCChannel.counterparty_chain missing when inside IBCAsset."""
    del ibc_asset_data["channels"][0]["counterparty_chain"]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("channels", 0, "counterparty_chain"),
                "msg": "Field required",
            }
        ],
    )


def test_ibc_channel_counterparty_chain_too_short(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCChannel.counterparty_chain empty (min_length=1)."""
    ibc_asset_data["channels"][0]["counterparty_chain"] = ""
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("channels", 0, "counterparty_chain"),
                "msg": "String should have at least 1 character",
            }
        ],
    )


def test_ibc_channel_counterparty_chain_too_long(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCChannel.counterparty_chain over 64 chars (max_length=64)."""
    ibc_asset_data["channels"][0]["counterparty_chain"] = "a" * 65
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("channels", 0, "counterparty_chain"),
                "msg": "String should have at most 64 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "counterparty_chain",
    [
        123,  # int
        12.3,  # float
        ["noble"],  # list
        {"counterparty_chain": "noble"},  # dict
        None,
        True,  # bool
    ],
)
def test_ibc_channel_counterparty_chain_bad_type(
    ibc_asset_data: Dict[str, Any],
    counterparty_chain: Any,
) -> None:
    """Test IBCChannel.counterparty_chain rejects non-string types when inside IBCAsset."""
    ibc_asset_data["channels"][0]["counterparty_chain"] = counterparty_chain
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("channels", 0, "counterparty_chain"),
                "msg": "Input should be a valid string",
            }
        ],
    )


@pytest.mark.parametrize(
    "counterparty_chain",
    [
        "'; DROP TABLE assets; --",
        "../../../etc/passwd",
        "noble\x00evil",
        "\x01\x02\x03",
    ],
)
def test_ibc_channel_counterparty_chain_malicious_inputs_rejected(
    ibc_asset_data: Dict[str, Any],
    counterparty_chain: str,
) -> None:
    """Test counterparty_chain rejects malicious inputs."""
    ibc_asset_data["channels"][0]["counterparty_chain"] = counterparty_chain
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("channels", 0, "counterparty_chain"),
                "msg": (
                    "Value error, counterparty_chain must start with a lowercase letter "
                    "and contain only lowercase letters, digits, or hyphens"
                ),
            }
        ],
    )


# ----------------
# Negative tests for IBCChannel.counterparty_channel
# ----------------


def test_ibc_channel_counterparty_channel_bad_type_bool() -> None:
    """Test IBCChannel.counterparty_channel field with bool value."""
    with pytest.raises(ValidationError) as exc:
        IBCChannel(
            zigchain_channel="channel-3",
            counterparty_chain="noble",
            counterparty_channel=True,  # type: ignore
        )

    # Field-level type validation runs before custom validator
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("counterparty_channel",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_ibc_channel_counterparty_channel_empty() -> None:
    """Test IBCChannel.counterparty_channel field with empty string."""
    with pytest.raises(ValidationError) as exc:
        IBCChannel(
            zigchain_channel="channel-3",
            counterparty_chain="noble",
            counterparty_channel="",
        )

    # Field-level min_length validation runs before custom validator
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("counterparty_channel",),
                "msg": "String should have at least 1 character",
            }
        ],
    )


def test_ibc_channel_counterparty_channel_missing(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCChannel.counterparty_channel missing when inside IBCAsset."""
    del ibc_asset_data["channels"][0]["counterparty_channel"]
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("channels", 0, "counterparty_channel"),
                "msg": "Field required",
            }
        ],
    )


def test_ibc_channel_counterparty_channel_bad_type_none(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCChannel.counterparty_channel with None when inside IBCAsset."""
    ibc_asset_data["channels"][0]["counterparty_channel"] = None
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("channels", 0, "counterparty_channel"),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_ibc_channel_counterparty_channel_too_short(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCChannel.counterparty_channel empty (min_length=1) when inside IBCAsset."""
    ibc_asset_data["channels"][0]["counterparty_channel"] = ""
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("channels", 0, "counterparty_channel"),
                "msg": "String should have at least 1 character",
            }
        ],
    )


def test_ibc_channel_counterparty_channel_whitespace_only(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCChannel.counterparty_channel rejects whitespace-only (custom validator)."""
    ibc_asset_data["channels"][0]["counterparty_channel"] = "   "
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("channels", 0, "counterparty_channel"),
                "msg": "Value error, channel identifiers must be non-empty strings",
            }
        ],
    )


def test_ibc_channel_counterparty_channel_too_long(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCChannel.counterparty_channel over 64 chars (max_length=64) when inside IBCAsset."""
    ibc_asset_data["channels"][0]["counterparty_channel"] = "a" * 65
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("channels", 0, "counterparty_channel"),
                "msg": "String should have at most 64 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "counterparty_channel",
    [
        123,  # int
        0,  # int zero
        12.3,  # float
        ["channel-175"],  # list
        [],  # empty list
        {"counterparty_channel": "channel-175"},  # dict
        (),  # empty tuple
        ("channel-175",),  # tuple
        True,  # bool
    ],
)
def test_ibc_channel_counterparty_channel_bad_type(
    ibc_asset_data: Dict[str, Any],
    counterparty_channel: Any,
) -> None:
    """Test IBCChannel.counterparty_channel rejects non-string types when inside IBCAsset."""
    ibc_asset_data["channels"][0]["counterparty_channel"] = counterparty_channel
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("channels", 0, "counterparty_channel"),
                "msg": "Input should be a valid string",
            }
        ],
    )


@pytest.mark.parametrize(
    "counterparty_channel",
    [
        "a",  # no channel- prefix
        "a" * 64,  # max-length string but wrong format
        "port-1/channel-2",  # port-prefixed format not accepted
    ],
)
def test_ibc_channel_counterparty_channel_bad_pattern(
    ibc_asset_data: Dict[str, Any],
    counterparty_channel: str,
) -> None:
    """Test IBCChannel.counterparty_channel rejects values not matching channel-N or 08-wasm-N."""
    ibc_asset_data["channels"][0]["counterparty_channel"] = counterparty_channel
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("channels", 0, "counterparty_channel"),
                "msg": "Value error, channel must match 'channel-<number>' or '08-wasm-<number>' format",
            }
        ],
    )

######################################################################
# Bytes tests for IBCAsset models (Phase 4).
######################################################################

# ----------------
# Bytes test for IBCAsset.asset_id (inherited, has reject_bytes_asset_id)
# ----------------


def test_ibc_asset_asset_id_bytes(
    ibc_asset_data: Dict[str, Any],
) -> None:
    """Test IBCAsset.asset_id rejects bytes (reject_bytes_asset_id in base.py, mode='before')."""
    ibc_asset_data["asset_id"] = b"ibc/" + b"A" * 64
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("asset_id",),
                "msg": "Value error, asset_id must be a string, not bytes",
            }
        ],
    )


# ----------------
# Bytes rejection for IBC-specific string fields
# ----------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("base_denom", b"ibc/" + b"A" * 64),
        ("hash", b"A" * 64),
        ("origin_chain", b"noble"),
        ("origin_denom", b"uusdc"),
    ],
)
def test_ibc_asset_string_fields_bytes_rejected(
    ibc_asset_data: Dict[str, Any],
    field: str,
    value: bytes,
) -> None:
    """Test that IBC-specific string fields reject bytes input (strict bytes policy)."""
    ibc_asset_data[field] = value
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (field,),
                "msg": f"Value error, {field} must be a string, not bytes",
            }
        ],
    )


######################################################################
# Deep coverage: origin_chain/origin_denom malicious input rejection
######################################################################


@pytest.mark.parametrize(
    "origin_chain",
    [
        "'; DROP TABLE assets; --",  # SQL injection
        "../../../etc/passwd",  # path traversal
        "noble\x00evil",  # null byte injection
        "\x01\x02\x03",  # control characters
    ],
)
def test_ibc_asset_origin_chain_malicious_inputs_rejected(
    ibc_asset_data: Dict[str, Any],
    origin_chain: str,
) -> None:
    """Test IBCAsset.origin_chain rejects malicious inputs."""
    ibc_asset_data["origin_chain"] = origin_chain
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("origin_chain",),
                "msg": (
                    "Value error, origin_chain must start with a lowercase letter "
                    "and contain only lowercase letters, digits, or hyphens"
                ),
            }
        ],
    )


@pytest.mark.parametrize(
    "origin_denom",
    [
        "'; DROP TABLE assets; --",  # SQL injection
        "../../../etc/passwd",  # path traversal
        "uusdc\x00evil",  # null byte injection
        "\x01\x02\x03",  # control characters
    ],
)
def test_ibc_asset_origin_denom_malicious_inputs_rejected(
    ibc_asset_data: Dict[str, Any],
    origin_denom: str,
) -> None:
    """Test IBCAsset.origin_denom rejects malicious inputs."""
    ibc_asset_data["origin_denom"] = origin_denom
    with pytest.raises(ValidationError) as exc:
        IBCAsset(**ibc_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("origin_denom",),
                "msg": (
                    "Value error, origin_denom must start with a letter or digit "
                    "and contain only letters, digits, or '/:._-'"
                ),
            }
        ],
    )

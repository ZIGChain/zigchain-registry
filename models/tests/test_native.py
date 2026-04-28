"""Tests for NativeAsset model."""

from typing import Any, Dict

import pytest
from pydantic import HttpUrl, ValidationError

from models import DenomUnit, NativeAsset
from . import check_model_error


######################################################################
# Fixtures
######################################################################


@pytest.fixture
def native_asset_data() -> Dict[str, Any]:
    """Fixture providing valid NativeAsset data with all fields (inherited + native-specific)."""
    return {
        "$schema": "../../schemas/asset.native.schema.json",
        "network": "mainnet",
        "asset_id": "zig",
        "order": 1,
        "type": "native",
        "symbol": "ZIG",
        "name": "ZIGChain Native Token",
        "decimals": 6,
        "denom_units": [
            {"denom": "uzig", "exponent": 0},
            {"denom": "zig", "exponent": 6},
        ],
        "display_denom": "ZIG",
        "description": "The native staking token of ZIGChain",
        "extended_description": "ZIGChain (ZIG) is a Layer 1 blockchain focused on unlocking financial opportunities.",
        "keywords": ["zigchain", "native", "staking"],
        "images": [{"png": "https://raw.githubusercontent.com/test/zig.png"}],
        "logo_uris": {"png": "https://raw.githubusercontent.com/test/logo.png"},
        "socials": {
            "website": "https://example.com",
            "x": "https://x.com/zigchain",
        },
        "coingecko_id": "zigchain",
        "is_verified": True,
        "base_denom": "uzig",
        "traces": [
            {
                "type": "additional-mintage",
                "counterparty": {
                    "chain_name": "ethereum",
                    "base_denom": "0xb2617246d0c6c0087f18703d576831899ca94f01",
                },
                "provider": "ZIGChain",
            }
        ],
    }


@pytest.fixture
def native_asset_data_minimal() -> Dict[str, Any]:
    """Fixture providing minimal valid NativeAsset data (required fields only)."""
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


######################################################################
# Positive tests for NativeAsset models.
######################################################################

# ----------------
# Positive tests for NativeAsset class
# ----------------


def test_native_asset(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset class with all fields; assert field count to detect model changes."""
    asset = NativeAsset(**native_asset_data)
    assert len(NativeAsset.model_fields) == 20

    # Inherited from AssetBase
    assert asset.schema_ref == native_asset_data["$schema"]
    assert asset.network == native_asset_data["network"]
    assert asset.asset_id == native_asset_data["asset_id"]
    assert asset.order == native_asset_data["order"]
    assert asset.type == native_asset_data["type"]
    assert asset.symbol == native_asset_data["symbol"]
    assert asset.name == native_asset_data["name"]
    assert asset.decimals == native_asset_data["decimals"]
    assert len(asset.denom_units) == len(native_asset_data["denom_units"])
    for i, unit in enumerate(asset.denom_units):
        assert unit.denom == native_asset_data["denom_units"][i]["denom"]
        assert unit.exponent == native_asset_data["denom_units"][i]["exponent"]
    assert asset.display_denom == native_asset_data["display_denom"]
    assert asset.description == native_asset_data["description"]
    assert asset.extended_description == native_asset_data["extended_description"]
    assert asset.keywords == native_asset_data["keywords"]
    assert len(asset.images) == len(native_asset_data["images"])
    assert str(asset.images[0].png) == native_asset_data["images"][0]["png"]
    assert str(asset.logo_uris.png) == native_asset_data["logo_uris"]["png"]
    assert str(asset.socials.website) == str(
        HttpUrl(native_asset_data["socials"]["website"])
    )
    assert str(asset.socials.x) == native_asset_data["socials"]["x"]
    assert asset.coingecko_id == native_asset_data["coingecko_id"]
    assert asset.is_verified == native_asset_data["is_verified"]

    # Native-specific
    assert asset.base_denom == native_asset_data["base_denom"]
    assert len(asset.traces) == len(native_asset_data["traces"])
    first_trace_data = native_asset_data["traces"][0]
    assert asset.traces[0].type == first_trace_data["type"]
    assert (
        asset.traces[0].counterparty.chain_name
        == first_trace_data["counterparty"]["chain_name"]
    )
    assert (
        asset.traces[0].counterparty.base_denom
        == first_trace_data["counterparty"]["base_denom"]
    )
    assert asset.traces[0].provider == first_trace_data["provider"]


def test_native_asset_minimal(
    native_asset_data_minimal: Dict[str, Any],
) -> None:
    """Test NativeAsset class with only required fields (optional inherited fields default to None)."""
    asset = NativeAsset(**native_asset_data_minimal)
    assert len(NativeAsset.model_fields) == 20
    assert asset.network == native_asset_data_minimal["network"]
    assert asset.asset_id == native_asset_data_minimal["asset_id"]
    assert asset.type == native_asset_data_minimal["type"]
    assert asset.symbol == native_asset_data_minimal["symbol"]
    assert asset.name == native_asset_data_minimal["name"]
    assert asset.decimals == native_asset_data_minimal["decimals"]
    assert asset.display_denom == native_asset_data_minimal["display_denom"]
    assert asset.base_denom == native_asset_data_minimal["base_denom"]
    assert len(asset.denom_units) == len(native_asset_data_minimal["denom_units"])
    for i, ch in enumerate(asset.denom_units):
        assert ch.denom == native_asset_data_minimal["denom_units"][i]["denom"]
        assert ch.exponent == native_asset_data_minimal["denom_units"][i]["exponent"]
    assert asset.schema_ref is None
    assert asset.order is None
    assert asset.description is None
    assert asset.extended_description is None
    assert asset.keywords is None
    assert asset.images is None
    assert asset.logo_uris is None
    assert asset.socials is None
    assert asset.coingecko_id is None
    assert asset.is_verified is None
    assert asset.traces is None


# ----------------
# Positive tests for NativeAsset.network field (inherited)
# ----------------


@pytest.mark.parametrize("network", ["mainnet", "testnet"])
def test_native_asset_network_valid(
    native_asset_data: Dict[str, Any],
    network: str,
) -> None:
    """Test NativeAsset.network field with valid values."""
    native_asset_data["network"] = network
    asset = NativeAsset(**native_asset_data)
    assert asset.network == network


# ----------------
# Positive tests for NativeAsset.type field
# ----------------


def test_native_asset_type_missing(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.type missing defaults to 'native'."""
    del native_asset_data["type"]
    asset = NativeAsset(**native_asset_data)
    assert asset.type == "native"


# ----------------
# Positive tests for NativeAsset.asset_id field
# ----------------


@pytest.mark.parametrize(
    "asset_id",
    [
        "zig",
        "uzig",
        "uatom",
        "a",  # single letter (min length)
        "z",
        "0",  # single digit
        "1",
        "abc123",  # letters and numbers
        "a1b2c3",
        "token0",
        "00",  # digits only
        "123",  # numbers only
        "abcdefgh",  # lowercase only
        "a" * 128,  # max length
        "zzz9",
    ],
)
def test_native_asset_asset_id_valid(
    native_asset_data: Dict[str, Any],
    asset_id: str,
) -> None:
    """Test NativeAsset.asset_id field with valid values (lowercase letters and digits only)."""
    native_asset_data["asset_id"] = asset_id
    asset = NativeAsset(**native_asset_data)
    assert asset.asset_id == asset_id


# ----------------
# Positive tests for NativeAsset.base_denom field
# ----------------


@pytest.mark.parametrize(
    "base_denom",
    [
        "uzig",
        "uatom",
        "uosmo",
        "aaa",  # min length
        "a" * 128,  # max length
        "token:token",
        "token/token",
        "token.token",
        "token-token",
        "token_token",
        "z1/-._",  # all valid characters
    ],
)
def test_native_asset_base_denom_valid(
    native_asset_data: Dict[str, Any],
    base_denom: str,
) -> None:
    """Test NativeAsset.base_denom field with valid values."""
    native_asset_data["base_denom"] = base_denom
    native_asset_data["denom_units"] = [
        {"denom": base_denom, "exponent": 0},
        {"denom": "token", "exponent": 6},
    ]
    asset = NativeAsset(**native_asset_data)
    assert asset.base_denom == base_denom


# ----------------
# Positive tests for NativeAsset.denom_units field
# ----------------


def test_native_asset_denom_units_with_aliases(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.denom_units field with aliases."""
    native_asset_data["denom_units"] = [
        {"denom": "uzig", "exponent": 0, "aliases": ["ZIG", "zigchain"]},
        {"denom": "zig", "exponent": 6},
    ]
    asset = NativeAsset(**native_asset_data)
    assert len(asset.denom_units) == 2
    assert asset.denom_units[0].aliases == ["ZIG", "zigchain"]


def test_native_asset_denom_units_without_aliases(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.denom_units field without aliases."""
    native_asset_data["denom_units"] = [
        {"denom": "uzig", "exponent": 0},
        {"denom": "zig", "exponent": 6},
    ]
    asset = NativeAsset(**native_asset_data)
    assert len(asset.denom_units) == 2
    assert asset.denom_units[0].aliases is None


# ----------------
# Positive tests for NativeAsset.traces field
# ----------------


def test_native_asset_traces_valid(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.traces with valid list of NativeTrace."""
    traces = [
        {
            "type": "additional-mintage",
            "counterparty": {
                "chain_name": "ethereum",
                "base_denom": "0xb2617246d0c6c0087f18703d576831899ca94f01",
            },
            "provider": "ZIGChain",
        }
    ]
    native_asset_data["traces"] = traces
    asset = NativeAsset(**native_asset_data)
    assert len(asset.traces) == 1
    assert asset.traces[0].type == "additional-mintage"
    assert asset.traces[0].counterparty.chain_name == "ethereum"
    assert asset.traces[0].provider == "ZIGChain"


def test_native_asset_traces_none(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.traces accepts None."""
    native_asset_data["traces"] = None
    asset = NativeAsset(**native_asset_data)
    assert asset.traces is None


def test_native_asset_traces_missing(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.traces when key is missing (defaults to None)."""
    del native_asset_data["traces"]
    asset = NativeAsset(**native_asset_data)
    assert asset.traces is None


def test_native_asset_traces_multiple(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.traces with multiple trace entries."""
    traces = [
        {
            "type": "additional-mintage",
            "counterparty": {
                "chain_name": "ethereum",
                "base_denom": "0xb2617246d0c6c0087f18703d576831899ca94f01",
            },
            "provider": "ZIGChain",
        },
        {
            "type": "synthetic",
            "counterparty": {
                "chain_name": "cosmoshub",
                "base_denom": "uatom",
            },
            "provider": "IBC Bridge",
        },
        {
            "type": "bridged",
            "counterparty": {
                "chain_name": "polygon",
                "base_denom": "0x2791bca1f2de4661ed88a30c99a7a9449aa84174",
            },
            "provider": None,
        },
    ]
    native_asset_data["traces"] = traces
    asset = NativeAsset(**native_asset_data)
    assert len(asset.traces) == 3
    assert asset.traces[0].type == "additional-mintage"
    assert asset.traces[0].counterparty.chain_name == "ethereum"
    assert (
        asset.traces[0].counterparty.base_denom
        == "0xb2617246d0c6c0087f18703d576831899ca94f01"
    )
    assert asset.traces[0].provider == "ZIGChain"
    assert asset.traces[1].type == "synthetic"
    assert asset.traces[1].counterparty.chain_name == "cosmoshub"
    assert asset.traces[1].counterparty.base_denom == "uatom"
    assert asset.traces[1].provider == "IBC Bridge"
    assert asset.traces[2].type == "bridged"
    assert asset.traces[2].counterparty.chain_name == "polygon"
    assert (
        asset.traces[2].counterparty.base_denom
        == "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"
    )
    assert asset.traces[2].provider is None



######################################################################
# Negative tests for NativeAsset models.
######################################################################

# ----------------
# Negative test for NativeAsset class
# ----------------


def test_native_asset_extra_forbidden(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset rejects unknown fields (model_config extra='forbid')."""
    native_asset_data["unknown_field"] = "value"
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
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
# Negative tests for NativeAsset.type field
# ----------------


@pytest.mark.parametrize(
    "asset_type",
    [
        "ibc",  # different type
        "NATIVE",  # capitalized
        "valid",  # non 'native' string
        "",  # empty str
        123,  # int
        12.3,  # float
        ["native"],  # list
        {"type": "native"},  # dict
        True,  # bool
        None,  # none
        "资产",  # unicode
        "123",  # numbers
    ],
)
def test_native_asset_type_bad_type(
    native_asset_data: Dict[str, Any],
    asset_type: Any,
) -> None:
    """Test NativeAsset.type must be literal 'native' — rejects bad_type values."""
    native_asset_data["type"] = asset_type
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "literal_error",
                "loc": ("type",),
                "msg": "Input should be 'native'",
            },
        ],
    )



# ----------------
# Negative tests for NativeAsset.asset_id field
# ----------------


def test_native_asset_asset_id_missing(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.asset_id field is missing."""
    del native_asset_data["asset_id"]
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "missing", "loc": ("asset_id",), "msg": "Field required"},
        ],
    )


def test_native_asset_asset_id_bad_type_none(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.asset_id field with None value."""
    native_asset_data["asset_id"] = None
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("asset_id",),
                "msg": "Input should be a valid string",
            },
        ],
    )


def test_native_asset_asset_id_bad_pattern_uppercase(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.asset_id with uppercase letters."""
    native_asset_data["asset_id"] = "ZIG"
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("asset_id",),
                "msg": "Value error, asset_id for native assets must use lowercase letters and digits only",
                "input": "ZIG",
            }
        ],
    )


@pytest.mark.parametrize("asset_id", ["ZIG", "zig!", "zig token", "zig-token", "@@@@"])
def test_native_asset_asset_id_bad_pattern(
    native_asset_data: Dict[str, Any],
    asset_id: str,
) -> None:
    """Test NativeAsset.asset_id with invalid patterns."""
    native_asset_data["asset_id"] = asset_id
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("asset_id",),
                "msg": "Value error, asset_id for native assets must use lowercase letters and digits only",
            }
        ],
    )


@pytest.mark.parametrize(
    "asset_id",
    [
        123,  # int
        3.14,  # float
        ["zig"],  # list
        {"id": "zig"},  # dict
        True,  # bool
        None,  # none
        (),  # empty tuple
        ("zig",),  # tuple
    ],
)
def test_native_asset_asset_id_bad_type(
    native_asset_data: Dict[str, Any],
    asset_id: Any,
) -> None:
    """Test NativeAsset.asset_id rejects non-string types."""
    native_asset_data["asset_id"] = asset_id
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("asset_id",),
                "msg": "Input should be a valid string",
            }
        ],
    )


# ----------------
# Negative tests for NativeAsset.base_denom field
# ----------------


def test_native_asset_base_denom_missing(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.base_denom field is missing."""
    del native_asset_data["base_denom"]
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

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


def test_native_asset_base_denom_bad_type_none(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.base_denom field with None value."""
    native_asset_data["base_denom"] = None
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

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


def test_native_asset_base_denom_bad_type_bool(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.base_denom field with bool value."""
    native_asset_data["base_denom"] = True
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

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


def test_native_asset_base_denom_too_short(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.base_denom field is too short."""
    native_asset_data["base_denom"] = "ab"
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("base_denom",),
                "msg": "String should have at least 3 characters",
            }
        ],
    )


def test_native_asset_base_denom_too_long(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.base_denom field is too long."""
    native_asset_data["base_denom"] = "a" * 129
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("base_denom",),
                "msg": "String should have at most 128 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "base_denom",
    [
        "1zig",  # starts with number
        "!zig",  # invalid char
        " zig",  # starts with space
        "zig!",  # invalid char at end
        "123",  # only numbers
        "####",  # invalid symbol
        ".zig",  # starts with valid symbol
        "/zig净资产",  # unicode
    ],
)
def test_native_asset_base_denom_bad_pattern(
    native_asset_data: Dict[str, Any],
    base_denom: str,
) -> None:
    """Test NativeAsset.base_denom field with invalid pattern."""
    native_asset_data["base_denom"] = base_denom
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("base_denom",),
                "msg": "Value error, base_denom must start with a letter and use letters, numbers or '/:._-'",
            }
        ],
    )


@pytest.mark.parametrize(
    "base_denom",
    [
        123,  # int
        3.14,  # float
        ["uzig"],  # list
        {"denom": "uzig"},  # dict
        True,  # bool
        (),  # empty tuple
        ("uzig",),  # tuple
    ],
)
def test_native_asset_base_denom_bad_type(
    native_asset_data: Dict[str, Any],
    base_denom: Any,
) -> None:
    """Test NativeAsset.base_denom rejects non-string types."""
    native_asset_data["base_denom"] = base_denom
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
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


# ----------------
# Negative tests for NativeAsset.denom_units field
# ----------------


def test_native_asset_denom_units_missing(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.denom_units field is missing."""
    del native_asset_data["denom_units"]
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("denom_units",),
                "msg": "Field required",
            }
        ],
    )


def test_native_asset_denom_units_empty(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.denom_units field with empty list."""
    native_asset_data["denom_units"] = []
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "too_short",
                "loc": ("denom_units",),
                "msg": "List should have at least 1 item after validation, not 0",
            }
        ],
    )


def test_native_asset_denom_units_bad_type_none(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.denom_units field with None value."""
    native_asset_data["denom_units"] = None
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "list_type",
                "loc": ("denom_units",),
                "msg": "Input should be a valid list",
            }
        ],
    )


def test_native_asset_denom_units_duplicate_denoms(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.denom_units with duplicate denoms."""
    native_asset_data["denom_units"] = [
        {"denom": "uzig", "exponent": 0},
        {"denom": "uzig", "exponent": 6},
    ]
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": "Value error, denom_units must contain unique denom values, found duplicate 'uzig'",
            }
        ],
    )


def test_native_asset_denom_units_duplicate_exponents(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.denom_units with duplicate exponents."""
    native_asset_data["denom_units"] = [
        {"denom": "uzig", "exponent": 0},
        {"denom": "zig", "exponent": 0},
    ]
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": "Value error, denom_units must contain unique exponent values, found duplicate '0'",
            }
        ],
    )


def test_native_asset_denom_units_missing_base_denom(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.denom_units without base denom at exponent 0."""
    native_asset_data["denom_units"] = [
        {"denom": "other", "exponent": 0},
        {"denom": "zig", "exponent": 6},
    ]
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": "Value error, denom_units must contain an entry with exponent=0 and denom matching base_denom 'uzig'",
            }
        ],
    )


def test_native_asset_denom_units_decimals_mismatch(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.denom_units with decimals not matching max exponent."""
    native_asset_data["decimals"] = 5
    native_asset_data["denom_units"] = [
        {"denom": "uzig", "exponent": 0},
        {"denom": "zig", "exponent": 6},
    ]
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": "Value error, decimals (5) must match highest exponent (6) in denom_units",
            }
        ],
    )


######################################################################
# Tests for DenomUnit model
######################################################################

######################################################################
# Positive tests for DenomUnit model
######################################################################

# ----------------
# Positive tests for DenomUnit class
# ----------------


def test_denom_unit_valid() -> None:
    """Test DenomUnit class with valid data."""
    unit = DenomUnit(denom="uzig", exponent=0)
    assert unit.denom == "uzig"
    assert unit.exponent == 0
    assert unit.aliases is None


def test_denom_unit_with_aliases() -> None:
    """Test DenomUnit class with aliases."""
    unit = DenomUnit(denom="uzig", exponent=0, aliases=["ZIG", "zigchain"])
    assert unit.denom == "uzig"
    assert unit.exponent == 0
    assert unit.aliases == ["ZIG", "zigchain"]


@pytest.mark.parametrize(
    "denom",
    [
        "uzig",
        "uatom",
        "a" * 64,  # max length
        "token:token",
        "token/token",
        "token.token",
        "token-token",
        "token_token",
    ],
)
def test_denom_unit_denom_valid(denom: str) -> None:
    """Test DenomUnit.denom field with valid values."""
    unit = DenomUnit(denom=denom, exponent=0)
    assert unit.denom == denom


@pytest.mark.parametrize(
    "exponent",
    [
        0,
        6,
        8,
        18,
    ],
)
def test_denom_unit_exponent_valid(exponent: int) -> None:
    """Test DenomUnit.exponent field with valid values."""
    unit = DenomUnit(denom="uzig", exponent=exponent)
    assert unit.exponent == exponent


@pytest.mark.parametrize(
    "aliases",
    [
        None,
        ["ZIG"],
        ["ZIG", "zigchain"],
        ["alias1", "alias2", "alias3"],
    ],
)
def test_denom_unit_aliases_valid(aliases: Any) -> None:
    """Test DenomUnit.aliases field with valid values."""
    unit = DenomUnit(denom="uzig", exponent=0, aliases=aliases)
    assert unit.aliases == aliases


######################################################################
# Negative tests for DenomUnit model
######################################################################

# ----------------
# Negative tests for DenomUnit.denom field
# ----------------


def test_denom_unit_denom_missing() -> None:
    """Test DenomUnit.denom field is missing."""
    with pytest.raises(ValidationError) as exc:
        DenomUnit(exponent=0)  # type: ignore

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("denom",),
                "msg": "Field required",
            }
        ],
    )


def test_denom_unit_denom_bad_type_none() -> None:
    """Test DenomUnit.denom field with None value."""
    with pytest.raises(ValidationError) as exc:
        DenomUnit(denom=None, exponent=0)  # type: ignore

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("denom",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_denom_unit_denom_too_short() -> None:
    """Test DenomUnit.denom field is too short."""
    with pytest.raises(ValidationError) as exc:
        DenomUnit(denom="", exponent=0)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("denom",),
                "msg": "String should have at least 1 character",
            }
        ],
    )


def test_denom_unit_denom_too_long() -> None:
    """Test DenomUnit.denom field is too long."""
    with pytest.raises(ValidationError) as exc:
        DenomUnit(denom="a" * 129, exponent=0)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("denom",),
                "msg": "String should have at most 128 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "denom",
    [
        "1zig",  # starts with number
        "!zig",  # invalid char
        " zig",  # starts with space
        "zig!",  # invalid char at end
    ],
)
def test_denom_unit_denom_bad_pattern(denom: str) -> None:
    """Test DenomUnit.denom field with invalid pattern."""
    with pytest.raises(ValidationError) as exc:
        DenomUnit(denom=denom, exponent=0)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("denom",),
                "msg": "Value error, denom must start with a letter and use letters, numbers or '/:._-'",
            }
        ],
    )


# ----------------
# Negative tests for DenomUnit.exponent field
# ----------------


def test_denom_unit_exponent_missing() -> None:
    """Test DenomUnit.exponent field is missing."""
    with pytest.raises(ValidationError) as exc:
        DenomUnit(denom="uzig")  # type: ignore

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("exponent",),
                "msg": "Field required",
            }
        ],
    )


def test_denom_unit_exponent_bad_type_bool() -> None:
    """Test DenomUnit.exponent field with bool value."""
    with pytest.raises(ValidationError) as exc:
        DenomUnit(denom="uzig", exponent=True)  # type: ignore

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("exponent",),
                "msg": "Value error, exponent cannot be bool, must be an integer",
                "input": True,
            }
        ],
    )


def test_denom_unit_exponent_negative() -> None:
    """Test DenomUnit.exponent field with negative value."""
    with pytest.raises(ValidationError) as exc:
        DenomUnit(denom="uzig", exponent=-1)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "greater_than_equal",
                "loc": ("exponent",),
                "msg": "Input should be greater than or equal to 0",
            }
        ],
    )


# ----------------
# Negative tests for DenomUnit.aliases field
# ----------------


def test_denom_unit_aliases_empty_string() -> None:
    """Test DenomUnit.aliases with empty string."""
    with pytest.raises(ValidationError) as exc:
        DenomUnit(denom="uzig", exponent=0, aliases=["", "zig"])

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("aliases",),
                "msg": "Value error, aliases must be non-empty strings",
                "input": ["", "zig"],
            }
        ],
    )


def test_denom_unit_aliases_whitespace() -> None:
    """Test DenomUnit.aliases with whitespace-only strings."""
    with pytest.raises(ValidationError) as exc:
        DenomUnit(denom="uzig", exponent=0, aliases=[" ", "zig"])

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("aliases",),
                "msg": "Value error, aliases must be non-empty strings",
                "input": [" ", "zig"],
            }
        ],
    )


def test_denom_unit_aliases_duplicate() -> None:
    """Test DenomUnit.aliases with duplicate values."""
    with pytest.raises(ValidationError) as exc:
        DenomUnit(denom="uzig", exponent=0, aliases=["zig", "zig"])

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("aliases",),
                "msg": "Value error, aliases must be unique",
            }
        ],
    )


@pytest.mark.parametrize(
    "aliases",
    [
        123,  # int
        3.14,  # float
        True,  # bool
        "not a list",  # str
        {"a": 1},  # dict
    ],
)
def test_denom_unit_aliases_bad_type_list(aliases: Any) -> None:
    """Test DenomUnit.aliases rejects non-list value (Input should be a valid list)."""
    with pytest.raises(ValidationError) as exc:
        DenomUnit(denom="uzig", exponent=0, aliases=aliases)  # type: ignore

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "list_type",
                "loc": ("aliases",),
                "msg": "Input should be a valid list",
            }
        ],
    )


@pytest.mark.parametrize(
    "aliases",
    [
        [123, "zig"],  # int in list
        [3.14],  # float in list
        [None],  # None in list
        [True],  # bool in list
        [{"x": 1}],  # dict in list
    ],
)
def test_denom_unit_aliases_bad_type_string(aliases: Any) -> None:
    """Test DenomUnit.aliases rejects list with non-string elements (Input should be a valid string)."""
    with pytest.raises(ValidationError) as exc:
        DenomUnit(denom="uzig", exponent=0, aliases=aliases)  # type: ignore

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("aliases", 0),
                "msg": "Input should be a valid string",
            }
        ],
    )


######################################################################
# Bytes tests for NativeAsset models (Phase 4).
######################################################################

# ----------------
# Bytes test for NativeAsset.asset_id (inherited, has reject_bytes_asset_id)
# ----------------


def test_native_asset_asset_id_bytes(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.asset_id rejects bytes (reject_bytes_asset_id in base.py, mode='before')."""
    native_asset_data["asset_id"] = b"uzig"
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
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
# Bytes rejection for NativeAsset.base_denom
# ----------------


def test_native_asset_base_denom_bytes_rejected(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test that base_denom rejects bytes input (strict bytes policy)."""
    native_asset_data["base_denom"] = b"uzig"
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("base_denom",),
                "msg": "Value error, base_denom must be a string, not bytes",
            }
        ],
    )


######################################################################
# Deep coverage: NativeAsset.traces sub-field and edge cases (Phase 5).
######################################################################

# ----------------
# NativeAsset.traces: list-level constraints
# ----------------


def test_native_asset_traces_bad_type_tuple(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.traces rejects tuple input (mode='before' validator)."""
    native_asset_data["traces"] = (
        {
            "type": "additional-mintage",
            "counterparty": {"chain_name": "ethereum", "base_denom": "0xabc"},
        },
    )
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("traces",),
                "msg": "Value error, traces must be a list, not tuple",
            }
        ],
    )


def test_native_asset_traces_too_many(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.traces rejects more than 10 entries (max_length=10)."""
    native_asset_data["traces"] = [
        {
            "type": "additional-mintage",
            "counterparty": {"chain_name": f"chain{i}", "base_denom": f"denom{i}"},
        }
        for i in range(11)
    ]
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
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

def test_native_asset_traces_identical_entries(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeAsset.traces rejects duplicate trace entries (model_validator)."""
    trace = {
        "type": "additional-mintage",
        "counterparty": {
            "chain_name": "ethereum",
            "base_denom": "0xb2617246d0c6c0087f18703d576831899ca94f01",
        },
        "provider": "ZIGChain",
    }
    native_asset_data["traces"] = [trace, trace]
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
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


# ----------------
# NativeTrace sub-field coverage
# ----------------


def test_native_asset_traces_trace_type_missing(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeTrace.type is required."""
    native_asset_data["traces"] = [
        {
            "counterparty": {"chain_name": "ethereum", "base_denom": "0xabc"},
            "provider": "ZIGChain",
        }
    ]
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("traces", 0, "type"),
                "msg": "Field required",
            }
        ],
    )


def test_native_asset_traces_counterparty_missing(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeTrace.counterparty is required."""
    native_asset_data["traces"] = [
        {
            "type": "additional-mintage",
            "provider": "ZIGChain",
        }
    ]
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("traces", 0, "counterparty"),
                "msg": "Field required",
            }
        ],
    )


def test_native_asset_traces_provider_optional(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test NativeTrace.provider is optional (defaults to None)."""
    native_asset_data["traces"] = [
        {
            "type": "additional-mintage",
            "counterparty": {"chain_name": "ethereum", "base_denom": "0xabc"},
        }
    ]
    asset = NativeAsset(**native_asset_data)
    assert asset.traces[0].provider is None


def test_native_asset_traces_counterparty_chain_name_missing(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test TraceCounterparty.chain_name is required."""
    native_asset_data["traces"] = [
        {
            "type": "additional-mintage",
            "counterparty": {"base_denom": "0xabc"},
        }
    ]
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("traces", 0, "counterparty", "chain_name"),
                "msg": "Field required",
            }
        ],
    )


def test_native_asset_traces_counterparty_base_denom_missing(
    native_asset_data: Dict[str, Any],
) -> None:
    """Test TraceCounterparty.base_denom is required."""
    native_asset_data["traces"] = [
        {
            "type": "additional-mintage",
            "counterparty": {"chain_name": "ethereum"},
        }
    ]
    with pytest.raises(ValidationError) as exc:
        NativeAsset(**native_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("traces", 0, "counterparty", "base_denom"),
                "msg": "Field required",
            }
        ],
    )



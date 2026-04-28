"""Tests for base Pydantic models."""

from typing import Any, Dict, List, Optional

import pytest
from pydantic import HttpUrl, TypeAdapter, ValidationError

from models import AssetBase, DenomUnit, LogoUris, Socials
from models.base import (
    _ALLOWED_LOGO_HOSTS,
    ImageEntry,
    ImageSyncPointer,
    ImageTheme,
    NativeTrace,
    TraceCounterparty,
    _validate_logo_host,
)
from models.factory import FactoryAsset
from models.ibc import IBCAsset, IBCChannel, IBCTrace
from models.native import NativeAsset
from . import check_model_error


######################################################################
# Fixtures
######################################################################

@pytest.fixture
def asset_base_data() -> Dict[str, Any]:
    """Fixture providing valid AssetBase data with all fields."""
    return {
        "$schema": "../../schemas/asset.native.schema.json",
        "network": "mainnet",
        "asset_id": "zig",
        "order": 2,
        "type": "native",
        "symbol": "ZIG",
        "name": "ZIGChain Native Token",
        "decimals": 6,
        "denom_units": [
                {"denom": "ibc/ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789", "exponent": 0},
                {"denom": "token", "exponent": 6},
            ],
        "display_denom": "ZIG",
        "description": "The native staking token of ZIGChain",
        "extended_description": "ZIGChain (ZIG) is a Layer 1 blockchain focused on unlocking financial opportunities for everyone.",
        "keywords": ["zigchain","zignaly"],
        "images": [
            {"png": "https://raw.githubusercontent.com/test/zig.png", "svg": "https://raw.githubusercontent.com/test/zig.svg"},
            {"chain_name": "zigchain", "base_denom": "uzig"},
        ],
        "logo_uris": {"png": "https://raw.githubusercontent.com/test/logo.png"},
        "socials": {
                "website": "https://example.com/",
                "x": "https://x.com/example"},
        "coingecko_id": "usd-coin",
        "is_verified": True,
    }


@pytest.fixture
def asset_base_data_minimal() -> Dict[str, Any]:
    """Fixture providing minimal valid AssetBase data (required fields only)."""
    return {
        "network": "mainnet",
        "asset_id": "zig",
        "type": "native",
        "symbol": "ZIG",
        "name": "ZIGChain Native Token",
        "decimals": 6,
        "display_denom": "ZIG",
    }


@pytest.fixture
def trace_counterparty_data() -> Dict[str, Any]:
    """Fixture providing valid TraceCounterparty data with all fields."""
    return {
        "chain_name": "ethereum",
        "base_denom": "0xb2617246d0c6c0087f18703d576831899ca94f01",
    }


@pytest.fixture
def native_trace_data() -> Dict[str, Any]:
    """Fixture providing valid NativeTrace data with all fields."""
    return {
        "type": "additional-mintage",
        "counterparty": {
            "chain_name": "ethereum",
            "base_denom": "0xb2617246d0c6c0087f18703d576831899ca94f01",
        },
        "provider": "ZIGChain",
    }


@pytest.fixture
def image_sync_pointer_data() -> Dict[str, Any]:
    """Fixture providing valid ImageSyncPointer data with all fields."""
    return {
        "chain_name": "zigchain",
        "base_denom": "uzig",
    }


@pytest.fixture
def image_theme_data() -> Dict[str, Any]:
    """Fixture providing valid ImageTheme data with at least one property."""
    return {"circle": True, "dark_mode": False}


@pytest.fixture
def image_entry_data() -> Dict[str, Any]:
    """Fixture providing valid ImageEntry data with all fields (image_sync, png, svg, theme)."""
    return {
        "image_sync": {"chain_name": "zigchain", "base_denom": "uzig"},
        "png": "https://raw.githubusercontent.com/test/logo.png",
        "svg": "https://raw.githubusercontent.com/test/logo.svg",
        "theme": {"circle": True, "dark_mode": False},
    }


@pytest.fixture
def denom_unit_data() -> Dict[str, Any]:
    """Fixture providing valid DenomUnit data with all fields."""
    return {"denom": "uzig", "exponent": 6, "aliases": ["ZIG", "zigchain"]}


@pytest.fixture
def logo_uris_data() -> Dict[str, Any]:
    """Fixture providing valid LogoUris data with all fields."""
    return {
        "chain_name": "cosmoshub",
        "png": "https://raw.githubusercontent.com/test/logo.png",
        "svg": "https://raw.githubusercontent.com/test/logo.svg",
    }


@pytest.fixture
def socials_data() -> Dict[str, Any]:
    """Fixture providing valid Socials data with all fields (at least one required)."""
    return {
        "website": "https://example.com",
        "x": "https://x.com/example",
        "telegram": "https://t.me/example",
        "discord": "https://discord.gg/example",
        "github": "https://github.com/example",
        "medium": "https://medium.com/@example",
        "reddit": "https://reddit.com/r/example",
    }


######################################################################
# Positive tests for AssetBase models.
######################################################################

# ----------------
# Positive tests for AssetBase class
# ----------------

def test_asset_base(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase class with all fields."""
    asset = AssetBase(**asset_base_data)
    assert isinstance(asset, AssetBase)
    assert len(AssetBase.model_fields) == 18

    assert asset.schema_ref == asset_base_data["$schema"]
    assert asset.network == asset_base_data["network"]
    assert asset.asset_id == asset_base_data["asset_id"]
    assert asset.order == asset_base_data["order"]
    assert asset.type == asset_base_data["type"]
    assert asset.symbol == asset_base_data["symbol"]
    assert asset.name == asset_base_data["name"]
    assert asset.decimals == asset_base_data["decimals"]

    assert asset.denom_units is not None
    assert len(asset.denom_units) == len(asset_base_data["denom_units"])
    for i, unit in enumerate(asset.denom_units):
        assert unit.denom == asset_base_data["denom_units"][i]["denom"]
        assert unit.exponent == asset_base_data["denom_units"][i]["exponent"]

    assert asset.display_denom == asset_base_data["display_denom"]
    assert asset.description == asset_base_data["description"]
    assert asset.extended_description == asset_base_data["extended_description"]
    assert asset.keywords == asset_base_data["keywords"]

    assert asset.images is not None
    assert len(asset.images) == len(asset_base_data["images"])
    # First entry: ImageEntry with png/svg URLs
    assert str(asset.images[0].png) == asset_base_data["images"][0]["png"]
    assert str(asset.images[0].svg) == asset_base_data["images"][0]["svg"]
    # Second entry: ImageSyncPointer (shortcut form chain_name + base_denom)
    assert asset.images[1].chain_name == asset_base_data["images"][1]["chain_name"]
    assert asset.images[1].base_denom == asset_base_data["images"][1]["base_denom"]

    assert asset.logo_uris is not None
    assert str(asset.logo_uris.png) == asset_base_data["logo_uris"]["png"]

    assert asset.socials is not None
    assert len(asset_base_data["socials"]) == 2
    assert str(asset.socials.website) == asset_base_data["socials"]["website"]
    assert str(asset.socials.x) == asset_base_data["socials"]["x"]

    assert asset.coingecko_id == asset_base_data["coingecko_id"]
    assert asset.is_verified == asset_base_data["is_verified"]


def test_asset_base_minimal(
    asset_base_data_minimal: Dict[str, Any],
) -> None:
    """Test AssetBase class with only required fields (no optionals)."""
    asset = AssetBase(**asset_base_data_minimal)
    assert asset.network == asset_base_data_minimal["network"]
    assert asset.asset_id == asset_base_data_minimal["asset_id"]
    assert asset.type == asset_base_data_minimal["type"]
    assert asset.symbol == asset_base_data_minimal["symbol"]
    assert asset.name == asset_base_data_minimal["name"]
    assert asset.decimals == asset_base_data_minimal["decimals"]
    assert asset.display_denom == asset_base_data_minimal["display_denom"]
    assert asset.description is None
    assert asset.logo_uris is None
    assert asset.coingecko_id is None
    assert asset.socials is None


# ----------------
# Positive tests for AssetBase.schema_ref field
# ----------------

@pytest.mark.parametrize(
    "schema",
    [
        "1",
        "abc",
        "@-*",
        "",
        "../../schemas/asset.native.schema.json",
        None,
    ],
)
def test_asset_base_schema_valid(
    asset_base_data: Dict[str, Any],
    schema: Optional[str],
) -> None:
    """Test AssetBase.schema_ref field with valid values (including None)."""
    asset_base_data["$schema"] = schema
    asset = AssetBase(**asset_base_data)
    assert asset.schema_ref == schema

# ----------------
# Positive tests for AssetBase.network field
# ----------------

@pytest.mark.parametrize(
    "network",
    [
        "mainnet",
        "testnet",
    ]
)
def test_asset_base_network_valid(
    asset_base_data: Dict[str, Any],
    network: str,
) -> None:
    """Test AssetBase.network field with valid values."""
    asset_base_data["network"] = network
    asset = AssetBase(**asset_base_data)
    assert asset.network == network


# ----------------
# Positive tests for AssetBase.asset_id field
# ----------------

@pytest.mark.parametrize(
    "asset_id",
    [
        "zig",
        "factory.zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw.panda",
        "ibc/EF48E6B1A1A19F47ECAEA62F5670C37C0580E86A9E88498B7E393EB6F49F33C0",
        "a" * 128,  # max length
        "z", # min length
        "usd ", # trailing space
        "@zig", # starting with symbol
        "123", # only numbers
        "z1g",  # values inbetween
        "ZIG",  # capital letters
    ],
)
def test_asset_base_asset_id_valid(
    asset_base_data: Dict[str, Any],
    asset_id: str,
) -> None:
    """Test AssetBase.asset_id field with valid values."""
    asset_base_data["asset_id"] = asset_id
    asset = AssetBase(**asset_base_data)
    assert asset.asset_id == asset_id



# ----------------
# Positive tests for AssetBase.order field
# ----------------

@pytest.mark.parametrize(
    "order",
    [
        0,
        1,
        10000000000000000000000000000,
        None,
    ],
)
def test_asset_base_order_valid(
    asset_base_data: Dict[str, Any],
    order: Optional[int],
) -> None:
    """Test AssetBase.order field with valid values (int >= 0 or None)."""
    asset_base_data["order"] = order
    asset = AssetBase(**asset_base_data)
    assert asset.order == order


def test_asset_base_order_missing(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.order field when key is missing (optional, defaults to None)."""
    del asset_base_data["order"]
    asset = AssetBase(**asset_base_data)
    assert asset.order is None


# ----------------
# Positive tests for AssetBase.type field
# ----------------

@pytest.mark.parametrize(
    "asset_type",
    [
        "native",
        "factory",
        "ibc",
    ]
)
def test_asset_base_type_valid(
    asset_base_data: Dict[str, Any],
    asset_type: str,
) -> None:
    """Test AssetBase.type field with valid values."""
    asset_base_data["type"] = asset_type
    asset = AssetBase(**asset_base_data)
    assert asset.type == asset_type



# ----------------
# Positive tests for AssetBase.symbol field
# ----------------

@pytest.mark.parametrize(
    "symbol",
    [
        "ZIG",
        "USDC",
        "BTC",
        "ETH",
        "A1", # min length
        "A" * 42,  # max length
        "ZIG.USDC",
        "ZIG-USDC",
        "ZIG_USDC",
        "1ZIG",
        "12", # only numbers
    ]
)
def test_asset_base_symbol_valid(
    asset_base_data: Dict[str, Any],
    symbol: str,
) -> None:
    """Test AssetBase.symbol field with valid values."""
    asset_base_data["symbol"] = symbol
    asset = AssetBase(**asset_base_data)
    assert asset.symbol == symbol


# ----------------
# Positive tests for AssetBase.name field
# ----------------

@pytest.mark.parametrize(
    "name",
    [
        "ZIGChain Native Token",
        "A" * 100,  # max length
        "Bitcoin",
        "Ethereum",
        "USD Coin",
        "Zg",  # min length (2 chars)
        "12345",  # only numbers
        " USDT",  # leading space (stored as-is; validator only rejects pure whitespace)
        "@@@",  # only symbols
        "[name]",
        "1zig",  # starting with number
        "!ZIG",  # starting with symbol
        "资产", # unicode
    ]
)
def test_asset_base_name_valid(
    asset_base_data: Dict[str, Any],
    name: str,
) -> None:
    """Test AssetBase.name field with valid values."""
    asset_base_data["name"] = name
    asset = AssetBase(**asset_base_data)
    assert asset.name == name


# ----------------
# Positive tests for AssetBase.decimals field
# ----------------

@pytest.mark.parametrize(
    "decimals_str,expected",
    [
        ("  6  ", 6),  # with space
        ("18", 18),
        ("0 ", 0),  # trailing space
    ],
)
def test_asset_base_decimals_string(
    asset_base_data: Dict[str, Any],
    decimals_str: str,
    expected: int,
) -> None:
    """Test AssetBase.decimals field can be provided as a numeric string."""
    asset_base_data["decimals"] = decimals_str
    asset = AssetBase(**asset_base_data)
    assert asset.decimals == expected


@pytest.mark.parametrize(
    "decimals",
    [
        0,
        6,
        8,
        18,  # max valid (le=18)
    ],
)
def test_asset_base_decimals_valid(
    asset_base_data: Dict[str, Any],
    decimals: int,
) -> None:
    """Test AssetBase.decimals field with valid values."""
    asset_base_data["decimals"] = decimals
    asset = AssetBase(**asset_base_data)
    assert asset.decimals == decimals


# ----------------
# Positive tests for AssetBase.denom_units field
# ----------------

def test_asset_base_denom_units_none(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.denom_units field accepts explicit None."""
    asset_base_data["denom_units"] = None
    asset = AssetBase(**asset_base_data)
    assert asset.denom_units is None


def test_asset_base_denom_units_missing(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.denom_units field when key is omitted (defaults to None)."""
    del asset_base_data["denom_units"]
    asset = AssetBase(**asset_base_data)
    assert asset.denom_units is None


@pytest.mark.parametrize(
    "denom_units",
    [
        [],  # empty list
        [{"denom": "uzig", "exponent": 0}],  # single base unit
        [{"denom":"u-zig", "exponent": 1}], # denom with valid symbol
        [{"denom": "uzig", "exponent": 0}, {"denom": "ZIG", "exponent": 6}],  # base + display
        [
            {"denom": "ibc/ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789", "exponent": 0},
            {"denom": "token", "exponent": 6},
        ],  # IBC-style long base + token
        [{"denom": "base", "exponent": 0}, {"denom": "display", "exponent": 6, "aliases": ["SYM"]}],  # with aliases
    ],
)
def test_asset_base_denom_units_valid(
    asset_base_data: Dict[str, Any],
    denom_units: Any,
) -> None:
    """Test AssetBase.denom_units field with valid list values (empty or list of DenomUnit)."""
    asset_base_data["denom_units"] = denom_units
    asset = AssetBase(**asset_base_data)
    assert len(asset.denom_units) == len(denom_units)
    for i, expected in enumerate(denom_units):
        assert asset.denom_units[i].denom == expected["denom"]
        assert asset.denom_units[i].exponent == expected["exponent"]
        assert asset.denom_units[i].aliases == expected.get("aliases")


# ----------------
# Positive tests for AssetBase.display_denom field
# ----------------

@pytest.mark.parametrize(
    "display_denom",
    [
        "ZIG",
        "1ZIG.axl",
        "A" * 32,  # max length
        "USDC:USDC",
        "ZIG-USDC",
        "ZIG_USDC",
        "a",  # min length
    ]
)
def test_asset_base_display_denom_valid(
    asset_base_data: Dict[str, Any],
    display_denom: str,
) -> None:
    """Test AssetBase.display_denom field with valid values."""
    asset_base_data["display_denom"] = display_denom
    asset = AssetBase(**asset_base_data)
    assert asset.display_denom == display_denom


# ----------------
# Positive tests for AssetBase.description field
# ----------------

@pytest.mark.parametrize(
    "description",
    [
        "The native staking token of ZIGChain",
        "A" * 2048,  # max length
        "a",  # min length
        " The native tokne.",  # Trailing space
        "1234",  # only numbers
        "@@@@",  # only symbols
        None,
    ]
)
def test_asset_base_description_valid(
    asset_base_data: Dict[str, Any],
    description: Any,
) -> None:
    """Test AssetBase.description field with valid values."""
    asset_base_data["description"] = description
    asset = AssetBase(**asset_base_data)
    assert asset.description == description


def test_asset_base_description_missing(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.description field missing, default to None."""
    del asset_base_data["description"]
    asset = AssetBase(**asset_base_data)
    assert asset.description is None


# ----------------
# Positive tests for AssetBase.extended_description field
# ----------------

@pytest.mark.parametrize(
    "extended_description",
    [
        "The native staking token of ZIGChain",
        "A" * 8192,  # max length
        "a",  # min length
        " The native tokne.",  # Trailing space
        "1234",  # only numbers
        "@@@@",  # only symbols
        None,
    ]
)
def test_asset_base_extended_description_valid(
    asset_base_data: Dict[str, Any],
    extended_description: Any,
) -> None:
    """Test AssetBase.extended_description accepts valid values."""
    asset_base_data["extended_description"] = extended_description
    asset = AssetBase(**asset_base_data)
    assert asset.extended_description == extended_description

def test_asset_base_extended_description_missing(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.description field missing, default to None."""
    del asset_base_data["extended_description"]
    asset = AssetBase(**asset_base_data)
    assert asset.extended_description is None

def test_asset_base_extended_description_bytes(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.extended_description rejects bytes input (consistent with asset_id bytes policy)."""
    asset_base_data["extended_description"] = b'Description'
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "loc": ("extended_description",),
                "type": "value_error",
                "msg": "Value error, extended_description must be a string, not bytes",
            }
        ],
    )



@pytest.mark.parametrize(
    "field,value",
    [
        ("symbol", b"ZIG"),
        ("name", b"ZIGChain Native Token"),
        ("display_denom", b"ZIG"),
        ("description", b"Some description"),
        ("coingecko_id", b"zigchain"),
    ],
)
def test_asset_base_string_fields_bytes_rejected(
    asset_base_data: Dict[str, Any],
    field: str,
    value: bytes,
) -> None:
    """Test that all string fields in AssetBase reject bytes input (strict bytes policy)."""
    asset_base_data[field] = value
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "loc": (field,),
                "type": "value_error",
                "msg": f"Value error, {field} must be a string, not bytes",
            }
        ],
    )


# ----------------
# Positive tests for AssetBase.keywords field
# ----------------

def test_asset_base_keywords_missing(asset_base_data: Dict[str, Any]) -> None:
    """Test AssetBase.keywords field when key is omitted (defaults to None)."""
    del asset_base_data["keywords"]
    asset = AssetBase(**asset_base_data)
    assert asset.keywords is None




@pytest.mark.parametrize(
    "keywords",
    [
        ["zigchain", "rwa"],
        ["single"],
        ["a", "b", "c"],
        ["token"] * 20,  # max length (20 items)
        ["12", "34", "56789"], # only numbers
        ["%", "##", "{$$$}"], # symbols
        ["资产"], # unicode
    ],
)
def test_asset_base_keywords_valid(
    asset_base_data: Dict[str, Any],
    keywords: List[str],
) -> None:
    """Test AssetBase.keywords field with valid list values."""
    asset_base_data["keywords"] = keywords
    asset = AssetBase(**asset_base_data)
    assert asset.keywords == keywords


# ----------------
# Positive tests for AssetBase.images field
# ----------------

def test_asset_base_images_missing(asset_base_data: Dict[str, Any]) -> None:
    """Test AssetBase.images field when key is omitted (defaults to None)."""
    del asset_base_data["images"]
    asset = AssetBase(**asset_base_data)
    assert asset.images is None

def test_asset_base_images_none(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.images field accepts explicit None."""
    asset_base_data["images"] = None
    asset = AssetBase(**asset_base_data)
    assert asset.images is None

@pytest.mark.parametrize(
    "images",
    [
        [],  # empty list (valid per Optional[List[...]])
        [{"chain_name": "ethereum", "base_denom": "0xabc"}],  # shortcut form (ImageSyncPointer)
        [{"chain_name": "1", "base_denom": "2"}],  # shortcut with minimal values
        [
            {
                "image_sync": {"chain_name": "ethereum", "base_denom": "0xabc"},
                "png": "https://raw.githubusercontent.com/test/a.png",
            }
        ],  # full ImageEntry with image_sync + png
        [{"png": "https://raw.githubusercontent.com/test/logo.png"}],  # ImageEntry png only (no image_sync)
        [{"svg": "https://raw.githubusercontent.com/test/logo.svg"}],  # ImageEntry svg only
        [
            {"png": "https://raw.githubusercontent.com/test/a.png", "svg": "https://raw.githubusercontent.com/test/a.svg"}
        ],  # ImageEntry png + svg
        [
            {
                "image_sync": {"chain_name": "cosmoshub", "base_denom": "uatom"},
                "svg": "https://raw.githubusercontent.com/test/atom.svg",
            }
        ],  # ImageEntry image_sync + svg (no png)
        [
            {"png": "https://raw.githubusercontent.com/test/a.png", "theme": {"circle": True}}
        ],  # ImageEntry with theme circle
        [
            {"png": "https://raw.githubusercontent.com/test/a.png", "theme": {"dark_mode": True}}
        ],  # ImageEntry with theme dark_mode
        [
            {"png": "https://raw.githubusercontent.com/test/a.png", "theme": {"circle": True, "dark_mode": False}}
        ],  # ImageEntry with theme both keys
        [
            {"chain_name": "ethereum", "base_denom": "0xabc"},
            {"png": "https://raw.githubusercontent.com/test/b.png"},
        ],  # multiple entries: shortcut + ImageEntry
        [
            {"chain_name": "zigchain", "base_denom": "uzig"},
            {"chain_name": "cosmoshub", "base_denom": "uatom"},
        ],  # two shortcuts
    ],
)
def test_asset_base_images_valid(
    asset_base_data: Dict[str, Any],
    images: Any,
) -> None:
    """Test AssetBase.images field with valid values (empty list, shortcut, ImageEntry variants, theme, multiple)."""
    asset_base_data["images"] = images
    asset = AssetBase(**asset_base_data)

    assert asset.images is not None
    assert len(asset.images) == len(images)
    if images and "chain_name" in (images[0] or {}) and "base_denom" in (images[0] or {}):
        # First entry is shortcut (ImageSyncPointer)
        assert asset.images[0].chain_name == images[0]["chain_name"]
        assert asset.images[0].base_denom == images[0]["base_denom"]


# ----------------
# Positive tests for AssetBase.logo_uris field
# ----------------

def test_asset_base_logo_uris_missing(asset_base_data: Dict[str, Any]) -> None:
    """Test AssetBase.logo_uris field when key is omitted (defaults to None)."""
    del asset_base_data["logo_uris"]
    asset = AssetBase(**asset_base_data)
    assert asset.logo_uris is None


def test_asset_base_logo_uris_none(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.logo_uris field accepts explicit None."""
    asset_base_data["logo_uris"] = None
    asset = AssetBase(**asset_base_data)
    assert asset.logo_uris is None


@pytest.mark.parametrize(
    "logo_uris",
    [
        {"png": "https://raw.githubusercontent.com/test/logo.png"},  # png only
        {"svg": "https://raw.githubusercontent.com/test/logo.svg"},  # svg only
        {"png": "https://raw.githubusercontent.com/test/logo.png", "svg": "https://raw.githubusercontent.com/test/logo.svg"},  # both
        {"chain_name": "cosmoshub", "png": "https://raw.githubusercontent.com/test/logo.png"},  # with chain_name
        {"chain_name": "cosmoshub"},  # only chain_name (no URL keys; validator skips URL check)
        {},  # empty dict
    ],
)
def test_asset_base_logo_uris_valid(
    asset_base_data: Dict[str, Any],
    logo_uris: Any,
) -> None:
    """Test AssetBase.logo_uris field with valid values."""
    asset_base_data["logo_uris"] = logo_uris
    asset = AssetBase(**asset_base_data)

    assert asset.logo_uris is not None
    for key, value in logo_uris.items():
        attr = getattr(asset.logo_uris, key)
        assert (str(attr) if attr is not None else attr) == value


def test_asset_base_logo_uris_logo_uris_instance_valid(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.logo_uris accepts a LogoUris instance (isinstance branch)."""
    asset_base_data["logo_uris"] = LogoUris(png="https://raw.githubusercontent.com/test/logo.png")
    asset = AssetBase(**asset_base_data)
    assert asset.logo_uris is not None
    assert str(asset.logo_uris.png).endswith("logo.png")


def test_asset_base_logo_uris_falsy_url_accepted(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.logo_uris validator skips URL check when url is falsy (None)."""
    asset_base_data["logo_uris"] = {"png": None}
    asset = AssetBase(**asset_base_data)
    assert asset.logo_uris is not None
    assert asset.logo_uris.png is None


# ----------------
# Positive tests for AssetBase.socials field
# ----------------

def test_asset_base_socials_missing(asset_base_data: Dict[str, Any]) -> None:
    """Test AssetBase.socials field when key is omitted (defaults to None)."""
    del asset_base_data["socials"]
    asset = AssetBase(**asset_base_data)
    assert asset.socials is None

def test_asset_base_socials_none(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.socials field accepts explicit None."""
    asset_base_data["socials"] = None
    asset = AssetBase(**asset_base_data)
    assert asset.socials is None


@pytest.mark.parametrize(
    "socials",
    [
        {"website": HttpUrl("https://example.com/")},  # single property (min required)
        {"x": "https://x.com/foo"},  # x is str on Socials (pattern), not HttpUrl
        {"telegram": HttpUrl("https://t.me/example")},  # single property (telegram)
        {
            "website": HttpUrl("https://valdora.finance/"),
            "telegram": HttpUrl("https://t.me/ValdoraWarriors"),
            "discord": HttpUrl("http://discord.gg/valdora"),
            "x": "https://x.com/Valdora_finance",
            "github": HttpUrl("https://github.com/cosmos"),
            "medium": HttpUrl("https://medium.com/@example"),
            "reddit": HttpUrl("https://reddit.com/r/example"),
        },  # all platforms
        {
            "x": "https://x.com/foo",
            "reddit": HttpUrl("https://reddit.com/r/example"),
        },
    ]
)
def test_asset_base_socials_valid(
    asset_base_data: Dict[str, Any],
    socials: Any,
) -> None:
    """Test AssetBase.socials field with valid values (HttpUrl for URI fields, str for x)."""
    asset_base_data["socials"] = socials
    asset = AssetBase(**asset_base_data)

    assert asset.socials is not None
    assert isinstance(asset.socials, Socials)
    for key, value in socials.items():
        assert getattr(asset.socials, key) == value


@pytest.mark.parametrize(
    "socials,expected_loc,expected_msg_fragment",
    [
        (
            {"reddit": HttpUrl("https://medium.com/example")},
            ("socials", "reddit"),
            "socials.reddit must be a reddit.com URL",
        ),
        (
            {"github": HttpUrl("https://reddit.com/r/example")},
            ("socials", "github"),
            "socials.github must be a github.com URL",
        ),
        (
            {"telegram": HttpUrl("https://discord.gg/example")},
            ("socials", "telegram"),
            "socials.telegram must be a t.me or telegram.me URL",
        ),
        (
            {"discord": HttpUrl("https://t.me/example")},
            ("socials", "discord"),
            "socials.discord must be a Discord URL (discord.gg, discord.com, discordapp.com, or custom discord domain)",
        ),
        (
            {"medium": HttpUrl("https://github.com/example")},
            ("socials", "medium"),
            "socials.medium must be a medium.com URL",
        ),
    ],
)
def test_asset_base_socials_wrong_platform_url_rejected(
    asset_base_data: Dict[str, Any],
    socials: Any,
    expected_loc: tuple,
    expected_msg_fragment: str,
) -> None:
    """Test that socials rejects URLs pointing to the wrong platform domain."""
    asset_base_data["socials"] = socials
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": expected_loc,
                "msg": f"Value error, {expected_msg_fragment}",
            }
        ],
    )


# ----------------
# Positive tests for AssetBase.coingecko_id field
# ----------------

def test_asset_base_coingecko_id_missing(asset_base_data: Dict[str, Any]) -> None:
    """Test AssetBase.coingecko_id field when key is omitted (defaults to None)."""
    del asset_base_data["coingecko_id"]
    asset = AssetBase(**asset_base_data)
    assert asset.coingecko_id is None

def test_asset_base_coingecko_id_none(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.coingecko_id field accepts explicit None."""
    asset_base_data["coingecko_id"] = None
    asset = AssetBase(**asset_base_data)
    assert asset.coingecko_id is None

@pytest.mark.parametrize(
    "coingecko_id",
    [
        "usd-coin",  # standard slug with hyphen
        "bitcoin",  # single segment
        "ethereum",  # single segment
        "zigchain",  # single segment
        "a" * 100,  # max length (100 chars)
        None,  # explicit None
        "1ha",  # starting with number (allowed by current regex)
        "usd1coin",  # containing numbers in between
        "us",  # min length (2 chars)
        "12",  # only numbers
    ],
)
def test_asset_base_coingecko_id_valid(
    asset_base_data: Dict[str, Any],
    coingecko_id: Any,
) -> None:
    """Test AssetBase.coingecko_id field with valid values."""
    asset_base_data["coingecko_id"] = coingecko_id
    asset = AssetBase(**asset_base_data)
    assert asset.coingecko_id == coingecko_id


# ----------------
# Positive tests for AssetBase.is_verified field
# ----------------

def test_asset_base_is_verified_missing(asset_base_data: Dict[str, Any]) -> None:
    """Test AssetBase.is_verified field when key is omitted (defaults to None)."""
    del asset_base_data["is_verified"]
    asset = AssetBase(**asset_base_data)
    assert asset.is_verified is None


@pytest.mark.parametrize(
    "is_verified",
    [
        None,   # explicit None
        True,  # verified
        False,  # not verified
    ],
)
def test_asset_base_is_verified_valid(
    asset_base_data: Dict[str, Any],
    is_verified: Any,
) -> None:
    """Test AssetBase.is_verified field with valid values (None, True, False)."""
    asset_base_data["is_verified"] = is_verified
    asset = AssetBase(**asset_base_data)
    assert asset.is_verified is is_verified


# ----------------
# Positive tests for LogoUris class
# ----------------

######################################################################
# Negative tests for AssetBase models.
######################################################################

# ----------------
# Negative tests for AssetBase.schema_ref field
# ----------------

@pytest.mark.parametrize(
    "schema",
    [
        123, # int value
        12.3, # float value
        True, # boolean
        ["schema"], # list
    ],
)
def test_asset_base_schema_invalid(
    asset_base_data: Dict[str, Any],
    schema: Any,
) -> None:
    """Test AssetBase.schema_ref field with valid values (including None)."""
    asset_base_data["$schema"] = schema
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("$schema",),
                "msg": "Input should be a valid string",
            }
        ],
    )

# ----------------
# Negative tests for AssetBase.network field
# ----------------

def test_asset_base_network_missing(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.network field is missing."""
    del asset_base_data["network"]

    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("network",),
                "msg": "Field required",
            }
        ],
    )


def test_asset_base_network_bad_type_none(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.network field with None value."""
    asset_base_data["network"] = None
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "ctx": {"expected": "'mainnet' or 'testnet'"},
                "type": "literal_error",
                "loc": ("network",),
                "msg": "Input should be 'mainnet' or 'testnet'",
            }
        ],
    )


@pytest.mark.parametrize(
    "network",
    [
        "invalid",
        "devnet",
        "",
        "MAINNET",
        "Testnet", # first letter capital
        "mainnet ", # trailing space
    ]
)
def test_asset_base_network_invalid_value(
    asset_base_data: Dict[str, Any],
    network: str,
) -> None:
    """Test AssetBase.network field with invalid values."""
    asset_base_data["network"] = network
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "literal_error",
                "loc": ("network",),
                "msg": "Input should be 'mainnet' or 'testnet'",
            }
        ],
    )


# ----------------
# Negative tests for AssetBase.asset_id field
# ----------------

def test_asset_base_asset_id_missing(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.asset_id field is missing."""
    del asset_base_data["asset_id"]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("asset_id",),
                "msg": "Field required",
            }
        ],
    )


def test_asset_base_asset_id_bad_type_none(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.asset_id field with None value."""
    asset_base_data["asset_id"] = None
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

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


def test_asset_base_asset_id_too_short(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.asset_id field is too short."""
    asset_base_data["asset_id"] = ""
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("asset_id",),
                "msg": "String should have at least 1 character",
            }
        ],
    )


def test_asset_base_asset_id_too_long(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.asset_id field is too long."""
    asset_base_data["asset_id"] = "a" * 129
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("asset_id",),
                "msg": "String should have at most 128 characters",
            }
        ],
    )

def test_asset_base_asset_id_bytes(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.asset_id rejects bytes."""
    asset_base_data["asset_id"] = b"zig"
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

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

@pytest.mark.parametrize(
    "asset_id",
    [
        123,  # int
        0,  # zero (not a string)
        12.3,  # float
        True,  # bool
        False,  # bool
        ["zig"],  # list
        {"id": "zig"},  # dict
        ("zig",),  # tuple
        {"zig"},  # set
    ],
)
def test_asset_base_asset_id_bad_type(
    asset_base_data: Dict[str, Any],
    asset_id: Any,
) -> None:
    """Test AssetBase.asset_id field rejects non-string types (int, float, bool, list, dict, tuple, set)."""
    asset_base_data["asset_id"] = asset_id
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
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
# Negative tests for AssetBase.order field
# ----------------

def test_asset_base_order_negative_value(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.order rejects values less than 0 (ge=0)."""
    asset_base_data["order"] = -1
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "greater_than_equal",
                "loc": ("order",),
                "msg": "Input should be greater than or equal to 0",
            }
        ],
    )


def test_asset_base_order_float_rejected(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.order rejects float (must be integer)."""
    asset_base_data["order"] = 12.3
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "int_from_float",
                "loc": ("order",),
                "msg": "Input should be a valid integer, got a number with a fractional part",
            }
        ],
    )


@pytest.mark.parametrize(
    "order",
    [
        True,
        False,
    ]
)
def test_asset_base_order_bool_rejected(
    asset_base_data: Dict[str, Any],
    order: bool,
) -> None:
    """Test AssetBase.order rejects bool (order_must_not_be_bool validator)."""
    asset_base_data["order"] = order
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("order",),
                "msg": "Value error, order cannot be bool, must be an integer",
            }
        ],
    )


@pytest.mark.parametrize(
    "order",
    [
        ["1"],  # list
        {"id": "2"},  # dict
        ("34",),  # tuple
        {"567"},  # set
    ],
)
def test_asset_base_order_bad_type(
    asset_base_data: Dict[str, Any],
    order: Any,
) -> None:
    """Test AssetBase.order rejects non-integer types (list, dict, tuple, set)."""
    asset_base_data["order"] = order
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "int_type",
                "loc": ("order",),
                "msg": "Input should be a valid integer",
            }
        ],
    )


@pytest.mark.parametrize(
    "order",
    [
        "",
        "abc",
    ],
)
def test_asset_base_order_invalid_string(
    asset_base_data: Dict[str, Any],
    order: str,
) -> None:
    """Test AssetBase.order rejects non-numeric or empty string."""
    asset_base_data["order"] = order
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "int_parsing",
                "loc": ("order",),
                "msg": "Input should be a valid integer, unable to parse string as an integer",
            }
        ],
    )


# ----------------
# Negative tests for AssetBase.type field
# ----------------

def test_asset_base_type_missing(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.type field is missing."""
    del asset_base_data["type"]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("type",),
                "msg": "Field required",
            }
        ],
    )


def test_asset_base_type_bad_type_none(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.type field with None value."""
    asset_base_data["type"] = None
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "literal_error",
                "loc": ("type",),
                "msg": "Input should be 'native', 'factory' or 'ibc'",
            }
        ],
    )


@pytest.mark.parametrize(
    "asset_type",
    [
        "invalid",
        "NATIVE",
        "",
        "custom",
        " factory", # trailing space
        ["ibc"], # list
        {"native"}, # set
        {"type": "factory"},  # dict
    ]
)
def test_asset_base_type_invalid_value(
    asset_base_data: Dict[str, Any],
    asset_type: Any,
) -> None:
    """Test AssetBase.type field with invalid values."""
    asset_base_data["type"] = asset_type
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "literal_error",
                "loc": ("type",),
                "msg": "Input should be 'native', 'factory' or 'ibc'",
            }
        ],
    )


# ----------------
# Negative tests for AssetBase.symbol field
# ----------------

def test_asset_base_symbol_missing(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.symbol field is missing."""
    del asset_base_data["symbol"]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("symbol",),
                "msg": "Field required",
            }
        ],
    )


def test_asset_base_symbol_bad_type_none(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.symbol field with None value."""
    asset_base_data["symbol"] = None
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("symbol",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_asset_base_symbol_too_short(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.symbol field is too short."""
    asset_base_data["symbol"] = "A"
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("symbol",),
                "msg": "String should have at least 2 characters",
            }
        ],
    )


def test_asset_base_symbol_too_long(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.symbol field is too long."""
    asset_base_data["symbol"] = "A" * 43
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("symbol",),
                "msg": "String should have at most 42 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "symbol",
    [
        "!ZIG",
        "ZIG!",
        " ZIG",
        "ZIG ",
        "@ZIG",
        "#ZIG",
        "$ZIG",
        ".ZIG", # starting with allowed character
        "zig ", # space at end
        "zig -usd" # space inbetween
    ]
)
def test_asset_base_symbol_bad_pattern(
    asset_base_data: Dict[str, Any],
    symbol: str,
) -> None:
    """Test AssetBase.symbol field with invalid pattern."""
    asset_base_data["symbol"] = symbol
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("symbol",),
                "msg": (
                    "Value error, symbol must start with a letter/number and contain only letters, numbers, "
                    "'.', '_' or '-'"
                ),
            }
        ],
    )


# ----------------
# Negative tests for AssetBase.name field
# ----------------

def test_asset_base_name_missing(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.name field is missing."""
    del asset_base_data["name"]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("name",),
                "msg": "Field required",
            }
        ],
    )


def test_asset_base_name_bad_type_none(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.name field with None value."""
    asset_base_data["name"] = None
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("name",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_asset_base_name_too_short(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.name field is too short."""
    asset_base_data["name"] = "A"
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("name",),
                "msg": "String should have at least 2 characters",
            }
        ],
    )


def test_asset_base_name_too_long(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.name field is too long."""
    asset_base_data["name"] = "A" * 101
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("name",),
                "msg": "String should have at most 100 characters",
            }
        ],
    )


def test_asset_base_name_empty_whitespace(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.name field with empty or whitespace-only string."""
    asset_base_data["name"] = "   "
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("name",),
                "msg": "Value error, name cannot be empty or whitespace",
            }
        ],
    )


@pytest.mark.parametrize(
    "name",
    [
        123,  # int
        12.3,  # float
        True,  # bool
        False,  # bool
        ["ZIG"],  # list
        {"name": "ZIG"},  # dict
        ("ZIG",),  # tuple
        {"ZIG"},  # set
    ],
)
def test_asset_base_name_bad_type(
    asset_base_data: Dict[str, Any],
    name: Any,
) -> None:
    """Test AssetBase.name field rejects non-string types (int, float, bool, list, dict, tuple, set)."""
    asset_base_data["name"] = name
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("name",),
                "msg": "Input should be a valid string",
            }
        ],
    )


# ----------------
# Negative tests for AssetBase.decimals field
# ----------------

def test_asset_base_decimals_missing(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.decimals field is missing."""
    del asset_base_data["decimals"]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("decimals",),
                "msg": "Field required",
            }
        ],
    )


def test_asset_base_decimals_bad_type_none(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.decimals field with None value."""
    asset_base_data["decimals"] = None
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "int_type",
                "loc": ("decimals",),
                "msg": "Input should be a valid integer",
            }
        ],
    )


@pytest.mark.parametrize("decimals", [True, False])
def test_asset_base_decimals_bad_type_bool(
    asset_base_data: Dict[str, Any],
    decimals: bool,
) -> None:
    """Test AssetBase.decimals field rejects bool (True and False)."""
    asset_base_data["decimals"] = decimals
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("decimals",),
                "msg": "Value error, decimals cannot be bool, must be an integer",
                "input": decimals,
            }
        ],
    )


def test_asset_base_decimals_negative(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.decimals field with negative value."""
    asset_base_data["decimals"] = -1
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "greater_than_equal",
                "loc": ("decimals",),
                "msg": "Input should be greater than or equal to 0",
            }
        ],
    )


@pytest.mark.parametrize(
    "decimals",
    [
        19,  # just over max (le=18)
        10**50,  # very large int: readable and exact
    ],
)
def test_asset_base_decimals_too_large(
    asset_base_data: Dict[str, Any],
    decimals: int,
) -> None:
    """Test AssetBase.decimals field rejects values greater than 18."""
    asset_base_data["decimals"] = decimals
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "less_than_equal",
                "loc": ("decimals",),
                "msg": "Input should be less than or equal to 18",
            }
        ],
    )


@pytest.mark.parametrize(
    "invalid_value",
    [
        [6],  # list
        {"decimals": 6},  # dict
        (6,),  # tuple
        {6},  # set
    ],
)
def test_asset_base_decimals_bad_type(
    asset_base_data: Dict[str, Any],
    invalid_value: Any,
) -> None:
    """Test AssetBase.decimals field rejects non-integer types (list, dict, tuple, set)."""
    asset_base_data["decimals"] = invalid_value
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "int_type",
                "loc": ("decimals",),
                "msg": "Input should be a valid integer",
            }
        ],
    )


def test_asset_base_decimals_float_rejected(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.decimals field rejects float (Pydantic raises int_from_float, not int_type)."""
    asset_base_data["decimals"] = 6.5
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "int_from_float",
                "loc": ("decimals",),
                "msg": "Input should be a valid integer, got a number with a fractional part",
            }
        ],
    )


@pytest.mark.parametrize(
    "invalid_string",
    [
        "",
        "   ",
        "abc",
        "true",
        "false",
        "12.5",  # float-like string (int() rejects)
    ],
)
def test_asset_base_decimals_invalid_string(
    asset_base_data: Dict[str, Any],
    invalid_string: str,
) -> None:
    """Test AssetBase.decimals field rejects non-parsable strings (empty, non-numeric, forbidden 'true'/'false')."""
    asset_base_data["decimals"] = invalid_string
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("decimals",),
                "msg": "Value error, decimals must be an integer or string that can be parsed as integer",
            }
        ],
    )


# ----------------
# Negative tests for AssetBase.denom_units field
# ----------------

@pytest.mark.parametrize(
    "invalid_value",
    [
        "uzig",  # str instead of list
        6,  # int instead of list
        {"denom": "uzig", "exponent": 0},  # dict instead of list
    ],
)
def test_asset_base_denom_units_bad_type(
    asset_base_data: Dict[str, Any],
    invalid_value: Any,
) -> None:
    """Test AssetBase.denom_units field rejects non-list types (str, int, dict)."""
    asset_base_data["denom_units"] = invalid_value
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
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


@pytest.mark.parametrize(
    "invalid_value,expected_msg",
    [
        (
            ({"denom": "uzig", "exponent": 0},),
            "Value error, denom_units must be a list, not tuple",
        ),
        (
            set(),
            "Value error, denom_units must be a list, not set",
        ),
    ],
)
def test_asset_base_denom_units_rejects_tuple_and_set(
    asset_base_data: Dict[str, Any],
    invalid_value: Any,
    expected_msg: str,
) -> None:
    """Test AssetBase.denom_units rejects tuple and set (reject_non_list_denom_units validator)."""
    asset_base_data["denom_units"] = invalid_value
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("denom_units",),
                "msg": expected_msg,
            }
        ],
    )


def test_asset_base_denom_units_missing_denom(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.denom_units list item missing required denom."""
    asset_base_data["denom_units"] = [{"exponent": 0}]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("denom_units", 0, "denom"),
                "msg": "Field required",
            }
        ],
    )


def test_asset_base_denom_units_denom_empty(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.denom_units list item with empty denom (min_length=1)."""
    asset_base_data["denom_units"] = [{"denom": "", "exponent": 0}]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("denom_units", 0, "denom"),
                "msg": "String should have at least 1 character",
            }
        ],
    )


@pytest.mark.parametrize(
    "denom",
    [
        "123",  # only numbers
        "9token",  # starts with number
        "-uzig",  # starts with valid symbol
        "@denom",  # starts with symbol
        "zig@chain",  # invalid char in middle
    ],
)
def test_asset_base_denom_units_denom_invalid_pattern(
    asset_base_data: Dict[str, Any],
    denom: str,
) -> None:
    """Test AssetBase.denom_units list item with denom that does not match pattern (must start with letter, use letters/numbers/'/:._-')."""
    asset_base_data["denom_units"] = [{"denom": denom, "exponent": 0}]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("denom_units", 0, "denom"),
                "msg": "Value error, denom must start with a letter and use letters, numbers or '/:._-'",
            }
        ],
    )


@pytest.mark.parametrize(
    "invalid_denom",
    [
        123,  # int
        6.5,  # float
        True,  # bool
        ["uzig"],  # list
        {"denom": "uzig"},  # dict
        None,  # None
    ],
)
def test_asset_base_denom_units_invalid_denom_type(
    asset_base_data: Dict[str, Any],
    invalid_denom: Any,
) -> None:
    """Test AssetBase.denom_units list item with denom as non-string (int, float, bool, list, dict, None)."""
    asset_base_data["denom_units"] = [{"denom": invalid_denom, "exponent": 0}]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("denom_units", 0, "denom"),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_asset_base_denom_units_negative_exponent(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.denom_units list item with negative exponent (ge=0)."""
    asset_base_data["denom_units"] = [{"denom": "uzig", "exponent": -1}]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "greater_than_equal",
                "loc": ("denom_units", 0, "exponent"),
                "msg": "Input should be greater than or equal to 0",
            }
        ],
    )


def test_asset_base_denom_units_float_exponent(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.denom_units list item with exponent as float."""
    asset_base_data["denom_units"] = [{"denom": "uzig", "exponent": 6.5}]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "int_from_float",
                "loc": ("denom_units", 0, "exponent"),
                "msg": "Input should be a valid integer, got a number with a fractional part",
            }
        ],
    )

def test_asset_base_denom_units_missing_exponent(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.denom_units list item missing required exponent."""
    asset_base_data["denom_units"] = [{"denom": "uzig"}]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("denom_units", 0, "exponent"),
                "msg": "Field required",
            }
        ],
    )


@pytest.mark.parametrize(
    "invalid_exponent,expected_type,expected_msg",
    [
        ([6], "int_type", "Input should be a valid integer"),
        ({"exponent": 6}, "int_type", "Input should be a valid integer"),
        (True, "value_error", "Value error, exponent cannot be bool, must be an integer"),
        (None, "int_type", "Input should be a valid integer"),  # None yields int_type, not missing
    ],
)
def test_asset_base_denom_units_invalid_exponent_type(
    asset_base_data: Dict[str, Any],
    invalid_exponent: Any,
    expected_type: str,
    expected_msg: str,
) -> None:
    """Test AssetBase.denom_units list item with exponent as wrong type (list, dict, bool, None)."""
    asset_base_data["denom_units"] = [{"denom": "uzig", "exponent": invalid_exponent}]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": expected_type,
                "loc": ("denom_units", 0, "exponent"),
                "msg": expected_msg,
            }
        ],
    )


# ----------------
# Negative tests for AssetBase.display_denom field
# ----------------

def test_asset_base_display_denom_missing(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.display_denom field is missing."""
    del asset_base_data["display_denom"]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("display_denom",),
                "msg": "Field required",
            }
        ],
    )


def test_asset_base_display_denom_bad_type_none(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.display_denom field with None value."""
    asset_base_data["display_denom"] = None
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("display_denom",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_asset_base_display_denom_too_short(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.display_denom field is too short."""
    asset_base_data["display_denom"] = ""
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("display_denom",),
                "msg": "String should have at least 1 character",
            }
        ],
    )


def test_asset_base_display_denom_too_long(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.display_denom field is too long."""
    asset_base_data["display_denom"] = "A" * 33
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("display_denom",),
                "msg": "String should have at most 32 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "display_denom",
    [
        "!ZIG",
        "ZIG!",
        " ZIG",
        "ZIG ",
        "@ZIG",
        "#ZIG",
        "$ZIG",
    ]
)
def test_asset_base_display_denom_bad_pattern(
    asset_base_data: Dict[str, Any],
    display_denom: str,
) -> None:
    """Test AssetBase.display_denom field with invalid pattern."""
    asset_base_data["display_denom"] = display_denom
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("display_denom",),
                "msg": (
                    "Value error, display_denom must start with a letter/number and contain only letters, numbers, "
                    "':', '.', '_' or '-'"
                ),
            }
        ],
    )

@pytest.mark.parametrize(
    "display_denom",
    [
        ["!ZIG"],  # list
        {"ZIG!"},  # set
        (" ZIG",),  # tuple
        True,  # bool
        {"display_denom" : "ZIG"},  # dict
    ]
)
def test_asset_base_display_denom_bad_type(
    asset_base_data: Dict[str, Any],
    display_denom: str,
) -> None:
    """Test AssetBase.display_denom field with invalid type (not string)."""
    asset_base_data["display_denom"] = display_denom
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("display_denom",),
                "msg": "Input should be a valid string"
            }
        ],
    )

# ----------------
# Negative tests for AssetBase.description field
# ----------------

def test_asset_base_description_too_short(asset_base_data: Dict[str, Any]) -> None:
    """Cosmos chain-registry requires minLength=1 when description is present."""
    asset_base_data["description"] = ""
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("description",),
                "msg": "String should have at least 1 character",
            }
        ],
    )

def test_asset_base_description_too_long(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.description field is too long."""
    asset_base_data["description"] = "A" * 2049
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("description",),
                "msg": "String should have at most 2048 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "invalid_value",
    [
        123,  # int
        3.14,  # float
        True,  # bool
        ["text"],  # list
        {"desc": "text"},  # dict
        ("tuple",),  # tuple
        {"set"},  # set
    ],
)
def test_asset_base_description_bad_type(
    asset_base_data: Dict[str, Any],
    invalid_value: Any,
) -> None:
    """Test AssetBase.description field rejects non-string types."""
    asset_base_data["description"] = invalid_value
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("description",),
                "msg": "Input should be a valid string",
            }
        ],
    )


# ----------------
# Negative tests for AssetBase.extended_description field
# ----------------

def test_asset_base_extended_description_too_short(
    asset_base_data: Dict[str, Any],
) -> None:
    """When extended_description is present, minLength=1 is required."""
    asset_base_data["extended_description"] = ""
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("extended_description",),
                "msg": "String should have at least 1 character",
            }
        ],
    )


@pytest.mark.parametrize(
    "invalid_value",
    [
        123,  # int
        3.14,  # float
        True,  # bool
        ["text"],  # list
        {"desc": "text"},  # dict
        ("tuple",),  # tuple
        {"set"},  # set
    ],
)
def test_asset_base_extended_description_bad_type(
    asset_base_data: Dict[str, Any],
    invalid_value: Any,
) -> None:
    """Test AssetBase.extended_description field rejects non-string types."""
    asset_base_data["extended_description"] = invalid_value
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("extended_description",),
                "msg": "Input should be a valid string",
            }
        ],
    )


# ----------------
# Negative tests for AssetBase.keywords field
# ----------------


@pytest.mark.parametrize(
    "keywords",
    [
        ([]),
        (["ok"] * 21),
    ],
)
def test_asset_base_keywords_invalid_length(
    asset_base_data: Dict[str, Any],
    keywords: Any,
) -> None:
    """Test AssetBase.keywords field rejects empty list and more than 20 items."""
    asset_base_data["keywords"] = keywords
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("keywords",),
                "msg": "Value error, keywords must contain between 1 and 20 items",
            }
        ],
    )

@pytest.mark.parametrize(
    "invalid_value",
    [
        "zigchain",  # str
        123,  # int
        {"key": "value"},  # dict
        True,  # bool
    ],
)
def test_asset_base_keywords_bad_type(
    asset_base_data: Dict[str, Any],
    invalid_value: Any,
) -> None:
    """Test AssetBase.keywords field rejects non-list types."""
    asset_base_data["keywords"] = invalid_value
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "list_type",
                "loc": ("keywords",),
                "msg": "Input should be a valid list",
            }
        ],
    )


def test_asset_base_keywords_bad_type_set(
    asset_base_data: Dict[str, Any]
) -> None:
    """Test AssetBase.keywords field rejects non-list type (set)."""
    asset_base_data["keywords"] = {"set"}
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("keywords",),
                "msg": "Value error, keywords must be a list, not set",
            }
        ],
    )

def test_asset_base_keywords_bad_type_tuple(
    asset_base_data: Dict[str, Any]
) -> None:
    """Test AssetBase.keywords field rejects non-list type (tuple)."""
    asset_base_data["keywords"] = ("a", "b")
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("keywords",),
                "msg": "Value error, keywords must be a list, not tuple",
            }
        ],
    )


def test_asset_base_keywords_item_empty_string(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.keywords list items must be non-empty strings."""
    asset_base_data["keywords"] = ["valid", ""]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("keywords",),
                "msg": "Value error, keywords items must be non-empty strings",
            }
        ],
    )


@pytest.mark.parametrize(
    "invalid_item",
    [
        123,  # int
        3.14,  # float
        True,  # bool
        None,  # None
        ["nested"],  # list
        {"key": "value"},  # dict
        ("tuple",),  # tuple
    ],
)
def test_asset_base_keywords_item_non_string(
    asset_base_data: Dict[str, Any],
    invalid_item: Any,
) -> None:
    """Test AssetBase.keywords list items must be strings (rejects int, float, bool, None, list, dict, tuple).

    Pydantic validates items as List[str] before validate_keywords runs, producing string_type
    at the item's index when a non-string value is provided.
    """
    asset_base_data["keywords"] = ["valid", invalid_item]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("keywords", 1),
                "msg": "Input should be a valid string",
            }
        ],
    )


# ----------------
# Negative tests for AssetBase.images field
# ----------------

@pytest.mark.parametrize(
    "invalid_value",
    [
        "https://raw.githubusercontent.com/test/img.png",  # str instead of list
        {},  # dict instead of list
        123,  # int instead of list
        True,  # bool instead of list
        3.14,  # float instead of list
    ],
)
def test_asset_base_images_bad_type(
    asset_base_data: Dict[str, Any],
    invalid_value: Any,
) -> None:
    """Test AssetBase.images field rejects non-list types (list_type from Pydantic)."""
    asset_base_data["images"] = invalid_value
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "list_type",
                "loc": ("images",),
                "msg": "Input should be a valid list",
            }
        ],
    )


@pytest.mark.parametrize(
    "images_value,expected_msg",
    [
        # Tuple/set rejected by reject_non_list_images (value_error), not list_type
        (
            ({"png": "https://raw.githubusercontent.com/test/logo.png"},),
            "Value error, images must be a list, not tuple",
        ),
        (set(), "Value error, images must be a list, not set"),
    ],
)
def test_asset_base_images_rejects_tuple_and_set(
    asset_base_data: Dict[str, Any],
    images_value: Any,
    expected_msg: str,
) -> None:
    """Test AssetBase.images rejects tuple and set (only list or None allowed; field validator)."""
    asset_base_data["images"] = images_value
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": ("images",), "msg": expected_msg},
        ],
    )


def test_asset_base_images_list_invalid_item_not_image_entry(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.images: list item that is not ImageEntry/ImageSyncPointer (e.g. bare str)."""
    asset_base_data["images"] = ["https://raw.githubusercontent.com/test/a.png"]
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "model_type",
                "loc": ("images", 0, "ImageEntry"),
                "msg": "Input should be a valid dictionary or instance of ImageEntry",
            }
        ],
    )


# ----------------
# Negative tests for AssetBase.logo_uris field
# ----------------

@pytest.mark.parametrize(
    "invalid_value",
    [
        True,  # bool
        123,  # int
        "https://raw.githubusercontent.com/test/logo.png",  # str
        [],  # list (not dict)
        ("png", "https://raw.githubusercontent.com/test/logo.png"),  # tuple
    ],
)
def test_asset_base_logo_uris_bad_type(
    asset_base_data: Dict[str, Any],
    invalid_value: Any,
) -> None:
    """Test AssetBase.logo_uris field rejects non-dict, non-LogoUris types."""
    asset_base_data["logo_uris"] = invalid_value
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("logo_uris",),
                "msg": "Value error, logo_uris must be a LogoUris object or mapping of logo types to URLs",
            }
        ],
    )


def test_asset_base_logo_uris_invalid_url(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.logo_uris field with invalid URL (png)."""
    asset_base_data["logo_uris"] = {"png": "not_a_url"}
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("logo_uris",),
                "msg": "Value error, logo_uris.png is not a valid URL: not_a_url",
                "input": {"png": "not_a_url"},
            }
        ],
    )


def test_asset_base_logo_uris_invalid_url_svg(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.logo_uris field with invalid URL (svg)."""
    asset_base_data["logo_uris"] = {"svg": "not_a_url"}
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("logo_uris",),
                "msg": "Value error, logo_uris.svg is not a valid URL: not_a_url",
            }
        ],
    )


# ----------------
# Negative tests for AssetBase.socials field
# ----------------

def test_asset_base_socials_empty_dict_invalid(asset_base_data: Dict[str, Any]) -> None:
    """Test AssetBase.socials rejects an empty dict (must have at least one property)."""
    asset_base_data["socials"] = {}
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("socials",),
                "msg": "Value error, socials must contain at least one property",
            }
        ],
    )


def test_asset_base_socials_extra_key_forbidden(asset_base_data: Dict[str, Any]) -> None:
    """Test AssetBase.socials rejects extra keys not in the allowed set."""
    asset_base_data["socials"] = {"website": "https://example.com", "linkedin": "https://linkedin.com/in/x"}
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "extra_forbidden",
                "loc": ("socials", "linkedin"),
                "msg": "Extra inputs are not permitted",
            }
        ],
    )


def test_asset_base_socials_bad_pattern(asset_base_data: Dict[str, Any]) -> None:
    """Test AssetBase.socials rejects URLs that do not match the required pattern."""
    asset_base_data["socials"] = {"x": "http://twitter.com/example"}
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("socials", "x"),
                "msg": "Value error, socials.x must match ^https://(x\\.com|twitter\\.com)/.+$",
            }
        ],
    )


def test_asset_base_socials_invalid_url(asset_base_data: Dict[str, Any]) -> None:
    """Test AssetBase.socials rejects values that are not valid URLs."""
    asset_base_data["socials"] = {"website": "not_a_url"}
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "url_parsing",
                "loc": ("socials", "website"),
                "msg": "Input should be a valid URL, relative URL without a base",
            }
        ],
    )


@pytest.mark.parametrize(
    "invalid_value",
    [
        123,  # int
        "https://example.com",  # str (single URL)
        [],  # list
        True,  # bool
        ("website", "https://example.com"),  # tuple
    ],
)
def test_asset_base_socials_bad_type(
    asset_base_data: Dict[str, Any],
    invalid_value: Any,
) -> None:
    """Test AssetBase.socials field rejects non-dict, non-Socials types."""
    asset_base_data["socials"] = invalid_value
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("socials",),
                "msg": "Value error, socials must be a Socials object or mapping of platform names to URLs",
            }
        ],
    )


# ----------------
# Negative tests for AssetBase.coingecko_id field
# ----------------

def test_asset_base_coingecko_id_too_short(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.coingecko_id field is too short."""
    asset_base_data["coingecko_id"] = "a"
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("coingecko_id",),
                "msg": "String should have at least 2 characters",
            }
        ],
    )


def test_asset_base_coingecko_id_too_long(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase.coingecko_id field is too long."""
    asset_base_data["coingecko_id"] = "a" * 101
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("coingecko_id",),
                "msg": "String should have at most 100 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "coingecko_id",
    [
        "Usdc",  # uppercase (must be lowercase)
        "USD-COIN",  # mixed/uppercase
        "usd_coin",  # underscore (only hyphens allowed)
        "usd coin",  # space
        "usd.coin",  # dot
        "usd@coin",  # at sign
        "资产",  # unicode
    ],
)
def test_asset_base_coingecko_id_bad_pattern(
    asset_base_data: Dict[str, Any],
    coingecko_id: str,
) -> None:
    """Test AssetBase.coingecko_id field with invalid format."""
    asset_base_data["coingecko_id"] = coingecko_id
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("coingecko_id",),
                "msg": "Value error, coingecko_id must be lowercase alphanumerics separated by hyphens",
            }
        ],
    )


@pytest.mark.parametrize(
    "invalid_value",
    [
        123,  # int
        True,  # bool
        [],  # list
        {"id": "usd-coin"},  # dict
        3.14,  # float
        ("usd",),  # tuple
    ],
)
def test_asset_base_coingecko_id_bad_type(
    asset_base_data: Dict[str, Any],
    invalid_value: Any,
) -> None:
    """Test AssetBase.coingecko_id field rejects non-string types."""
    asset_base_data["coingecko_id"] = invalid_value
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("coingecko_id",),
                "msg": "Input should be a valid string",
            }
        ],
    )


# ----------------
# Negative tests for AssetBase.is_verified field
# ----------------

# reject_non_bool_is_verified (mode=before) runs before Pydantic bool coercion — same value_error for all.
@pytest.mark.parametrize(
    "invalid_value",
    [
        1.2,  # float
        [True],  # list
        {"verified": True},  # dict
        (True, False),  # tuple
        3,  # int
        "",  # empty string
        "Truest",  # string
        1,      # int 1
        0,      # int 0
        "True",  # string "True"
        "false", # string "false"
    ],
)
def test_asset_base_is_verified_bad_type(
    asset_base_data: Dict[str, Any],
    invalid_value: Any,
) -> None:
    """Test AssetBase.is_verified rejects non-bool container/scalar types (field validator)."""
    asset_base_data["is_verified"] = invalid_value
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("is_verified",),
                "msg": "Value error, is_verified must be a boolean, not a bool-like value",
            }
        ],
    )


# ----------------
# Negative tests for AssetBase extra fields
# ----------------

def test_asset_base_extra_forbidden(
    asset_base_data: Dict[str, Any],
) -> None:
    """Test AssetBase rejects unknown fields (extra='forbid')."""
    asset_base_data["unknown_key"] = "value"
    with pytest.raises(ValidationError) as exc:
        AssetBase(**asset_base_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "extra_forbidden",
                "loc": ("unknown_key",),
                "msg": "Extra inputs are not permitted",
            }
        ],
    )


######################################################################
# Positive tests for LogoUris models
######################################################################

# ----------------
# Positive tests for LogoUris class
# ----------------

def test_logo_uris_class(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris class with all fields."""
    logos = LogoUris(**logo_uris_data)
    assert len(LogoUris.model_fields) == 3
    assert logos.chain_name == logo_uris_data["chain_name"]
    assert str(logos.png) == logo_uris_data["png"]
    assert str(logos.svg) == logo_uris_data["svg"]


def test_logo_uris_all_none() -> None:
    """Test LogoUris with all fields omitted (all None)."""
    logos = LogoUris()
    assert logos.chain_name is None
    assert logos.png is None
    assert logos.svg is None

def test_logo_uris_only_chain_name(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris with only chain_name field."""
    del logo_uris_data["svg"]
    del logo_uris_data["png"]
    logos = LogoUris(**logo_uris_data)
    assert logos.chain_name == logo_uris_data["chain_name"]
    assert logos.png is None
    assert logos.svg is None

def test_logo_uris_only_png(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris with only png field."""
    del logo_uris_data["svg"]
    del logo_uris_data["chain_name"]
    logos = LogoUris(**logo_uris_data)
    assert str(logos.png) == logo_uris_data["png"]
    assert logos.chain_name is None
    assert logos.svg is None

def test_logo_uris_only_svg(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris with only svg field."""
    del logo_uris_data["chain_name"]
    del logo_uris_data["png"]
    logos = LogoUris(**logo_uris_data)
    assert str(logos.svg) == logo_uris_data["svg"]
    assert logos.chain_name is None
    assert logos.png is None

# ----------------
# Positive tests for LogoUris.chain_name field
# ----------------

def test_logo_uris_chain_name_none(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris.chain_name field with explicit None."""
    logo_uris_data["chain_name"] = None
    logos = LogoUris(**logo_uris_data)
    assert logos.chain_name is None


def test_logo_uris_chain_name_missing(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris.chain_name when key is omitted (defaults to None)."""
    del logo_uris_data["chain_name"]
    logos = LogoUris(**logo_uris_data)
    assert logos.chain_name is None


@pytest.mark.parametrize(
    "chain_name",
    [
        "cosmoshub",
        "ethereum",
        "noble",
        "stride",
        "a",  # min length edge case
        "z",  # single char
        "arbitrum-one",  # hyphen
        "avalanche_2",  # underscore
        "chain123",  # with digits
        "CosmosHub",  # mixed case
        "UPPERCASE",
        "b" * 1000,  # long string
        "123",  # numbers only
        "@@@",  # symbols only
        "ChainName",  # mixed case
        "asset_123.456.789",  # letters, numbers and underscore and dot and hyphen
    ],
)
def test_logo_uris_chain_name_valid(
    logo_uris_data: Dict[str, Any],
    chain_name: str,
) -> None:
    """Test LogoUris.chain_name field with valid non-empty string values."""
    logo_uris_data["chain_name"] = chain_name
    logos = LogoUris(**logo_uris_data)
    assert logos.chain_name == chain_name


# ----------------
# Positive tests for LogoUris.png field
# ----------------

def test_logo_uris_png_none(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris.png field with explicit None."""
    logo_uris_data["png"] = None
    logos = LogoUris(**logo_uris_data)
    assert logos.png is None


def test_logo_uris_png_missing(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris.png when key is omitted (defaults to None)."""
    del logo_uris_data["png"]
    logos = LogoUris(**logo_uris_data)
    assert logos.png is None


@pytest.mark.parametrize(
    "png",
    [
        "https://raw.githubusercontent.com/test/logo.png",
        "https://raw.githubusercontent.com/test/a.png",
        "https://raw.githubusercontent.com/test/logo.png?q=1",  # query string
        "https://raw.githubusercontent.com/test/logo.png#anchor",  # fragment
        "https://raw.githubusercontent.com/test/logo.png/",  # trailing slash
        "https://raw.githubusercontent.com/test/path%2Fto%2Flogo.png",  # encoded path
        "https://raw.githubusercontent.com/ZIGChain/assets/main/logos/LOGO.PNG",  # uppercase extension
    ],
)
def test_logo_uris_png_valid(
    logo_uris_data: Dict[str, Any],
    png: str,
) -> None:
    """Test LogoUris.png field with valid HTTP(S) URL values on the allowlisted host."""
    logo_uris_data["png"] = png
    logos = LogoUris(**logo_uris_data)
    assert logos.png is not None
    assert str(logos.png) == png


# ----------------
# Positive tests for LogoUris.svg field
# ----------------

def test_logo_uris_svg_none(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris.svg field with explicit None."""
    logo_uris_data["svg"] = None
    logos = LogoUris(**logo_uris_data)
    assert logos.svg is None


def test_logo_uris_svg_missing(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris.svg when key is omitted (defaults to None)."""
    del logo_uris_data["svg"]
    logos = LogoUris(**logo_uris_data)
    assert logos.svg is None


@pytest.mark.parametrize(
    "svg",
    [
        "https://raw.githubusercontent.com/test/logo.svg",
        "https://raw.githubusercontent.com/test/a.svg",
        "https://raw.githubusercontent.com/test/logo.svg/",  # trailing slash
        "https://raw.githubusercontent.com/test/assets/logo.svg?v=1",  # query string
        "https://raw.githubusercontent.com/ZIGChain/assets/main/logos/LOGO.SVG",  # uppercase extension
    ],
)
def test_logo_uris_svg_valid(
    logo_uris_data: Dict[str, Any],
    svg: str,
) -> None:
    """Test LogoUris.svg field with valid HTTP(S) URL values on the allowlisted host."""
    logo_uris_data["svg"] = svg
    logos = LogoUris(**logo_uris_data)
    assert logos.svg is not None
    assert str(logos.svg) == svg


######################################################################
# Negative tests for LogoUris models
######################################################################

# ----------------
# Negative tests for LogoUris class
# ----------------

def test_logo_uris_extra_forbidden(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris rejects unknown fields (extra='forbid')."""
    logo_uris_data["unknown_key"] = "value"
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "extra_forbidden", "loc": ("unknown_key",), "msg": "Extra inputs are not permitted"},
        ],
    )


# ----------------
# Negative tests for LogoUris.chain_name field
# ----------------

def test_logo_uris_chain_name_empty_string(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris.chain_name with empty string (fails min_length when provided)."""
    logo_uris_data["chain_name"] = ""
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_too_short", "loc": ("chain_name",), "msg": "String should have at least 1 character"},
        ],
    )


@pytest.mark.parametrize(
    "chain_name",
    [
        123,  # int
        3.14,  # float
        True,  # bool
        False,  # bool
        ["cosmoshub"],  # list
        {"chain_name": "cosmoshub"},  # dict
        (),  # tuple
        ("cosmoshub",),  # tuple with value
    ],
)
def test_logo_uris_chain_name_bad_type(
    logo_uris_data: Dict[str, Any],
    chain_name: Any,
) -> None:
    """Test LogoUris.chain_name rejects non-string types when provided."""
    logo_uris_data["chain_name"] = chain_name
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_type", "loc": ("chain_name",), "msg": "Input should be a valid string"},
        ],
    )


# ----------------
# Negative tests for LogoUris.png field
# ----------------

@pytest.mark.parametrize(
    "png",
    [
        "ftp://example.com/logo.png",  # wrong scheme (non-http)
        "javascript:alert(1)",  # javascript scheme
        "file:///tmp/logo.png",  # file scheme
    ],
)
def test_logo_uris_png_invalid_url_scheme(
    logo_uris_data: Dict[str, Any],
    png: str,
) -> None:
    """Test LogoUris.png rejects URLs with non-http(s) scheme (url_scheme)."""
    logo_uris_data["png"] = png
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_scheme", "loc": ("png",), "msg": "URL scheme should be 'http' or 'https'"},
        ],
    )


@pytest.mark.parametrize(
    "png",
    [
        "//example.com/logo.png",  # no scheme (relative)
        "not-a-url",  # invalid format
        "   ",  # whitespace only
    ],
)
def test_logo_uris_png_invalid_url_parsing_relative(
    logo_uris_data: Dict[str, Any],
    png: str,
) -> None:
    """Test LogoUris.png rejects relative/invalid URLs (url_parsing, relative URL without a base)."""
    logo_uris_data["png"] = png
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("png",), "msg": "Input should be a valid URL, relative URL without a base"},
        ],
    )


def test_logo_uris_png_invalid_url_empty(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris.png rejects empty string (url_parsing)."""
    logo_uris_data["png"] = ""
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("png",), "msg": "Input should be a valid URL, input is empty"},
        ],
    )


def test_logo_uris_png_invalid_url_empty_host(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris.png rejects URL with empty host (url_parsing)."""
    logo_uris_data["png"] = "https://"
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("png",), "msg": "Input should be a valid URL, empty host"},
        ],
    )


def test_logo_uris_png_invalid_url_parsing_invalid_domain(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris.png rejects URL with space in host (url_parsing, invalid international domain name)."""
    logo_uris_data["png"] = "https://example .com/logo.png"
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("png",), "msg": "Input should be a valid URL, invalid international domain name"},
        ],
    )


@pytest.mark.parametrize(
    "png",
    [
        123,  # int
        3.14,  # float
        True,  # bool
        False,  # bool
        ["https://raw.githubusercontent.com/test/logo.png"],  # list
        {"png": "https://raw.githubusercontent.com/test/logo.png"},  # dict
        (),  # tuple
    ],
)
def test_logo_uris_png_bad_type(
    logo_uris_data: Dict[str, Any],
    png: Any,
) -> None:
    """Test LogoUris.png rejects non-string types when provided."""
    logo_uris_data["png"] = png
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_type", "loc": ("png",), "msg": "URL input should be a string or URL"},
        ],
    )


# ----------------
# Negative tests for LogoUris.svg field
# ----------------

@pytest.mark.parametrize(
    "svg",
    [
        "ftp://example.com/logo.svg",  # wrong scheme
        "javascript:alert(1)",  # javascript scheme
        "file:///tmp/logo.svg",  # file scheme
    ],
)
def test_logo_uris_svg_invalid_url_scheme(
    logo_uris_data: Dict[str, Any],
    svg: str,
) -> None:
    """Test LogoUris.svg rejects URLs with non-http(s) scheme (url_scheme)."""
    logo_uris_data["svg"] = svg
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_scheme", "loc": ("svg",), "msg": "URL scheme should be 'http' or 'https'"},
        ],
    )


@pytest.mark.parametrize(
    "svg",
    [
        "//example.com/logo.svg",  # no scheme (relative)
        "not-a-url",  # invalid format
        "   ",  # whitespace only
    ],
)
def test_logo_uris_svg_invalid_url_parsing_relative(
    logo_uris_data: Dict[str, Any],
    svg: str,
) -> None:
    """Test LogoUris.svg rejects relative/invalid URLs (url_parsing, relative URL without a base)."""
    logo_uris_data["svg"] = svg
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("svg",), "msg": "Input should be a valid URL, relative URL without a base"},
        ],
    )


def test_logo_uris_svg_invalid_url_parsing_empty(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris.svg rejects empty string (url_parsing)."""
    logo_uris_data["svg"] = ""
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("svg",), "msg": "Input should be a valid URL, input is empty"},
        ],
    )


def test_logo_uris_svg_invalid_url_parsing_empty_host(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris.svg rejects URL with empty host (url_parsing)."""
    logo_uris_data["svg"] = "https://"
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("svg",), "msg": "Input should be a valid URL, empty host"},
        ],
    )


def test_logo_uris_svg_invalid_url_parsing_invalid_domain(
    logo_uris_data: Dict[str, Any],
) -> None:
    """Test LogoUris.svg rejects URL with space in host (url_parsing, invalid international domain name)."""
    logo_uris_data["svg"] = "https://example .com/logo.svg"
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("svg",), "msg": "Input should be a valid URL, invalid international domain name"},
        ],
    )


@pytest.mark.parametrize(
    "svg",
    [
        123,  # int
        3.14,  # float
        True,  # bool
        False,  # bool
        ["https://raw.githubusercontent.com/test/logo.svg"],  # list
        {"svg": "https://raw.githubusercontent.com/test/logo.svg"},  # dict
        (),  # tuple
    ],
)
def test_logo_uris_svg_bad_type(
    logo_uris_data: Dict[str, Any],
    svg: Any,
) -> None:
    """Test LogoUris.svg rejects non-string types when provided."""
    logo_uris_data["svg"] = svg
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_type", "loc": ("svg",), "msg": "URL input should be a string or URL"},
        ],
    )


# ----------------
# Negative tests for LogoUris host allowlist
# ----------------


@pytest.mark.parametrize(
    "field,url",
    [
        ("png", "https://evil.com/logo.png"),
        ("png", "https://example.com/logo.png"),
        ("png", "https://raw.githubusercontent.com.evil.com/logo.png"),  # suffix confusable
        ("svg", "https://evil.com/logo.svg"),
        ("svg", "https://cdn.jsdelivr.net/logo.svg"),
        ("svg", "https://sub.raw.githubusercontent.com/logo.svg"),  # subdomain is NOT exact host
    ],
)
def test_logo_uris_host_not_in_allowlist_rejected(
    logo_uris_data: Dict[str, Any],
    field: str,
    url: str,
) -> None:
    """LogoUris rejects png/svg whose host is not exactly `raw.githubusercontent.com`."""
    logo_uris_data[field] = url
    with pytest.raises(ValidationError) as exc:
        LogoUris(**logo_uris_data)
    # Partial match: type + loc. The full msg includes the allowlist for operator debugging.
    check_model_error(
        errors=exc,
        expected_errors=[{"type": "value_error", "loc": (field,)}],
    )
    assert any("allowlist" in e["msg"].lower() for e in exc.value.errors())


######################################################################
# Positive tests for Socials models
######################################################################

# ----------------
# Positive tests for Socials class
# ----------------

def test_socials_class(
    socials_data: Dict[str, Any],
) -> None:
    """Test Socials class with all fields."""
    socials = Socials(**socials_data)
    assert len(Socials.model_fields) == 7
    # HttpUrl fields are normalized on parse; compare via str(HttpUrl(...)) to handle trailing-slash normalization
    assert str(socials.website) == str(HttpUrl(socials_data["website"]))
    assert socials.x == socials_data["x"]  # x is str, not HttpUrl
    assert str(socials.telegram) == str(HttpUrl(socials_data["telegram"]))
    assert str(socials.discord) == str(HttpUrl(socials_data["discord"]))
    assert str(socials.github) == str(HttpUrl(socials_data["github"]))
    assert str(socials.medium) == str(HttpUrl(socials_data["medium"]))
    assert str(socials.reddit) == str(HttpUrl(socials_data["reddit"]))


def test_socials_minimal_single_property() -> None:
    """Test Socials with single property (minProperties: 1)."""
    socials = Socials(medium="https://medium.com/@example")
    assert str(socials.medium) == str(HttpUrl("https://medium.com/@example"))
    assert socials.x is None
    assert socials.telegram is None
    assert socials.discord is None
    assert socials.github is None
    assert socials.reddit is None


# ----------------
# Positive tests for Socials.website field
# ----------------

def test_socials_website_none(
    socials_data: Dict[str, Any],
) -> None:
    """Test Socials.website field with explicit None."""
    socials_data["website"] = None
    socials = Socials(**socials_data)
    assert socials.website is None


def test_socials_website_missing(
    socials_data: Dict[str, Any],
) -> None:
    """Test Socials.website when key is omitted (defaults to None)."""
    del socials_data["website"]
    socials = Socials(**socials_data)
    assert socials.website is None


@pytest.mark.parametrize(
    "website",
    [
        "https://example.com",
        "https://sub.example.com/path",  # path
        "https://example.com/path/to/page",  # deep path
        "https://example.com?q=1",  # query
        "https://example.com#section",  # fragment
        "https://a.co",  # short domain
        "https://example.com:8443/page",  # non-default port
        "https://example.com/",  # trailing slash
        "https://user:pass@example.com/page",  # userinfo (edge case)
    ],
)
def test_socials_website_valid(
    socials_data: Dict[str, Any],
    website: str,
) -> None:
    """Test Socials.website field with valid URL values."""
    socials_data["website"] = website
    socials = Socials(**socials_data)
    # Pydantic normalizes HttpUrl (e.g. adds trailing slash); compare via str(HttpUrl(...))
    assert str(socials.website) == str(HttpUrl(website))


# ----------------
# Positive tests for Socials.x field
# ----------------

def test_socials_x_none(
    socials_data: Dict[str, Any],
) -> None:
    """Test Socials.x field with explicit None."""
    socials_data["x"] = None
    socials = Socials(**socials_data)
    assert socials.x is None


def test_socials_x_missing(
    socials_data: Dict[str, Any],
) -> None:
    """Test Socials.x when key is omitted (defaults to None)."""
    del socials_data["x"]
    socials = Socials(**socials_data)
    assert socials.x is None


@pytest.mark.parametrize(
    "x_url",
    [
        "https://x.com/username",
        "https://twitter.com/username",
        "https://x.com/a",  # min path
        "https://x.com/user/sub",  # path with slash
        "https://twitter.com/handle",  # twitter handle
        "https://x.com/123",  # digits in path
        "https://x.com/user-name",  # hyphen in path
        "https://x.com/user_name",  # underscore in path
    ],
)
def test_socials_x_valid(
    socials_data: Dict[str, Any],
    x_url: str,
) -> None:
    """Test Socials.x field with valid x.com/twitter.com URLs."""
    socials_data["x"] = x_url
    socials = Socials(**socials_data)
    assert socials.x == x_url


######################################################################
# Negative tests for Socials models
######################################################################

# ----------------
# Negative tests for Socials class
# ----------------

def test_socials_extra_forbidden(
    socials_data: Dict[str, Any],
) -> None:
    """Test Socials rejects unknown fields (extra='forbid')."""
    socials_data["unknown_key"] = "value"
    with pytest.raises(ValidationError) as exc:
        Socials(**socials_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "extra_forbidden", "loc": ("unknown_key",), "msg": "Extra inputs are not permitted"},
        ],
    )


def test_socials_all_properties_none_fails() -> None:
    """Test Socials model validator: at least one property required."""
    with pytest.raises(ValidationError) as exc:
        Socials(
            website=None,
            x=None,
            telegram=None,
            discord=None,
            github=None,
            medium=None,
            reddit=None,
        )
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": (), "msg": "Value error, socials must contain at least one property"},
        ],
    )


# ----------------
# Negative tests for Socials.website field
# ----------------

def test_socials_website_empty_string(
    socials_data: Dict[str, Any],
) -> None:
    """Test Socials.website rejects empty string (HttpUrl validation)."""
    socials_data["website"] = ""
    with pytest.raises(ValidationError) as exc:
        Socials(**socials_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("website",), "msg": "Input should be a valid URL, input is empty"},
        ],
    )


@pytest.mark.parametrize(
    "website",
    [
        123,  # int
        3.14,  # float
        True,  # bool
        False,  # bool
        ["https://example.com"],  # list
        {"url": "https://example.com"},  # dict
        (),  # tuple
    ],
)
def test_socials_website_bad_type(
    socials_data: Dict[str, Any],
    website: Any,
) -> None:
    """Test Socials.website rejects non-string/non-URL types (HttpUrl validation)."""
    socials_data["website"] = website
    with pytest.raises(ValidationError) as exc:
        Socials(**socials_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_type", "loc": ("website",), "msg": "URL input should be a string or URL"},
        ],
    )


def test_socials_website_invalid_url_not_a_url(
    socials_data: Dict[str, Any],
) -> None:
    """Test Socials.website rejects invalid URL format (HttpUrl validation)."""
    socials_data["website"] = "not-a-url"
    with pytest.raises(ValidationError) as exc:
        Socials(**socials_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("website",), "msg": "Input should be a valid URL, relative URL without a base"},
        ],
    )


def test_socials_website_invalid_url_whitespace(
    socials_data: Dict[str, Any],
) -> None:
    """Test Socials.website rejects whitespace-only URL (HttpUrl validation)."""
    socials_data["website"] = "   "
    with pytest.raises(ValidationError) as exc:
        Socials(**socials_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("website",), "msg": "Input should be a valid URL, relative URL without a base"},
        ],
    )


def test_socials_website_invalid_url_no_scheme(
    socials_data: Dict[str, Any],
) -> None:
    """Test Socials.website rejects URL without scheme (HttpUrl validation)."""
    socials_data["website"] = "//example.com/page"
    with pytest.raises(ValidationError) as exc:
        Socials(**socials_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("website",), "msg": "Input should be a valid URL, relative URL without a base"},
        ],
    )


def test_socials_website_invalid_url_missing_host(
    socials_data: Dict[str, Any],
) -> None:
    """Test Socials.website rejects URL with missing host (HttpUrl validation)."""
    socials_data["website"] = "https://"
    with pytest.raises(ValidationError) as exc:
        Socials(**socials_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("website",), "msg": "Input should be a valid URL, empty host"},
        ],
    )


# ----------------
# Negative tests for Socials.x field
# ----------------

def test_socials_x_empty_string(
    socials_data: Dict[str, Any],
) -> None:
    """Test Socials.x with empty string (fails min_length when provided)."""
    socials_data["x"] = ""
    with pytest.raises(ValidationError) as exc:
        Socials(**socials_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_too_short", "loc": ("x",), "msg": "String should have at least 1 character"},
        ],
    )


@pytest.mark.parametrize(
    "x_url",
    [
        "https://example.com/not-x",  # wrong domain
        "https://facebook.com/page",  # wrong domain
        "http://x.com/user",  # http not https
        "https://x.com/",  # missing path (pattern requires .+)
        "https://twitter.com/",  # missing path
        "https://instagram.com/user",  # wrong domain
        "https://linkedin.com/in/user",  # wrong domain
    ],
)
def test_socials_x_bad_pattern(
    socials_data: Dict[str, Any],
    x_url: str,
) -> None:
    """Test Socials.x rejects URLs that do not match x.com or twitter.com pattern."""
    socials_data["x"] = x_url
    with pytest.raises(ValidationError) as exc:
        Socials(**socials_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": ("x",), "msg": "Value error, socials.x must match ^https://(x\\.com|twitter\\.com)/.+$"},
        ],
    )


# ----------------
# Negative tests for Socials.telegram / discord / github / medium / reddit fields
# ----------------

@pytest.mark.parametrize(
    "field",
    ["telegram", "discord", "github", "medium", "reddit"],
)
@pytest.mark.parametrize(
    "invalid_value",
    [
        123,    # int
        True,   # bool
        [],     # list
        (),     # tuple
    ],
)
def test_socials_httpurl_fields_bad_type(
    socials_data: Dict[str, Any],
    field: str,
    invalid_value: Any,
) -> None:
    """Test Socials HttpUrl fields (telegram/discord/github/medium/reddit) reject non-string types."""
    socials_data[field] = invalid_value
    with pytest.raises(ValidationError) as exc:
        Socials(**socials_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "url_type",
                "loc": (field,),
                "msg": "URL input should be a string or URL",
            }
        ],
    )


@pytest.mark.parametrize(
    "field",
    ["telegram", "discord", "github", "medium", "reddit"],
)
def test_socials_httpurl_fields_invalid_url(
    socials_data: Dict[str, Any],
    field: str,
) -> None:
    """Test Socials HttpUrl fields (telegram/discord/github/medium/reddit) reject invalid URL strings."""
    socials_data[field] = "not-a-url"
    with pytest.raises(ValidationError) as exc:
        Socials(**socials_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "url_parsing",
                "loc": (field,),
                "msg": "Input should be a valid URL, relative URL without a base",
            }
        ],
    )


@pytest.mark.parametrize(
    "field",
    ["telegram", "discord", "github", "medium", "reddit"],
)
def test_socials_httpurl_fields_empty_string(
    socials_data: Dict[str, Any],
    field: str,
) -> None:
    """Test Socials HttpUrl fields (telegram/discord/github/medium/reddit) reject empty string."""
    socials_data[field] = ""
    with pytest.raises(ValidationError) as exc:
        Socials(**socials_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "url_parsing",
                "loc": (field,),
                "msg": "Input should be a valid URL, input is empty",
            }
        ],
    )


######################################################################
# Positive tests for TraceCounterparty models
######################################################################

# ----------------
# Positive tests for TraceCounterparty class
# ----------------

def test_trace_counterparty(
    trace_counterparty_data: Dict[str, Any],
) -> None:
    """Test TraceCounterparty class with all fields."""
    counterparty = TraceCounterparty(**trace_counterparty_data)
    assert len(TraceCounterparty.model_fields) == 2
    assert counterparty.chain_name == trace_counterparty_data["chain_name"]
    assert counterparty.base_denom == trace_counterparty_data["base_denom"]


# ----------------
# Positive tests for TraceCounterparty.chain_name field
# ----------------

@pytest.mark.parametrize(
    "chain_name",
    [
        "ethereum",
        "cosmoshub",
        "polygon",
        "noble",
        "a",  # min length
        "b" * 64,  # max length
        "123", # numbers only
        "@@@", # symbols only
        "chain-1", # hyphen
        "chain_2", # underscore
        "ChainName", # mixed case
        "asset", # single letter
        "asset123", # letters and numbers
        "asset_123.456.789", # letters, numbers and underscore and dot and hyphen
        " chain-name", # space
    ],
)
def test_trace_counterparty_chain_name_valid(
    trace_counterparty_data: Dict[str, Any],
    chain_name: str,
) -> None:
    """Test TraceCounterparty.chain_name field with valid values."""
    trace_counterparty_data["chain_name"] = chain_name
    counterparty = TraceCounterparty(**trace_counterparty_data)
    assert counterparty.chain_name == chain_name


# ----------------
# Positive tests for TraceCounterparty.base_denom field
# ----------------

@pytest.mark.parametrize(
    "base_denom",
    [
        "uatom",
        "uusdc",
        "uzig",
        "uosmo",
        "0xb2617246d0c6c0087f18703d576831899ca94f01",
        "0x2791bca1f2de4661ed88a30c99a7a9449aa84174",
        "a",  # min length
        "b" * 256,  # max length
        "factory/creator/subdenom",
        "ibc/ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789",
        "123", # numbers only
        "@@@", # symbols only
        "chain-1", # hyphen
        "chain_2", # underscore
        "ChainName", # mixed case
        "asset", # single letter
        "asset123", # letters and numbers
        "asset_123.456.789", # letters, numbers and underscore and dot and hyphen
    ],
)
def test_trace_counterparty_base_denom_valid(
    trace_counterparty_data: Dict[str, Any],
    base_denom: str,
) -> None:
    """Test TraceCounterparty.base_denom field with valid values."""
    trace_counterparty_data["base_denom"] = base_denom
    counterparty = TraceCounterparty(**trace_counterparty_data)
    assert counterparty.base_denom == base_denom


######################################################################
# Negative tests for TraceCounterparty models
######################################################################

# ----------------
# Negative tests for TraceCounterparty class
# ----------------

def test_trace_counterparty_extra_forbidden(
    trace_counterparty_data: Dict[str, Any],
) -> None:
    """Test TraceCounterparty rejects unknown fields (extra='forbid')."""
    trace_counterparty_data["unknown_key"] = "value"
    with pytest.raises(ValidationError) as exc:
        TraceCounterparty(**trace_counterparty_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "extra_forbidden", "loc": ("unknown_key",), "msg": "Extra inputs are not permitted"},
        ],
    )


# ----------------
# Negative tests for TraceCounterparty.chain_name field
# ----------------

def test_trace_counterparty_chain_name_missing(
    trace_counterparty_data: Dict[str, Any],
) -> None:
    """Test TraceCounterparty.chain_name field is missing."""
    del trace_counterparty_data["chain_name"]
    with pytest.raises(ValidationError) as exc:
        TraceCounterparty(**trace_counterparty_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "missing", "loc": ("chain_name",), "msg": "Field required"},
        ],
    )


def test_trace_counterparty_chain_name_too_short(
    trace_counterparty_data: Dict[str, Any],
) -> None:
    """Test TraceCounterparty.chain_name with empty string."""
    trace_counterparty_data["chain_name"] = ""
    with pytest.raises(ValidationError) as exc:
        TraceCounterparty(**trace_counterparty_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_too_short", "loc": ("chain_name",), "msg": "String should have at least 1 character"},
        ],
    )


def test_trace_counterparty_chain_name_too_long(
    trace_counterparty_data: Dict[str, Any],
) -> None:
    """Test TraceCounterparty.chain_name exceeds max length."""
    trace_counterparty_data["chain_name"] = "a" * 65
    with pytest.raises(ValidationError) as exc:
        TraceCounterparty(**trace_counterparty_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_too_long", "loc": ("chain_name",), "msg": "String should have at most 64 characters"},
        ],
    )


@pytest.mark.parametrize(
    "chain_name",
    [
        123,  # int
        3.14,  # float
        ["ethereum"],  # list
        {"chain_name": "ethereum"},  # dict
        True,  # bool
        (),  # tuple
        None,  # none
    ],
)
def test_trace_counterparty_chain_name_bad_type(
    trace_counterparty_data: Dict[str, Any],
    chain_name: Any,
) -> None:
    """Test TraceCounterparty.chain_name rejects non-string types."""
    trace_counterparty_data["chain_name"] = chain_name
    with pytest.raises(ValidationError) as exc:
        TraceCounterparty(**trace_counterparty_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_type", "loc": ("chain_name",), "msg": "Input should be a valid string"},
        ],
    )


@pytest.mark.parametrize(
    "chain_name",
    [
        "   ",  # spaces
        "\t",  # tab
        "\n",  # newline
        "  \t\n  ",  # mixed whitespace
    ],
)
def test_trace_counterparty_chain_name_bad_pattern(
    trace_counterparty_data: Dict[str, Any],
    chain_name: str,
) -> None:
    """Test TraceCounterparty.chain_name rejects whitespace-only (validator: non-empty after strip)."""
    trace_counterparty_data["chain_name"] = chain_name
    with pytest.raises(ValidationError) as exc:
        TraceCounterparty(**trace_counterparty_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": ("chain_name",), "msg": "Value error, value must be a non-empty string"},
        ],
    )


# ----------------
# Negative tests for TraceCounterparty.base_denom field
# ----------------

def test_trace_counterparty_base_denom_missing(
    trace_counterparty_data: Dict[str, Any],
) -> None:
    """Test TraceCounterparty.base_denom field is missing."""
    del trace_counterparty_data["base_denom"]
    with pytest.raises(ValidationError) as exc:
        TraceCounterparty(**trace_counterparty_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "missing", "loc": ("base_denom",), "msg": "Field required"},
        ],
    )


def test_trace_counterparty_base_denom_too_short(
    trace_counterparty_data: Dict[str, Any],
) -> None:
    """Test TraceCounterparty.base_denom with empty string."""
    trace_counterparty_data["base_denom"] = ""
    with pytest.raises(ValidationError) as exc:
        TraceCounterparty(**trace_counterparty_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_too_short", "loc": ("base_denom",), "msg": "String should have at least 1 character"},
        ],
    )


def test_trace_counterparty_base_denom_too_long(
    trace_counterparty_data: Dict[str, Any],
) -> None:
    """Test TraceCounterparty.base_denom exceeds max length."""
    trace_counterparty_data["base_denom"] = "a" * 257
    with pytest.raises(ValidationError) as exc:
        TraceCounterparty(**trace_counterparty_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_too_long", "loc": ("base_denom",), "msg": "String should have at most 256 characters"},
        ],
    )


@pytest.mark.parametrize(
    "base_denom",
    [
        123,  # int
        3.14,  # float
        ["uatom"],  # list
        {"base_denom": "uatom"},  # dict
        True,  # bool
        (),  # tuple
        None,  # none
    ],
)
def test_trace_counterparty_base_denom_bad_type(
    trace_counterparty_data: Dict[str, Any],
    base_denom: Any,
) -> None:
    """Test TraceCounterparty.base_denom rejects non-string types."""
    trace_counterparty_data["base_denom"] = base_denom
    with pytest.raises(ValidationError) as exc:
        TraceCounterparty(**trace_counterparty_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_type", "loc": ("base_denom",), "msg": "Input should be a valid string"},
        ],
    )


@pytest.mark.parametrize(
    "base_denom",
    [
        "   ",  # spaces
        "\t",  # tab
        "\n",  # newline
        "  \t\n  ",  # mixed whitespace
    ],
)
def test_trace_counterparty_base_denom_bad_pattern(
    trace_counterparty_data: Dict[str, Any],
    base_denom: str,
) -> None:
    """Test TraceCounterparty.base_denom rejects whitespace-only (validator: non-empty after strip)."""
    trace_counterparty_data["base_denom"] = base_denom
    with pytest.raises(ValidationError) as exc:
        TraceCounterparty(**trace_counterparty_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": ("base_denom",), "msg": "Value error, value must be a non-empty string"},
        ],
    )


######################################################################
# Positive tests for NativeTrace models
######################################################################

# ----------------
# Positive tests for NativeTrace class
# ----------------

def test_native_trace(
    native_trace_data: Dict[str, Any],
) -> None:
    """Test NativeTrace class with all fields."""
    trace = NativeTrace(**native_trace_data)
    assert len(NativeTrace.model_fields) == 3
    assert trace.type == native_trace_data["type"]
    assert trace.counterparty.chain_name == native_trace_data["counterparty"]["chain_name"]
    assert trace.counterparty.base_denom == native_trace_data["counterparty"]["base_denom"]
    assert trace.provider == native_trace_data["provider"]


# ----------------
# Positive tests for NativeTrace.type field
# ----------------

@pytest.mark.parametrize(
    "trace_type",
    [
        "additional-mintage",
        "synthetic",
        "bridged",
        "ibc",
        "a",  # min length
        "custom-type-123",
        "type_with_underscore",
        "123",  # numbers only
        "@@@",  # symbols
        " abc",  # space
        "UPPERCASE",
        "a" * 64,  # max length (max_length=64)
    ],
)
def test_native_trace_type_valid(
    native_trace_data: Dict[str, Any],
    trace_type: str,
) -> None:
    """Test NativeTrace.type field with valid values."""
    native_trace_data["type"] = trace_type
    trace = NativeTrace(**native_trace_data)
    assert trace.type == trace_type


# ----------------
# Positive tests for NativeTrace.counterparty field
# ----------------

@pytest.mark.parametrize(
    "chain_name,base_denom",
    [
        ("ethereum", "0xb2617246d0c6c0087f18703d576831899ca94f01"),  # EVM address
        ("cosmoshub", "uatom"),
        ("polygon", "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"),  # EVM address
        ("noble", "uusdc"),
        ("osmosis", "uosmo"),
        ("stride", "ustrd"),
        ("arbitrum", "0x912ce59144191c1204e64559fe8253a0e49e6548"),  # EVM
        ("a", "b"),  # min length
    ],
)
def test_native_trace_counterparty_valid(
    native_trace_data: Dict[str, Any],
    chain_name: str,
    base_denom: str,
) -> None:
    """Test NativeTrace.counterparty field with valid TraceCounterparty data (various chain_name and base_denom)."""
    native_trace_data["counterparty"] = {"chain_name": chain_name, "base_denom": base_denom}
    trace = NativeTrace(**native_trace_data)
    assert trace.counterparty.chain_name == chain_name
    assert trace.counterparty.base_denom == base_denom



# ----------------
# Positive tests for NativeTrace.provider field
# ----------------

@pytest.mark.parametrize(
    "provider",
    [
        None,
        "ZIGChain",
        "IBC Bridge",
        "Circle",
        "a",  # min length
        "1",  # numbers
        "@@@",  # symbols
        " abc",  # space
        "UPPERCASE",
        "a" * 64,  # max length (max_length=64)
    ],
)
def test_native_trace_provider_valid(
    native_trace_data: Dict[str, Any],
    provider: Any,
) -> None:
    """Test NativeTrace.provider field with valid values (None or non-empty string)."""
    native_trace_data["provider"] = provider
    trace = NativeTrace(**native_trace_data)
    # Model strips string provider values
    expected = provider.strip() if isinstance(provider, str) else provider
    assert trace.provider == expected


def test_native_trace_provider_missing(
    native_trace_data: Dict[str, Any],
) -> None:
    """Test NativeTrace.provider when key is omitted (defaults to None)."""
    del native_trace_data["provider"]
    trace = NativeTrace(**native_trace_data)
    assert trace.provider is None


######################################################################
# Negative tests for NativeTrace models
######################################################################

# ----------------
# Negative tests for NativeTrace class
# ----------------

def test_native_trace_extra_forbidden(
    native_trace_data: Dict[str, Any],
) -> None:
    """Test NativeTrace rejects unknown fields (extra='forbid')."""
    native_trace_data["unknown_key"] = "value"
    with pytest.raises(ValidationError) as exc:
        NativeTrace(**native_trace_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "extra_forbidden", "loc": ("unknown_key",), "msg": "Extra inputs are not permitted"},
        ],
    )


def test_native_trace_type_too_long(
    native_trace_data: Dict[str, Any],
) -> None:
    """Test NativeTrace.type rejects strings longer than 64 characters (max_length=64)."""
    native_trace_data["type"] = "a" * 65
    with pytest.raises(ValidationError) as exc:
        NativeTrace(**native_trace_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "loc": ("type",),
                "type": "string_too_long",
                "msg": "String should have at most 64 characters",
            }
        ],
    )


def test_native_trace_provider_too_long(
    native_trace_data: Dict[str, Any],
) -> None:
    """Test NativeTrace.provider rejects strings longer than 64 characters (max_length=64)."""
    native_trace_data["provider"] = "a" * 65
    with pytest.raises(ValidationError) as exc:
        NativeTrace(**native_trace_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "loc": ("provider",),
                "type": "string_too_long",
                "msg": "String should have at most 64 characters",
            }
        ],
    )


# ----------------
# Negative tests for NativeTrace.type field
# ----------------

def test_native_trace_type_missing(
    native_trace_data: Dict[str, Any],
) -> None:
    """Test NativeTrace.type field is missing."""
    del native_trace_data["type"]
    with pytest.raises(ValidationError) as exc:
        NativeTrace(**native_trace_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "missing", "loc": ("type",), "msg": "Field required"},
        ],
    )


@pytest.mark.parametrize(
    "trace_type",
    [
        123,  # int
        3.14,  # float
        ["additional-mintage"],  # list
        {"type": "additional-mintage"},  # dict
        True,  # bool
        (),
        None,
    ],
)
def test_native_trace_type_bad_type(
    native_trace_data: Dict[str, Any],
    trace_type: Any,
) -> None:
    """Test NativeTrace.type rejects non-string types."""
    native_trace_data["type"] = trace_type
    with pytest.raises(ValidationError) as exc:
        NativeTrace(**native_trace_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_type", "loc": ("type",), "msg": "Input should be a valid string"},
        ],
    )


def test_native_trace_type_too_short(
    native_trace_data: Dict[str, Any],
) -> None:
    """Test NativeTrace.type with empty string."""
    native_trace_data["type"] = ""
    with pytest.raises(ValidationError) as exc:
        NativeTrace(**native_trace_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_too_short", "loc": ("type",), "msg": "String should have at least 1 character"},
        ],
    )


@pytest.mark.parametrize(
    "trace_type",
    [
         "   ",  # spaces only
        "\t",  # tab only
        "\n",  # newline only
        "  \t\n  ",  # mixed whitespace
    ],
)
def test_native_trace_type_bad_pattern(
    native_trace_data: Dict[str, Any],
    trace_type: str,
) -> None:
    """Test NativeTrace.type rejects whitespace-only (validator: non-empty after strip)."""
    native_trace_data["type"] = trace_type
    with pytest.raises(ValidationError) as exc:
        NativeTrace(**native_trace_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": ("type",), "msg": "Value error, type must be a non-empty string"},
        ],
    )


# ----------------
# Negative tests for NativeTrace.counterparty field
# ----------------

def test_native_trace_counterparty_missing(
    native_trace_data: Dict[str, Any],
) -> None:
    """Test NativeTrace.counterparty field is missing."""
    del native_trace_data["counterparty"]
    with pytest.raises(ValidationError) as exc:
        NativeTrace(**native_trace_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "missing", "loc": ("counterparty",), "msg": "Field required"},
        ],
    )


@pytest.mark.parametrize(
    "counterparty",
    [
        None,
        123,  # int
        12.3,  # float
        "ethereum",  # string
        ["ethereum", "0xb26..."],  # list
        True,  # bool
    ],
)
def test_native_trace_counterparty_bad_type(
    native_trace_data: Dict[str, Any],
    counterparty: Any,
) -> None:
    """Test NativeTrace.counterparty rejects non-dict types."""
    native_trace_data["counterparty"] = counterparty
    with pytest.raises(ValidationError) as exc:
        NativeTrace(**native_trace_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "model_type", "loc": ("counterparty",), "msg": "Input should be a valid dictionary or instance of TraceCounterparty"},
        ],
    )


# ----------------
# Negative tests for NativeTrace.provider field
# ----------------

@pytest.mark.parametrize(
    "provider",
    [
        123,  # int
        3.14,  # float
        ["ZIGChain"],  # list
        {"provider": "ZIGChain"},  # dict
        True,  # bool
        (),
    ],
)
def test_native_trace_provider_bad_type(
    native_trace_data: Dict[str, Any],
    provider: Any,
) -> None:
    """Test NativeTrace.provider rejects non-string types when provided."""
    native_trace_data["provider"] = provider
    with pytest.raises(ValidationError) as exc:
        NativeTrace(**native_trace_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_type", "loc": ("provider",), "msg": "Input should be a valid string"},
        ],
    )


@pytest.mark.parametrize(
    "provider",
    [
        "   ",  # spaces only
        "\t",  # tab only
        "\n",  # newline only
        "  \t\n  ",  # mixed whitespace
    ],
)
def test_native_trace_provider_bad_pattern(
    native_trace_data: Dict[str, Any],
    provider: str,
) -> None:
    """Test NativeTrace.provider rejects whitespace-only when provided (validator)."""
    native_trace_data["provider"] = provider
    with pytest.raises(ValidationError) as exc:
        NativeTrace(**native_trace_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": ("provider",), "msg": "Value error, provider must be a non-empty string when provided"},
        ],
    )


######################################################################
# Positive tests for ImageSyncPointer
######################################################################

# ----------------
# Positive tests for ImageSyncPointer class
# ----------------

def test_image_sync_pointer(
    image_sync_pointer_data: Dict[str, Any],
) -> None:
    """Test ImageSyncPointer class with all fields."""
    ptr = ImageSyncPointer(**image_sync_pointer_data)
    assert len(ImageSyncPointer.model_fields) == 2
    assert ptr.chain_name == image_sync_pointer_data["chain_name"]
    assert ptr.base_denom == image_sync_pointer_data["base_denom"]


# ----------------
# Positive tests for ImageSyncPointer.chain_name field
# ----------------

@pytest.mark.parametrize(
    "chain_name",
    [
        "zigchain",
        "cosmoshub",
        "ethereum",
        "polygon",
        "a",  # min length
        "a" * 64,  # max length (max_length=64)
        "123",  # numbers only
        "@@@",  # symbols only
        "chain-1",  # hyphen
        "chain_2",  # underscore
        "ChainName",  # mixed case
        "asset123",
        "资产",  # unicode
    ],
)
def test_image_sync_pointer_chain_name_valid(
    image_sync_pointer_data: Dict[str, Any],
    chain_name: str,
) -> None:
    """Test ImageSyncPointer.chain_name field with valid values."""
    image_sync_pointer_data["chain_name"] = chain_name
    ptr = ImageSyncPointer(**image_sync_pointer_data)
    assert ptr.chain_name == chain_name


# ----------------
# Positive tests for ImageSyncPointer.base_denom field
# ----------------

@pytest.mark.parametrize(
    "base_denom",
    [
        "uzig",
        "uatom",
        "uusdc",
        "0xb2617246d0c6c0087f18703d576831899ca94f01",
        "a",  # min length
        "factory/creator/subdenom",
        "ibc/ABCDEF0123456789",
        "token:sub",  # colon
        "token.token",  # dot
        "token-token",  # hyphen
        "a" * 256,  # max length (max_length=256)
        "123",  # numbers only
        "@@@",  # symbols only
        "base-1",  # hyphen
        "base_2",  # underscore
        "BaseDenomName",  # mixed case
        "asset123",
        "资产",  # unicode
    ],
)
def test_image_sync_pointer_base_denom_valid(
    image_sync_pointer_data: Dict[str, Any],
    base_denom: str,
) -> None:
    """Test ImageSyncPointer.base_denom field with valid values."""
    image_sync_pointer_data["base_denom"] = base_denom
    ptr = ImageSyncPointer(**image_sync_pointer_data)
    assert ptr.base_denom == base_denom


######################################################################
# Negative tests for ImageSyncPointer
######################################################################

# ----------------
# Negative tests for ImageSyncPointer class
# ----------------

def test_image_sync_pointer_extra_forbidden(
    image_sync_pointer_data: Dict[str, Any],
) -> None:
    """Test ImageSyncPointer rejects unknown fields (extra='forbid')."""
    image_sync_pointer_data["unknown_key"] = "value"
    with pytest.raises(ValidationError) as exc:
        ImageSyncPointer(**image_sync_pointer_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "extra_forbidden", "loc": ("unknown_key",), "msg": "Extra inputs are not permitted"},
        ],
    )


def test_image_sync_pointer_chain_name_too_long(
    image_sync_pointer_data: Dict[str, Any],
) -> None:
    """Test ImageSyncPointer.chain_name rejects strings longer than 64 characters (max_length=64)."""
    image_sync_pointer_data["chain_name"] = "a" * 65
    with pytest.raises(ValidationError) as exc:
        ImageSyncPointer(**image_sync_pointer_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "loc": ("chain_name",),
                "type": "string_too_long",
                "msg": "String should have at most 64 characters",
            }
        ],
    )


def test_image_sync_pointer_base_denom_too_long(
    image_sync_pointer_data: Dict[str, Any],
) -> None:
    """Test ImageSyncPointer.base_denom rejects strings longer than 256 characters (max_length=256)."""
    image_sync_pointer_data["base_denom"] = "a" * 257
    with pytest.raises(ValidationError) as exc:
        ImageSyncPointer(**image_sync_pointer_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "loc": ("base_denom",),
                "type": "string_too_long",
                "msg": "String should have at most 256 characters",
            }
        ],
    )


# ----------------
# Negative tests for ImageSyncPointer.chain_name field
# ----------------

def test_image_sync_pointer_chain_name_missing(
    image_sync_pointer_data: Dict[str, Any],
) -> None:
    """Test ImageSyncPointer.chain_name field is missing."""
    del image_sync_pointer_data["chain_name"]
    with pytest.raises(ValidationError) as exc:
        ImageSyncPointer(**image_sync_pointer_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "missing", "loc": ("chain_name",), "msg": "Field required"},
        ],
    )


@pytest.mark.parametrize(
    "chain_name",
    [
        123,  # int
        3.14,  # float
        True,  # bool
        ["zigchain"],  # list
        {"chain_name": "zigchain"},  # dict
        (),  # tuple
        None,
    ],
)
def test_image_sync_pointer_chain_name_bad_type(
    image_sync_pointer_data: Dict[str, Any],
    chain_name: Any,
) -> None:
    """Test ImageSyncPointer.chain_name rejects non-string types."""
    image_sync_pointer_data["chain_name"] = chain_name
    with pytest.raises(ValidationError) as exc:
        ImageSyncPointer(**image_sync_pointer_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_type", "loc": ("chain_name",), "msg": "Input should be a valid string"},
        ],
    )


def test_image_sync_pointer_chain_name_too_short(
    image_sync_pointer_data: Dict[str, Any],
) -> None:
    """Test ImageSyncPointer.chain_name with empty string."""
    image_sync_pointer_data["chain_name"] = ""
    with pytest.raises(ValidationError) as exc:
        ImageSyncPointer(**image_sync_pointer_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_too_short", "loc": ("chain_name",), "msg": "String should have at least 1 character"},
        ],
    )


# ----------------
# Negative tests for ImageSyncPointer.base_denom field
# ----------------

def test_image_sync_pointer_base_denom_missing(
    image_sync_pointer_data: Dict[str, Any],
) -> None:
    """Test ImageSyncPointer.base_denom field is missing."""
    del image_sync_pointer_data["base_denom"]
    with pytest.raises(ValidationError) as exc:
        ImageSyncPointer(**image_sync_pointer_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "missing", "loc": ("base_denom",), "msg": "Field required"},
        ],
    )


@pytest.mark.parametrize(
    "base_denom",
    [
        123,  # int
        3.14,  # float
        True,  # bool
        ["uzig"],  # list
        {"base_denom": "uzig"},  # dict
        (),  # tuple
        None,
    ],
)
def test_image_sync_pointer_base_denom_bad_type(
    image_sync_pointer_data: Dict[str, Any],
    base_denom: Any,
) -> None:
    """Test ImageSyncPointer.base_denom rejects non-string types."""
    image_sync_pointer_data["base_denom"] = base_denom
    with pytest.raises(ValidationError) as exc:
        ImageSyncPointer(**image_sync_pointer_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_type", "loc": ("base_denom",), "msg": "Input should be a valid string"},
        ],
    )


def test_image_sync_pointer_base_denom_too_short(
    image_sync_pointer_data: Dict[str, Any],
) -> None:
    """Test ImageSyncPointer.base_denom with empty string."""
    image_sync_pointer_data["base_denom"] = ""
    with pytest.raises(ValidationError) as exc:
        ImageSyncPointer(**image_sync_pointer_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_too_short", "loc": ("base_denom",), "msg": "String should have at least 1 character"},
        ],
    )


######################################################################
# Positive tests for ImageTheme
######################################################################

# ----------------
# Positive tests for ImageTheme class
# ----------------

@pytest.mark.parametrize(
    "circle,dark_mode",
    [
        (True, True),   # both True
        (True, False),  # circle True, dark_mode False
        (False, True),  # circle False, dark_mode True
        (False, False), # both False
    ],
)
def test_image_theme(
    circle: bool,
    dark_mode: bool,
) -> None:
    """Test ImageTheme class with both fields (all circle/dark_mode combinations)."""
    theme = ImageTheme(circle=circle, dark_mode=dark_mode)
    assert theme.circle is circle
    assert theme.dark_mode is dark_mode


@pytest.mark.parametrize(
    "circle",
    [True, False],
)
def test_image_theme_circle_only(
    circle: bool,
) -> None:
    """Test ImageTheme with circle only (dark_mode omitted)."""
    theme = ImageTheme(circle=circle)
    assert theme.circle is circle
    assert theme.dark_mode is None


@pytest.mark.parametrize(
    "dark_mode",
    [True, False],
)
def test_image_theme_dark_mode_only(
    dark_mode: bool,
) -> None:
    """Test ImageTheme with dark_mode only (circle omitted)."""
    theme = ImageTheme(dark_mode=dark_mode)
    assert theme.circle is None
    assert theme.dark_mode is dark_mode


######################################################################
# Negative tests for ImageTheme
######################################################################

# ----------------
# Negative tests for ImageTheme class
# ----------------

def test_image_theme_extra_forbidden(
    image_theme_data: Dict[str, Any],
) -> None:
    """Test ImageTheme rejects unknown fields (extra='forbid')."""
    image_theme_data["unknown_key"] = "value"
    with pytest.raises(ValidationError) as exc:
        ImageTheme(**image_theme_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "extra_forbidden", "loc": ("unknown_key",), "msg": "Extra inputs are not permitted"},
        ],
    )


def test_image_theme_all_properties_none_fails() -> None:
    """Test ImageTheme model validator: at least one property required."""
    with pytest.raises(ValidationError) as exc:
        ImageTheme(circle=None, dark_mode=None)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": (), "msg": "Value error, images[].theme must contain at least one property"},
        ],
    )

# ----------------
# Negative tests for ImageTheme.circle field
# ----------------

@pytest.mark.parametrize(
    "circle",
    [
        "not_a_bool",  # string (unable to interpret)
        123,  # int (unable to interpret)
    ],
)
def test_image_theme_circle_bad_type_parsing(
    image_theme_data: Dict[str, Any],
    circle: Any,
) -> None:
    """Test ImageTheme.circle rejects non-bool values (reject_non_bool_theme validator fires before bool parsing)."""
    image_theme_data["circle"] = circle
    with pytest.raises(ValidationError) as exc:
        ImageTheme(**image_theme_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": ("circle",), "msg": "Value error, must be a boolean, not a bool-like value"},
        ],
    )


@pytest.mark.parametrize(
    "circle",
    [
        12.3,  # float
        ["True"],  # list
        {"circle": "True"},  # dict
        (),  # tuple
    ],
)
def test_image_theme_circle_bad_type(
    image_theme_data: Dict[str, Any],
    circle: Any,
) -> None:
    """Test ImageTheme.circle rejects non-boolean types (reject_non_bool_theme validator)."""
    image_theme_data["circle"] = circle
    with pytest.raises(ValidationError) as exc:
        ImageTheme(**image_theme_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": ("circle",), "msg": "Value error, must be a boolean, not a bool-like value"},
        ],
    )


# ----------------
# Negative tests for ImageTheme.dark_mode field
# ----------------

@pytest.mark.parametrize(
    "dark_mode",
    [
        "not_a_bool",  # string
        123,           # int
    ],
)
def test_image_theme_dark_mode_bad_type_parsing(
    image_theme_data: Dict[str, Any],
    dark_mode: Any,
) -> None:
    """Test ImageTheme.dark_mode rejects non-bool values (reject_non_bool_theme validator fires before bool parsing)."""
    image_theme_data["dark_mode"] = dark_mode
    with pytest.raises(ValidationError) as exc:
        ImageTheme(**image_theme_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("dark_mode",),
                "msg": "Value error, must be a boolean, not a bool-like value",
            }
        ],
    )


@pytest.mark.parametrize(
    "dark_mode",
    [
        12.3,          # float
        ["True"],      # list
        {"dark_mode": "True"},  # dict
        (),            # tuple
    ],
)
def test_image_theme_dark_mode_bad_type(
    image_theme_data: Dict[str, Any],
    dark_mode: Any,
) -> None:
    """Test ImageTheme.dark_mode rejects non-boolean types (reject_non_bool_theme validator)."""
    image_theme_data["dark_mode"] = dark_mode
    with pytest.raises(ValidationError) as exc:
        ImageTheme(**image_theme_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("dark_mode",),
                "msg": "Value error, must be a boolean, not a bool-like value",
            }
        ],
    )


######################################################################
# Positive tests for ImageEntry
######################################################################

# ----------------
# Positive tests for ImageEntry class
# ----------------

def test_image_entry(
    image_entry_data: Dict[str, Any],
) -> None:
    """Test ImageEntry class with all fields (image_sync, png, svg, theme)."""
    entry = ImageEntry(**image_entry_data)
    assert entry.image_sync is not None
    assert entry.image_sync.chain_name == image_entry_data["image_sync"]["chain_name"]
    assert entry.image_sync.base_denom == image_entry_data["image_sync"]["base_denom"]
    assert entry.png is not None
    assert str(entry.png) == image_entry_data["png"]
    assert entry.svg is not None
    assert str(entry.svg) == image_entry_data["svg"]
    assert entry.theme is not None
    assert entry.theme.circle is True
    assert entry.theme.dark_mode is False


def test_image_entry_image_sync_only(
    image_sync_pointer_data: Dict[str, Any],
) -> None:
    """Test ImageEntry with image_sync only (shortcut form)."""
    entry = ImageEntry(image_sync=image_sync_pointer_data)
    assert entry.image_sync is not None
    assert entry.image_sync.chain_name == image_sync_pointer_data["chain_name"]
    assert entry.image_sync.base_denom == image_sync_pointer_data["base_denom"]
    assert entry.png is None
    assert entry.svg is None


def test_image_entry_png_only() -> None:
    """Test ImageEntry with png only."""
    png_url = "https://raw.githubusercontent.com/test/logo.png"
    entry = ImageEntry(png=png_url)
    assert entry.png is not None
    assert str(entry.png) == png_url
    assert entry.svg is None
    assert entry.image_sync is None
    assert entry.theme is None


def test_image_entry_svg_only() -> None:
    """Test ImageEntry with svg only."""
    svg_url = "https://raw.githubusercontent.com/test/logo.svg"
    entry = ImageEntry(svg=svg_url)
    assert entry.svg is not None
    assert str(entry.svg) == svg_url
    assert entry.png is None
    assert entry.image_sync is None
    assert entry.theme is None


@pytest.mark.parametrize(
    "png",
    [
        "https://raw.githubusercontent.com/test/logo.png",
        "https://raw.githubusercontent.com/test/nested/dir/a.png",
        "https://raw.githubusercontent.com/ZIGChain/assets/main/logos/zig.png",
    ],
)
def test_image_entry_png_valid(
    png: str,
) -> None:
    """Test ImageEntry.png field with valid URLs on the allowlisted host."""
    entry = ImageEntry(png=png)
    assert str(entry.png) == png


@pytest.mark.parametrize(
    "svg",
    [
        "https://raw.githubusercontent.com/test/logo.svg",
        "https://raw.githubusercontent.com/test/a.svg",
        "https://raw.githubusercontent.com/ZIGChain/assets/main/logos/zig.svg",
    ],
)
def test_image_entry_svg_valid(
    svg: str,
) -> None:
    """Test ImageEntry.svg field with valid URLs on the allowlisted host."""
    entry = ImageEntry(svg=svg)
    assert str(entry.svg) == svg


def test_image_entry_with_theme(
    image_entry_data: Dict[str, Any],
) -> None:
    """Test ImageEntry with theme (fixture includes theme)."""
    entry = ImageEntry(**image_entry_data)
    assert entry.theme is not None
    assert entry.theme.circle == image_entry_data["theme"]["circle"]
    assert entry.theme.dark_mode == image_entry_data["theme"]["dark_mode"]


def test_image_entry_all_none_accepted() -> None:
    """ImageEntry with all fields None is accepted (no minProperties constraint)."""
    entry = ImageEntry()
    assert entry.image_sync is None
    assert entry.png is None
    assert entry.svg is None
    assert entry.theme is None


######################################################################
# Negative tests for ImageEntry
######################################################################

# ----------------
# Negative tests for ImageEntry class
# ----------------

def test_image_entry_extra_forbidden(
    image_entry_data: Dict[str, Any],
) -> None:
    """Test ImageEntry rejects unknown fields (extra='forbid')."""
    data = {**image_entry_data, "unknown_key": "value"}
    with pytest.raises(ValidationError) as exc:
        ImageEntry(**data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "extra_forbidden", "loc": ("unknown_key",), "msg": "Extra inputs are not permitted"},
        ],
    )


# ----------------
# Negative tests for ImageEntry.png field
# ----------------

@pytest.mark.parametrize(
    "png",
    [
        "ftp://example.com/logo.png",
        "file:///tmp/logo.png",
        "javascript:alert(1)",
    ],
)
def test_image_entry_png_invalid_url_scheme(
    image_entry_data: Dict[str, Any],
    png: str,
) -> None:
    """Test ImageEntry.png rejects non-http(s) scheme (url_scheme)."""
    data = {**image_entry_data, "png": png}
    with pytest.raises(ValidationError) as exc:
        ImageEntry(**data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_scheme", "loc": ("png",), "msg": "URL scheme should be 'http' or 'https'"},
        ],
    )


def test_image_entry_png_invalid_url_parsing(
    image_entry_data: Dict[str, Any],
) -> None:
    """Test ImageEntry.png rejects invalid URL (url_parsing)."""
    data = {**image_entry_data, "png": "not-a-url"}
    with pytest.raises(ValidationError) as exc:
        ImageEntry(**data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("png",), "msg": "Input should be a valid URL, relative URL without a base"},
        ],
    )


@pytest.mark.parametrize(
    "png",
    [
        123,  # int
        3.14,  # float
        True,  # bool
        ["https://raw.githubusercontent.com/test/logo.png"],  # list
        (),  # tuple
    ],
)
def test_image_entry_png_bad_type(
    image_entry_data: Dict[str, Any],
    png: Any,
) -> None:
    """Test ImageEntry.png rejects non-string types."""
    data = {**image_entry_data, "png": png}
    with pytest.raises(ValidationError) as exc:
        ImageEntry(**data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_type", "loc": ("png",), "msg": "URL input should be a string or URL"},
        ],
    )


# ----------------
# Negative tests for ImageEntry.svg field
# ----------------

@pytest.mark.parametrize(
    "svg",
    [
        "ftp://example.com/logo.svg",
        "file:///tmp/logo.svg",
        "javascript:alert(1)",
    ],
)
def test_image_entry_svg_invalid_url_scheme(
    image_entry_data: Dict[str, Any],
    svg: str,
) -> None:
    """Test ImageEntry.svg rejects non-http(s) scheme (url_scheme)."""
    data = {**image_entry_data, "svg": svg}
    with pytest.raises(ValidationError) as exc:
        ImageEntry(**data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_scheme", "loc": ("svg",), "msg": "URL scheme should be 'http' or 'https'"},
        ],
    )


def test_image_entry_svg_invalid_url_parsing(
    image_entry_data: Dict[str, Any],
) -> None:
    """Test ImageEntry.svg rejects invalid URL (url_parsing)."""
    data = {**image_entry_data, "svg": "not-a-url"}
    with pytest.raises(ValidationError) as exc:
        ImageEntry(**data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_parsing", "loc": ("svg",), "msg": "Input should be a valid URL, relative URL without a base"},
        ],
    )


@pytest.mark.parametrize(
    "svg",
    [
        123,  # int
        3.14,  # float
        True,  # bool
        ["https://raw.githubusercontent.com/test/logo.svg"],  # list
        (),  # tuple
    ],
)
def test_image_entry_svg_bad_type(
    image_entry_data: Dict[str, Any],
    svg: Any,
) -> None:
    """Test ImageEntry.svg rejects non-string types."""
    data = {**image_entry_data, "svg": svg}
    with pytest.raises(ValidationError) as exc:
        ImageEntry(**data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "url_type", "loc": ("svg",), "msg": "URL input should be a string or URL"},
        ],
    )


# ----------------
# Negative tests for ImageEntry host allowlist
# ----------------


@pytest.mark.parametrize(
    "field,url",
    [
        ("png", "https://evil.com/logo.png"),
        ("png", "https://cdn.example.net/a.png"),
        ("svg", "https://evil.com/logo.svg"),
        ("svg", "https://raw.githubusercontent.io/test/logo.svg"),  # .io vs .com
    ],
)
def test_image_entry_host_not_in_allowlist_rejected(
    field: str,
    url: str,
) -> None:
    """ImageEntry rejects png/svg whose host is not exactly `raw.githubusercontent.com`."""
    with pytest.raises(ValidationError) as exc:
        ImageEntry(**{field: url})
    check_model_error(
        errors=exc,
        expected_errors=[{"type": "value_error", "loc": (field,)}],
    )
    assert any("allowlist" in e["msg"].lower() for e in exc.value.errors())


# ----------------
# Negative tests for ImageEntry.theme field
# ----------------

@pytest.mark.parametrize(
    "theme",
    [
        123,  # int
        "circle",  # string
        ["circle"],  # list
    ],
)
def test_image_entry_theme_bad_type(
    image_entry_data: Dict[str, Any],
    theme: Any,
) -> None:
    """Test ImageEntry.theme rejects non-ImageTheme types (model_type)."""
    data = {**image_entry_data, "theme": theme}
    with pytest.raises(ValidationError) as exc:
        ImageEntry(**data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "model_type", "loc": ("theme",), "msg": "Input should be a valid dictionary or instance of ImageTheme"},
        ],
    )


def test_image_entry_theme_extra_forbidden(
    image_entry_data: Dict[str, Any],
) -> None:
    """Test ImageEntry.theme rejects dict with invalid key (ImageTheme extra='forbid' -> extra_forbidden)."""
    data = {**image_entry_data, "theme": {"invalid_key": True}}
    with pytest.raises(ValidationError) as exc:
        ImageEntry(**data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "extra_forbidden", "loc": ("theme", "invalid_key"), "msg": "Extra inputs are not permitted"},
        ],
    )


######################################################################
# Positive tests for DenomUnit
######################################################################

# ----------------
# Positive tests for DenomUnit class
# ----------------

def test_denom_unit(
    denom_unit_data: Dict[str, Any],
) -> None:
    """Test DenomUnit class with all fields."""
    unit = DenomUnit(**denom_unit_data)
    assert unit.denom == denom_unit_data["denom"]
    assert unit.exponent == denom_unit_data["exponent"]
    assert unit.aliases == denom_unit_data["aliases"]


def test_denom_unit_minimal() -> None:
    """Test DenomUnit with required fields only."""
    unit = DenomUnit(denom="uzig", exponent=0)
    assert unit.denom == "uzig"
    assert unit.exponent == 0
    assert unit.aliases is None


# ----------------
# Positive tests for DenomUnit.denom field
# ----------------

@pytest.mark.parametrize(
    "denom",
    [
        "uzig",
        "uatom",
        "a", # min length
        "token",
        "token:sub",  # valid symbol
        "token/token", # valid symbol
        "token.token", # valid symbol
        "token-token", # valid symbol
        "token_token", # valid symbol
        "a" * 128,  # max length
        "factory/creator/subdenom",
        "ibc/ABCDEF0123456789",
        "TOKEN", # Capitalized
        "AbcdA", # Mixed case
        "T123.a_",  # letters, symbols, numbers
    ],
)
def test_denom_unit_denom_valid(
    denom_unit_data: Dict[str, Any],
    denom: str,
) -> None:
    """Test DenomUnit.denom field with valid values."""
    denom_unit_data["denom"] = denom
    unit = DenomUnit(**denom_unit_data)
    assert unit.denom == denom


# ----------------
# Positive tests for DenomUnit.exponent field
# ----------------

@pytest.mark.parametrize(
    "exponent",
    [0, 1, 6, 8, 18],  # valid range: ge=0, le=18
)
def test_denom_unit_exponent_valid(
    denom_unit_data: Dict[str, Any],
    exponent: int,
) -> None:
    """Test DenomUnit.exponent field with valid values."""
    denom_unit_data["exponent"] = exponent
    unit = DenomUnit(**denom_unit_data)
    assert unit.exponent == exponent


def test_denom_unit_exponent_too_large(
    denom_unit_data: Dict[str, Any],
) -> None:
    """Test DenomUnit.exponent rejects values above 18 (le=18)."""
    denom_unit_data["exponent"] = 19
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "loc": ("exponent",),
                "type": "less_than_equal",
                "msg": "Input should be less than or equal to 18",
            }
        ],
    )


# ----------------
# Positive tests for DenomUnit.aliases field
# ----------------

@pytest.mark.parametrize(
    "aliases",
    [
        None,
        ["ZIG"],
        ["ZIG", "zigchain"],
        ["a", "b", "c"],
        ["single"],
        ["123", "321"],  # numbers
        ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],  # max length (max_length=10)
        [],  # empty list
    ],
)
def test_denom_unit_aliases_valid(
    denom_unit_data: Dict[str, Any],
    aliases: Any,
) -> None:
    """Test DenomUnit.aliases field with valid values."""
    denom_unit_data["aliases"] = aliases
    unit = DenomUnit(**denom_unit_data)
    assert unit.aliases == aliases


######################################################################
# Negative tests for DenomUnit
######################################################################

# ----------------
# Negative tests for DenomUnit.aliases max_length
# ----------------

def test_denom_unit_aliases_too_many(
    denom_unit_data: Dict[str, Any],
) -> None:
    """Test DenomUnit.aliases rejects list longer than 10 items (max_length=10)."""
    denom_unit_data["aliases"] = [f"alias{i}" for i in range(11)]
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "loc": ("aliases",),
                "type": "too_long",
                "msg": "List should have at most 10 items after validation, not 11",
            }
        ],
    )


# ----------------
# Negative tests for DenomUnit class
# ----------------

def test_denom_unit_extra_forbidden(
    denom_unit_data: Dict[str, Any],
) -> None:
    """Test DenomUnit rejects unknown fields (extra='forbid')."""
    denom_unit_data["unknown_key"] = "value"
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "extra_forbidden", "loc": ("unknown_key",), "msg": "Extra inputs are not permitted"},
        ],
    )


# ----------------
# Negative tests for DenomUnit.denom field
# ----------------

def test_denom_unit_denom_missing(
    denom_unit_data: Dict[str, Any],
) -> None:
    """Test DenomUnit.denom field is missing."""
    del denom_unit_data["denom"]
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "missing", "loc": ("denom",), "msg": "Field required"},
        ],
    )


@pytest.mark.parametrize(
    "denom",
    [
        123,  # int
        3.14,  # float
        True,  # bool
        ["uzig"],  # list
        {"denom": "uzig"},  # dict
        (),  # tuple
        None,
    ],
)
def test_denom_unit_denom_bad_type(
    denom_unit_data: Dict[str, Any],
    denom: Any,
) -> None:
    """Test DenomUnit.denom rejects non-string types."""
    denom_unit_data["denom"] = denom
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_type", "loc": ("denom",), "msg": "Input should be a valid string"},
        ],
    )


def test_denom_unit_denom_too_short(
    denom_unit_data: Dict[str, Any],
) -> None:
    """Test DenomUnit.denom with empty string."""
    denom_unit_data["denom"] = ""
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_too_short", "loc": ("denom",), "msg": "String should have at least 1 character"},
        ],
    )


def test_denom_unit_denom_too_long(
    denom_unit_data: Dict[str, Any],
) -> None:
    """Test DenomUnit.denom exceeds max length."""
    denom_unit_data["denom"] = "a" * 129
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_too_long", "loc": ("denom",), "msg": "String should have at most 128 characters"},
        ],
    )


@pytest.mark.parametrize(
    "denom",
    [
        "1zig",  # starts with number
        "!zig",  # invalid char at start
        " zig",  # starts with space
        "zig!",  # invalid char at end
        "zig zig",  # space in middle
    ],
)
def test_denom_unit_denom_bad_pattern(
    denom_unit_data: Dict[str, Any],
    denom: str,
) -> None:
    """Test DenomUnit.denom rejects invalid pattern (must start with letter, use letters/numbers/'/:._-')."""
    denom_unit_data["denom"] = denom
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": ("denom",), "msg": "Value error, denom must start with a letter and use letters, numbers or '/:._-'"},
        ],
    )


# ----------------
# Negative tests for DenomUnit.exponent field
# ----------------

def test_denom_unit_exponent_missing(
    denom_unit_data: Dict[str, Any],
) -> None:
    """Test DenomUnit.exponent field is missing."""
    del denom_unit_data["exponent"]
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "missing", "loc": ("exponent",), "msg": "Field required"},
        ],
    )


def test_denom_unit_exponent_bad_type_bool(
    denom_unit_data: Dict[str, Any],
) -> None:
    """Test DenomUnit.exponent with bool (validator rejects)."""
    denom_unit_data["exponent"] = True
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": ("exponent",), "msg": "Value error, exponent cannot be bool, must be an integer"},
        ],
    )


def test_denom_unit_exponent_negative(
    denom_unit_data: Dict[str, Any],
) -> None:
    """Test DenomUnit.exponent with negative value (ge=0)."""
    denom_unit_data["exponent"] = -1
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "greater_than_equal", "loc": ("exponent",), "msg": "Input should be greater than or equal to 0"},
        ],
    )


@pytest.mark.parametrize(
    "exponent",
    [
        ["6"],  # list
        {"exponent": 6},  # dict
        None,
    ],
)
def test_denom_unit_exponent_bad_type(
    denom_unit_data: Dict[str, Any],
    exponent: Any,
) -> None:
    """Test DenomUnit.exponent rejects non-integer types (int_type)."""
    denom_unit_data["exponent"] = exponent
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "int_type", "loc": ("exponent",), "msg": "Input should be a valid integer"},
        ],
    )


def test_denom_unit_exponent_bad_type_float(
    denom_unit_data: Dict[str, Any],
) -> None:
    """Test DenomUnit.exponent with float (int_from_float)."""
    denom_unit_data["exponent"] = 3.14
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "int_from_float", "loc": ("exponent",), "msg": "Input should be a valid integer, got a number with a fractional part"},
        ],
    )


# ----------------
# Negative tests for DenomUnit.aliases field
# ----------------

def test_denom_unit_aliases_empty_string(
    denom_unit_data: Dict[str, Any],
) -> None:
    """Test DenomUnit.aliases with list containing empty string (validator: non-empty strings)."""
    denom_unit_data["aliases"] = [""]
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": ("aliases",), "msg": "Value error, aliases must be non-empty strings"},
        ],
    )


def test_denom_unit_aliases_whitespace_only(
    denom_unit_data: Dict[str, Any],
) -> None:
    """Test DenomUnit.aliases with list containing whitespace-only (validator: non-empty strings)."""
    denom_unit_data["aliases"] = ["   "]
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": ("aliases",), "msg": "Value error, aliases must be non-empty strings"},
        ],
    )


def test_denom_unit_aliases_duplicate(
    denom_unit_data: Dict[str, Any],
) -> None:
    """Test DenomUnit.aliases with duplicate values (validator: unique)."""
    denom_unit_data["aliases"] = ["ZIG", "ZIG"]
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "value_error", "loc": ("aliases",), "msg": "Value error, aliases must be unique"},
        ],
    )

# Non-list scalars/mappings produce list_type; tuples/sets are explicitly rejected by validator with value_error
@pytest.mark.parametrize(
    "aliases",
    [
        123,       # int
        3.14,      # float
        True,      # bool
        "ZIG",     # string (not list)
        {"a": "b"},  # dict
    ],
)
def test_denom_unit_aliases_bad_type_list(
    denom_unit_data: Dict[str, Any],
    aliases: Any,
) -> None:
    """Test DenomUnit.aliases rejects non-list scalars/mappings (list_type error)."""
    denom_unit_data["aliases"] = aliases
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "list_type", "loc": ("aliases",), "msg": "Input should be a valid list"},
        ],
    )


@pytest.mark.parametrize(
    "aliases, expected_type_name",
    [
        (("ZIG", "zigchain"), "tuple"),  # tuple rejected by reject_non_list_aliases
        ({"ZIG", "zigchain"}, "set"),    # set rejected by reject_non_list_aliases
    ],
)
def test_denom_unit_aliases_bad_type_rejected(
    denom_unit_data: Dict[str, Any],
    aliases: Any,
    expected_type_name: str,
) -> None:
    """Test DenomUnit.aliases rejects tuple/set (reject_non_list_aliases validator)."""
    denom_unit_data["aliases"] = aliases
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("aliases",),
                "msg": f"Value error, aliases must be a list, not {expected_type_name}",
            },
        ],
    )


@pytest.mark.parametrize(
    "aliases",
    [
        [123, "zig"],  # int in list
        [3.14],  # float in list
        [True],  # bool in list
        [None],  # None in list
        [{"x": 1}],  # dict in list
    ],
)
def test_denom_unit_aliases_bad_type_string(
    denom_unit_data: Dict[str, Any],
    aliases: Any,
) -> None:
    """Test DenomUnit.aliases rejects list with non-string elements."""
    denom_unit_data["aliases"] = aliases
    with pytest.raises(ValidationError) as exc:
        DenomUnit(**denom_unit_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {"type": "string_type", "loc": ("aliases", 0), "msg": "Input should be a valid string"},
        ],
    )


######################################################################
# Tests for _validate_logo_host helper
######################################################################

# ----------------
# Positive tests for _validate_logo_host
# ----------------

def test_validate_logo_host_allowlisted_url_returned_unchanged() -> None:
    """Allowlisted URL returns unchanged — same object, no reconstruction."""
    url = TypeAdapter(HttpUrl).validate_python("https://raw.githubusercontent.com/logo.png")
    assert _validate_logo_host(url) is url


def test_validate_logo_host_none_returned_as_none() -> None:
    """None short-circuits — png/svg are Optional, so the validator is called with None
    whenever the field is unset."""
    assert _validate_logo_host(None) is None


def test_allowed_logo_hosts_frozenset_pin() -> None:
    """Pin allowlist contents and type. Frozenset blocks runtime mutation; pinning the
    exact set forces any CDN addition through a deliberate edit to this test, which
    gets reviewed alongside the allowlist change."""
    assert isinstance(_ALLOWED_LOGO_HOSTS, frozenset)
    assert _ALLOWED_LOGO_HOSTS == frozenset({"raw.githubusercontent.com"})


# ----------------
# Negative tests for _validate_logo_host
# ----------------

@pytest.mark.parametrize(
    "bad_url,expected_host",
    [
        ("https://evil.com/logo.png", "evil.com"),
        ("https://cdn.jsdelivr.net/logo.svg", "cdn.jsdelivr.net"),
        ("https://raw.githubusercontent.com.evil.com/logo.png", "raw.githubusercontent.com.evil.com"),  # suffix confusable
        ("https://sub.raw.githubusercontent.com/logo.svg", "sub.raw.githubusercontent.com"),  # subdomain is NOT exact host
        ("https://raw.githubusercontent.io/logo.png", "raw.githubusercontent.io"),  # TLD confusable
    ],
)
def test_validate_logo_host_rejects_non_allowlisted(
    bad_url: str, expected_host: str
) -> None:
    """Non-allowlisted hosts raise ValueError with a message naming the rejected host
    and the full allowlist — operators need both to diagnose a rejection."""
    # Arrange: parse the bad URL into an HttpUrl so the helper receives the same type Pydantic would pass it.
    url = TypeAdapter(HttpUrl).validate_python(bad_url)
    # Act: call the helper directly and capture the ValueError it raises on non-allowlisted hosts.
    with pytest.raises(ValueError) as exc:
        _validate_logo_host(url)
    # Assert: error message names the rejected host and lists the allowlist for operator debugging.
    message = str(exc.value)
    assert "is not in the allowlist" in message.lower()
    assert expected_host in message
    assert "raw.githubusercontent.com" in message


def test_validate_logo_host_raises_bare_valueerror_not_validationerror() -> None:
    """Helper raises a bare ValueError, not pydantic.ValidationError. Pydantic wraps
    ValueError into ValidationError at the class boundary, so the primitive must
    raise the unwrapped form to stay reusable outside a Pydantic validator context."""
    # Arrange: build a non-allowlisted HttpUrl that is guaranteed to trigger the helper's reject path.
    url = TypeAdapter(HttpUrl).validate_python("https://evil.com/logo.png")
    # Act: invoke the helper outside any Pydantic model so nothing wraps the raised exception.
    with pytest.raises(ValueError) as exc:
        _validate_logo_host(url)
    # Assert: the caught exception is a bare ValueError, not the ValidationError subclass Pydantic would raise.
    assert not isinstance(exc.value, ValidationError)


######################################################################
# Invariant: all model classes must enforce extra="forbid"
######################################################################


@pytest.mark.parametrize(
    "model_class",
    [
        # base.py models
        LogoUris,
        Socials,
        TraceCounterparty,
        NativeTrace,
        ImageSyncPointer,
        ImageTheme,
        ImageEntry,
        DenomUnit,
        AssetBase,
        # subclass models (native.py, factory.py, ibc.py)
        NativeAsset,
        FactoryAsset,
        IBCAsset,
        IBCTrace,
        IBCChannel,
    ],
    ids=lambda cls: cls.__name__,
)
def test_all_base_models_enforce_extra_forbid(model_class: type) -> None:
    """Every model class must set extra='forbid' to prevent silent field injection.

    If a future PR relaxes this on any model, arbitrary JSON fields would be
    accepted without error — enabling metadata spoofing and schema bypass.
    This test catches the regression automatically.
    """
    # Act: read the model's Pydantic config
    extra = model_class.model_config.get("extra")

    # Assert: must be "forbid", not "allow", "ignore", or missing
    assert extra == "forbid", (
        f"{model_class.__name__}.model_config['extra'] is {extra!r}, expected 'forbid'"
    )


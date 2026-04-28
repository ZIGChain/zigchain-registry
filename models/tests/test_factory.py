"""Tests for FactoryAsset model."""

from typing import Any, Dict, List, Optional

import pytest
from pydantic import HttpUrl, ValidationError

from models import FactoryAsset
from . import check_model_error


######################################################################
# Fixtures
######################################################################


@pytest.fixture
def factory_asset_data() -> Dict[str, Any]:
    """Fixture providing valid FactoryAsset data with all fields."""
    creator = "zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw"
    subdenom = "panda01"
    base = f"coin.{creator}.{subdenom}"
    return {
        "$schema": "../../schemas/asset.factory.schema.json",
        "network": "mainnet",
        "asset_id": base,
        "order": 1,
        "type": "factory",
        "symbol": "PANDA",
        "name": "Factory Panda Token",
        "decimals": 6,
        "denom_units": [
            {"denom": base, "exponent": 0},
            {"denom": "panda", "exponent": 6},
        ],
        "display_denom": "Panda",
        "description": "Factory Token Panda",
        "extended_description": "Token created by Panda team",
        "keywords": ["Factory", "Token"],
        "images": [{"png": "https://raw.githubusercontent.com/test/zig.png"}],
        "logo_uris": {"png": "https://raw.githubusercontent.com/test/logo.png"},
        "socials": {"website": "https://example.com", "x": "https://x.com/example"},
        "coingecko_id": "panda",
        "is_verified": True,
        "base_denom": base,
        "creator": creator,
        "subdenom": subdenom,
        "uri": "https://example.com/whitepaper.pdf",
        "uri_hash": "a3f4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4",
    }


@pytest.fixture
def factory_asset_data_minimal() -> Dict[str, Any]:
    """Fixture providing minimal valid FactoryAsset data (required fields only)."""
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


######################################################################
# Positive tests for FactoryAsset models.
######################################################################

# ----------------
# Positive tests for FactoryAsset class
# ----------------


def test_factory_asset(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset class with all fields."""
    asset = FactoryAsset(**factory_asset_data)
    # 18 inherited from AssetBase + 5 factory-specific (base_denom, creator, subdenom, uri, uri_hash)
    assert len(FactoryAsset.model_fields) == 23

    # Inherited from AssetBase
    assert asset.schema_ref == factory_asset_data["$schema"]
    assert asset.network == factory_asset_data["network"]
    assert asset.asset_id == factory_asset_data["asset_id"]
    assert asset.order == factory_asset_data["order"]
    assert asset.type == factory_asset_data["type"]
    assert asset.symbol == factory_asset_data["symbol"]
    assert asset.name == factory_asset_data["name"]
    assert asset.decimals == factory_asset_data["decimals"]
    assert len(asset.denom_units) == len(factory_asset_data["denom_units"])
    for i, unit in enumerate(asset.denom_units):
        assert unit.denom == factory_asset_data["denom_units"][i]["denom"]
        assert unit.exponent == factory_asset_data["denom_units"][i]["exponent"]
    assert asset.display_denom == factory_asset_data["display_denom"]
    assert asset.description == factory_asset_data["description"]
    assert asset.extended_description == factory_asset_data["extended_description"]
    assert asset.keywords == factory_asset_data["keywords"]
    assert len(asset.images) == len(factory_asset_data["images"])
    assert str(asset.logo_uris.png) == factory_asset_data["logo_uris"]["png"]
    assert str(asset.socials.website) == str(
        HttpUrl(factory_asset_data["socials"]["website"])
    )
    assert str(asset.socials.x) == factory_asset_data["socials"]["x"]
    assert asset.coingecko_id == factory_asset_data["coingecko_id"]
    assert asset.is_verified == factory_asset_data["is_verified"]

    # Factory-specific
    assert asset.base_denom == factory_asset_data["base_denom"]
    assert asset.creator == factory_asset_data["creator"]
    assert asset.subdenom == factory_asset_data["subdenom"]
    assert str(asset.uri) == factory_asset_data["uri"]
    assert asset.uri_hash == factory_asset_data["uri_hash"]


def test_factory_asset_minimal(
    factory_asset_data_minimal: Dict[str, Any],
) -> None:
    """Test FactoryAsset class with only required fields (no optionals)."""
    asset = FactoryAsset(**factory_asset_data_minimal)
    assert asset.network == factory_asset_data_minimal["network"]
    assert asset.asset_id == factory_asset_data_minimal["asset_id"]
    assert asset.type == factory_asset_data_minimal["type"]
    assert asset.symbol == factory_asset_data_minimal["symbol"]
    assert asset.name == factory_asset_data_minimal["name"]
    assert asset.decimals == factory_asset_data_minimal["decimals"]
    assert asset.display_denom == factory_asset_data_minimal["display_denom"]
    assert asset.base_denom == factory_asset_data_minimal["base_denom"]
    assert asset.creator == factory_asset_data_minimal["creator"]
    assert asset.subdenom == factory_asset_data_minimal["subdenom"]
    assert len(asset.denom_units) == len(factory_asset_data_minimal["denom_units"])
    assert asset.is_verified is None
    assert asset.uri is None
    assert asset.uri_hash is None
    assert asset.order is None
    assert asset.description is None
    assert asset.extended_description is None
    assert asset.keywords is None
    assert asset.images is None
    assert asset.logo_uris is None
    assert asset.socials is None
    assert asset.coingecko_id is None


# ----------------
# Positive tests for FactoryAsset.network field
# ----------------


@pytest.mark.parametrize("network", ["mainnet", "testnet"])
def test_factory_asset_network_valid(
    factory_asset_data: Dict[str, Any],
    network: str,
) -> None:
    """Test FactoryAsset.network field with valid values."""
    factory_asset_data["network"] = network
    asset = FactoryAsset(**factory_asset_data)
    assert asset.network == network


# ----------------
# Positive tests for FactoryAsset.asset_id field
# ----------------


@pytest.mark.parametrize(
    "creator,subdenom",
    [
        ("zig1" + "a" * 38, "panda"),  # min creator length (38 chars after zig1)
        ("zig1" + "a" * 38, "abc"),  # min subdenom length (3 chars)
        ("zig1" + "a" * 38, "test-token"),  # hyphen in subdenom
        ("zig1" + "a" * 38 + "0123456789", "token01"),  # digits in creator and subdenom
        ("zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw", "panda01"),  # fixture-style
        ("zig1" + "a" * 38, "a" + "b" * 43),  # max subdenom length (44 chars)
        ("zig1" + "0" * 38 + "z", "x-y-z"),  # digits in creator, hyphens in subdenom
    ],
)
def test_factory_asset_asset_id_valid(
    factory_asset_data: Dict[str, Any],
    creator: str,
    subdenom: str,
) -> None:
    """Test FactoryAsset.asset_id with valid factory format (coin.zig1<38+>.<subdenom>)."""
    asset_id = f"coin.{creator}.{subdenom}"
    factory_asset_data["asset_id"] = asset_id
    factory_asset_data["base_denom"] = asset_id
    factory_asset_data["creator"] = creator
    factory_asset_data["subdenom"] = subdenom
    factory_asset_data["denom_units"] = [
        {"denom": asset_id, "exponent": 0},
        {"denom": "tkn", "exponent": 6},
    ]
    asset = FactoryAsset(**factory_asset_data)
    assert asset.asset_id == asset_id
    assert asset.asset_id.startswith("coin.")
    assert asset.base_denom == asset_id
    assert asset.creator == creator
    assert asset.subdenom == subdenom


# ----------------
# Positive tests for FactoryAsset.order field
# ----------------


@pytest.mark.parametrize("order", [0, 1, 100, None])
def test_factory_asset_order_valid(
    factory_asset_data: Dict[str, Any],
    order: Optional[int],
) -> None:
    """Test FactoryAsset.order field with valid values (int >= 0 or None)."""
    if order is None:
        del factory_asset_data["order"]
    else:
        factory_asset_data["order"] = order
    asset = FactoryAsset(**factory_asset_data)
    assert asset.order == order


# ----------------
# Positive tests for FactoryAsset.type field
# ----------------


def test_factory_asset_type_valid(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.type is literal 'factory'."""
    asset = FactoryAsset(**factory_asset_data)
    assert asset.type == "factory"


def test_factory_asset_type_missing(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.type defaults to 'factory' when field is missing."""
    del factory_asset_data["type"]
    asset = FactoryAsset(**factory_asset_data)
    assert asset.type == "factory"


# ----------------
# Positive tests for FactoryAsset.symbol field
# ----------------


@pytest.mark.parametrize("symbol", ["PANDA", "TOKEN", "A1", "A" * 42])
def test_factory_asset_symbol_valid(
    factory_asset_data: Dict[str, Any],
    symbol: str,
) -> None:
    """Test FactoryAsset.symbol field with valid values."""
    factory_asset_data["symbol"] = symbol
    asset = FactoryAsset(**factory_asset_data)
    assert asset.symbol == symbol


# ----------------
# Positive tests for FactoryAsset.name field
# ----------------


@pytest.mark.parametrize("name", ["Factory Panda Token", "My Token", "A" * 100])
def test_factory_asset_name_valid(
    factory_asset_data: Dict[str, Any],
    name: str,
) -> None:
    """Test FactoryAsset.name field with valid values."""
    factory_asset_data["name"] = name
    asset = FactoryAsset(**factory_asset_data)
    assert asset.name == name


# ----------------
# Positive tests for FactoryAsset.decimals field
# ----------------


@pytest.mark.parametrize("decimals", [3, 6, 18])
def test_factory_asset_decimals_valid(
    factory_asset_data: Dict[str, Any],
    decimals: int,
) -> None:
    """Test FactoryAsset.decimals field with valid values."""
    factory_asset_data["decimals"] = decimals
    if decimals != 6:
        base = factory_asset_data["base_denom"]
        factory_asset_data["denom_units"] = [
            {"denom": base, "exponent": 0},
            {"denom": "tkn", "exponent": decimals},
        ]
    asset = FactoryAsset(**factory_asset_data)
    assert asset.decimals == decimals


# ----------------
# Positive tests for FactoryAsset.description field
# ----------------


@pytest.mark.parametrize("description", ["A description", None])
def test_factory_asset_description_valid(
    factory_asset_data: Dict[str, Any],
    description: Optional[str],
) -> None:
    """Test FactoryAsset.description field with valid values."""
    factory_asset_data["description"] = description
    asset = FactoryAsset(**factory_asset_data)
    assert asset.description == description


# ----------------
# Positive tests for FactoryAsset.extended_description field
# ----------------


@pytest.mark.parametrize("extended_description", ["Extended text", None])
def test_factory_asset_extended_description_valid(
    factory_asset_data: Dict[str, Any],
    extended_description: Optional[str],
) -> None:
    """Test FactoryAsset.extended_description field with valid values."""
    factory_asset_data["extended_description"] = extended_description
    asset = FactoryAsset(**factory_asset_data)
    assert asset.extended_description == extended_description


# ----------------
# Positive tests for FactoryAsset.keywords field
# ----------------


@pytest.mark.parametrize("keywords", [["factory", "token"], None])
def test_factory_asset_keywords_valid(
    factory_asset_data: Dict[str, Any],
    keywords: Optional[List[str]],
) -> None:
    """Test FactoryAsset.keywords field with valid values."""
    factory_asset_data["keywords"] = keywords
    asset = FactoryAsset(**factory_asset_data)
    assert asset.keywords == keywords


# ----------------
# Positive tests for FactoryAsset.images field
# ----------------


@pytest.mark.parametrize(
    "images",
    [
        [{"png": "https://raw.githubusercontent.com/test/logo.png"}],
        [{"chain_name": "zigchain", "base_denom": "uzig"}],
        [],
        None,
    ],
)
def test_factory_asset_images_valid(
    factory_asset_data: Dict[str, Any],
    images: Any,
) -> None:
    """Test FactoryAsset.images field with valid values."""
    factory_asset_data["images"] = images
    asset = FactoryAsset(**factory_asset_data)
    if images is None:
        assert asset.images is None
    else:
        assert asset.images is not None
        assert len(asset.images) == len(images)


# ----------------
# Positive tests for FactoryAsset.logo_uris field
# ----------------


@pytest.mark.parametrize(
    "logo_uris",
    [
        {"png": "https://raw.githubusercontent.com/test/logo.png"},
        {"svg": "https://raw.githubusercontent.com/test/logo.svg"},
        None,
    ],
)
def test_factory_asset_logo_uris_valid(
    factory_asset_data: Dict[str, Any],
    logo_uris: Any,
) -> None:
    """Test FactoryAsset.logo_uris field with valid values."""
    factory_asset_data["logo_uris"] = logo_uris
    asset = FactoryAsset(**factory_asset_data)
    if logo_uris is None:
        assert asset.logo_uris is None


# ----------------
# Positive tests for FactoryAsset.socials field
# ----------------


@pytest.mark.parametrize(
    "socials",
    [
        {"website": "https://example.com"},
        {"x": "https://x.com/foo"},
        None,
    ],
)
def test_factory_asset_socials_valid(
    factory_asset_data: Dict[str, Any],
    socials: Any,
) -> None:
    """Test FactoryAsset.socials field with valid values."""
    factory_asset_data["socials"] = socials
    asset = FactoryAsset(**factory_asset_data)
    if socials is None:
        assert asset.socials is None


# ----------------
# Positive tests for FactoryAsset.coingecko_id field
# ----------------


@pytest.mark.parametrize("coingecko_id", ["panda", "usd-coin", None])
def test_factory_asset_coingecko_id_valid(
    factory_asset_data: Dict[str, Any],
    coingecko_id: Optional[str],
) -> None:
    """Test FactoryAsset.coingecko_id field with valid values."""
    factory_asset_data["coingecko_id"] = coingecko_id
    asset = FactoryAsset(**factory_asset_data)
    assert asset.coingecko_id == coingecko_id


# ----------------
# Positive tests for FactoryAsset.display_denom field
# ----------------


@pytest.mark.parametrize(
    "display_denom",
    [
        "ZIG",
        "1ZIG.axl",  # starting with number
        "A"
        * 33,  # exceeds base AssetBase limit of 32 — proves factory override is active
        "A" * 128,  # max length
        "USDC:USDC",  # valid symbol :
        "ZIG-USDC",  # valid symbol -
        "ZIG_USDC",  # valid symbol _
        "PANDA.1",  # valid symbol .
        "a",  # min length
        "Panda",  # lowercase
        "1234",  # only numbers
    ],
)
def test_factory_asset_display_denom_valid(
    factory_asset_data: Dict[str, Any],
    display_denom: str,
) -> None:
    """Test FactoryAsset.display_denom field with valid values."""
    factory_asset_data["display_denom"] = display_denom
    asset = FactoryAsset(**factory_asset_data)
    assert asset.display_denom == display_denom


# ----------------
# Positive tests for FactoryAsset.base_denom field
# ----------------


@pytest.mark.parametrize(
    "creator,subdenom",
    [
        (
            "zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw",
            "panda",
        ),  # Standard creator + short subdenom
        ("zig1wze8mn5nsgl9qrgazq6a92fvh7m5e6psjcx2du", "token"),
        (
            "zig1pt9u490q0km4lx8h9h48vzu3q20yl9nmq3ulkqjeelrfp5ec7nws68c2rn",
            "test-token",
        ),  # Max-length creator
        ("zig1" + "a" * 38, "abc"),  # Min-length creator
        (
            "zig1wze8mn5nsgl9qrgazq6a92fvh7m5e6psjcx2du",
            "token01",
        ),  # subdenom with numbers
        ("zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw", "a1b2"),
        (
            "zig1wze8mn5nsgl9qrgazq6a92fvh7m5e6psjcx2du",
            "my-token-v2",
        ),  # Subdenom with multiple hyphens
        (
            "zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw",
            "a" + "b" * 42 + "c",
        ),  # Max-length subdenom
        (
            "zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw",
            "x-0-1",
        ),  # Single-letter prefix subdenom with numeric suffix
    ],
)
def test_factory_asset_base_denom_valid(
    factory_asset_data: Dict[str, Any],
    creator: str,
    subdenom: str,
) -> None:
    """Test FactoryAsset.base_denom with valid creator/subdenom; base_denom must equal coin.<creator>.<subdenom>."""
    base_denom = f"coin.{creator}.{subdenom}"
    factory_asset_data["base_denom"] = base_denom
    factory_asset_data["asset_id"] = base_denom
    factory_asset_data["creator"] = creator
    factory_asset_data["subdenom"] = subdenom
    factory_asset_data["denom_units"] = [
        {"denom": base_denom, "exponent": 0},
        {"denom": "token", "exponent": 6},
    ]
    asset = FactoryAsset(**factory_asset_data)
    assert asset.base_denom == base_denom


# ----------------
# Positive tests for FactoryAsset.creator field
# ----------------


@pytest.mark.parametrize(
    "creator",
    [
        "zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw",  # Min-length
        "zig1wze8mn5nsgl9qrgazq6a92fvh7m5e6psjcx2du",
        "zig1pt9u490q0km4lx8h9h48vzu3q20yl9nmq3ulkqjeelrfp5ec7nws68c2rn",
        "zig1" + "a" * 96,  # Max-length
    ],
)
def test_factory_asset_creator_valid(
    factory_asset_data: Dict[str, Any],
    creator: str,
) -> None:
    """Test FactoryAsset.creator field with valid values."""
    subdenom = factory_asset_data["subdenom"]
    base_denom = f"coin.{creator}.{subdenom}"
    factory_asset_data["creator"] = creator
    factory_asset_data["base_denom"] = base_denom
    factory_asset_data["asset_id"] = base_denom
    factory_asset_data["denom_units"] = [
        {"denom": base_denom, "exponent": 0},
        {"denom": "token", "exponent": 6},
    ]
    asset = FactoryAsset(**factory_asset_data)
    assert asset.creator == creator


# ----------------
# Positive tests for FactoryAsset.subdenom field
# ----------------


@pytest.mark.parametrize(
    "subdenom",
    [
        "panda",
        "token",
        "test-token",
        "a" * 44,  # max length
    ],
)
def test_factory_asset_subdenom_valid(
    factory_asset_data: Dict[str, Any],
    subdenom: str,
) -> None:
    """Test FactoryAsset.subdenom field with valid values."""
    creator = factory_asset_data["creator"]
    base_denom = f"coin.{creator}.{subdenom}"
    factory_asset_data["subdenom"] = subdenom
    factory_asset_data["base_denom"] = base_denom
    factory_asset_data["asset_id"] = base_denom
    factory_asset_data["denom_units"] = [
        {"denom": base_denom, "exponent": 0},
        {"denom": "token", "exponent": 6},
    ]
    asset = FactoryAsset(**factory_asset_data)
    assert asset.subdenom == subdenom


# ----------------
# Positive tests for FactoryAsset.denom_units field
# ----------------


def test_factory_asset_denom_units_valid_minimal(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.denom_units with only exponent=0 entry; decimals unconstrained (max_exponent guard skips check)."""
    base = factory_asset_data["base_denom"]
    denom_units = [{"denom": base, "exponent": 0}]
    factory_asset_data["denom_units"] = denom_units
    asset = FactoryAsset(**factory_asset_data)
    assert len(asset.denom_units) == 1
    assert asset.denom_units[0].denom == base
    assert asset.denom_units[0].exponent == 0


def test_factory_asset_denom_units_valid_base_and_display(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.denom_units with base and display (exponent 0 and 6)."""
    base = factory_asset_data["base_denom"]
    denom_units = [
        {"denom": base, "exponent": 0},
        {"denom": "panda", "exponent": 6},
    ]
    factory_asset_data["denom_units"] = denom_units
    asset = FactoryAsset(**factory_asset_data)
    assert len(asset.denom_units) == 2
    assert asset.denom_units[0].denom == base and asset.denom_units[0].exponent == 0
    assert asset.denom_units[1].denom == "panda" and asset.denom_units[1].exponent == 6


def test_factory_asset_denom_units_valid_three_units(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.denom_units with three units (exponents 0, 3, 6)."""
    base = factory_asset_data["base_denom"]
    denom_units = [
        {"denom": base, "exponent": 0},
        {"denom": "x", "exponent": 3},
        {"denom": "panda", "exponent": 6},
    ]
    factory_asset_data["denom_units"] = denom_units
    asset = FactoryAsset(**factory_asset_data)
    assert len(asset.denom_units) == 3
    assert asset.denom_units[0].denom == base and asset.denom_units[0].exponent == 0
    assert asset.denom_units[1].denom == "x" and asset.denom_units[1].exponent == 3
    assert asset.denom_units[2].denom == "panda" and asset.denom_units[2].exponent == 6


# ----------------
# Positive tests for FactoryAsset.is_verified field
# ----------------


@pytest.mark.parametrize(
    "is_verified",
    [
        True,
        False,
        None,
    ],
)
def test_factory_asset_is_verified_valid(
    factory_asset_data: Dict[str, Any],
    is_verified: Any,
) -> None:
    """Test FactoryAsset.is_verified field with valid values."""
    factory_asset_data["is_verified"] = is_verified
    asset = FactoryAsset(**factory_asset_data)
    assert asset.is_verified == is_verified


# ----------------
# Positive tests for FactoryAsset.uri field
# ----------------


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.com/whitepaper.pdf",
        "https://example.com/doc",
        None,
    ],
)
def test_factory_asset_uri_valid(
    factory_asset_data: Dict[str, Any],
    uri: Any,
) -> None:
    """Test FactoryAsset.uri field with valid values."""
    factory_asset_data["uri"] = uri
    if uri is not None:
        factory_asset_data["uri_hash"] = (
            "a3f4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4"
        )
    else:
        factory_asset_data["uri_hash"] = None
    asset = FactoryAsset(**factory_asset_data)
    if uri is None:
        assert asset.uri is None
    else:
        assert str(asset.uri) == uri


# ----------------
# Positive tests for FactoryAsset.uri_hash field
# ----------------


@pytest.mark.parametrize(
    "uri_hash",
    [
        "a3f4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4",
        "A3F4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0F1A2B3C4",
        "0" * 64,
        "f" * 64,
    ],
)
def test_factory_asset_uri_hash_valid(
    factory_asset_data: Dict[str, Any],
    uri_hash: str,
) -> None:
    """Test FactoryAsset.uri_hash field with valid values."""
    factory_asset_data["uri_hash"] = uri_hash
    asset = FactoryAsset(**factory_asset_data)
    assert asset.uri_hash == uri_hash


######################################################################
# Negative tests for FactoryAsset models.
######################################################################

# ----------------
# Negative test for FactoryAsset class
# ----------------


def test_factory_asset_extra_forbidden(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset rejects unknown fields (model_config extra='forbid')."""
    factory_asset_data["unknown_field"] = "value"
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
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
# Negative tests for FactoryAsset.network field
# ----------------


def test_factory_asset_network_missing(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.network field is missing."""
    del factory_asset_data["network"]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
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


@pytest.mark.parametrize("network", ["invalid", "devnet", ""])
def test_factory_asset_network_invalid_value(
    factory_asset_data: Dict[str, Any],
    network: str,
) -> None:
    """Test FactoryAsset.network field with invalid values."""
    factory_asset_data["network"] = network
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
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
# Negative tests for FactoryAsset.asset_id field
# ----------------


def test_factory_asset_asset_id_missing(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.asset_id field is missing."""
    del factory_asset_data["asset_id"]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
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


@pytest.mark.parametrize(
    "asset_id",
    [
        "native.zig1xxx.yyy",  # wrong prefix (native. instead of coin.)
        "coin.zig1short.token",  # creator too short (< 38 chars after zig1)
        "ibc/xxx",  # wrong prefix
        "coin.zig1" + "a" * 38 + ".1token",  # subdenom starts with number
        "coin.zig1" + "a" * 38 + ".ab",  # subdenom too short (2 chars)
        "coin.ZIG1" + "a" * 38 + ".token",  # uppercase in creator (zig1)
        "coin.zig1" + "a" * 38 + ".token!",  # invalid char in subdenom
        "coin.zig1" + "a" * 38 + ".Token",  # uppercase in subdenom
        "coin.zig1" + "a" * 38 + ".tok en",  # space in subdenom
        "aaaaa",  # wrong format
        "coin." + "a" * 38 + ".token",  # no zig prefix
        "coin.zig1" + "a" * 38 + "1token",  # missing .
    ],
)
def test_factory_asset_asset_id_bad_pattern(
    factory_asset_data: Dict[str, Any],
    asset_id: str,
) -> None:
    """Test FactoryAsset.asset_id with invalid format (must be coin.zig1<38+>.<subdenom>)."""
    factory_asset_data["asset_id"] = asset_id
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("asset_id",),
                "msg": "Value error, asset_id must match format coin.<creator>.<subdenom>",
            }
        ],
    )


def test_factory_asset_asset_id_empty_string(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.asset_id rejects empty string (Field min_length=1, before custom validator)."""
    factory_asset_data["asset_id"] = ""
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
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


def test_factory_asset_asset_id_too_long(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.asset_id rejects string longer than 128 characters (Field max_length=128)."""
    factory_asset_data["asset_id"] = "a" * 129
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
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


@pytest.mark.parametrize(
    "asset_id",
    [
        123,  # int
        12.4,  # float
        ["coin.zig1" + "a" * 38 + ".token"],  # list
        {"asset_id": "coin.zig1" + "a" * 38 + ".token"},  # dict
        True,  # bool
    ],
)
def test_factory_asset_asset_id_bad_type(
    factory_asset_data: Dict[str, Any],
    asset_id: Any,
) -> None:
    """Test FactoryAsset.asset_id rejects non-string types."""
    factory_asset_data["asset_id"] = asset_id
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
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


def test_factory_asset_asset_id_bytes(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.asset_id rejects bytes (reject_bytes_asset_id in base.py, mode='before')."""
    factory_asset_data["asset_id"] = b"coin.zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw.panda01"
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
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
# Negative tests for FactoryAsset.type field
# ----------------


@pytest.mark.parametrize(
    "asset_type",
    [
        "native",
        "ibc",
        "invalid",
        "",  # empty str
        123,  # int
        ["factory"],  # list
        {"type": "factory"},  # dict
        True,  # bool
        None,  # none
    ],
)
def test_factory_asset_type_invalid_value(
    factory_asset_data: Dict[str, Any],
    asset_type: Any,
) -> None:
    """Test FactoryAsset.type must be literal 'factory'."""
    factory_asset_data["type"] = asset_type
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "literal_error",
                "loc": ("type",),
                "msg": "Input should be 'factory'",
            }
        ],
    )


# ----------------
# Negative tests for FactoryAsset.symbol field
# ----------------


def test_factory_asset_symbol_missing(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.symbol field is missing."""
    del factory_asset_data["symbol"]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
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


# ----------------
# Negative tests for FactoryAsset.name field
# ----------------


def test_factory_asset_name_missing(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.name field is missing."""
    del factory_asset_data["name"]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
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


# ----------------
# Negative tests for FactoryAsset.decimals field
# ----------------


def test_factory_asset_decimals_missing(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.decimals field is missing."""
    del factory_asset_data["decimals"]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
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


# ----------------
# Negative tests for FactoryAsset.order field
# ----------------


def test_factory_asset_order_negative(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.order rejects negative values."""
    factory_asset_data["order"] = -1
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
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


# ----------------
# Negative tests for FactoryAsset.display_denom field
# ----------------


def test_factory_asset_display_denom_missing(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.display_denom field is missing."""
    del factory_asset_data["display_denom"]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

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


def test_factory_asset_display_denom_bad_type_none(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.display_denom field with None value."""
    factory_asset_data["display_denom"] = None
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

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


def test_factory_asset_display_denom_too_short(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.display_denom field is too short."""
    factory_asset_data["display_denom"] = ""
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

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


def test_factory_asset_display_denom_too_long(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.display_denom field is too long."""
    factory_asset_data["display_denom"] = "A" * 129
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("display_denom",),
                "msg": "String should have at most 128 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "display_denom",
    [
        ":ZIG",  # starting with valid symbol
        ".ZIG",  # starting with valid symbol
        "-ZIG",  # starting with valid symbol
        "ZIG!",  # invalid symbol
        " ZIG",  # trailing space
        "@ZIG",  # starting with invalid symbol
    ],
)
def test_factory_asset_display_denom_bad_pattern(
    factory_asset_data: Dict[str, Any],
    display_denom: str,
) -> None:
    """Test FactoryAsset.display_denom field with invalid pattern."""
    factory_asset_data["display_denom"] = display_denom
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

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
        {"display_denom": "ZIG"},  # dict
    ],
)
def test_factory_asset_display_denom_bad_type(
    factory_asset_data: Dict[str, Any],
    display_denom: Any,
) -> None:
    """Test FactoryAsset.display_denom field with invalid type (not string)."""
    factory_asset_data["display_denom"] = display_denom
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

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


# ----------------
# Negative tests for FactoryAsset.base_denom field
# ----------------


def test_factory_asset_base_denom_missing(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.base_denom field is missing."""
    del factory_asset_data["base_denom"]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

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


def test_factory_asset_base_denom_bad_type_none(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.base_denom field with None value."""
    factory_asset_data["base_denom"] = None
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

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


def test_factory_asset_base_denom_too_short(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.base_denom field is too short."""
    factory_asset_data["base_denom"] = "coin.zig1a.b"
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("base_denom",),
                "msg": "String should have at least 51 characters",
            }
        ],
    )


def test_factory_asset_base_denom_too_long(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.base_denom field is too long."""
    factory_asset_data["base_denom"] = "coin." + "a" * 124 + ".b"
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

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
        "coin.zig1" + "a" * 38 + ".to_ken",  # underscore in subdenom (invalid pattern)
        "coin.zig1" + "A" * 38 + ".token",  # uppercase in creator (invalid pattern)
        "coin.zig1" + "a" * 38 + ".TOKEN",  # uppercase in subdenom
        "COIN.zig1" + "a" * 38 + ".token",  # uppercase prefix
        "coin" + "zig1" + "a" * 38 + ".token",  # missing dot after coin
        "coin.zig1" + "a" * 38 + "token",  # missing dot before subdenom
    ],
)
def test_factory_asset_base_denom_bad_pattern(
    factory_asset_data: Dict[str, Any],
    base_denom: str,
) -> None:
    """Test FactoryAsset.base_denom field with invalid pattern."""
    # Remove uri_hash and uri to avoid validation conflicts when testing base_denom
    factory_asset_data.pop("uri_hash", None)
    factory_asset_data.pop("uri", None)
    factory_asset_data["base_denom"] = base_denom
    # Update denom_units[0].denom to match base_denom to avoid model validation error
    # (we want to test pattern validation, not model validation)
    factory_asset_data["denom_units"][0]["denom"] = base_denom

    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_pattern_mismatch",
                "loc": ("base_denom",),
                "msg": "String should match pattern '^coin\\.zig1[0-9a-z]{38,}\\.[a-z][a-z0-9-]{2,43}$'",
            }
        ],
    )


# ----------------
# Negative tests for FactoryAsset.creator field
# ----------------


def test_factory_asset_creator_missing(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.creator field is missing."""
    del factory_asset_data["creator"]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("creator",),
                "msg": "Field required",
            }
        ],
    )


def test_factory_asset_creator_bad_type_none(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.creator field with None value."""
    factory_asset_data["creator"] = None
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("creator",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_factory_asset_creator_bad_type_bool(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.creator field with bool value."""
    factory_asset_data["creator"] = True
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    # Field-level type validation runs before custom validator
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("creator",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_factory_asset_creator_too_short(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.creator field is too short."""
    factory_asset_data["creator"] = "zig1a"
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("creator",),
                "msg": "String should have at least 42 characters",
            }
        ],
    )


def test_factory_asset_creator_too_long(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.creator field is too long."""
    factory_asset_data["creator"] = "zig1" + "a" * 100
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("creator",),
                "msg": "String should have at most 100 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "creator",
    [
        "ZIG1a" * 10,  # uppercase
        "cosmos1a" * 10,  # wrong prefix
        "a" * 42,  # no prefix
        "zig1" + "a" * 36 + "x-y",  # hyphen in body
        "zig1" + "b" * 36 + "c_d",  # underscore in body
        "zig2" + "a" * 38,  # wrong prefix zig2
        "zigl" + "a" * 38,  # typo prefix zigl
        "zig1" + "ABCDefghij0123456789abcdefghijklmnopqrst",  # uppercase in body
        "x" + "zig1" + "a" * 38,  # leading char before zig1
        "bic1" + "a" * 38,  # wrong prefix bc1
    ],
)
def test_factory_asset_creator_bad_pattern(
    factory_asset_data: Dict[str, Any],
    creator: str,
) -> None:
    """Test FactoryAsset.creator field with invalid pattern."""
    factory_asset_data["creator"] = creator
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    # Field-level validation (pattern, min_length) runs before custom validator
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_pattern_mismatch",
                "loc": ("creator",),
                "msg": "String should match pattern '^zig1[0-9a-z]{38,}$'",
            }
        ],
    )


# ----------------
# Negative tests for FactoryAsset.subdenom field
# ----------------


def test_factory_asset_subdenom_missing(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.subdenom field is missing."""
    del factory_asset_data["subdenom"]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "missing",
                "loc": ("subdenom",),
                "msg": "Field required",
            }
        ],
    )


def test_factory_asset_subdenom_bad_type_none(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.subdenom field with None value."""
    factory_asset_data["subdenom"] = None
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("subdenom",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_factory_asset_subdenom_bad_type_bool(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.subdenom field with bool value."""
    factory_asset_data["subdenom"] = True
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    # Field-level type validation runs before custom validator
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("subdenom",),
                "msg": "Input should be a valid string",
            }
        ],
    )


def test_factory_asset_subdenom_too_short(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.subdenom field is too short."""
    factory_asset_data["subdenom"] = "ab"
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_short",
                "loc": ("subdenom",),
                "msg": "String should have at least 3 characters",
            }
        ],
    )


def test_factory_asset_subdenom_too_long(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.subdenom field is too long."""
    factory_asset_data["subdenom"] = "a" * 45
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_too_long",
                "loc": ("subdenom",),
                "msg": "String should have at most 44 characters",
            }
        ],
    )


@pytest.mark.parametrize(
    "subdenom",
    [
        "1token",  # starts with number
        "Token",  # uppercase
        "TOKEN",  # all uppercase
        "token!",  # invalid char
        "token token",  # space
        " token",  # leading space
    ],
)
def test_factory_asset_subdenom_bad_pattern(
    factory_asset_data: Dict[str, Any],
    subdenom: str,
) -> None:
    """Test FactoryAsset.subdenom field with invalid pattern."""
    factory_asset_data["subdenom"] = subdenom
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    # Field-level pattern validation runs before custom validator
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_pattern_mismatch",
                "loc": ("subdenom",),
                "msg": "String should match pattern '^[a-z][a-z0-9-]{2,43}$'",
            }
        ],
    )


# ----------------
# Negative tests for FactoryAsset.denom_units field
# ----------------


def test_factory_asset_denom_units_missing(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.denom_units field is missing."""
    del factory_asset_data["denom_units"]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

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


def test_factory_asset_denom_units_empty(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.denom_units field with empty list."""
    factory_asset_data["denom_units"] = []
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

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


def test_factory_asset_denom_units_bad_type_none(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.denom_units field with None value."""
    factory_asset_data["denom_units"] = None
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

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
    "bad_value,type_name",
    [
        (
            tuple(
                [
                    {
                        "denom": "coin.zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw.panda01",
                        "exponent": 0,
                    }
                ],
            ),
            "tuple",
        ),
        ({"panda"}, "set"),
    ],
)
def test_factory_asset_denom_units_bad_type_non_list(
    factory_asset_data: Dict[str, Any],
    bad_value: Any,
    type_name: str,
) -> None:
    """Test FactoryAsset.denom_units rejects non-list iterables (tuple, set); factory re-declares reject_non_list."""
    factory_asset_data["denom_units"] = bad_value
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("denom_units",),
                "msg": f"Value error, denom_units must be a list, not {type_name}",
            }
        ],
    )


def test_factory_asset_denom_units_duplicate_exponents(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.denom_units with duplicate exponents."""
    base = factory_asset_data["base_denom"]
    factory_asset_data["denom_units"] = [
        {"denom": base, "exponent": 0},
        {"denom": "tkn", "exponent": 0},
    ]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

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


def test_factory_asset_denom_units_missing_base_denom(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.denom_units without base denom at exponent 0 (wrong denom at exp 0)."""
    factory_asset_data["denom_units"] = [
        {"denom": "other", "exponent": 0},
        {"denom": "tkn", "exponent": 6},
    ]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": f"Value error, denom_units must contain an entry with exponent=0 and denom matching base_denom '{factory_asset_data['base_denom']}'",
            }
        ],
    )


def test_factory_asset_denom_units_no_exponent_zero(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.denom_units with no exponent 0 entry (only higher exponents)."""
    factory_asset_data["denom_units"] = [
        {"denom": "panda", "exponent": 6},
    ]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": f"Value error, denom_units must contain an entry with exponent=0 and denom matching base_denom '{factory_asset_data['base_denom']}'",
            }
        ],
    )


def test_factory_asset_denom_units_decimals_mismatch(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.denom_units with decimals not matching max exponent."""
    base = factory_asset_data["base_denom"]
    factory_asset_data["decimals"] = 5
    factory_asset_data["denom_units"] = [
        {"denom": base, "exponent": 0},
        {"denom": "tkn", "exponent": 6},
    ]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

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


def test_factory_asset_denom_units_negative_exponent(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.denom_units rejects DenomUnit with negative exponent (ge=0)."""
    base = factory_asset_data["base_denom"]
    factory_asset_data["denom_units"] = [
        {"denom": base, "exponent": 0},
        {"denom": "tkn", "exponent": -1},
    ]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "greater_than_equal",
                "loc": ("denom_units", 1, "exponent"),
                "msg": "Input should be greater than or equal to 0",
            }
        ],
    )


def test_factory_asset_denom_units_exponent_bool(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.denom_units rejects DenomUnit with exponent as bool (DenomUnit validator)."""
    base = factory_asset_data["base_denom"]
    factory_asset_data["denom_units"] = [
        {"denom": base, "exponent": 0},
        {"denom": "tkn", "exponent": True},
    ]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("denom_units", 1, "exponent"),
                "msg": "Value error, exponent cannot be bool, must be an integer",
            }
        ],
    )


def test_factory_asset_denom_units_invalid_denom(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.denom_units rejects DenomUnit with invalid denom (must start with letter)."""
    base = factory_asset_data["base_denom"]
    factory_asset_data["denom_units"] = [
        {"denom": base, "exponent": 0},
        {"denom": "1invalid", "exponent": 6},
    ]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": ("denom_units", 1, "denom"),
                "msg": "Value error, denom must start with a letter and use letters, numbers or '/:._-'",
            }
        ],
    )


# ----------------
# Negative tests for FactoryAsset.uri field
# ----------------


def test_factory_asset_uri_bad_type(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.uri field with invalid type."""
    factory_asset_data["uri"] = "not_a_url"
    factory_asset_data["uri_hash"] = (
        "a3f4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4"
    )
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "url_parsing",
                "loc": ("uri",),
                "msg": "Input should be a valid URL, relative URL without a base",
            }
        ],
    )


def test_factory_asset_uri_without_hash(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.uri without uri_hash (uri_hash=None)."""
    factory_asset_data["uri"] = "https://example.com/whitepaper.pdf"
    factory_asset_data["uri_hash"] = None
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": "Value error, uri_hash is required when uri is provided",
            }
        ],
    )


def test_factory_asset_uri_hash_missing_when_uri_provided(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset rejects when uri is set but uri_hash key is missing (defaults to None)."""
    factory_asset_data["uri"] = "https://example.com/whitepaper.pdf"
    del factory_asset_data["uri_hash"]
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": "Value error, uri_hash is required when uri is provided",
            }
        ],
    )


# ----------------
# Negative tests for FactoryAsset.uri_hash field
# ----------------


def test_factory_asset_uri_hash_bad_type_bool(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.uri_hash field with bool value."""
    factory_asset_data["uri_hash"] = True
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    # Field-level type validation runs before custom validator
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_type",
                "loc": ("uri_hash",),
                "msg": "Input should be a valid string",
            }
        ],
    )


@pytest.mark.parametrize(
    "uri_hash",
    [
        "a3f4d5e6",  # too short
        "a" * 65,  # too long
        "g" * 64,  # invalid hex char
        "A3F4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0F1A2B3C4!",  # invalid char
    ],
)
def test_factory_asset_uri_hash_bad_pattern(
    factory_asset_data: Dict[str, Any],
    uri_hash: str,
) -> None:
    """Test FactoryAsset.uri_hash field with invalid format."""
    factory_asset_data["uri_hash"] = uri_hash
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    # Pydantic Field pattern validation happens before custom validator
    # So we check for string_pattern_mismatch first
    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "string_pattern_mismatch",
                "loc": ("uri_hash",),
                "msg": "String should match pattern '^[a-fA-F0-9]{64}$'",
            }
        ],
    )


# ----------------
# Negative tests for FactoryAsset model validators
# ----------------


def test_factory_asset_asset_id_must_match_creator_and_subdenom(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.asset_id must derive from creator and subdenom."""
    wrong_asset_id = f"coin.{factory_asset_data['creator']}.other"
    factory_asset_data["asset_id"] = wrong_asset_id
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": f"Value error, asset_id must be '{factory_asset_data['base_denom']}' derived from creator and subdenom",
            }
        ],
    )


def test_factory_asset_base_denom_must_match_creator_and_subdenom(
    factory_asset_data: Dict[str, Any],
) -> None:
    """Test FactoryAsset.base_denom must derive from creator and subdenom."""
    creator_wrong = "zig1wrongaddressxxxxxxxxxxxxxxxxxxxxxxxxxx"
    factory_asset_data["creator"] = creator_wrong
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)

    check_model_error(
        errors=exc,
        expected_errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": f"Value error, base_denom must be 'coin.{creator_wrong}.{factory_asset_data['subdenom']}' derived from creator and subdenom",
            }
        ],
    )


######################################################################
# Bytes-rejection tests for factory-specific string fields
######################################################################

@pytest.mark.parametrize(
    "field,value",
    [
        ("base_denom", b"coin.zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw.panda01"),
        ("creator", b"zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw"),
        ("subdenom", b"panda01"),
        ("uri_hash", b"a3f4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4"),
    ],
)
def test_factory_asset_string_fields_bytes_rejected(
    factory_asset_data: Dict[str, Any],
    field: str,
    value: bytes,
) -> None:
    """Test that factory-specific string fields reject bytes input (strict bytes policy)."""
    factory_asset_data[field] = value
    with pytest.raises(ValidationError) as exc:
        FactoryAsset(**factory_asset_data)
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

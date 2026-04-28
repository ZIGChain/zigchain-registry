"""Tests for the generate_schemas script."""

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

import scripts.generate_schemas as gen
from scripts.generate_schemas import (
    generate_common_schema,
    generate_factory_schema,
    generate_ibc_schema,
    generate_native_schema,
    main,
)


######################################################################
# Fixtures
######################################################################


@pytest.fixture
def patched_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect repo_root to tmp_path so main() reads/writes to a temp directory.

    Does not create any subdirectories — each test controls whether schemas/ exists.
    monkeypatch handles teardown automatically so no explicit restore is needed.
    """
    monkeypatch.setattr(gen, "repo_root", tmp_path)
    return tmp_path


@pytest.fixture
def schemas_dir(patched_repo_root: Path) -> Path:
    """Create schemas/ under the patched repo_root, as main() expects.

    Chains onto patched_repo_root so the negative test can use patched_repo_root
    directly (no schemas/ created) while the positive test uses this fixture
    (schemas/ created automatically).
    """
    d = patched_repo_root / "schemas"
    d.mkdir()
    return d


@pytest.fixture
def minimal_common_data() -> dict[str, Any]:
    """Minimal required fields for a valid AssetBase (common schema) instance."""
    return {
        "network": "mainnet",
        "asset_id": "testasset",
        "type": "native",
        "symbol": "TEST",
        "name": "Test Asset",
        "decimals": 6,
        "display_denom": "TEST",
    }


@pytest.fixture
def minimal_native_data() -> dict[str, Any]:
    """Minimal required fields for a valid NativeAsset instance."""
    return {
        "network": "mainnet",
        "asset_id": "uzig",
        "type": "native",
        "symbol": "ZIG",
        "name": "ZIGChain",
        "decimals": 6,
        "display_denom": "ZIG",
        "base_denom": "uzig",
        "denom_units": [
            {"denom": "uzig", "exponent": 0},
            {"denom": "ZIG", "exponent": 6},
        ],
    }


@pytest.fixture
def minimal_factory_data() -> dict[str, Any]:
    """Minimal required fields for a valid FactoryAsset instance."""
    return {
        "network": "mainnet",
        "asset_id": "coin.zig1wze8mn5nsgl9qrgazq6a92fvh7m5e6psjcx2du.panda",
        "type": "factory",
        "symbol": "PANDA",
        "name": "Panda Token",
        "decimals": 0,
        "display_denom": "coin.zig1wze8mn5nsgl9qrgazq6a92fvh7m5e6psjcx2du.panda",
        "base_denom": "coin.zig1wze8mn5nsgl9qrgazq6a92fvh7m5e6psjcx2du.panda",
        "creator": "zig1wze8mn5nsgl9qrgazq6a92fvh7m5e6psjcx2du",
        "subdenom": "panda",
        "denom_units": [
            {"denom": "coin.zig1wze8mn5nsgl9qrgazq6a92fvh7m5e6psjcx2du.panda", "exponent": 0},
        ],
    }


@pytest.fixture
def minimal_ibc_data() -> dict[str, Any]:
    """Minimal required fields for a valid IBCAsset instance."""
    return {
        "network": "mainnet",
        "asset_id": "ibc/EF48E6B1A1A19F47ECAEA62F5670C37C0580E86A9E88498B7E393EB6F49F33C0",
        "type": "ibc",
        "symbol": "USDC",
        "name": "USD Coin",
        "decimals": 6,
        "display_denom": "USDC",
        "base_denom": "ibc/EF48E6B1A1A19F47ECAEA62F5670C37C0580E86A9E88498B7E393EB6F49F33C0",
        "hash": "EF48E6B1A1A19F47ECAEA62F5670C37C0580E86A9E88498B7E393EB6F49F33C0",
        "origin_chain": "noble",
        "origin_denom": "uusdc",
        "traces": [
            {
                "type": "ibc",
                "chain_name": "zigchain",
                "base_denom": "ibc/EF48E6B1A1A19F47ECAEA62F5670C37C0580E86A9E88498B7E393EB6F49F33C0",
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
# Tests for generate_common_schema
######################################################################


def test_generate_common_schema_returns_dict_with_correct_metadata() -> None:
    """generate_common_schema() injects $schema, title, and description into the AssetBase schema."""
    # Act: call the generator
    result = generate_common_schema()
    # Assert: return type and all three injected metadata keys with exact values
    assert isinstance(result, dict)
    assert result["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert result["title"] == "Common Asset Schema"
    assert result["description"] == "Base schema for all ZIGChain assets with common fields"



def test_generate_common_schema_contains_all_minimal_fields(
    minimal_common_data: dict[str, Any],
) -> None:
    """generate_common_schema() produces a schema whose properties and required array match AssetBase."""
    # Act: generate the schema
    result = generate_common_schema()
    properties = result["properties"]
    required = result.get("required", [])
    # Assert: every field in the minimal data appears in schema properties
    for field in minimal_common_data:
        assert field in properties
    # Assert: all minimal fields are required — none have defaults in AssetBase
    assert isinstance(required, list)
    for field in minimal_common_data:
        assert field in required
    # Assert: schema_ref ($schema alias) and other optional fields are not required
    assert "order" not in required
    assert "description" not in required
    assert "socials" not in required


######################################################################
# Tests for generate_native_schema
######################################################################


def test_generate_native_schema_returns_dict_with_correct_metadata() -> None:
    """generate_native_schema() injects $schema, title, and description into the NativeAsset schema."""
    # Act: call the generator
    result = generate_native_schema()
    # Assert: return type and all three injected metadata keys with exact values
    assert isinstance(result, dict)
    assert result["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert result["title"] == "Native Asset Schema"
    assert result["description"] == "Schema for native ZIGChain assets"



def test_generate_native_schema_contains_all_minimal_fields(
    minimal_native_data: dict[str, Any],
) -> None:
    """generate_native_schema() schema includes base_denom and denom_units as required; traces and type are not."""
    # Act: generate the schema
    result = generate_native_schema()
    properties = result["properties"]
    required = result.get("required", [])
    # Assert: every field in the minimal data appears in schema properties
    for field in minimal_native_data:
        assert field in properties
    # Assert: NativeAsset-specific required fields are in the required array
    assert isinstance(required, list)
    assert "base_denom" in required
    assert "denom_units" in required
    # Assert: traces is NOT required — Optional with default None in NativeAsset
    assert "traces" not in required
    # Assert: type is NOT required — has default "native" in NativeAsset
    assert "type" not in required


######################################################################
# Tests for generate_factory_schema
######################################################################


def test_generate_factory_schema_returns_dict_with_correct_metadata() -> None:
    """generate_factory_schema() injects $schema, title, and description into the FactoryAsset schema."""
    # Act: call the generator
    result = generate_factory_schema()
    # Assert: return type and all three injected metadata keys with exact values
    assert isinstance(result, dict)
    assert result["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert result["title"] == "Factory Asset Schema"
    assert result["description"] == "Schema for factory ZIGChain assets"



def test_generate_factory_schema_contains_all_minimal_fields(
    minimal_factory_data: dict[str, Any],
) -> None:
    """generate_factory_schema() schema includes creator, subdenom, base_denom, denom_units as required; uri and type are not."""
    # Act: generate the schema
    result = generate_factory_schema()
    properties = result["properties"]
    required = result.get("required", [])
    # Assert: every field in the minimal data appears in schema properties
    for field in minimal_factory_data:
        assert field in properties
    # Assert: FactoryAsset-specific required fields are in the required array
    assert isinstance(required, list)
    assert "base_denom" in required
    assert "creator" in required
    assert "subdenom" in required
    assert "denom_units" in required
    # Assert: optional fields are NOT in required
    assert "uri" not in required
    assert "uri_hash" not in required
    # Assert: type is NOT required — has default "factory" in FactoryAsset
    assert "type" not in required


######################################################################
# Tests for generate_ibc_schema
######################################################################


def test_generate_ibc_schema_returns_dict_with_correct_metadata() -> None:
    """generate_ibc_schema() injects $schema, title, and description into the IBCAsset schema."""
    # Act: call the generator
    result = generate_ibc_schema()
    # Assert: return type and all three injected metadata keys with exact values
    assert isinstance(result, dict)
    assert result["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert result["title"] == "IBC Asset Schema"
    assert result["description"] == "Schema for IBC ZIGChain assets"


def test_generate_ibc_schema_contains_all_minimal_fields(
    minimal_ibc_data: dict[str, Any],
) -> None:
    """generate_ibc_schema() schema includes hash, origin_chain, origin_denom, traces, channels as required; type is not."""
    # Act: generate the schema
    result = generate_ibc_schema()
    properties = result["properties"]
    required = result.get("required", [])
    # Assert: every field in the minimal data appears in schema properties
    for field in minimal_ibc_data:
        assert field in properties
    # Assert: IBCAsset-specific required fields are in the required array
    assert isinstance(required, list)
    assert "base_denom" in required
    assert "hash" in required
    assert "origin_chain" in required
    assert "origin_denom" in required
    assert "traces" in required
    assert "channels" in required
    # Assert: type is NOT required — has default "ibc" in IBCAsset
    assert "type" not in required


######################################################################
# Tests for main
######################################################################

# ----------------
# Positive test for main
# ----------------

def test_main_generates_all_four_schema_files_with_correct_content_and_output(
    schemas_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main() writes all four schema files with correct JSON content and emits all six progress messages."""
    # Arrange: repo_root patched and schemas/ exists (via fixtures); map filenames to expected titles
    expected_files = [
        ("asset.common.schema.json", "Common Asset Schema"),
        ("asset.native.schema.json", "Native Asset Schema"),
        ("asset.factory.schema.json", "Factory Asset Schema"),
        ("asset.ibc.schema.json", "IBC Asset Schema"),
    ]
    # Act: success path returns normally — no sys.exit(), so no pytest.raises needed
    main()
    # Assert: verify each file was created with valid JSON and correct metadata
    for filename, expected_title in expected_files:
        schema_path = schemas_dir / filename
        assert schema_path.exists()                                          # file written to disk
        parsed = json.loads(schema_path.read_text(encoding="utf-8"))        # valid JSON
        assert isinstance(parsed, dict)
        assert parsed["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert parsed["title"] == expected_title                             # title matches generator
    # Assert: capture stdout after the loop; `in` used because main() emits 6 separate print() calls
    out = capsys.readouterr().out
    assert "Generating JSON schemas from Pydantic models..." in out
    assert "✅ Generated asset.common.schema.json" in out
    assert "✅ Generated asset.native.schema.json" in out
    assert "✅ Generated asset.factory.schema.json" in out
    assert "✅ Generated asset.ibc.schema.json" in out
    assert "✅ All schemas generated successfully!" in out


# ----------------
# Negative test for main
# ----------------

def test_main_schemas_dir_missing_exits_one_with_error_message(
    patched_repo_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main() exits with code 1 and prints the missing schemas/ path when the directory does not exist."""
    # Arrange: repo_root is patched to tmp_path; schemas/ directory was NOT created
    expected_schemas_dir = patched_repo_root / "schemas"
    # Act: call main() — should detect missing schemas/ and exit immediately
    with pytest.raises(SystemExit) as exc:
        main()
    # Assert: exit code 1 and the exact single-line error message
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert out == f"Error: schemas directory not found: {expected_schemas_dir}\n"


def test_main_import_error_exits_one_with_error_messages(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Module-level ImportError prints both error messages and exits with code 1."""
    # Arrange: evict cached module so importlib re-executes module-level code;
    #          set models to None so `from models import ...` raises ImportError
    monkeypatch.delitem(sys.modules, "scripts.generate_schemas")
    monkeypatch.setitem(sys.modules, "models", None)
    # Act: reimport — module-level import of models fails, except branch fires
    with pytest.raises(SystemExit) as exc:
        importlib.import_module("scripts.generate_schemas")
    # Assert: exit code 1 and both error messages present in output
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Error: Failed to import models:" in out
    assert "Make sure you're running from the repository root and Pydantic is installed." in out




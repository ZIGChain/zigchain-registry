#!/usr/bin/env python3
"""
Generate JSON schemas from Pydantic models.

This script generates JSON schema files from Pydantic models and writes them
to the schemas/ directory, replacing existing schema files.
"""

import json
import sys
from pathlib import Path

# Add repository root to Python path
script_dir = Path(__file__).parent
repo_root = script_dir.parent
sys.path.insert(0, str(repo_root))

try:
    from models import AssetBase, NativeAsset, FactoryAsset, IBCAsset
except ImportError as e:
    print(f"Error: Failed to import models: {e}")
    print("Make sure you're running from the repository root and Pydantic is installed.")
    sys.exit(1)


def generate_common_schema() -> dict:
    """Generate the common asset schema from AssetBase model."""
    schema = AssetBase.model_json_schema(mode="serialization")
    
    # Add JSON Schema metadata
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    schema["title"] = "Common Asset Schema"
    schema["description"] = "Base schema for all ZIGChain assets with common fields"
    
    # Remove $defs and inline them if needed, or keep them for reference
    # For now, we'll keep the structure as Pydantic generates it
    return schema


def generate_native_schema() -> dict:
    """Generate the native asset schema from NativeAsset model."""
    # Get the complete schema (already includes all base properties via inheritance)
    schema = NativeAsset.model_json_schema(mode="serialization")
    
    # Add JSON Schema metadata
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    schema["title"] = "Native Asset Schema"
    schema["description"] = "Schema for native ZIGChain assets"
    
    return schema


def generate_factory_schema() -> dict:
    """Generate the native asset schema from NativeAsset model."""
    # Get the complete schema (already includes all base properties via inheritance)
    schema = FactoryAsset.model_json_schema(mode="serialization")
    
    # Add JSON Schema metadata
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    schema["title"] = "Factory Asset Schema"
    schema["description"] = "Schema for factory ZIGChain assets"
    
    return schema


def generate_ibc_schema() -> dict:
    """Generate the native asset schema from NativeAsset model."""
    # Get the complete schema (already includes all base properties via inheritance)
    schema = IBCAsset.model_json_schema(mode="serialization")
    
    # Add JSON Schema metadata
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    schema["title"] = "IBC Asset Schema"
    schema["description"] = "Schema for IBC ZIGChain assets"
    
    return schema


def main():
    """Generate all JSON schema files."""
    # Get repository root (already set above)
    schemas_dir = repo_root / "schemas"
    
    if not schemas_dir.exists():
        print(f"Error: schemas directory not found: {schemas_dir}")
        sys.exit(1)
    
    # Generate schemas
    print("Generating JSON schemas from Pydantic models...")
    
    schemas = {
        "asset.common.schema.json": generate_common_schema(),
        "asset.native.schema.json": generate_native_schema(),
        "asset.factory.schema.json": generate_factory_schema(),
        "asset.ibc.schema.json": generate_ibc_schema(),
    }
    
    # Write schemas to files
    for filename, schema in schemas.items():
        schema_path = schemas_dir / filename
        with open(schema_path, "w") as f:
            json.dump(schema, f, indent=2)
        print(f"✅ Generated {filename}")
    
    print("\n✅ All schemas generated successfully!")


if __name__ == "__main__":
    main()


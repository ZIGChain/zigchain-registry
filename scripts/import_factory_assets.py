#!/usr/bin/env python3
"""
Import factory assets from ZIGChain by querying all factory denoms.

This script queries the ZIGChain network for all factory denoms using
`zigchaind q factory list-denom` and automatically generates factory asset
JSON files in the assets/factory/ directory.

Usage:
    python scripts/import_factory_assets.py [--network mainnet|testnet] [--zigchaind-path PATH] [--overwrite]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add repository root to Python path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from models.factory import FactoryAsset  # noqa: E402
from models.native import DenomUnit  # noqa: E402
from scripts.config import get_rpc_endpoint  # noqa: E402

def load_existing_factory_assets(repo_root: Path) -> Dict[str, Dict[str, FactoryAsset]]:
    """
    Load existing factory assets from assets/factory/*.json.

    Returns:
      network -> asset_id -> FactoryAsset
    """
    assets_dir = repo_root / "assets" / "factory"
    out: Dict[str, Dict[str, FactoryAsset]] = {"mainnet": {}, "testnet": {}}
    if not assets_dir.exists():
        return out

    for file_path in sorted(assets_dir.glob("*.json")):
        if file_path.is_symlink():
            # Reject symlinks to block arbitrary file reads via PR-supplied
            # symlinks pointing outside assets/factory/.
            print(f"Warning: skipping symlink {file_path}", file=sys.stderr)
            continue
        if not file_path.is_file():
            continue
        try:
            with file_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            payload.pop("$schema", None)
            asset = FactoryAsset.model_validate(payload)
            out.setdefault(asset.network, {})[asset.asset_id] = asset
        except Exception as e:
            print(f"Warning: failed to load existing factory asset {file_path}: {e}", file=sys.stderr)
            continue

    return out


def detect_collisions(factory_assets_by_network: Dict[str, Dict[str, FactoryAsset]]) -> Dict[str, Dict[str, List[FactoryAsset]]]:
    """
    Detect display_denom collisions (case-insensitive) per network.

    Returns:
      network -> normalized_display_key -> [FactoryAsset, ...] (only keys with collisions, i.e. len >= 2)
    """
    out: Dict[str, Dict[str, List[FactoryAsset]]] = {}
    for network, by_id in factory_assets_by_network.items():
        groups: Dict[str, List[FactoryAsset]] = {}
        for a in by_id.values():
            key = (a.display_denom or "").strip().lower()
            if not key:
                continue
            groups.setdefault(key, []).append(a)
        out[network] = {k: v for k, v in groups.items() if len(v) >= 2}
    return out


def normalize_display_denom(
    *,
    asset: FactoryAsset,
    collision_group: Optional[List[FactoryAsset]],
) -> tuple[str, List[DenomUnit]]:
    """
    Apply display normalization rules for factory assets.

    Returns:
      (normalized_display_denom, normalized_denom_units_as_dicts)
    """
    is_verified = getattr(asset, "is_verified", False) is True
    colliding = collision_group is not None and len(collision_group) >= 2

    verified_in_group = [a for a in (collision_group or []) if getattr(a, "is_verified", False) is True]
    one_verified_in_group = colliding and len(verified_in_group) == 1

    # Scenario A: No collision + unverified => full base denom
    # Scenario B: Collision + one verified => verified keeps display_denom, unverified uses base_denom
    # Scenario C: Collision + all unverified => all use base_denom
    if not colliding:
        display_out = asset.display_denom if is_verified else asset.base_denom
    elif one_verified_in_group:
        display_out = asset.display_denom if is_verified else asset.base_denom
    else:
        display_out = asset.base_denom

    # Factory assets: keep denom_units minimal (only base denom at exponent 0).
    denom_units_out = [
        DenomUnit(denom=asset.base_denom, exponent=0),
    ]

    return display_out, denom_units_out

def detect_network() -> str:
    """Detect network from environment variables or default to mainnet."""
    chain_id = os.environ.get("ZIGCHAIN_CHAIN_ID", "").strip()
    
    if chain_id == "zig-test-2":
        return "testnet"
    elif chain_id == "zigchain-1":
        return "mainnet"
    
    # Default to mainnet if not detected
    return "mainnet"


def run_zigchaind_query(
    zigchaind_path: str,
    network: str,
    page_key: Optional[str] = None,
) -> Dict:
    """Execute zigchaind query and return parsed JSON."""
    node = get_rpc_endpoint(network)
    
    cmd = [
        zigchaind_path,
        "q",
        "factory",
        "list-denom",
        "--output",
        "json",
        "--node",
        node,
    ]
    
    if page_key:
        cmd.extend(["--page-key", page_key])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error executing zigchaind command: {e}", file=sys.stderr)
        print(f"Command: {' '.join(cmd)}", file=sys.stderr)
        if e.stderr:
            print(f"Error output: {e.stderr}", file=sys.stderr)
        raise
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}", file=sys.stderr)
        print(f"Output: {result.stdout if 'result' in locals() else 'N/A'}", file=sys.stderr)
        raise


def fetch_all_denoms(zigchaind_path: str, network: str) -> List[Dict]:
    """Fetch all factory denoms with pagination support."""
    all_denoms = []
    page_key = None
    
    print(f"Fetching factory denoms from {network}...")
    
    while True:
        try:
            response = run_zigchaind_query(zigchaind_path, network, page_key)
            
            # Extract denoms from response
            denoms = response.get("denom", [])
            if not denoms:
                break
            
            all_denoms.extend(denoms)
            print(f"  Fetched {len(denoms)} denoms (total: {len(all_denoms)})")
            
            # Check for next page
            pagination = response.get("pagination", {})
            next_key = pagination.get("next_key")
            
            if not next_key:
                break
            
            # next_key is already base64-encoded in the response
            page_key = next_key
            
        except Exception as e:
            print(f"Error fetching denoms: {e}", file=sys.stderr)
            raise
    
    print(f"✅ Total denoms fetched: {len(all_denoms)}")
    return all_denoms


def parse_denom(denom: str) -> tuple[str, str]:
    """
    Parse denom string to extract creator and subdenom.
    
    Format: coin.{creator}.{subdenom}
    Returns: (creator, subdenom)
    """
    # Pattern: coin.{creator}.{subdenom}
    # Creator is a bech32 address (zig1 followed by alphanumeric)
    # Subdenom can contain lowercase letters, numbers, and hyphens
    pattern = r"^coin\.(zig1[a-z0-9]+)\.([a-z0-9-]+)$"
    match = re.match(pattern, denom)
    
    if not match:
        raise ValueError(f"Invalid denom format: {denom}. Expected format: coin.{{creator}}.{{subdenom}}")
    
    creator = match.group(1)
    subdenom = match.group(2)
    
    return creator, subdenom


def derive_metadata_from_subdenom(subdenom: str) -> Dict[str, str]:
    """Derive symbol, name, and display_denom from subdenom."""
    # Symbol: uppercase
    symbol = subdenom.upper()
    
    # Name: capitalized (first letter uppercase, rest lowercase)
    name = subdenom.capitalize()
    
    # Display denom: uppercase
    display_denom = subdenom.upper()
    
    return {
        "symbol": symbol,
        "name": name,
        "display_denom": display_denom,
    }


def create_factory_asset(
    denom_data: Dict,
    network: str,
) -> FactoryAsset:
    """Create a FactoryAsset from denom data."""
    denom_str = denom_data.get("denom", "")
    creator_addr = denom_data.get("creator", "")
    
    # Parse denom to extract creator and subdenom
    parsed_creator, subdenom = parse_denom(denom_str)
    
    # Verify parsed creator matches the creator from data
    if creator_addr and parsed_creator != creator_addr:
        print(f"Warning: Creator mismatch for {denom_str}: parsed={parsed_creator}, data={creator_addr}", file=sys.stderr)
    
    # Use creator from data if available, otherwise use parsed
    creator = creator_addr if creator_addr else parsed_creator
    
    # Factory denom format on ZIGChain: coin.{creator}.{subdenom}
    base_denom = f"coin.{creator}.{subdenom}"
    asset_id = base_denom
    
    # Derive metadata from subdenom
    metadata = derive_metadata_from_subdenom(subdenom)
    
    # Default decimals to 6
    decimals = 6
    
    # Create denom_units (factory assets keep this minimal; base denom is the authoritative unit)
    denom_units = [DenomUnit(denom=base_denom, exponent=0)]
    
    # Create asset data
    asset_data = {
        "network": network,
        "asset_id": asset_id,
        "type": "factory",
        "symbol": metadata["symbol"],
        "name": metadata["name"],
        "description": None,
        "decimals": decimals,
        "display_denom": metadata["display_denom"],
        "base_denom": base_denom,
        "creator": creator,
        "subdenom": subdenom,
        "denom_units": denom_units,
    }
    
    # Validate using Pydantic model
    return FactoryAsset.model_validate(asset_data)


def write_asset_file(asset: FactoryAsset, output_path: Path, overwrite: bool = False) -> bool:
    """Write asset to JSON file."""
    if output_path.exists() and not overwrite:
        return False
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Prepare JSON data
    # Use JSON mode so HttpUrl (and other JSON types) are converted to plain strings.
    asset_dict = asset.model_dump(mode="json", exclude_none=True)
    # Keep schema references consistent across assets/* (relative to assets/factory/)
    asset_dict["$schema"] = "../../schemas/asset.factory.schema.json"
    
    # Write file
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(asset_dict, f, indent=2, ensure_ascii=False)
        f.write("\n")
    
    return True


def import_factory_assets(
    zigchaind_path: str,
    network: str,
    repo_root: Path,
    overwrite: bool = False,
) -> tuple[int, int]:
    """Import all factory assets from chain."""
    existing_by_network = load_existing_factory_assets(repo_root)
    collisions = detect_collisions(existing_by_network)

    # Fetch all denoms
    denoms = fetch_all_denoms(zigchaind_path, network)
    
    if not denoms:
        print("No factory denoms found.")
        return 0, 0
    
    # Process each denom
    assets_dir = repo_root / "assets" / "factory"
    created_count = 0
    skipped_count = 0
    error_count = 0
    
    print(f"\nProcessing {len(denoms)} denoms...")

    # NOTE: collisions should include newly normalized assets too; we refresh collision groups
    # incrementally as we process denoms to keep behavior stable across a single run.
    warned_unresolved: set[str] = set()
    
    for denom_data in denoms:
        try:
            denom_str = denom_data.get("denom", "")
            parse_denom(denom_str)
            
            # Create asset
            asset = create_factory_asset(denom_data, network)

            # Preserve existing metadata when present (especially is_verified)
            existing = existing_by_network.get(network, {}).get(asset.asset_id)
            if existing is not None:
                asset = asset.model_copy(
                    update={
                        "is_verified": existing.is_verified,
                        "description": existing.description,
                        "extended_description": getattr(existing, "extended_description", None),
                        "keywords": getattr(existing, "keywords", None),
                        "socials": getattr(existing, "socials", None),
                        "logo_uris": getattr(existing, "logo_uris", None),
                        "images": getattr(existing, "images", None),
                        "coingecko_id": getattr(existing, "coingecko_id", None),
                        "order": getattr(existing, "order", None),
                        "website": getattr(existing, "website", None),
                        "twitter": getattr(existing, "twitter", None),
                        "uri": getattr(existing, "uri", None),
                        "uri_hash": getattr(existing, "uri_hash", None),
                    }
                )

            # Apply display normalization against current collision groups
            raw_display = asset.display_denom
            collision_key = (raw_display or "").strip().lower()
            group = collisions.get(network, {}).get(collision_key)
            normalized_display, normalized_units = normalize_display_denom(asset=asset, collision_group=group)
            asset = asset.model_copy(update={"display_denom": normalized_display, "denom_units": normalized_units})

            # Update collision groups with the normalized asset for subsequent iterations
            existing_by_network.setdefault(network, {})[asset.asset_id] = asset
            collisions = detect_collisions(existing_by_network)

            # Scenario C warning: collisions with no verified asset (de-duped per collision key)
            if group and not any(getattr(a, "is_verified", False) is True for a in group):
                if collision_key and collision_key not in warned_unresolved:
                    warned_unresolved.add(collision_key)
                    sample_ids = sorted({a.asset_id for a in group})
                    print(
                        f"Warning: unresolved display_denom collision for '{raw_display}' "
                        f"({len(sample_ids)} assets). Maintainer should verify one authoritative asset. "
                        f"asset_ids: {', '.join(sample_ids)}",
                        file=sys.stderr,
                    )
            
            # Determine output path
            # Use full denom in filename to avoid subdenom collisions across creators
            output_path = assets_dir / f"{asset.asset_id}.{asset.network}.json"
            
            # Write file
            if write_asset_file(asset, output_path, overwrite):
                created_count += 1
                print(f"  ✅ Created: {output_path.name}")
            else:
                skipped_count += 1
                print(f"  ⏭️  Skipped (exists): {output_path.name}")
                
        except Exception as e:
            error_count += 1
            denom_str = denom_data.get("denom", "unknown")
            print(f"  ❌ Error processing {denom_str}: {e}", file=sys.stderr)
            continue
    
    print(f"\n✅ Import complete:")
    print(f"   Created: {created_count}")
    print(f"   Skipped: {skipped_count}")
    if error_count > 0:
        print(f"   Errors: {error_count}")
    
    return created_count, skipped_count


def check_zigchaind(zigchaind_path: str) -> bool:
    """Check if zigchaind command is available."""
    try:
        result = subprocess.run(
            [zigchaind_path, "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Import factory assets from ZIGChain",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import from mainnet (default)
  python scripts/import_factory_assets.py

  # Import from testnet
  python scripts/import_factory_assets.py --network testnet

  # Overwrite existing files
  python scripts/import_factory_assets.py --overwrite

  # Use custom zigchaind path
  python scripts/import_factory_assets.py --zigchaind-path /usr/local/bin/zigchaind
        """,
    )
    
    parser.add_argument(
        "--network",
        type=str,
        choices=["mainnet", "testnet"],
        default=None,
        help="Network to query (mainnet or testnet). Defaults to auto-detect from environment or mainnet.",
    )
    
    parser.add_argument(
        "--zigchaind-path",
        type=str,
        default="zigchaind",
        help="Path to zigchaind binary (default: 'zigchaind' in PATH)",
    )
    
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing asset files (default: skip existing files)",
    )
    
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help=f"Repository root directory (default: {REPO_ROOT})",
    )
    
    args = parser.parse_args()
    
    # Determine network
    network = args.network or detect_network()
    print(f"Using network: {network}")
    
    # Check zigchaind availability
    if not check_zigchaind(args.zigchaind_path):
        print(f"Error: zigchaind not found at '{args.zigchaind_path}'", file=sys.stderr)
        print("Make sure zigchaind is installed and in your PATH, or specify --zigchaind-path", file=sys.stderr)
        sys.exit(1)
    
    # Import assets
    try:
        created, skipped = import_factory_assets(
            args.zigchaind_path,
            network,
            args.repo_root,
            args.overwrite,
        )
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nFatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


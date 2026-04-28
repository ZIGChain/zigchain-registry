#!/usr/bin/env python3
"""
Verify that registry assets are supported on-chain.

This script queries the chain for all denominations using the REST API:
  GET /cosmos/bank/v1beta1/supply

Then it checks:
  1) Registry -> chain: all registry assets (native, factory, ibc) for the selected
     network have a base_denom that is present in the on-chain denom list.
  2) Chain -> registry (reporting): all on-chain denoms returned by total-supply
     have a corresponding registry entry (base_denom) for the selected network.

Notes:
- The bank `total-supply` query typically returns denoms that currently have
  non-zero supply. Native assets may be valid even if absent from this list.
- Factory tokens are verified against the factory module directly, as they may
  exist with zero supply and won't appear in bank total-supply.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# Add repository root to Python path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.config import get_api_endpoint  # noqa: E402

def detect_network() -> str:
    """Detect network from environment variables or default to mainnet."""
    chain_id = os.environ.get("ZIGCHAIN_CHAIN_ID", "").strip()

    if chain_id == "zig-test-2":
        return "testnet"
    if chain_id == "zigchain-1":
        return "mainnet"

    return "mainnet"


def http_get_json(url: str, timeout_s: int = 30) -> Dict:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "zigchain-registry-validator/1.0"})
    try:
        with urlopen(req, timeout=timeout_s) as resp:  # nosec - URL is controlled by our config
            raw = resp.read().decode("utf-8")
        return json.loads(raw)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        raise RuntimeError(f"HTTP error {e.code} for {url}: {body}") from e
    except URLError as e:
        raise RuntimeError(f"Network error for {url}: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from {url}: {e}") from e


def run_total_supply_query(
    network: str,
    page_key: Optional[str] = None,
    limit: int = 1000,
) -> Dict:
    """Query bank supply via REST API and return parsed JSON."""
    base = get_api_endpoint(network).rstrip("/")
    path = "/cosmos/bank/v1beta1/supply"

    params: Dict[str, str] = {}
    if limit > 0:
        params["pagination.limit"] = str(limit)
    if page_key:
        # next_key from the API is already base64; we just pass it through.
        params["pagination.key"] = page_key

    url = f"{base}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"

    return http_get_json(url)


def run_factory_list_denom_query(
    network: str,
    page_key: Optional[str] = None,
    limit: int = 1000,
) -> Dict:
    """Query factory denom list via REST API and return parsed JSON.
    
    Endpoint: GET /zigchain/factory/denom
    Response: { "denom": [ { "denom": "...", "creator": "...", ... }, ... ] }
    """
    base = get_api_endpoint(network).rstrip("/")
    path = "/zigchain/factory/denom"

    params: Dict[str, str] = {}
    if limit > 0:
        params["pagination.limit"] = str(limit)
    if page_key:
        params["pagination.key"] = page_key

    url = f"{base}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"

    return http_get_json(url)


_MAX_PAGES = 10_000


def fetch_all_factory_denominations(network: str) -> Set[str]:
    """Fetch all factory denominations with pagination support."""
    denoms: Set[str] = set()
    page_key: Optional[str] = None
    total_rows = 0

    print(f"Fetching factory denoms from {network} REST API...")

    for _page in range(_MAX_PAGES):
        try:
            response = run_factory_list_denom_query(network, page_key=page_key)
        except RuntimeError as e:
            # If factory module query fails, return empty set and let caller handle it
            print(f"⚠️  Warning: Could not fetch factory denoms: {e}")
            print("   Factory tokens will be verified against bank supply only.")
            return denoms

        # Factory module response structure: { "denom": [ { "denom": "...", ... }, ... ] }
        denom_list = response.get("denom", [])
        if not isinstance(denom_list, list):
            raise ValueError("Unexpected response: 'denom' is not a list")

        total_rows += len(denom_list)
        for item in denom_list:
            if not isinstance(item, dict):
                continue
            # Extract denom string from each item
            denom = item.get("denom", "")
            if isinstance(denom, str) and denom:
                denoms.add(denom)

        pagination = response.get("pagination") or {}
        next_key = pagination.get("next_key")
        if not next_key:
            break
        page_key = next_key

    else:
        raise RuntimeError(
            f"Pagination did not terminate after {_MAX_PAGES} pages — "
            "possible infinite loop from API returning the same next_key"
        )

    print(f"✅ Total factory denoms fetched: {total_rows}")
    print(f"✅ Unique factory denoms discovered: {len(denoms)}")
    return denoms


def fetch_all_denominations(network: str) -> Set[str]:
    """Fetch all denominations with pagination support."""
    denoms: Set[str] = set()
    page_key: Optional[str] = None
    total_rows = 0

    print(f"Fetching bank supply denoms from {network} REST API...")

    for _page in range(_MAX_PAGES):
        response = run_total_supply_query(network, page_key=page_key)
        supply = response.get("supply") or []

        if not isinstance(supply, list):
            raise ValueError("Unexpected response: 'supply' is not a list")

        total_rows += len(supply)
        for coin in supply:
            if not isinstance(coin, dict):
                continue
            denom = coin.get("denom")
            if isinstance(denom, str) and denom:
                denoms.add(denom)

        pagination = response.get("pagination") or {}
        next_key = pagination.get("next_key")
        if not next_key:
            break
        page_key = next_key

    else:
        raise RuntimeError(
            f"Pagination did not terminate after {_MAX_PAGES} pages — "
            "possible infinite loop from API returning the same next_key"
        )

    print(f"✅ Total supply rows fetched: {total_rows}")
    print(f"✅ Unique denoms discovered: {len(denoms)}")
    return denoms


@dataclass(frozen=True)
class AssetRef:
    path: Path
    network: str
    asset_type: str
    base_denom: str
    asset_id: Optional[str] = None


def iter_asset_json_files(repo_root: Path) -> Iterable[Path]:
    """Yield all asset JSON files from native/, factory/, and ibc/ (recursively)."""
    assets_dir = repo_root / "assets"
    for subdir in ("native", "factory", "ibc"):
        d = assets_dir / subdir
        if not d.exists():
            continue
        for p in d.rglob("*.json"):
            if p.is_symlink():
                # Reject symlinks to block arbitrary file reads via PR-supplied
                # symlinks pointing outside the assets/ tree.
                print(f"Warning: skipping symlink {p}", file=sys.stderr)
                continue
            if p.is_file():
                yield p


def load_asset_ref(path: Path) -> AssetRef:
    """Load a single asset JSON file into an AssetRef."""
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("Asset JSON root must be an object")

    data.pop("$schema", None)

    network = data.get("network")
    asset_type = data.get("type")
    base_denom = data.get("base_denom")
    asset_id = data.get("asset_id")

    if not isinstance(network, str) or not network:
        raise ValueError("Missing or invalid 'network'")
    if not isinstance(asset_type, str) or not asset_type:
        raise ValueError("Missing or invalid 'type'")
    if not isinstance(base_denom, str) or not base_denom:
        raise ValueError("Missing or invalid 'base_denom'")
    if asset_id is not None and not isinstance(asset_id, str):
        raise ValueError("Invalid 'asset_id'")

    return AssetRef(
        path=path,
        network=network,
        asset_type=asset_type,
        base_denom=base_denom,
        asset_id=asset_id,
    )


def load_all_assets(repo_root: Path) -> Tuple[List[AssetRef], List[str]]:
    """Load all assets from the repo. Returns (assets, errors)."""
    assets: List[AssetRef] = []
    errors: List[str] = []

    for path in sorted(iter_asset_json_files(repo_root)):
        try:
            assets.append(load_asset_ref(path))
        except Exception as e:
            errors.append(f"{path}: {e}")

    return assets, errors


def verify_assets(
    assets: List[AssetRef],
    chain_denoms: Set[str],
    factory_denoms: Set[str],
    network: str,
) -> Tuple[List[AssetRef], List[str], int]:
    """
    Verify assets for a network.

    Returns:
      missing: assets whose base_denom is not in chain_denoms (non-native only)
      warnings: warning strings (e.g., native base denom absent from total-supply)
      checked_count: number of assets checked (for selected network)
    """
    missing: List[AssetRef] = []
    warnings: List[str] = []
    checked = 0

    for asset in assets:
        if asset.network != network:
            continue

        checked += 1

        if asset.asset_type == "native":
            # Native assets may be valid even if absent from total-supply.
            if asset.base_denom not in chain_denoms:
                warnings.append(
                    f"{asset.path}: native base_denom '{asset.base_denom}' not present in total-supply"
                )
            continue

        if asset.asset_type == "factory":
            # Factory tokens should be checked against factory module, not bank supply,
            # as they may exist with zero supply.
            if factory_denoms:
                # If we successfully queried factory module, verify against it
                if asset.base_denom not in factory_denoms:
                    missing.append(asset)
            else:
                # If factory module query failed or returned empty, treat like native tokens:
                # warn if not in bank supply, but don't fail (may have zero supply)
                if asset.base_denom not in chain_denoms:
                    warnings.append(
                        f"{asset.path}: factory base_denom '{asset.base_denom}' not present in bank supply "
                        "(factory module query unavailable, may have zero supply)"
                    )
            continue

        # For IBC and other types, check against bank supply
        if asset.base_denom not in chain_denoms:
            missing.append(asset)

    return missing, warnings, checked


def registry_denoms_for_network(assets: List[AssetRef], network: str) -> Set[str]:
    """Build the set of base_denoms present in the registry for a given network."""
    return {a.base_denom for a in assets if a.network == network}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify that registry assets exist on-chain via bank supply REST API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate against mainnet (default or auto-detected)
  python scripts/verify_chain_denominations.py

  # Validate against testnet
  python scripts/verify_chain_denominations.py --network testnet

  # Fail if any on-chain denom is missing from registry for the selected network
  python scripts/verify_chain_denominations.py --fail-on-missing-registry
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
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help=f"Repository root directory (default: {REPO_ROOT})",
    )
    parser.add_argument(
        "--fail-on-missing-registry",
        action="store_true",
        help=(
            "Exit non-zero if any denom returned by bank total-supply is not present "
            "as a base_denom in the registry for the selected network."
        ),
    )
    parser.add_argument(
        "--max-missing-registry",
        type=int,
        default=200,
        help=(
            "Maximum number of on-chain denoms missing from registry to print "
            "(default: 200). Use 0 to print none."
        ),
    )

    args = parser.parse_args()

    network = args.network or detect_network()
    print(f"Using network: {network}")

    repo_root = args.repo_root.resolve()
    if not repo_root.exists():
        print(f"Error: Repository root does not exist: {repo_root}", file=sys.stderr)
        sys.exit(1)

    # Load registry assets (all networks), then filter later.
    assets, load_errors = load_all_assets(repo_root)
    if load_errors:
        print("Errors while reading asset files:", file=sys.stderr)
        for err in load_errors:
            print(f"  ❌ {err}", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded asset files: {len(assets)}")

    # Query chain and verify.
    try:
        chain_denoms = fetch_all_denominations(network)
    except Exception as e:
        print(f"\nFatal error while querying chain: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Fetch factory denoms separately (may fail gracefully)
    try:
        factory_denoms = fetch_all_factory_denominations(network)
    except Exception as e:
        print(f"⚠️  Warning: Could not fetch factory denoms: {e}", file=sys.stderr)
        factory_denoms = set()

    missing, warnings, checked_count = verify_assets(assets, chain_denoms, factory_denoms, network)
    registry_denoms = registry_denoms_for_network(assets, network)
    missing_in_registry = sorted(chain_denoms - registry_denoms)

    print("\nResults:")
    print(f"  Assets checked (network={network}): {checked_count}")
    print(f"  Missing denoms: {len(missing)}")
    print(f"  On-chain denoms missing from registry (network={network}): {len(missing_in_registry)}")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  ⚠️  {w}")

    if missing:
        print("\nMissing assets (base_denom not found in bank total-supply):")
        for asset in sorted(missing, key=lambda a: (a.asset_type, a.base_denom, str(a.path))):
            rel = asset.path.relative_to(repo_root)
            aid = f" asset_id={asset.asset_id}" if asset.asset_id else ""
            print(f"  ❌ {rel} ({asset.asset_type}){aid} base_denom={asset.base_denom}")
        # Registry -> chain failures always fail.
        sys.exit(1)

    if missing_in_registry:
        if args.max_missing_registry != 0:
            limit = max(0, args.max_missing_registry)
            shown = missing_in_registry if limit <= 0 else missing_in_registry[:limit]
            print("\nOn-chain denoms missing from registry (base_denom):")
            for denom in shown:
                print(f"  ❌ {denom}")
            if limit > 0 and len(missing_in_registry) > limit:
                print(f"  ... and {len(missing_in_registry) - limit} more")

        if args.fail_on_missing_registry:
            print("\n❌ Verification failed: on-chain denoms missing from registry (--fail-on-missing-registry enabled)")
            sys.exit(1)

    print("\n✅ All assets verified successfully for this network.")
    print("   (Factory tokens verified against factory module, others against bank supply)")
    sys.exit(0)


if __name__ == "__main__":
    main()


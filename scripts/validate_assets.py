#!/usr/bin/env python3
"""
Validation script for ZIGChain assets registry.

Validates all asset files against their corresponding Pydantic models and performs
cross-file integrity checks. Includes protected external asset verification to prevent
factory tokens from impersonating canonical assets (e.g., USDC, USDT, ATOM).
"""

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add repository root to Python path
script_dir = Path(__file__).parent
repo_root = script_dir.parent
sys.path.insert(0, str(repo_root))

try:
    from pydantic import ValidationError
    from models import NativeAsset, FactoryAsset, IBCAsset, EvmChain
except ImportError as e:
    print(f"Error: Failed to import required modules: {e}")
    print("Make sure Pydantic is installed: pip install pydantic")
    sys.exit(1)

PROTECTED_ASSETS_FILENAME = "protected_assets.json"


@dataclass
class ProtectedAssetEntry:
    """Single protected asset definition from config."""

    symbol: str
    name: str
    allowed_types: List[str]
    expected_origin_chains: List[str]
    similar_patterns: List[str]
    description: str


@dataclass
class ProtectedAssetConfig:
    """Loaded and validated protected assets configuration with O(1) lookup structures."""

    assets: List[ProtectedAssetEntry]
    case_sensitive: bool
    enforce_on_testnet: bool
    warn_on_similar: bool
    # O(1) lookups: symbol/name (normalized) -> protected asset
    symbols: Dict[str, ProtectedAssetEntry] = field(default_factory=dict)
    names: Dict[str, ProtectedAssetEntry] = field(default_factory=dict)
    # Compiled regex for similar patterns: (pattern, protected_asset)
    similar_patterns: List[Tuple[re.Pattern, ProtectedAssetEntry]] = field(default_factory=list)


class AssetValidator:
    def __init__(
        self,
        repo_root: Path,
        network_filter: str = None,
        warn_only: bool = False,
    ):
        self.repo_root = Path(repo_root)
        self.assets_dir = self.repo_root / "assets"
        self.network_filter = network_filter
        self.warn_only = warn_only
        self.errors: List[str] = []
        self.warnings: List[str] = []
        
        # Track assets for integrity checks
        self.asset_ids: Dict[str, Dict[str, str]] = {}  # network -> asset_id -> file_path
        self.base_denoms: Dict[str, Dict[str, str]] = {}  # network -> base_denom -> file_path

        # Protected asset verification stats
        self.protection_checked: int = 0
        self.protection_violations: int = 0
        self.protection_warnings: int = 0

        # Loaded protected config (set in validate_all)
        self._protected_config: Optional[ProtectedAssetConfig] = None

    def _get_model_for_type(self, asset_type: str):
        """Get the appropriate Pydantic model for an asset type."""
        model_map = {
            "native": NativeAsset,
            "factory": FactoryAsset,
            "ibc": IBCAsset,
        }
        return model_map.get(asset_type)

    def _load_protected_config(self) -> bool:
        """
        Load and validate protected_assets.json. Returns False if config is missing or invalid
        (fail-safe). Populates self._protected_config on success.
        """
        config_path = self.repo_root / "config" / PROTECTED_ASSETS_FILENAME
        if not config_path.exists():
            self.errors.append(
                f"Invalid or empty protected_assets.json: config file not found at {config_path}"
            )
            return False

        try:
            with open(config_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid or empty protected_assets.json: invalid JSON: {e}")
            return False

        if not data or not isinstance(data, dict):
            self.errors.append("Invalid or empty protected_assets.json")
            return False

        assets_raw = data.get("assets")
        config_raw = data.get("config", {})

        if not assets_raw or not isinstance(assets_raw, list):
            self.errors.append("Invalid or empty protected_assets.json: 'assets' must be a non-empty array")
            return False

        assets: List[ProtectedAssetEntry] = []
        symbols: Dict[str, ProtectedAssetEntry] = {}
        names: Dict[str, ProtectedAssetEntry] = {}
        similar_patterns: List[Tuple[re.Pattern, ProtectedAssetEntry]] = []

        case_sensitive = config_raw.get("case_sensitive", False)
        enforce_on_testnet = config_raw.get("enforce_on_testnet", False)
        warn_on_similar = config_raw.get("warn_on_similar", True)

        for item in assets_raw:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol")
            name = item.get("name")
            if not symbol or not name:
                continue

            allowed_types = item.get("allowed_types", [])
            expected_origin_chains = item.get("expected_origin_chains", [])
            similar_raw = item.get("similar_patterns", [])
            description = item.get("description", "")

            if not isinstance(allowed_types, list):
                allowed_types = []
            if not isinstance(expected_origin_chains, list):
                expected_origin_chains = []
            if not isinstance(similar_raw, list):
                similar_raw = []

            entry = ProtectedAssetEntry(
                symbol=symbol,
                name=name,
                allowed_types=allowed_types,
                expected_origin_chains=[str(c).lower() for c in expected_origin_chains],
                similar_patterns=similar_raw,
                description=description,
            )
            assets.append(entry)

            # Normalize for lookup — shares _normalize() with the match path so that
            # NFKC collapses Unicode confusables (e.g. Cyrillic "UЅDC") on both sides.
            sym_key = self._normalize(symbol, case_sensitive)
            name_key = self._normalize(name, case_sensitive)
            symbols[sym_key] = entry
            names[name_key] = entry

            # Compile similar patterns — honour case_sensitive config. Before this change the
            # similar_patterns path silently stayed case-sensitive even when case_sensitive=False,
            # which contradicted the docs; pair with the sym_norm match at line 267.
            pattern_flags = 0 if case_sensitive else re.IGNORECASE
            for pat_str in similar_raw:
                if not isinstance(pat_str, str):
                    continue
                try:
                    compiled = re.compile(pat_str, pattern_flags)
                    similar_patterns.append((compiled, entry))
                except re.error:
                    # Invalid regex: log warning, skip pattern (spec Section 6)
                    self.warnings.append(
                        f"Invalid regex in protected_assets.json similar_patterns: '{pat_str}' — skipped"
                    )

        if not assets:
            self.errors.append("Invalid or empty protected_assets.json: no valid assets defined")
            return False

        self._protected_config = ProtectedAssetConfig(
            assets=assets,
            case_sensitive=case_sensitive,
            enforce_on_testnet=enforce_on_testnet,
            warn_on_similar=warn_on_similar,
            symbols=symbols,
            names=names,
            similar_patterns=similar_patterns,
        )
        return True

    def _normalize(self, value: str, case_sensitive: bool) -> str:
        """Normalize value for comparison: NFKC then casefold (unless case_sensitive).

        NFKC collapses Unicode confusables (e.g. full-width `ＵＳＤＣ`, Cyrillic-S
        `UЅDC`, compatibility ligatures) to their canonical ASCII form before
        comparison, so `similar_patterns` regexes written in plain ASCII still
        catch spoofing attempts. `casefold()` is equivalent to `.lower()` for ASCII.
        """
        if not isinstance(value, str):
            return value
        normalized = unicodedata.normalize("NFKC", value)
        return normalized if case_sensitive else normalized.casefold()

    def _validate_protected_assets(self, asset_data: dict, file_path: Path) -> bool:
        """
        Run protected asset verification. Returns False if validation failed (violation).
        Adds to self.errors or self.warnings as appropriate.
        """
        if not self._protected_config:
            return True

        cfg = self._protected_config
        asset_type = asset_data.get("type", "")
        network = asset_data.get("network", "")

        # Skip protection when testnet and enforce_on_testnet is False (FEAT-12)
        if network == "testnet" and not cfg.enforce_on_testnet:
            return True

        # Native assets skip protection checks (Edge Case 8)
        if asset_type == "native":
            return True

        self.protection_checked += 1

        symbol = asset_data.get("symbol", "")
        name = asset_data.get("name", "")
        sym_norm = self._normalize(symbol, cfg.case_sensitive)
        name_norm = self._normalize(name, cfg.case_sensitive)

        # Factory assets: exact symbol/name match (FAIL), similar (WARN)
        if asset_type == "factory":
            # Exact symbol match (FEAT-2, FEAT-4) — is_verified does NOT override (Edge Case 7)
            if sym_norm in cfg.symbols:
                entry = cfg.symbols[sym_norm]
                origins = ", ".join(entry.expected_origin_chains)
                msg = (
                    f"Factory token cannot use protected symbol '{symbol}' — this symbol is reserved "
                    f"for canonical {origins} assets. Use a different symbol or ensure your asset is "
                    f"the legitimate IBC representation."
                )
                if self.warn_only:
                    self.warnings.append(f"{file_path}: {msg}")
                    self.protection_warnings += 1
                else:
                    self.errors.append(f"{file_path}: {msg}")
                    self.protection_violations += 1
                return self.warn_only

            # Exact name match (FEAT-3)
            if name_norm in cfg.names:
                entry = cfg.names[name_norm]
                msg = (
                    f"Factory token cannot use protected name '{name}' — this name is reserved. "
                    f"Use a different name or ensure your asset is the legitimate IBC representation from {entry.expected_origin_chains}."
                )
                if self.warn_only:
                    self.warnings.append(f"{file_path}: {msg}")
                    self.protection_warnings += 1
                else:
                    self.errors.append(f"{file_path}: {msg}")
                    self.protection_violations += 1
                return self.warn_only

            # Similar symbol match (FEAT-5) — match against sym_norm so NFKC-normalized
            # confusables (Cyrillic, full-width, ligatures) hit the ASCII regexes too.
            if cfg.warn_on_similar:
                for pattern, entry in cfg.similar_patterns:
                    if pattern.search(sym_norm):
                        self.warnings.append(
                            f"{file_path}: Symbol '{symbol}' is similar to protected asset "
                            f"'{entry.symbol}' — manual review required"
                        )
                        self.protection_warnings += 1
                        break

            return True

        # IBC assets: origin chain validation
        if asset_type == "ibc":
            origin_chain = asset_data.get("origin_chain", "").lower()

            # Check if symbol matches a protected asset
            if sym_norm in cfg.symbols:
                entry = cfg.symbols[sym_norm]
                if "ibc" in entry.allowed_types:
                    if origin_chain in entry.expected_origin_chains:
                        # FEAT-7: Pass
                        return True
                    else:
                        # FEAT-6, Edge Case 2: Warning for unexpected origin
                        self.warnings.append(
                            f"{file_path}: IBC asset with protected symbol '{symbol}' has unexpected "
                            f"origin chain '{origin_chain}' (expected: {entry.expected_origin_chains}) — "
                            "review required"
                        )
                        self.protection_warnings += 1

            return True

        return True

    def validate_asset_file(self, file_path: Path) -> bool:
        """Validate a single asset file using Pydantic models."""
        try:
            with open(file_path, "r") as f:
                asset_data = json.load(f)
        except json.JSONDecodeError as e:
            self.errors.append(f"{file_path}: Invalid JSON: {e}")
            return False
        except Exception as e:
            self.errors.append(f"{file_path}: Error reading file: {e}")
            return False
        
        # Remove $schema field if present (it's for JSON Schema validation tools, not part of asset data)
        asset_data.pop("$schema", None)
        
        # Check network filter early
        network = asset_data.get("network", "")
        if self.network_filter and network != self.network_filter:
            return True  # Skip this file, but don't count as error
        
        if not network:
            self.errors.append(f"{file_path}: Missing required field 'network'")
            return False
        
        # Get model for asset type
        asset_type = asset_data.get("type", "")
        model_class = self._get_model_for_type(asset_type)
        
        if not model_class:
            self.errors.append(f"{file_path}: Unknown asset type '{asset_type}'")
            return False
        
        # Validate using Pydantic model
        try:
            asset = model_class.model_validate(asset_data)
        except ValidationError as e:
            # Format Pydantic validation errors
            for error in e.errors():
                field_path = " -> ".join(str(loc) for loc in error["loc"])
                error_msg = error["msg"]
                self.errors.append(f"{file_path}: Validation error at '{field_path}': {error_msg}")
            return False
        except Exception as e:
            self.errors.append(f"{file_path}: Unexpected validation error: {e}")
            return False
        
        # Track for integrity checks (duplicate asset_id and base_denom per network)
        asset_id = asset.asset_id
        base_denom = getattr(asset, "base_denom", None)
        
        if asset_id:
            if network not in self.asset_ids:
                self.asset_ids[network] = {}
            if asset_id in self.asset_ids[network]:
                self.errors.append(
                    f"{file_path}: Duplicate asset_id '{asset_id}' (also in {self.asset_ids[network][asset_id]})"
                )
                return False
            else:
                self.asset_ids[network][asset_id] = str(file_path)
        
        if base_denom:
            if network not in self.base_denoms:
                self.base_denoms[network] = {}
            if base_denom in self.base_denoms[network]:
                self.errors.append(
                    f"{file_path}: Duplicate base_denom '{base_denom}' (also in {self.base_denoms[network][base_denom]})"
                )
                return False
            else:
                self.base_denoms[network][base_denom] = str(file_path)
        
        # Protected asset verification (runs only when config loaded and asset passed schema checks)
        if self._protected_config is not None:
            protection_ok = self._validate_protected_assets(asset_data, file_path)
            if not protection_ok:
                return False
        
        return True

    def validate_all(self) -> bool:
        """Validate all asset files in the repository."""
        if not self._load_protected_config():
            return False

        asset_dirs = ["native", "factory", "ibc"]

        for asset_dir in asset_dirs:
            dir_path = self.assets_dir / asset_dir
            if not dir_path.exists():
                continue

            # Handle nested directories (e.g., ibc/cosmoshub/)
            for file_path in dir_path.rglob("*.json"):
                if file_path.is_file():
                    self.validate_asset_file(file_path)

        # Validate EVM chain registry entries (chains/evm/*.json). Separate
        # from assets — they describe chains, not tokens on chains.
        self._validate_evm_chains()

        # Cross-file checks (warnings)
        self._warn_on_display_collisions()

        return len(self.errors) == 0

    def _validate_evm_chains(self) -> None:
        """Validate every chains/evm/*.json file against the EvmChain model.

        Errors append to self.errors and surface in CI. Missing chains/ dir is
        not an error — the registry may have no EVM chains yet.
        """
        evm_dir = self.repo_root / "chains" / "evm"
        if not evm_dir.exists():
            return

        for file_path in sorted(evm_dir.rglob("*.json")):
            if not file_path.is_file():
                continue
            try:
                with open(file_path, "r") as f:
                    payload = json.load(f)
            except json.JSONDecodeError as e:
                self.errors.append(f"Invalid JSON in {file_path}: {e}")
                continue

            try:
                EvmChain.model_validate(payload)
            except ValidationError as e:
                # Render each error with field path so reviewers can locate it.
                for err in e.errors():
                    loc = ".".join(str(part) for part in err.get("loc", ()))
                    self.errors.append(
                        f"EvmChain validation failed in {file_path} at '{loc}': "
                        f"{err.get('msg', err)}"
                    )

    def _warn_on_display_collisions(self) -> None:
        """
        Warn on case-insensitive display_denom collisions per network.

        - If multiple assets share the same display_denom, warn maintainers.
        - If more than one is_verified=True exists in a collision group, warn.
        """
        # Build: network -> display_key -> [{file, type, asset_id, is_verified}]
        index: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
        for network, by_id in self.asset_ids.items():
            index.setdefault(network, {})
            for asset_id, file_path in by_id.items():
                try:
                    with open(file_path, "r") as f:
                        payload = json.load(f)
                    payload.pop("$schema", None)
                    display = str(payload.get("display_denom", "")).strip()
                    if not display:
                        continue
                    key = display.lower()
                    index[network].setdefault(key, []).append(
                        {
                            "file": file_path,
                            "type": str(payload.get("type", "")),
                            "asset_id": str(payload.get("asset_id", "")),
                            "is_verified": str(bool(payload.get("is_verified") is True)),
                        }
                    )
                except Exception:
                    continue

        for network, groups in index.items():
            for key, items in groups.items():
                if len(items) < 2:
                    continue
                verified_count = sum(1 for it in items if it.get("is_verified") == "True")
                files_list = ", ".join(sorted({it["file"] for it in items}))
                self.warnings.append(
                    f"[{network}] display_denom collision for '{key}': {len(items)} assets -> {files_list}"
                )
                if verified_count > 1:
                    self.warnings.append(
                        f"[{network}] multiple verified assets share display_denom '{key}' ({verified_count} verified)."
                    )

    def print_results(self):
        """Print validation results."""
        if self.errors:
            print("Validation Errors:")
            for error in self.errors:
                print(f"  ❌ {error}")
        
        if self.warnings:
            print("\nValidation Warnings:")
            for warning in self.warnings:
                print(f"  ⚠️  {warning}")
        
        if self._protected_config is not None:
            print(
                f"\nProtection validation: {self.protection_checked} assets checked, "
                f"{self.protection_violations} violations, {self.protection_warnings} warnings"
            )
        
        if not self.errors and not self.warnings:
            network_msg = f" for network '{self.network_filter}'" if self.network_filter else ""
            print(f"✅ All assets validated successfully{network_msg}!")
        elif not self.errors:
            print("\n✅ No validation errors found (warnings may be present)")


def main():
    parser = argparse.ArgumentParser(
        description="Validate ZIGChain assets registry files"
    )
    parser.add_argument(
        "--repo-root",
        type=str,
        default=".",
        help="Root directory of the repository (default: current directory)"
    )
    parser.add_argument(
        "--network",
        type=str,
        choices=["mainnet", "testnet"],
        help="Filter validation to specific network"
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Treat protected asset violations as warnings instead of errors (for migration)"
    )
    
    args = parser.parse_args()
    
    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists():
        print(f"Error: Repository root does not exist: {repo_root}")
        sys.exit(1)
    
    validator = AssetValidator(
        repo_root,
        network_filter=args.network,
        warn_only=args.warn_only,
    )
    success = validator.validate_all()
    validator.print_results()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

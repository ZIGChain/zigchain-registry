#!/usr/bin/env python3
"""
Generate Cosmos chain-registry compatible artifacts for ZIGChain.

Outputs:
- generated/chain-registry/zigchain/assetlist.json
- generated/chain-registry/zigchain/images/*
- generated/chain-registry/_non-cosmos/ethereum/assetlist.json (when ERC20s exist)
- generated/chain-registry/_non-cosmos/ethereum/images/* (when ERC20s exist)

Usage:
    python scripts/generate_chain_registry.py
    python scripts/generate_chain_registry.py --root . --out generated/chain-registry
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

# Ensure local imports work when executed as a script
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pydantic import AnyUrl  # noqa: E402

from models.factory import FactoryAsset  # noqa: E402
from models.ibc import IBCAsset, IBCTrace  # noqa: E402
from models.native import NativeAsset  # noqa: E402
from models.base import NativeTrace  # noqa: E402


@dataclass
class AssetImages:
    png: Optional[str]
    svg: Optional[str]

    def as_logo_uris(self, base_url: str) -> Dict[str, str]:
        uris: Dict[str, str] = {}
        if self.png:
            uris["png"] = f"{base_url}/{self.png}"
        if self.svg:
            uris["svg"] = f"{base_url}/{self.svg}"
        return uris

    def as_images_entry(self, base_url: str) -> List[Dict[str, str]]:
        entries: List[Dict[str, str]] = []
        if self.png or self.svg:
            entry: Dict[str, str] = {}
            if self.png:
                entry["png"] = f"{base_url}/{self.png}"
            if self.svg:
                entry["svg"] = f"{base_url}/{self.svg}"
            entries.append(entry)
        return entries


def _merge_images_with_declared_sync(
    *,
    declared_images: Optional[Sequence[object]],
    computed: AssetImages,
    base_url: str,
) -> List[Dict]:
    """
    Build chain-registry `images` entries.

    If an asset declares the shortcut form:
      images: [{ "chain_name": "...", "base_denom": "..." }]
    we convert it into:
      images: [{ "image_sync": { "chain_name": "...", "base_denom": "..." }, "png": "...", "svg": "..." }]

    If an asset declares full Cosmos-style entries (with image_sync/theme/png/svg),
    we preserve those keys and fill missing png/svg from computed local logos.
    """
    computed_entry: Dict[str, str] = {}
    if computed.png:
        computed_entry["png"] = f"{base_url}/{computed.png}"
    if computed.svg:
        computed_entry["svg"] = f"{base_url}/{computed.svg}"

    if not declared_images:
        return [computed_entry] if computed_entry else []

    out: List[Dict] = []
    for item in declared_images:
        if hasattr(item, "model_dump"):
            raw = item.model_dump(exclude_none=True)
        else:
            raw = item

        if not isinstance(raw, dict):
            continue

        # Shortcut form: {chain_name, base_denom}
        if "chain_name" in raw and "base_denom" in raw and "image_sync" not in raw:
            entry: Dict = {"image_sync": {"chain_name": raw["chain_name"], "base_denom": raw["base_denom"]}}
            entry.update(computed_entry)
            out.append(entry)
            continue

        # Full form: merge in png/svg if not already provided
        entry = dict(raw)
        if "png" not in entry and "png" in computed_entry:
            entry["png"] = computed_entry["png"]
        if "svg" not in entry and "svg" in computed_entry:
            entry["svg"] = computed_entry["svg"]
        out.append(entry)

    return out if out else ([computed_entry] if computed_entry else [])

def read_json_files(directory: Path) -> Sequence[Dict]:
    """Read JSON asset files, prefer network-suffixed names, and de-dupe."""
    payloads: List[Dict] = []
    seen: set[tuple[Optional[str], Optional[str]]] = set()

    # Prefer files with explicit network suffixes
    preferred = sorted(directory.glob("*.mainnet.json")) + sorted(directory.glob("*.testnet.json"))

    for path in preferred:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        data.pop("$schema", None)

        key = (data.get("asset_id"), data.get("network"))
        if key in seen:
            continue
        seen.add(key)
        payloads.append(data)

    return payloads


def load_assets(root: Path) -> Tuple[List[NativeAsset], List[FactoryAsset], List[IBCAsset]]:
    assets_dir = root / "assets"
    native_dir = assets_dir / "native"
    factory_dir = assets_dir / "factory"
    ibc_dir = assets_dir / "ibc"

    natives = [NativeAsset.model_validate(obj) for obj in read_json_files(native_dir)]
    factories = [FactoryAsset.model_validate(obj) for obj in read_json_files(factory_dir)]
    ibcs = [IBCAsset.model_validate(obj) for obj in read_json_files(ibc_dir)]

    return natives, factories, ibcs


def parse_channel_id_from_path(path: str) -> Optional[str]:
    """Extract channel identifier from a transfer path (transfer/<channel-id>/...)."""
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "transfer":
        return parts[1]
    return None


def _slugify_for_filename(value: str) -> str:
    v = (value or "").strip().lower()
    # Keep it simple: filenames in this repo are lowercase alpha-numeric.
    return "".join(ch for ch in v if ch.isalnum() or ch in ("-", "_"))


def _slug_from_logo_uri(uri: Optional[str]) -> Optional[str]:
    if not uri:
        return None
    try:
        path = urlparse(uri).path
    except Exception:
        return None
    name = Path(path).name
    if not name:
        return None
    stem = Path(name).stem
    return _slugify_for_filename(stem) if stem else None


def locate_image_filenames(*, slugs: Sequence[str], logos_dir: Path) -> AssetImages:
    """Find png/svg assets by trying candidate slugs (without extension)."""
    for raw in slugs:
        slug = _slugify_for_filename(raw)
        if not slug:
            continue
        png_path = logos_dir / f"{slug}.png"
        svg_path = logos_dir / f"{slug}.svg"
        if png_path.exists() or svg_path.exists():
            return AssetImages(
                png=png_path.name if png_path.exists() else None,
                svg=svg_path.name if svg_path.exists() else None,
            )
    return AssetImages(png=None, svg=None)


def _declared_logo_slug(asset: object) -> Optional[str]:
    """If asset declares logo_uris, return the referenced filename stem (slug), else None."""
    logo_uris = getattr(asset, "logo_uris", None)
    if not logo_uris:
        return None
    png_uri = getattr(logo_uris, "png", None)
    svg_uri = getattr(logo_uris, "svg", None)
    slug = _slug_from_logo_uri(str(png_uri)) or _slug_from_logo_uri(str(svg_uri))
    return slug


def _asset_logo_slugs(asset: object) -> List[str]:
    slugs: List[str] = []

    # Prefer explicit logo_uris filenames (lets zigchain -> zigchain.png even if display is ZIG)
    declared = _declared_logo_slug(asset)
    if declared:
        slugs.append(declared)

    # Native asset_id is often a good fallback (e.g. zigchain)
    asset_id = getattr(asset, "asset_id", None)
    if isinstance(asset_id, str) and asset_id and "/" not in asset_id and "." not in asset_id:
        slugs.append(asset_id)

    # Display denom works for most (atom, eth, usdc...)
    display = getattr(asset, "display_denom", None)
    if isinstance(display, str) and display:
        slugs.append(display)

    # Symbol as last resort
    symbol = getattr(asset, "symbol", None)
    if isinstance(symbol, str) and symbol:
        slugs.append(symbol)

    # De-dupe while preserving order
    seen: set[str] = set()
    out: List[str] = []
    for s in slugs:
        ss = _slugify_for_filename(s)
        if ss and ss not in seen:
            seen.add(ss)
            out.append(ss)
    return out


def _compact_dict(d: Dict) -> Dict:
    """Remove optional fields we don't want to serialize when empty."""
    out: Dict = {}
    for k, v in d.items():
        if v is None:
            continue
        if v == {} or v == []:
            continue
        out[k] = v
    return out


def _declared_logo_uris_dict(asset: object) -> Optional[Dict[str, str]]:
    declared = getattr(asset, "logo_uris", None)
    if declared is None:
        return None
    if hasattr(declared, "model_dump"):
        d = declared.model_dump(exclude_none=True)
    elif isinstance(declared, dict):
        d = {k: v for k, v in declared.items() if v is not None}
    else:
        return None
    out: Dict[str, str] = {}
    for k in ("png", "svg"):
        if k in d and d[k]:
            out[k] = str(d[k])
    return out or None


def _is_our_assets_repo_raw(url: str) -> bool:
    # Our asset JSONs commonly reference local repo logos via GitHub raw URLs.
    # Trailing slash narrows the match so look-alikes like
    # `zigchain-registry-old` / `zigchain-registry-demo` won't false-positive.
    return "raw.githubusercontent.com/ZIGChain/zigchain-registry/" in (url or "")


def _should_preserve_declared_logo_uris(asset: object) -> bool:
    """
    If an asset explicitly declares logo_uris pointing somewhere else (e.g. cosmos/chain-registry _non-cosmos),
    keep it verbatim. Only rewrite when the declared URL points to our own assets repo.
    """
    d = _declared_logo_uris_dict(asset)
    if not d:
        return False
    # If any declared URL points to our own repo, we treat it as "local" and allow rewriting.
    return not any(_is_our_assets_repo_raw(u) for u in d.values())


_NON_COSMOS_CHAIN_NAMES = {"ethereum"}


def _chain_registry_images_base_url(*, chain_name: str) -> str:
    """
    Build cosmos/chain-registry raw base URL for a chain's images folder.
    - cosmos chain folders:      <chain_name>/images
    - non-cosmos chain folders:  _non-cosmos/<chain_name>/images
    """
    cn = chain_name.strip()
    if cn in _NON_COSMOS_CHAIN_NAMES:
        return f"https://raw.githubusercontent.com/cosmos/chain-registry/master/_non-cosmos/{cn}/images"
    return f"https://raw.githubusercontent.com/cosmos/chain-registry/master/{cn}/images"


def _ibc_logo_chain_name(asset: object) -> Optional[str]:
    """
    Optional hint to resolve IBC logo URIs to a different chain-registry folder.
    Stored in asset JSON as: logo_uris.chain_name
    """
    logo_uris = getattr(asset, "logo_uris", None)
    cn = getattr(logo_uris, "chain_name", None) if logo_uris is not None else None
    if isinstance(cn, str) and cn.strip():
        return cn.strip()
    return None


def _basename_from_uri(uri: str) -> Optional[str]:
    try:
        name = Path(urlparse(uri).path).name
    except Exception:
        return None
    return name or None


def _ibc_logo_uris_from_chain_name(asset: object) -> Optional[Dict[str, str]]:
    """
    If logo_uris.chain_name is set, rewrite output URLs to point at cosmos/chain-registry
    under that chain's images folder, using the basename from the declared logo_uris URLs.
    """
    cn = _ibc_logo_chain_name(asset)
    if not cn:
        return None
    declared = _declared_logo_uris_dict(asset)
    if not declared:
        return None
    base_url = _chain_registry_images_base_url(chain_name=cn)
    out: Dict[str, str] = {}
    for k in ("png", "svg"):
        if k in declared and declared[k]:
            name = _basename_from_uri(declared[k])
            if name:
                out[k] = f"{base_url}/{name}"
    return out or None


def _ibc_images_base_url_override(asset: object) -> Optional[str]:
    cn = _ibc_logo_chain_name(asset)
    if not cn:
        return None
    return _chain_registry_images_base_url(chain_name=cn)


def _ibc_computed_images_from_declared_basenames(asset: object) -> AssetImages:
    """
    For IBC assets with logo_uris.chain_name set, we want images to use the same filenames
    as the declared logo_uris (but pointed at the chain-registry folder), without depending
    on local logo discovery.
    """
    declared = _declared_logo_uris_dict(asset) or {}
    png_name = _basename_from_uri(declared["png"]) if "png" in declared else None
    svg_name = _basename_from_uri(declared["svg"]) if "svg" in declared else None
    return AssetImages(png=png_name, svg=svg_name)


def _logo_uris_for_output(*, asset: object, computed: AssetImages, local_base_url: str) -> Optional[Dict[str, str]]:
    """
    Compute logo_URIs for chain-registry output.

    Rule:
    - If we have local images for this asset (computed png/svg), emit canonical chain-registry URLs.
    - Else if the asset file declares logo_uris, preserve it verbatim.
    - Else omit.
    """
    declared_dict = _declared_logo_uris_dict(asset)

    # If the asset declares logo_uris and it's not our repo, preserve it exactly.
    if declared_dict and _should_preserve_declared_logo_uris(asset):
        return declared_dict

    # Otherwise, prefer local computed URLs (canonical chain-registry path).
    computed_logo = computed.as_logo_uris(local_base_url)
    if computed_logo:
        return computed_logo

    # Fall back to declared (e.g. our repo URLs) if we couldn't compute.
    return declared_dict or None


def _images_for_output(
    *,
    asset: object,
    computed: AssetImages,
    local_base_url: str,
    logo_uris_out: Optional[Dict[str, str]],
) -> Optional[List[Dict]]:
    """
    Compute images[] for chain-registry output.

    - If asset declares images, use them (and fill missing png/svg from computed local logos).
    - Else if computed local logos exist, use those.
    - Else if we preserved declared logo_uris, mirror them into images[] (common chain-registry convention).
    - Else omit.
    """
    declared_images = getattr(asset, "images", None)
    if declared_images:
        out = _merge_images_with_declared_sync(declared_images=declared_images, computed=computed, base_url=local_base_url)
        return out or None

    computed_images = computed.as_images_entry(local_base_url)
    if computed_images:
        return computed_images

    if logo_uris_out:
        return [dict(logo_uris_out)]

    return None


def copy_images(
    images: AssetImages, logos_dir: Path, dest_dir: Path, copied: Optional[set[str]] = None
) -> int:
    """Copy image files once; return number of files copied."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied_count = 0
    for filename in (images.png, images.svg):
        if filename is None:
            continue
        if copied is not None and filename in copied:
            continue
        src = logos_dir / filename
        if src.exists():
            shutil.copyfile(src, dest_dir / filename)
            copied_count += 1
            if copied is not None:
                copied.add(filename)
    return copied_count


def _supplemental_traces_for_output(items: Optional[Sequence[object]]) -> List[Dict]:
    """
    Build supplemental trace entries of the form:
      { type, counterparty: {chain_name, base_denom}, provider? }
    """
    if not items:
        return []
    out: List[Dict] = []
    for t in items:
        if hasattr(t, "model_dump"):
            raw = t.model_dump(exclude_none=True)
        else:
            raw = t
        if not isinstance(raw, dict):
            continue
        entry: Dict = {
            "type": raw.get("type"),
            "counterparty": raw.get("counterparty"),
        }
        provider = raw.get("provider")
        if isinstance(provider, str) and provider.strip() and provider.strip().lower() != "ibc":
            entry["provider"] = provider.strip()
        # Only emit well-formed entries
        if not isinstance(entry.get("type"), str) or not entry["type"].strip():
            continue
        if not isinstance(entry.get("counterparty"), dict):
            continue
        if not isinstance(entry["counterparty"].get("chain_name"), str) or not entry["counterparty"]["chain_name"].strip():
            continue
        if not isinstance(entry["counterparty"].get("base_denom"), str) or not entry["counterparty"]["base_denom"].strip():
            continue
        out.append(entry)
    return out


def build_traces(asset: IBCAsset, zig_trace: Optional[IBCTrace]) -> List[Dict]:
    traces: List[Dict] = []
    zigchain_channel_from_trace = parse_channel_id_from_path(zig_trace.path) if zig_trace else None
    channel_index = {ch.counterparty_chain: ch for ch in asset.channels}

    def _trace_provider(trace: IBCTrace) -> Optional[str]:
        """
        Return a chain-registry provider string ONLY when explicitly present in the source trace.

        Requirement: if the trace JSON did not define a provider, we must omit the provider field
        from the generated assetlist.json (no inference/defaults like 'ibc').
        """
        provider = getattr(trace, "provider", None)
        # Special case: if explicitly set to IBC, we intentionally omit it from output.
        if provider == "ibc":
            return None
        if provider == "eureka":
            return "Eureka"
        return None

    ibc_hops = [t for t in asset.traces if isinstance(t, IBCTrace)]
    supplemental = [t for t in asset.traces if isinstance(t, NativeTrace)]

    traces_to_emit = [t for t in ibc_hops if t.chain_name != "zigchain"]
    traces_to_emit.sort(
        key=lambda t: (
            0 if t.chain_name == asset.origin_chain else 1,  # origin chain first
            1 if (t.chain_name == "cosmoshub" and t.chain_name != asset.origin_chain) else 0,  # cosmoshub last among non-origin
        )
    )

    for trace in traces_to_emit:

        ch = channel_index.get(trace.chain_name)
        counterparty_channel = ch.counterparty_channel if ch else parse_channel_id_from_path(trace.path)
        chain_channel = ch.zigchain_channel if ch else zigchain_channel_from_trace or parse_channel_id_from_path(trace.path)

        if zig_trace and parse_channel_id_from_path(zig_trace.path) == chain_channel:
            chain_path = zig_trace.path
        elif chain_channel:
            chain_path = f"transfer/{chain_channel}/{asset.origin_denom}"
        else:
            chain_path = trace.path

        trace_entry: Dict = {
            "type": trace.type,
            "counterparty": {"chain_name": trace.chain_name, "base_denom": trace.base_denom},
            "chain": {"channel_id": chain_channel, "path": chain_path},
        }
        provider_out = _trace_provider(trace)
        if provider_out:
            trace_entry["provider"] = provider_out
        if counterparty_channel:
            trace_entry["counterparty"]["channel_id"] = counterparty_channel
        traces.append(trace_entry)

    # Prepend supplemental (non-routing) trace metadata at the top of the traces list.
    # This keeps the extra context visible first in consumers that only display the first hop(s).
    supplemental_out = _supplemental_traces_for_output(supplemental)
    return supplemental_out + traces


def ibc_asset_to_chain_registry(asset: IBCAsset, images: AssetImages) -> Dict:
    zig_trace = next((t for t in asset.traces if isinstance(t, IBCTrace) and t.chain_name == "zigchain"), None)
    traces = build_traces(asset, zig_trace)

    # If denom_units are declared on the IBC asset, prefer them verbatim (chain-registry compatible).
    # Otherwise fall back to a minimal derived set.
    if getattr(asset, "denom_units", None):
        denom_units = [du.model_dump(exclude_none=True) for du in asset.denom_units]  # type: ignore[union-attr]
    else:
        denom_units = [{"denom": asset.base_denom, "exponent": 0}]
        if asset.origin_denom and asset.origin_denom != asset.base_denom:
            denom_units[0]["aliases"] = [asset.origin_denom]
        denom_units.append({"denom": asset.display_denom, "exponent": asset.decimals})

    local_base_url = "https://raw.githubusercontent.com/cosmos/chain-registry/master/zigchain/images"
    # If logo_uris.chain_name is set for IBC assets, resolve output to that chain folder.
    ibc_base_url = _ibc_images_base_url_override(asset) or local_base_url
    logo_uris_out = _ibc_logo_uris_from_chain_name(asset) or _logo_uris_for_output(
        asset=asset, computed=images, local_base_url=local_base_url
    )
    computed_for_images = _ibc_computed_images_from_declared_basenames(asset) if _ibc_logo_chain_name(asset) else images
    return _compact_dict({
        "description": asset.description,
        "extended_description": getattr(asset, "extended_description", None),
        "denom_units": denom_units,
        "base": asset.base_denom,
        "name": asset.name,
        "display": asset.display_denom,
        "symbol": asset.symbol,
        "traces": traces,
        "coingecko_id": asset.coingecko_id,
        "keywords": getattr(asset, "keywords", None),
        "socials": (
            getattr(asset.socials, "model_dump", None)(exclude_none=True)
            if getattr(asset, "socials", None) is not None
            else None
        ),
        "type_asset": "ics20",
        "logo_URIs": logo_uris_out,
        "images": _images_for_output(
            asset=asset,
            computed=computed_for_images,
            local_base_url=ibc_base_url,
            logo_uris_out=logo_uris_out,
        ),
    })


def build_native_traces(asset: object) -> Optional[List[Dict]]:
    """
    Build chain-registry `traces` entries for native assets.

    Input format (as defined in assets/native/*.json):
      traces: [{ type, counterparty: { chain_name, base_denom }, provider? }]

    Output:
      Same shape, but `provider` is omitted if not explicitly defined.
    """
    traces_in = getattr(asset, "traces", None)
    if not traces_in:
        return None

    out: List[Dict] = []
    for t in traces_in:
        # Support both Pydantic models and raw dicts
        if hasattr(t, "model_dump"):
            raw = t.model_dump(exclude_none=True)
        else:
            raw = t

        if not isinstance(raw, dict):
            continue

        entry: Dict = {
            "type": raw.get("type"),
            "counterparty": raw.get("counterparty"),
        }
        provider = raw.get("provider")
        if isinstance(provider, str) and provider.strip() and provider.strip().lower() != "ibc":
            entry["provider"] = provider.strip()

        # Drop obviously-invalid entries rather than emitting junk
        if not isinstance(entry.get("type"), str) or not entry["type"].strip():
            continue
        if not isinstance(entry.get("counterparty"), dict):
            continue
        if not isinstance(entry["counterparty"].get("chain_name"), str) or not entry["counterparty"]["chain_name"].strip():
            continue
        if not isinstance(entry["counterparty"].get("base_denom"), str) or not entry["counterparty"]["base_denom"].strip():
            continue

        out.append(entry)

    return out or None


def non_ibc_asset_to_chain_registry(asset: NativeAsset | FactoryAsset, images: AssetImages) -> Dict:
    local_base_url = "https://raw.githubusercontent.com/cosmos/chain-registry/master/zigchain/images"
    logo_uris_out = _logo_uris_for_output(asset=asset, computed=images, local_base_url=local_base_url)
    return _compact_dict({
        "description": asset.description,
        "extended_description": getattr(asset, "extended_description", None),
        "denom_units": [du.model_dump(exclude_none=True) for du in asset.denom_units],
        "base": asset.base_denom,
        "name": asset.name,
        "display": asset.display_denom,
        "symbol": asset.symbol,
        "coingecko_id": asset.coingecko_id,
        "keywords": getattr(asset, "keywords", None),
        "socials": (
            getattr(asset.socials, "model_dump", None)(exclude_none=True)
            if getattr(asset, "socials", None) is not None
            else None
        ),
        "traces": build_native_traces(asset),
        "type_asset": "sdk.coin",
        "logo_URIs": logo_uris_out,
        "images": _images_for_output(
            asset=asset,
            computed=images,
            local_base_url=local_base_url,
            logo_uris_out=logo_uris_out,
        ),
    })


_ERC20_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def erc20_from_ibc(asset: IBCAsset, images: AssetImages) -> Optional[Dict]:
    if asset.origin_chain != "ethereum" or not _ERC20_ADDRESS_RE.match(asset.origin_denom):
        return None

    denom_units = [
        {"denom": asset.origin_denom, "exponent": 0, "aliases": []},
        {"denom": asset.display_denom, "exponent": asset.decimals},
    ]

    local_base_url = "https://raw.githubusercontent.com/cosmos/chain-registry/master/_non-cosmos/ethereum/images"
    logo_uris_out = _logo_uris_for_output(asset=asset, computed=images, local_base_url=local_base_url)
    return _compact_dict({
        "description": asset.description,
        "extended_description": getattr(asset, "extended_description", None),
        "denom_units": denom_units,
        "base": asset.origin_denom,
        "name": asset.name,
        "display": asset.display_denom,
        "symbol": asset.symbol,
        "type_asset": "erc20",
        "coingecko_id": asset.coingecko_id,
        "keywords": getattr(asset, "keywords", None),
        "socials": (
            getattr(asset.socials, "model_dump", None)(exclude_none=True)
            if getattr(asset, "socials", None) is not None
            else None
        ),
        "logo_URIs": logo_uris_out,
        "images": _images_for_output(
            asset=asset,
            computed=images,
            local_base_url=local_base_url,
            logo_uris_out=logo_uris_out,
        ),
    })


def _json_default(o: object) -> str:
    # Pydantic HttpUrl/AnyUrl aren't subclasses of str, so the stdlib JSON
    # encoder can't serialize them — model_dump() leaves them as Url objects.
    # Any other unexpected type raises so it surfaces in tests instead of
    # silently stringifying.
    if isinstance(o, AnyUrl):
        return str(o)
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=_json_default)
        fh.write("\n")


def _run(
    cmd: List[str],
    *,
    cwd: Path,
    check: bool = True,
    no_prompt: bool = False,
    env_overrides: Optional[Mapping[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if env_overrides:
        env.update({k: v for k, v in env_overrides.items() if v is not None})
    if no_prompt:
        # Useful for CI/non-interactive environments. If git needs credentials it will fail fast.
        env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )


_GIT_ENV_KEYS = {
    "GIT_AUTHOR_EMAIL",
    "GIT_AUTHOR_NAME",
    "GIT_COMMITTER_EMAIL",
    "GIT_COMMITTER_NAME",
    "GIT_SSH_COMMAND",
}

# Shell metacharacters and patterns that must not appear in GIT_SSH_COMMAND values.
_GIT_SSH_COMMAND_DENY = re.compile(
    r"[;|`$]|ProxyCommand", re.IGNORECASE
)


def _load_git_env_from_env_file(path: Path) -> Dict[str, str]:
    """
    Load a minimal set of git-related env vars from a dotenv-style file.

    Supported format:
      KEY=value
      export KEY=value
    Lines starting with # are ignored. Quotes are preserved as-is (simple parser).
    Only keys in _GIT_ENV_KEYS are returned.
    """
    out: Dict[str, str] = {}
    if not path.exists():
        return out

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        # Work around common typo like KEY==value
        while v.startswith("="):
            v = v[1:].lstrip()
        if k in _GIT_ENV_KEYS and v:
            # Sanitize GIT_SSH_COMMAND: reject dangerous shell metacharacters
            if k == "GIT_SSH_COMMAND" and _GIT_SSH_COMMAND_DENY.search(v):
                raise ValueError(
                    f"GIT_SSH_COMMAND contains unsafe characters or patterns: {v!r}"
                )
            out[k] = v
    return out


def _prepare_git_env(*, root: Path, git_env_file: Optional[Path]) -> Dict[str, str]:
    """
    Build env overrides for git subprocesses:
    - Load from optional dotenv file (repo-local)
    - Overlay current process env
    - Expand ~ in GIT_SSH_COMMAND if present
    """
    overrides: Dict[str, str] = {}

    # Auto-load root/.env if no explicit file was provided
    candidate = git_env_file
    if candidate is None:
        default_env = root / ".env"
        if default_env.exists():
            candidate = default_env

    if candidate is not None:
        overrides.update(_load_git_env_from_env_file(candidate))

    for k in _GIT_ENV_KEYS:
        if k in os.environ and os.environ[k]:
            overrides[k] = os.environ[k]

    ssh_cmd = overrides.get("GIT_SSH_COMMAND")
    if ssh_cmd:
        overrides["GIT_SSH_COMMAND"] = os.path.expanduser(ssh_cmd)

    return overrides


def _github_https_to_ssh(url: str) -> Optional[str]:
    """
    Convert GitHub HTTPS URL to SSH URL.

    Examples:
      https://github.com/ORG/REPO      -> git@github.com:ORG/REPO.git
      https://github.com/ORG/REPO/     -> git@github.com:ORG/REPO.git
      https://github.com/ORG/REPO.git  -> git@github.com:ORG/REPO.git
    """
    u = url.strip()
    if not u.startswith("https://github.com/"):
        return None
    path = u[len("https://github.com/") :].strip("/")
    if not path:
        return None
    if path.endswith(".git"):
        path = path[: -len(".git")]
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    org, repo = parts[0], parts[1]
    return f"git@github.com:{org}/{repo}.git"


def _ensure_remote(repo_dir: Path, remote_name: str, remote_url: str) -> None:
    res = _run(["git", "remote"], cwd=repo_dir)
    remotes = {r.strip() for r in res.stdout.splitlines() if r.strip()}
    if remote_name in remotes:
        _run(["git", "remote", "set-url", remote_name, remote_url], cwd=repo_dir)
    else:
        _run(["git", "remote", "add", remote_name, remote_url], cwd=repo_dir)


def _rm_tree_if_exists(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _copy_tree_replace(src: Path, dst: Path) -> None:
    """
    Replace dst with src (including deletions).
    If src doesn't exist, do nothing.
    """
    if not src.exists():
        return
    _rm_tree_if_exists(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=False)


def _copy_images_merge(src_images_dir: Path, dst_images_dir: Path) -> int:
    """
    Copy images from src to dst without deleting existing files.
    Returns number of files copied.
    """
    if not src_images_dir.exists():
        return 0
    dst_images_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for p in src_images_dir.iterdir():
        if not p.is_file():
            continue
        shutil.copyfile(p, dst_images_dir / p.name)
        copied += 1
    return copied


def _sync_chain_folder(src_chain_dir: Path, dst_chain_dir: Path) -> None:
    """
    Sync only chain-local generated artifacts into an existing chain folder:
    - assetlist.json (overwrite)
    - images/ (replace)

    Does NOT touch other upstream files (e.g. chain.json).
    """
    if not src_chain_dir.exists():
        return

    src_assetlist = src_chain_dir / "assetlist.json"
    if src_assetlist.exists():
        dst_chain_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_assetlist, dst_chain_dir / "assetlist.json")

    src_images = src_chain_dir / "images"
    if src_images.exists():
        _copy_tree_replace(src_images, dst_chain_dir / "images")


def _timestamped_branch(prefix: str = "zigchain-sync") -> str:
    return f"{prefix}-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"


def sync_to_chain_registry(
    *,
    out_root: Path,
    upstream_repo: str,
    fork_repo: str,
    upstream_base_branch: str = "master",
    git_no_prompt: bool = False,
    git_env_overrides: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """
    Sync generated outputs into a fresh clone of the upstream Cosmos chain-registry,
    push a new branch to the fork, and return a compare URL for PR creation.
    """
    out_root = out_root.resolve()
    if not out_root.exists():
        raise RuntimeError(f"Output root does not exist: {out_root}")

    src_zigchain = out_root / "zigchain"
    src_eth = out_root / "_non-cosmos" / "ethereum"
    src_testnet_zigchain = out_root / "testnets" / "zigchaintestnet"
    src_testnet_eth = out_root / "testnets" / "_non-cosmos" / "ethereumtestnet"

    with tempfile.TemporaryDirectory(prefix="zigchain-chain-registry-") as tmp:
        repo_dir = Path(tmp) / "chain-registry"
        print(f"\nSyncing to chain-registry fork via fresh clone: {upstream_repo}")
        _run(
            ["git", "clone", "--depth", "1", upstream_repo, str(repo_dir)],
            cwd=Path(tmp),
            no_prompt=git_no_prompt,
            env_overrides=git_env_overrides,
        )

        _ensure_remote(repo_dir, "upstream", upstream_repo)
        _ensure_remote(repo_dir, "fork", fork_repo)

        # Ensure we're based on upstream base branch
        _run(
            ["git", "fetch", "upstream", upstream_base_branch],
            cwd=repo_dir,
            no_prompt=git_no_prompt,
            env_overrides=git_env_overrides,
        )
        _run(
            ["git", "checkout", "-B", upstream_base_branch, f"upstream/{upstream_base_branch}"],
            cwd=repo_dir,
            no_prompt=git_no_prompt,
            env_overrides=git_env_overrides,
        )

        branch = _timestamped_branch()
        _run(["git", "checkout", "-b", branch], cwd=repo_dir, no_prompt=git_no_prompt, env_overrides=git_env_overrides)

        # Copy generated outputs into the repo clone.
        # IMPORTANT:
        # - For zigchain folders: only overwrite assetlist.json and images/, keep other upstream files intact.
        # - For ethereum folders: do NOT overwrite upstream assetlist.json; only copy images (additive).
        _sync_chain_folder(src_zigchain, repo_dir / "zigchain")
        _sync_chain_folder(src_testnet_zigchain, repo_dir / "testnets" / "zigchaintestnet")

        eth_images_copied = _copy_images_merge(
            src_eth / "images", repo_dir / "_non-cosmos" / "ethereum" / "images"
        )
        eth_testnet_images_copied = _copy_images_merge(
            src_testnet_eth / "images", repo_dir / "testnets" / "_non-cosmos" / "ethereumtestnet" / "images"
        )
        if eth_images_copied or eth_testnet_images_copied:
            print(
                f"ℹ️ Copied ethereum images -> mainnet: {eth_images_copied}, testnet: {eth_testnet_images_copied}"
            )

        _run(["git", "add", "-A"], cwd=repo_dir)
        status = _run(["git", "status", "--porcelain"], cwd=repo_dir)
        if not status.stdout.strip():
            print("ℹ️ No changes detected in chain-registry clone; skipping commit/push.")
            return None

        commit_msg = f"zigchain: sync generated assets ({branch})"
        try:
            _run(["git", "commit", "-m", commit_msg], cwd=repo_dir, env_overrides=git_env_overrides)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                "git commit failed. Ensure git user.name and user.email are configured.\n"
                f"Command output:\n{e.stdout}"
            ) from e

        try:
            _run(
                ["git", "push", "fork", f"HEAD:{branch}"],
                cwd=repo_dir,
                no_prompt=git_no_prompt,
                env_overrides=git_env_overrides,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                "git push failed. Ensure you have push access to the fork and credentials are configured.\n"
                f"Command output:\n{e.stdout}"
            ) from e

        compare_url = (
            f"https://github.com/cosmos/chain-registry/compare/"
            f"{upstream_base_branch}...ZIGChain:chain-registry:{branch}"
        )
        print("\n✅ Pushed branch to fork.")
        print("Create PR (review changes first):")
        print(compare_url)
        return compare_url


def generate_for_network(
    network: str,
    natives: List[NativeAsset],
    factories: List[FactoryAsset],
    ibcs: List[IBCAsset],
    logos_dir: Path,
    out_root: Path,
    chain_name: str,
    eth_chain_name: str,
    use_testnet_paths: bool = False,
    verified_only: bool = True,
) -> None:
    """Generate outputs for a specific network."""
    if verified_only:
        pre_n, pre_f, pre_i = len(natives), len(factories), len(ibcs)
        natives = [a for a in natives if getattr(a, "is_verified", False) is True]
        factories = [a for a in factories if getattr(a, "is_verified", False) is True]
        ibcs = [a for a in ibcs if getattr(a, "is_verified", False) is True]
        excluded_n = pre_n - len(natives)
        excluded_f = pre_f - len(factories)
        excluded_i = pre_i - len(ibcs)
        if excluded_n + excluded_f + excluded_i > 0:
            print(
                f"[{network}] verified-only filter: excluded "
                f"{excluded_n} native, {excluded_f} factory, {excluded_i} ibc"
            )

    if use_testnet_paths:
        zigchain_out = out_root / "testnets" / chain_name
        eth_out = out_root / "testnets" / "_non-cosmos" / eth_chain_name
    else:
        zigchain_out = out_root / chain_name
        eth_out = out_root / "_non-cosmos" / eth_chain_name

    print(f"\nProcessing network={network} -> chain={chain_name}, eth_chain={eth_chain_name}")
    print(f"Assets -> native: {len(natives)}, factory: {len(factories)}, ibc: {len(ibcs)}")

    def _asset_sort_key(asset: object) -> tuple:
        """
        Deterministic sort for generated assetlist.json.

        Rules:
        - Assets with `order` set come first (ascending).
        - Assets without `order` come after, sorted deterministically.
        - Ties are broken by type then asset_id to ensure stable output.
        """
        order = getattr(asset, "order", None)
        asset_type = getattr(asset, "type", "")
        asset_id = getattr(asset, "asset_id", "")
        return (
            order is None,  # False (ordered) before True (unordered)
            order if order is not None else 0,
            asset_type,
            asset_id,
        )

    chain_assets: List[Dict] = []
    erc20_assets: List[Dict] = []
    zig_images_copied: set[str] = set()
    eth_images_copied: set[str] = set()
    # Additional per-chain images for IBC assets when logo_uris.chain_name is set (e.g. cosmoshub/images)
    extra_chain_images_copied: Dict[str, set[str]] = {}
    zig_image_count = 0
    eth_image_count = 0
    extra_chain_image_count = 0

    def _extra_chain_images_dir(chain_folder_name: str) -> Path:
        # Mirror chain-registry folder structure for non-cosmos chains.
        if chain_folder_name in _NON_COSMOS_CHAIN_NAMES:
            return (out_root / ("testnets" if use_testnet_paths else "") / "_non-cosmos" / chain_folder_name / "images") if use_testnet_paths else (out_root / "_non-cosmos" / chain_folder_name / "images")
        return (out_root / ("testnets" if use_testnet_paths else "") / chain_folder_name / "images") if use_testnet_paths else (out_root / chain_folder_name / "images")

    def _copy_extra_chain_images(chain_folder_name: str, imgs: AssetImages) -> None:
        nonlocal extra_chain_image_count
        if not chain_folder_name:
            return
        dest = _extra_chain_images_dir(chain_folder_name)
        copied_set = extra_chain_images_copied.setdefault(str(dest), set())
        extra_chain_image_count += copy_images(imgs, logos_dir, dest, copied_set)

    all_assets: List[object] = []
    all_assets.extend(natives)
    all_assets.extend(factories)
    all_assets.extend(ibcs)

    for asset in sorted(all_assets, key=_asset_sort_key):
        declared = _declared_logo_slug(asset)
        preserve_declared = _should_preserve_declared_logo_uris(asset)

        if preserve_declared:
            images = AssetImages(png=None, svg=None)
        else:
            images = locate_image_filenames(
                slugs=[declared] if declared else _asset_logo_slugs(asset),
                logos_dir=logos_dir,
            )

        # IBC assets need special handling for extra chain image folders + ERC20 mirror assetlist.
        if isinstance(asset, IBCAsset):
            logo_chain = _ibc_logo_chain_name(asset)

            if logo_chain and logo_chain != chain_name and not preserve_declared:
                _copy_extra_chain_images(logo_chain, images)
            elif not preserve_declared:
                zig_image_count += copy_images(images, logos_dir, zigchain_out / "images", zig_images_copied)

            chain_assets.append(ibc_asset_to_chain_registry(asset, images))

            erc20_entry = erc20_from_ibc(asset, images)
            if erc20_entry:
                eth_image_count += copy_images(images, logos_dir, eth_out / "images", eth_images_copied)
                erc20_assets.append(erc20_entry)
        else:
            if not preserve_declared:
                zig_image_count += copy_images(images, logos_dir, zigchain_out / "images", zig_images_copied)
            chain_assets.append(non_ibc_asset_to_chain_registry(asset, images))

    zigchain_assetlist = {
        "$schema": "../assetlist.schema.json" if not use_testnet_paths else "../../assetlist.schema.json",
        "chain_name": chain_name,
        "assets": chain_assets,
    }
    write_json(zigchain_out / "assetlist.json", zigchain_assetlist)
    print(f"✅ Wrote {zigchain_out.relative_to(out_root)}/assetlist.json with {len(chain_assets)} assets")
    print(f"✅ Copied {zig_image_count} {chain_name} image files")
    if extra_chain_image_count:
        print(f"✅ Copied {extra_chain_image_count} extra chain image files (IBC chain folders)")

    if erc20_assets:
        eth_assetlist = {
            "$schema": "../../assetlist.schema.json" if not use_testnet_paths else "../../../assetlist.schema.json",
            "chain_name": eth_chain_name,
            "assets": erc20_assets,
        }
        write_json(eth_out / "assetlist.json", eth_assetlist)
        print(
            f"✅ Wrote {eth_out.relative_to(out_root)}/assetlist.json with {len(erc20_assets)} assets"
        )
        print(f"✅ Copied {eth_image_count} {eth_chain_name} image files")
    else:
        print(f"ℹ️ No ERC20-origin assets detected for {network}; skipped ethereum assetlist")
        # Avoid leaving stale outputs behind from previous runs.
        if eth_out.exists():
            shutil.rmtree(eth_out)


def generate(
    root: Path,
    out_root: Path,
    *,
    skip_sync: bool = False,
    verified_only: bool = True,
    upstream_repo: str = "https://github.com/cosmos/chain-registry",
    fork_repo: str = "https://github.com/ZIGChain/chain-registry",
    git_no_prompt: bool = False,
    git_env_file: Optional[Path] = None,
) -> None:
    logos_dir = root / "logos"

    print("Generating chain-registry artifacts...")
    mode = "verified-only" if verified_only else "including unverified assets (local debug)"
    print(f"Mode: {mode}")
    natives, factories, ibcs = load_assets(root)
    print(f"Loaded total assets -> native: {len(natives)}, factory: {len(factories)}, ibc: {len(ibcs)}")

    # Partition by network
    mainnet_natives = [a for a in natives if a.network == "mainnet"]
    testnet_natives = [a for a in natives if a.network == "testnet"]
    mainnet_factories = [a for a in factories if a.network == "mainnet"]
    testnet_factories = [a for a in factories if a.network == "testnet"]
    mainnet_ibcs = [a for a in ibcs if a.network == "mainnet"]
    testnet_ibcs = [a for a in ibcs if a.network == "testnet"]

    # Mainnet
    generate_for_network(
        network="mainnet",
        natives=mainnet_natives,
        factories=mainnet_factories,
        ibcs=mainnet_ibcs,
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        use_testnet_paths=False,
        verified_only=verified_only,
    )

    # Testnet
    if testnet_natives or testnet_factories or testnet_ibcs:
        generate_for_network(
            network="testnet",
            natives=testnet_natives,
            factories=testnet_factories,
            ibcs=testnet_ibcs,
            logos_dir=logos_dir,
            out_root=out_root,
            chain_name="zigchaintestnet",
            eth_chain_name="ethereumtestnet",
            use_testnet_paths=True,
            verified_only=verified_only,
        )
    else:
        print("ℹ️ No testnet assets detected; skipping testnet outputs")

    print("\n✅ All chain-registry artifacts generated successfully!")

    if skip_sync:
        print("ℹ️ Sync to cosmos/chain-registry skipped (--skip-sync).")
        return

    try:
        git_env = _prepare_git_env(root=root, git_env_file=git_env_file)
        effective_fork_repo = fork_repo
        # If SSH is configured, prefer SSH URL for GitHub pushes to avoid HTTPS askpass (401).
        if git_env.get("GIT_SSH_COMMAND"):
            ssh_url = _github_https_to_ssh(fork_repo)
            if ssh_url:
                effective_fork_repo = ssh_url
                print(f"ℹ️ Using SSH fork remote (via GIT_SSH_COMMAND): {effective_fork_repo}")
        sync_to_chain_registry(
            out_root=out_root,
            upstream_repo=upstream_repo,
            fork_repo=effective_fork_repo,
            git_no_prompt=git_no_prompt,
            git_env_overrides=git_env,
        )
    except Exception as e:
        # Keep generation success even if sync fails; provide actionable error.
        print("\n❌ Sync to chain-registry failed.")
        print(str(e))
        if isinstance(e, subprocess.CalledProcessError) and getattr(e, "stdout", None):
            print("\nGit output:")
            print(e.stdout)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate chain-registry files for ZIGChain")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root containing assets/ and logos/ (default: repo root)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "generated" / "chain-registry",
        help="Output root directory (default: generated/chain-registry)",
    )
    parser.add_argument(
        "--include-unverified",
        action="store_true",
        help=(
            "Include assets with is_verified not set to true. For local debugging "
            "ONLY — the upstream chain-registry should never be synced with "
            "unverified assets. Pair with --skip-sync."
        ),
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Only generate local outputs; do not clone/push to chain-registry fork.",
    )
    parser.add_argument(
        "--upstream-repo",
        type=str,
        default="https://github.com/cosmos/chain-registry",
        help="Upstream chain-registry repo URL to clone (default: https://github.com/cosmos/chain-registry)",
    )
    parser.add_argument(
        "--fork-repo",
        type=str,
        default="https://github.com/ZIGChain/chain-registry",
        help="Fork repo URL to push to (default: https://github.com/ZIGChain/chain-registry)",
    )
    parser.add_argument(
        "--git-no-prompt",
        action="store_true",
        help="Disable interactive git prompts (CI-friendly). If credentials are needed, git will fail fast.",
    )
    parser.add_argument(
        "--git-env-file",
        type=Path,
        default=None,
        help="Optional dotenv-style file to load git env vars from (e.g. .env). If omitted, root/.env is used if present.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    generate(
        args.root,
        args.out,
        verified_only=not args.include_unverified,
        skip_sync=args.skip_sync,
        upstream_repo=args.upstream_repo,
        fork_repo=args.fork_repo,
        git_no_prompt=args.git_no_prompt,
        git_env_file=args.git_env_file,
    )

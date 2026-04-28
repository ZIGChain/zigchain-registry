#!/usr/bin/env python3
"""
Dry-run audit: Check existing asset JSONs against proposed stricter validation rules.

Reports any assets that would break under the new constraints without modifying anything.
"""

import json
import re
import sys
from pathlib import Path

repo_root = Path(__file__).parent.parent
assets_dir = repo_root / "assets"

CHANNEL_PATTERN = re.compile(r"^(channel-\d+|08-wasm-\d+)$")

issues: list[str] = []
stats = {"factory": 0, "ibc": 0, "native": 0}


def audit_factory(data: dict, path: Path) -> None:
    """Check factory assets for website/twitter usage and field lengths."""
    stats["factory"] += 1
    if "website" in data:
        issues.append(f"FACTORY website field present: {path}")
    if "twitter" in data:
        issues.append(f"FACTORY twitter field present: {path}")


def audit_ibc(data: dict, path: Path) -> None:
    """Check IBC assets for channel patterns, trace counts, path prefixes."""
    stats["ibc"] += 1
    for ch in data.get("channels", []):
        zc = ch.get("zigchain_channel", "")
        cc = ch.get("counterparty_channel", "")
        if zc and not CHANNEL_PATTERN.match(zc):
            issues.append(f"IBC zigchain_channel '{zc}' doesn't match pattern: {path}")
        if cc and not CHANNEL_PATTERN.match(cc):
            issues.append(f"IBC counterparty_channel '{cc}' doesn't match pattern: {path}")

    traces = data.get("traces", [])
    if len(traces) > 10:
        issues.append(f"IBC traces count {len(traces)} > 10: {path}")
    channels = data.get("channels", [])
    if len(channels) > 5:
        issues.append(f"IBC channels count {len(channels)} > 5: {path}")

    for t in traces:
        p = t.get("path", "")
        if p and not p.startswith("transfer/"):
            issues.append(f"IBC trace path doesn't start with 'transfer/': '{p}' in {path}")
        elif p and (".." in p or any(ord(c) < 0x20 for c in p) or not re.match(r"^transfer/[a-zA-Z0-9/._-]+$", p)):
            issues.append(f"IBC trace path contains unsafe characters or sequences: '{p}' in {path}")


def audit_native(data: dict, path: Path) -> None:
    """Check native assets for duplicate traces, field lengths."""
    stats["native"] += 1
    traces = data.get("traces", [])
    if len(traces) > 10:
        issues.append(f"NATIVE traces count {len(traces)} > 10: {path}")
    # Check duplicates (full object equality)
    seen = []
    for t in traces:
        t_str = json.dumps(t, sort_keys=True)
        if t_str in seen:
            issues.append(f"NATIVE duplicate trace entry: {path}")
        seen.append(t_str)


def audit_common(data: dict, path: Path) -> None:
    """Check fields common to all asset types for proposed limits."""
    # ImageSyncPointer / images field lengths
    for img in data.get("images", []):
        if isinstance(img, dict):
            cn = img.get("chain_name", "")
            bd = img.get("base_denom", "")
            if len(cn) > 64:
                issues.append(f"ImageSyncPointer chain_name > 64 chars: {path}")
            if len(bd) > 256:
                issues.append(f"ImageSyncPointer base_denom > 256 chars: {path}")

    # DenomUnit aliases count
    for du in data.get("denom_units", []):
        if isinstance(du, dict):
            aliases = du.get("aliases", [])
            if aliases and len(aliases) > 10:
                issues.append(f"DenomUnit aliases count {len(aliases)} > 10: {path}")
            exp = du.get("exponent")
            if isinstance(exp, int) and exp > 18:
                issues.append(f"DenomUnit exponent {exp} > 18: {path}")

    # extended_description length
    ed = data.get("extended_description", "")
    if ed and len(ed) > 8192:
        issues.append(f"extended_description > 8192 chars: {path}")

    # Socials URL check (would HttpUrl reject any?)
    socials = data.get("socials", {})
    if isinstance(socials, dict):
        for key, url in socials.items():
            if url and isinstance(url, str):
                if not url.startswith(("http://", "https://")):
                    issues.append(f"Socials.{key} not http/https: '{url}' in {path}")


def main() -> None:
    audit_map = {
        "native": audit_native,
        "factory": audit_factory,
        "ibc": audit_ibc,
    }

    for asset_dir in ["native", "factory", "ibc"]:
        dir_path = assets_dir / asset_dir
        if not dir_path.exists():
            continue
        for file_path in dir_path.rglob("*.json"):
            try:
                data = json.load(open(file_path))
            except Exception as e:
                issues.append(f"JSON parse error: {file_path}: {e}")
                continue

            asset_type = data.get("type", "")
            audit_fn = audit_map.get(asset_type)
            if audit_fn:
                audit_fn(data, file_path)
            audit_common(data, file_path)

    print(f"Audited: {stats['native']} native, {stats['factory']} factory, {stats['ibc']} IBC")
    if issues:
        print(f"\n{len(issues)} issue(s) found:\n")
        for issue in issues:
            print(f"  ⚠️  {issue}")
        sys.exit(1)
    else:
        print("\n✅ No issues found — all assets are compatible with proposed strict rules.")
        sys.exit(0)


if __name__ == "__main__":
    main()

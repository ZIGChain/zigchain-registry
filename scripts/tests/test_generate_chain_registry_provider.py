from typing import Any, Dict

from models import IBCAsset
from scripts.generate_chain_registry import build_traces


HASH = "6490A7EAB61059BFC1CDDEB05917DD70BDF3A611654162A1A47DB930D40D8AF4"


def _base_ibc_asset_data() -> Dict[str, Any]:
    # Minimal valid IBCAsset data to exercise build_traces() behavior.
    return {
        "network": "mainnet",
        "asset_id": f"ibc/{HASH}",
        "type": "ibc",
        "symbol": "USDC",
        "name": "Noble USDC",
        "decimals": 6,
        "display_denom": "usdc",
        "base_denom": f"ibc/{HASH}",
        "hash": HASH,
        "origin_chain": "noble",
        "origin_denom": "uusdc",
        "traces": [
            # Required IBC hop trace entry for validation; this is the "zigchain" trace.
            {
                "type": "ibc",
                "chain_name": "zigchain",
                "base_denom": f"ibc/{HASH}",
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


def test_build_traces_provider_is_root_level_for_eureka() -> None:
    data = _base_ibc_asset_data()
    data["traces"].append(
        {
            "type": "ibc-bridge",
            "chain_name": "ethereum",
            "base_denom": "0x0000000000000000000000000000000000000000",
            "path": "transfer/08-wasm-1369/0x0000000000000000000000000000000000000000",
            "provider": "Eureka",
        }
    )
    asset = IBCAsset(**data)
    zig_trace = next(t for t in asset.traces if getattr(t, "chain_name", None) == "zigchain")

    out = build_traces(asset, zig_trace)
    assert len(out) == 1
    assert out[0]["provider"] == "Eureka"
    assert "provider" not in out[0]["chain"]


def test_build_traces_provider_ibc_is_omitted() -> None:
    data = _base_ibc_asset_data()
    data["traces"].append(
        {
            "type": "ibc-bridge",
            "chain_name": "ethereum",
            "base_denom": "0x0000000000000000000000000000000000000000",
            "path": "transfer/08-wasm-1369/0x0000000000000000000000000000000000000000",
            "provider": "IBC",
        }
    )
    asset = IBCAsset(**data)
    zig_trace = next(t for t in asset.traces if getattr(t, "chain_name", None) == "zigchain")

    out = build_traces(asset, zig_trace)
    assert len(out) == 1
    assert "provider" not in out[0]
    assert "provider" not in out[0]["chain"]

